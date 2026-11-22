import sqlite3
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional

CHAT_DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")

def parse_real_sms(text: str, sender: str, dt_str: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    clean = text.strip()
    lower = clean.lower()

    # Skip noise: OTP, promos, failures
    if any(k in lower for k in ["otp is", "do not share", "verification code", "declined", "has failed", "insufficient funds", "apply now", "pre-approved", "congratulations", "beware of scams", "lifetime free", "we have activated standing instruction"]):
        return None

    # Identify Institution
    bank = "Other"
    sender_up = sender.upper()
    if "SCB" in sender_up or "STAN" in sender_up:
        bank = "Standard Chartered"
    elif "HDFC" in sender_up:
        bank = "HDFC"
    elif "ICICI" in sender_up:
        bank = "ICICI"
    elif "IDFC" in sender_up:
        bank = "IDFC FIRST"
    elif "CREDWL" in sender_up or "CREDIN" in sender_up or "CRED" in sender_up:
        bank = "CRED"

    # --- 1. FIXED DEPOSITS & INVESTMENTS ---
    if "fd a/c has been created" in lower or "term deposit" in lower or "fixed deposit" in lower:
        amt_m = re.search(r'(?:inr|rs\.?)\s*([\d,]+\.?\d*)', clean, re.IGNORECASE)
        if amt_m:
            amt = float(amt_m.group(1).replace(",", ""))
            return {
                "amount": amt,
                "type": "INVESTMENT",
                "mode": "FD",
                "category": "Investments & FD",
                "merchant": f"{bank} Fixed Deposit",
                "bank": bank,
                "date": dt_str,
                "raw_text": clean
            }

    # --- 2. SELF-TRANSFERS (Between Harish's Own Accounts) ---
    if "harish" in lower or "harish kumar" in lower or "own a/c" in lower:
        amt_m = re.search(r'(?:debited by|credited for|is debited for|credited with|is credited for|rs\.?|inr)\s*([\d,]+\.?\d*)', clean, re.IGNORECASE)
        if amt_m:
            try:
                amt = float(amt_m.group(1).replace(",", ""))
                is_credit = "credited" in lower and not "debited" in lower[:lower.find("credited")]
                return {
                    "amount": amt,
                    "type": "TRANSFER",
                    "mode": "SELF_TRANSFER",
                    "category": "Self Transfer",
                    "merchant": "Self Account Transfer",
                    "bank": bank,
                    "date": dt_str,
                    "raw_text": clean
                }
            except Exception:
                pass

    # --- 3. CRED WALLET SPECIAL PATTERNS ---
    # Top-up: "Rs.200.00 has been successfully credited to your CRED wallet"
    cred_load_m = re.search(r'(?:rs\.?|inr)\s*([\d,]+\.?\d*)\s+has been successfully credited to your cred wallet', clean, re.IGNORECASE)
    if cred_load_m:
        amt = float(cred_load_m.group(1).replace(",", ""))
        return {
            "amount": amt,
            "type": "EXPENSE",
            "mode": "WALLET_LOAD",
            "category": "CRED & Wallet",
            "merchant": "CRED Wallet Top-Up",
            "bank": "CRED",
            "date": dt_str,
            "raw_text": clean
        }

    # CRED Wallet Spend: "You have successfully paid Rs.80.0 and your updated wallet balance is..."
    cred_spend_m = re.search(r'successfully paid (?:rs\.?|inr)?\s*([\d,]+\.?\d*)', clean, re.IGNORECASE)
    if cred_spend_m and "cred wallet" in lower:
        amt = float(cred_spend_m.group(1).replace(",", ""))
        return {
            "amount": amt,
            "type": "EXPENSE",
            "mode": "CRED_PAY",
            "category": "Food & Dining" if amt < 400 else "General",
            "merchant": "CRED Wallet Merchant",
            "bank": "CRED",
            "date": dt_str,
            "raw_text": clean
        }

    # --- 4. CARD SPENDS (HDFC / ICICI / SC) AT DREAMPLUG (CRED) ---
    if "dreamplug" in lower:
        amt_m = re.search(r'(?:spent|txn of|for)\s*(?:rs\.?|inr)?\s*([\d,]+\.?\d*)', clean, re.IGNORECASE)
        if amt_m:
            amt = float(amt_m.group(1).replace(",", ""))
            return {
                "amount": amt,
                "type": "EXPENSE",
                "mode": "CARD",
                "category": "CRED & Wallet",
                "merchant": "CRED (Dreamplug)",
                "bank": bank,
                "date": dt_str,
                "raw_text": clean
            }

    # --- 5. STANDARD CHARTERED PATTERNS ---
    if bank == "Standard Chartered":
        sc_cr = re.search(r'is credited for (?:rs\.?|inr)?\s*([\d,]+\.?\d*)', clean, re.IGNORECASE)
        if sc_cr:
            amt = float(sc_cr.group(1).replace(",", ""))
            is_salary = amt >= 30000 or "salary" in lower or "payroll" in lower
            return {
                "amount": amt,
                "type": "INCOME",
                "mode": "NETBANKING" if is_salary else "UPI",
                "category": "Salary & Income" if is_salary else "Transfers",
                "merchant": "Employer / Salary" if is_salary else "Incoming Transfer",
                "bank": "Standard Chartered",
                "date": dt_str,
                "raw_text": clean
            }
        sc_db = re.search(r'is debited for (?:rs\.?|inr)?\s*([\d,]+\.?\d*)', clean, re.IGNORECASE)
        if sc_db:
            amt = float(sc_db.group(1).replace(",", ""))
            return {
                "amount": amt,
                "type": "EXPENSE",
                "mode": "UPI",
                "category": "Transfers" if amt > 5000 else "General",
                "merchant": "UPI Transfer",
                "bank": "Standard Chartered",
                "date": dt_str,
                "raw_text": clean
            }

    # --- 6. HDFC BANK PATTERNS ---
    if bank == "HDFC":
        hdfc_card = re.search(r'spent (?:rs\.?|inr)?\s*([\d,]+\.?\d*)\s+on hdfc bank card .*? at (.*?)(?: on|\.|$)', clean, re.IGNORECASE)
        if hdfc_card:
            amt = float(hdfc_card.group(1).replace(",", ""))
            merch = hdfc_card.group(2).strip().title()
            return {
                "amount": amt,
                "type": "EXPENSE",
                "mode": "CARD",
                "category": "Shopping" if any(x in merch.lower() for x in ["amazon", "zara", "flipkart"]) else "General",
                "merchant": merch,
                "bank": "HDFC",
                "date": dt_str,
                "raw_text": clean
            }
        hdfc_db = re.search(r'(?:rs\.?|inr)\s*([\d,]+\.?\d*)\s+debited', clean, re.IGNORECASE)
        if hdfc_db:
            amt = float(hdfc_db.group(1).replace(",", ""))
            return {
                "amount": amt,
                "type": "EXPENSE",
                "mode": "UPI",
                "category": "General",
                "merchant": "HDFC Payment",
                "bank": "HDFC",
                "date": dt_str,
                "raw_text": clean
            }

    # --- 7. ICICI BANK PATTERNS ---
    if bank == "ICICI":
        icici_card = re.search(r'(?:inr|rs\.?)\s*([\d,]+\.?\d*)\s+spent using icici bank card .*? on (?:.*? on )?(.*?)(?:\. avl|$)', clean, re.IGNORECASE)
        if icici_card:
            amt = float(icici_card.group(1).replace(",", ""))
            merch = icici_card.group(2).strip().title()
            cat = "Subscriptions & Tech" if "apple" in merch.lower() or "google" in merch.lower() else "General"
            return {
                "amount": amt,
                "type": "EXPENSE",
                "mode": "CARD",
                "category": cat,
                "merchant": merch,
                "bank": "ICICI",
                "date": dt_str,
                "raw_text": clean
            }
        icici_db = re.search(r'acct .*? debited (?:for|by)?\s*(?:rs\.?|inr)?\s*([\d,]+\.?\d*)', clean, re.IGNORECASE)
        if icici_db:
            amt = float(icici_db.group(1).replace(",", ""))
            return {
                "amount": amt,
                "type": "EXPENSE",
                "mode": "UPI",
                "category": "General",
                "merchant": "ICICI Payment",
                "bank": "ICICI",
                "date": dt_str,
                "raw_text": clean
            }

    # --- 8. IDFC FIRST BANK PATTERNS ---
    if bank == "IDFC FIRST":
        if "interest amt" in lower and "credited" in lower:
            int_m = re.search(r'interest amt\.? of (?:rs\.?|inr)?\s*([\d,]+\.?\d*)', clean, re.IGNORECASE)
            if int_m:
                amt = float(int_m.group(1).replace(",", ""))
                return {
                    "amount": amt,
                    "type": "INCOME",
                    "mode": "INTEREST",
                    "category": "Salary & Income",
                    "merchant": "IDFC Bank Interest",
                    "bank": "IDFC FIRST",
                    "date": dt_str,
                    "raw_text": clean
                }
        idfc_db = re.search(r'(?:debited by|spent|withdrawn)\s*(?:rs\.?|inr)?\s*([\d,]+\.?\d*)', clean, re.IGNORECASE)
        if idfc_db:
            amt = float(idfc_db.group(1).replace(",", ""))
            return {
                "amount": amt,
                "type": "EXPENSE",
                "mode": "UPI",
                "category": "General",
                "merchant": "IDFC Payment",
                "bank": "IDFC FIRST",
                "date": dt_str,
                "raw_text": clean
            }

    return None

def run_local_ingest(months_back: int = 3) -> Dict[str, Any]:
    if not os.path.exists(CHAT_DB_PATH):
        return {"success": False, "error": "chat.db not found"}

    from engine.db import insert_transaction, init_db, get_db
    init_db()

    # Clear and re-populate with clean parser rules
    conn_db = get_db()
    c_db = conn_db.cursor()
    c_db.execute("DELETE FROM transactions")
    conn_db.commit()
    conn_db.close()

    conn = sqlite3.connect(f"file:{CHAT_DB_PATH}?mode=ro", uri=True)
    c = conn.cursor()

    query = """
    SELECT 
        datetime(m.date/1000000000 + 978307200, 'unixepoch', 'localtime') as dt,
        h.id as sender,
        m.text
    FROM message m
    JOIN handle h ON m.handle_id = h.ROWID
    WHERE (
        h.id LIKE '%SCB%' OR 
        h.id LIKE '%HDFC%' OR 
        h.id LIKE '%ICICI%' OR 
        h.id LIKE '%IDFC%' OR 
        h.id LIKE '%CREDWL%' OR
        h.id LIKE '%CREDIN%'
    )
      AND m.text IS NOT NULL
      AND m.date > 0
      AND datetime(m.date/1000000000 + 978307200, 'unixepoch', 'localtime') >= datetime('now', '-95 days')
    ORDER BY m.date ASC
    """
    c.execute(query)
    rows = c.fetchall()
    conn.close()

    recorded = 0
    skipped_duplicates = 0
    by_bank = {}

    for dt, sender, text in rows:
        parsed = parse_real_sms(text, sender, dt)
        if parsed:
            b = parsed["bank"]
            by_bank[b] = by_bank.get(b, 0) + 1
            res = insert_transaction(
                amount=parsed["amount"],
                tx_type=parsed["type"],
                date=parsed["date"],
                category=parsed["category"],
                merchant=parsed["merchant"],
                mode=parsed["mode"],
                source="SMS_LOCAL",
                bank=parsed["bank"],
                raw_text=parsed["raw_text"]
            )
            if res is not None:
                recorded += 1
            else:
                skipped_duplicates += 1

    return {
        "success": True,
        "scanned_messages": len(rows),
        "recorded_transactions": recorded,
        "skipped_duplicates": skipped_duplicates,
        "breakdown": by_bank
    }

if __name__ == "__main__":
    res = run_local_ingest()
    print("Ingest Result:", res)
