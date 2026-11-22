import sqlite3
import os
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ledger.db")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Transactions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tx_hash TEXT UNIQUE NOT NULL,
        date TEXT NOT NULL,
        amount REAL NOT NULL,
        type TEXT NOT NULL,
        mode TEXT DEFAULT 'UPI',
        category TEXT DEFAULT 'General',
        merchant TEXT,
        account_ref TEXT,
        balance_after REAL,
        reference_id TEXT,
        raw_text TEXT,
        source TEXT DEFAULT 'MANUAL',
        bank TEXT DEFAULT 'Other',
        created_at TEXT NOT NULL
    );
    """)

    # Ensure bank column exists if table existed previously
    cursor.execute("PRAGMA table_info(transactions)")
    cols = [c[1] for c in cursor.fetchall()]
    if "bank" not in cols:
        cursor.execute("ALTER TABLE transactions ADD COLUMN bank TEXT DEFAULT 'Other'")

    # Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)

    # Ingestion logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ingest_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        source TEXT NOT NULL,
        status TEXT NOT NULL,
        details TEXT
    );
    """)

    # Default settings
    defaults = {
        "monthly_budget": "35000",
        "currency_symbol": "₹",
        "email_host": "imap.gmail.com",
        "email_port": "993",
        "email_user": "",
        "email_pass": "",
        "email_sync_enabled": "false",
        "sms_sync_enabled": "true"
    }
    for k, v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()

def generate_tx_hash(amount: float, tx_type: str, date: str, merchant: str, ref: Optional[str] = None) -> str:
    clean_date = date[:10] if date else datetime.now().strftime("%Y-%m-%d")
    raw = f"{amount:.2f}_{tx_type.upper()}_{clean_date}_{merchant.lower().strip()}_{ref or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()

def insert_transaction(
    amount: float,
    tx_type: str,
    date: str,
    category: str,
    merchant: str,
    mode: str = "UPI",
    account_ref: Optional[str] = None,
    balance_after: Optional[float] = None,
    reference_id: Optional[str] = None,
    raw_text: Optional[str] = None,
    source: str = "MANUAL",
    bank: str = "Other"
) -> Optional[int]:
    tx_hash = generate_tx_hash(amount, tx_type, date, merchant, reference_id)
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO transactions (
            tx_hash, date, amount, type, mode, category, merchant,
            account_ref, balance_after, reference_id, raw_text, source, bank, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_hash,
            date or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            amount,
            tx_type.upper(),
            mode,
            category,
            merchant,
            account_ref,
            balance_after,
            reference_id,
            raw_text,
            source,
            bank,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_transactions(
    limit: int = 150,
    offset: int = 0,
    category: Optional[str] = None,
    tx_type: Optional[str] = None,
    search: Optional[str] = None,
    month: Optional[str] = None,
    bank: Optional[str] = None
) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    if month and month != "All":
        query += " AND date LIKE ?"
        params.append(f"{month}%")

    if bank and bank != "All":
        query += " AND bank = ?"
        params.append(bank)

    if category and category != "All":
        query += " AND category = ?"
        params.append(category)

    if tx_type and tx_type != "All":
        query += " AND type = ?"
        params.append(tx_type.upper())

    if search:
        query += " AND (merchant LIKE ? OR raw_text LIKE ? OR reference_id LIKE ? OR bank LIKE ?)"
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard, wildcard])

    query += " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def delete_transaction(tx_id: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def update_transaction_category(tx_id: int, category: str) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE transactions SET category = ? WHERE id = ?", (category, tx_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def get_monthly_analysis(target_month: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()

    # If no month provided, use current YYYY-MM
    if not target_month or target_month == "current":
        target_month = datetime.now().strftime("%Y-%m")

    month_pattern = f"{target_month}%"

    # Distinct months in DB
    cursor.execute("SELECT DISTINCT substr(date, 1, 7) as m FROM transactions ORDER BY m DESC")
    available_months = [r[0] for r in cursor.fetchall() if r[0]]
    if target_month not in available_months:
        available_months.insert(0, target_month)

    # 1. Salary Inflow (Standard Chartered Bank or Salary Category)
    cursor.execute("""
    SELECT COALESCE(SUM(amount), 0) FROM transactions 
    WHERE (bank = 'Standard Chartered' OR category = 'Salary & Income') 
      AND type = 'INCOME' 
      AND date LIKE ?
    """, (month_pattern,))
    salary_inflow = cursor.fetchone()[0]

    # Total Income (all sources)
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'INCOME' AND date LIKE ?", (month_pattern,))
    total_income = cursor.fetchone()[0]

    # 2. CRED Loaded / Put into CRED
    cursor.execute("""
    SELECT COALESCE(SUM(amount), 0) FROM transactions 
    WHERE (bank = 'CRED' OR category = 'CRED & Wallet' OR merchant LIKE '%CRED%') 
      AND type = 'EXPENSE' 
      AND date LIKE ?
    """, (month_pattern,))
    cred_loaded = cursor.fetchone()[0]

    # 3. Self-Transfers (Moving between SC, HDFC, ICICI, IDFC)
    cursor.execute("""
    SELECT COALESCE(SUM(amount), 0) FROM transactions 
    WHERE category = 'Self Transfer' 
      AND date LIKE ?
    """, (month_pattern,))
    self_transfers = cursor.fetchone()[0]

    # 4. Real Expenses (Excludes Self-Transfers and CRED Loads to prevent double counting!)
    cursor.execute("""
    SELECT COALESCE(SUM(amount), 0) FROM transactions 
    WHERE type = 'EXPENSE' 
      AND category NOT IN ('Self Transfer', 'CRED & Wallet')
      AND date LIKE ?
    """, (month_pattern,))
    real_expenses = cursor.fetchone()[0]

    # 5. Total Gross Debits
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'EXPENSE' AND date LIKE ?", (month_pattern,))
    gross_debits = cursor.fetchone()[0]

    # 6. UPI Outflow this month
    cursor.execute("""
    SELECT COALESCE(SUM(amount), 0) FROM transactions 
    WHERE type = 'EXPENSE' AND mode = 'UPI' AND date LIKE ?
    """, (month_pattern,))
    monthly_upi = cursor.fetchone()[0]

    # 7. Breakdown by Bank for this month
    banks = ["Standard Chartered", "HDFC", "ICICI", "IDFC FIRST", "CRED", "Other"]
    bank_stats = []
    for b in banks:
        # Expenses
        cursor.execute("SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM transactions WHERE bank = ? AND type = 'EXPENSE' AND date LIKE ?", (b, month_pattern))
        exp_row = cursor.fetchone()
        b_exp = exp_row[0]
        b_count = exp_row[1]

        # Inflow
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE bank = ? AND type = 'INCOME' AND date LIKE ?", (b, month_pattern))
        b_inc = cursor.fetchone()[0]

        bank_stats.append({
            "bank": b,
            "spent": b_exp,
            "inflow": b_inc,
            "tx_count": b_count
        })

    # 8. Category Breakdown for Real Expenses this month
    cursor.execute("""
    SELECT category, COALESCE(SUM(amount), 0) as total, COUNT(*) as count 
    FROM transactions 
    WHERE type = 'EXPENSE' 
      AND category NOT IN ('Self Transfer')
      AND date LIKE ?
    GROUP BY category 
    ORDER BY total DESC
    """, (month_pattern,))
    categories = [dict(r) for r in cursor.fetchall()]

    # 9. Budget
    cursor.execute("SELECT value FROM settings WHERE key = 'monthly_budget'")
    budget_row = cursor.fetchone()
    monthly_budget = float(budget_row[0]) if budget_row and budget_row[0] else 35000.0

    conn.close()

    net_surplus = total_income - real_expenses

    return {
        "month": target_month,
        "available_months": available_months,
        "salary_inflow": salary_inflow,
        "total_income": total_income,
        "cred_loaded": cred_loaded,
        "self_transfers": self_transfers,
        "real_expenses": real_expenses,
        "gross_debits": gross_debits,
        "net_surplus": net_surplus,
        "savings_rate": round((net_surplus / total_income) * 100, 1) if total_income > 0 else 0,
        "monthly_upi": monthly_upi,
        "monthly_budget": monthly_budget,
        "budget_remaining": max(0.0, monthly_budget - real_expenses),
        "budget_percent_used": round((real_expenses / monthly_budget) * 100, 1) if monthly_budget > 0 else 0,
        "bank_stats": bank_stats,
        "categories": categories
    }

def get_stats() -> Dict[str, Any]:
    return get_monthly_analysis()

def get_settings() -> Dict[str, str]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    settings = {r["key"]: r["value"] for r in cursor.fetchall()}
    conn.close()
    return settings

def update_setting(key: str, value: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def log_ingest_event(source: str, status: str, details: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO ingest_logs (timestamp, source, status, details) VALUES (?, ?, ?, ?)", (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source,
        status,
        details
    ))
    conn.commit()
    conn.close()

def get_ingest_logs(limit: int = 15) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ingest_logs ORDER BY id DESC LIMIT ?", (limit,))
    logs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return logs
