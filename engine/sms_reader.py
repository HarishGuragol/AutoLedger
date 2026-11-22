import os
import sqlite3
import logging
from typing import Dict, Any, List
from datetime import datetime
from engine.parser import parse_transaction_text
from engine.db import insert_transaction, get_settings, update_setting, log_ingest_event

logger = logging.getLogger("SMSReader")
CHAT_DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")

def check_sms_permission() -> bool:
    """Check if macOS has granted Full Disk Access to read ~/Library/Messages/chat.db"""
    if not os.path.exists(CHAT_DB_PATH):
        return False
    try:
        # Open in URI read-only mode
        uri = f"file:{CHAT_DB_PATH}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        cur = conn.cursor()
        cur.execute("SELECT ROWID FROM message LIMIT 1")
        cur.fetchone()
        conn.close()
        return True
    except Exception:
        return False

def scan_sms_messages() -> Dict[str, Any]:
    """
    Scans macOS Messages database (chat.db) for bank and UPI transaction alerts.
    Only processes messages that arrived since the last scan.
    """
    if not check_sms_permission():
        log_ingest_event("SMS", "ERROR", "macOS Full Disk Access not granted for chat.db")
        return {
            "success": False,
            "fda_granted": False,
            "message": "Full Disk Access required to read Messages app. Go to System Settings > Privacy & Security > Full Disk Access.",
            "processed": 0
        }

    settings = get_settings()
    last_processed_rowid = int(settings.get("sms_last_rowid", "0"))

    try:
        uri = f"file:{CHAT_DB_PATH}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Query messages with text containing transaction indicators
        query = """
        SELECT m.ROWID as rowid, m.text, m.date, h.id as sender
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        WHERE m.ROWID > ? 
          AND m.text IS NOT NULL
          AND (
              m.text LIKE '%debited%' OR 
              m.text LIKE '%credited%' OR 
              m.text LIKE '%spent%' OR 
              m.text LIKE '%paid%' OR 
              m.text LIKE '%withdrawn%' OR 
              m.text LIKE '%UPI%' OR 
              m.text LIKE '%Rs.%' OR 
              m.text LIKE '%INR%'
          )
        ORDER BY m.ROWID ASC
        LIMIT 200
        """
        cur.execute(query, (last_processed_rowid,))
        rows = cur.fetchall()

        processed_count = 0
        max_rowid = last_processed_rowid

        for row in rows:
            max_rowid = max(max_rowid, row["rowid"])
            text = row["text"]
            parsed = parse_transaction_text(text, source="SMS")
            if parsed:
                res = insert_transaction(
                    amount=parsed["amount"],
                    tx_type=parsed["type"],
                    date=parsed["date"],
                    category=parsed["category"],
                    merchant=parsed["merchant"],
                    mode=parsed["mode"],
                    account_ref=parsed["account_ref"],
                    balance_after=parsed["balance_after"],
                    reference_id=parsed["reference_id"],
                    raw_text=parsed["raw_text"],
                    source="SMS"
                )
                if res is not None:
                    processed_count += 1

        conn.close()

        if max_rowid > last_processed_rowid:
            update_setting("sms_last_rowid", str(max_rowid))
            update_setting("sms_last_scan", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        log_ingest_event("SMS", "SUCCESS", f"Scanned messages. {processed_count} new transactions recorded.")
        return {
            "success": True,
            "fda_granted": True,
            "processed": processed_count,
            "last_rowid": max_rowid
        }

    except Exception as e:
        logger.error(f"Error scanning SMS: {e}")
        log_ingest_event("SMS", "ERROR", str(e))
        return {
            "success": False,
            "fda_granted": True,
            "error": str(e),
            "processed": 0
        }
