import imaplib
import email
from email.header import decode_header
import re
import logging
from typing import Dict, Any, List
from datetime import datetime
from engine.parser import parse_transaction_text
from engine.db import insert_transaction, get_settings, update_setting, log_ingest_event

logger = logging.getLogger("EmailReader")

def clean_subject(header_val: str) -> str:
    if not header_val:
        return ""
    decoded = decode_header(header_val)
    parts = []
    for text, enc in decoded:
        if isinstance(text, bytes):
            try:
                parts.append(text.decode(enc or "utf-8", errors="ignore"))
            except Exception:
                parts.append(text.decode("latin-1", errors="ignore"))
        else:
            parts.append(str(text))
    return "".join(parts)

def extract_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition"))
            if ctype == "text/plain" and "attachment" not in cdisp:
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode("utf-8", errors="ignore") + "\n"
            elif ctype == "text/html" and "attachment" not in cdisp and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode("utf-8", errors="ignore")
                    # Quick strip HTML tags
                    clean_text = re.sub(r'<[^>]+>', ' ', html)
                    clean_text = re.sub(r'\s+', ' ', clean_text)
                    body += clean_text + "\n"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            text = payload.decode("utf-8", errors="ignore")
            if msg.get_content_type() == "text/html":
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text)
            body = text
    return body.strip()

def scan_email_inbox() -> Dict[str, Any]:
    """
    Connects to configured IMAP server (e.g. Gmail) and scans for bank / UPI transaction emails.
    """
    settings = get_settings()
    host = settings.get("email_host", "imap.gmail.com")
    port = int(settings.get("email_port", "993"))
    user = settings.get("email_user", "").strip()
    password = settings.get("email_pass", "").strip()

    if not user or not password:
        return {
            "success": False,
            "configured": False,
            "message": "Email IMAP not configured. Please enter your email and App Password in Settings.",
            "processed": 0
        }

    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(user, password)
        mail.select("INBOX")

        # Search for recent emails with bank/transaction keywords
        # We can search UNSEEN or search subject/body
        status, messages = mail.search(None, 'OR OR (SUBJECT "debited") (SUBJECT "credited") (SUBJECT "UPI")')
        if status != "OK" or not messages[0]:
            # Try searching recent unseen
            status, messages = mail.search(None, 'UNSEEN')

        if status != "OK" or not messages[0]:
            mail.logout()
            return {
                "success": True,
                "configured": True,
                "message": "No new transaction emails found.",
                "processed": 0
            }

        msg_ids = messages[0].split()
        # Take at most the last 25 emails to avoid freezing
        msg_ids = msg_ids[-25:]

        processed_count = 0

        for mid in msg_ids:
            res, data = mail.fetch(mid, "(RFC822)")
            if res != "OK":
                continue
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            subject = clean_subject(msg.get("Subject", ""))
            body = extract_body(msg)

            combined_text = f"{subject}\n{body[:1200]}"
            parsed = parse_transaction_text(combined_text, source="EMAIL")

            if parsed:
                tx_id = insert_transaction(
                    amount=parsed["amount"],
                    tx_type=parsed["type"],
                    date=parsed["date"],
                    category=parsed["category"],
                    merchant=parsed["merchant"],
                    mode=parsed["mode"],
                    account_ref=parsed["account_ref"],
                    balance_after=parsed["balance_after"],
                    reference_id=parsed["reference_id"],
                    raw_text=parsed["raw_text"][:500],
                    source="EMAIL"
                )
                if tx_id is not None:
                    processed_count += 1

        mail.logout()
        update_setting("email_last_scan", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        log_ingest_event("EMAIL", "SUCCESS", f"Email scan finished. {processed_count} new transactions recorded.")

        return {
            "success": True,
            "configured": True,
            "message": f"Email scan complete. Found {processed_count} new transactions.",
            "processed": processed_count
        }

    except Exception as e:
        logger.error(f"IMAP scan failed: {e}")
        log_ingest_event("EMAIL", "ERROR", str(e))
        return {
            "success": False,
            "configured": True,
            "error": str(e),
            "message": f"Connection error: {str(e)}",
            "processed": 0
        }
