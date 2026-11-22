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
        created_at TEXT NOT NULL
    );
    """)

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

    # Default settings if not present
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
    """Generate unique hash to prevent duplicate entries from multiple SMS or email alerts"""
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
    source: str = "MANUAL"
) -> Optional[int]:
    tx_hash = generate_tx_hash(amount, tx_type, date, merchant, reference_id)
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO transactions (
            tx_hash, date, amount, type, mode, category, merchant,
            account_ref, balance_after, reference_id, raw_text, source, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        tx_id = cursor.lastrowid
        return tx_id
    except sqlite3.IntegrityError:
        # Duplicate transaction, ignored
        return None
    finally:
        conn.close()

def get_transactions(limit: int = 100, offset: int = 0, category: Optional[str] = None, tx_type: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    if category and category != "All":
        query += " AND category = ?"
        params.append(category)

    if tx_type and tx_type != "All":
        query += " AND type = ?"
        params.append(tx_type.upper())

    if search:
        query += " AND (merchant LIKE ? OR raw_text LIKE ? OR reference_id LIKE ?)"
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard])

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

def get_stats() -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()

    # Current month string
    current_month = datetime.now().strftime("%Y-%m")
    today = datetime.now().strftime("%Y-%m-%d")

    # Monthly Expenses
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'EXPENSE' AND date LIKE ?", (f"{current_month}%",))
    monthly_expense = cursor.fetchone()[0]

    # Monthly Inflow / Income
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'INCOME' AND date LIKE ?", (f"{current_month}%",))
    monthly_income = cursor.fetchone()[0]

    # Today's Expense
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'EXPENSE' AND date LIKE ?", (f"{today}%",))
    today_expense = cursor.fetchone()[0]

    # Monthly UPI Spend
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'EXPENSE' AND mode = 'UPI' AND date LIKE ?", (f"{current_month}%",))
    monthly_upi = cursor.fetchone()[0]

    # Category Breakdown for this month
    cursor.execute("""
    SELECT category, COALESCE(SUM(amount), 0) as total, COUNT(*) as count 
    FROM transactions 
    WHERE type = 'EXPENSE' AND date LIKE ?
    GROUP BY category 
    ORDER BY total DESC
    """, (f"{current_month}%",))
    categories = [dict(r) for r in cursor.fetchall()]

    # Last 14 days daily expenses
    cursor.execute("""
    SELECT substr(date, 1, 10) as day, COALESCE(SUM(amount), 0) as total
    FROM transactions
    WHERE type = 'EXPENSE'
    GROUP BY day
    ORDER BY day DESC
    LIMIT 14
    """)
    daily_trend = [dict(r) for r in cursor.fetchall()]
    daily_trend.reverse()

    # Total transaction count
    cursor.execute("SELECT COUNT(*) FROM transactions")
    total_tx_count = cursor.fetchone()[0]

    # Latest balance from transactions if available
    cursor.execute("SELECT balance_after FROM transactions WHERE balance_after IS NOT NULL ORDER BY date DESC, id DESC LIMIT 1")
    latest_bal_row = cursor.fetchone()
    latest_balance = latest_bal_row[0] if latest_bal_row else None

    # Budget
    cursor.execute("SELECT value FROM settings WHERE key = 'monthly_budget'")
    budget_row = cursor.fetchone()
    monthly_budget = float(budget_row[0]) if budget_row and budget_row[0] else 35000.0

    conn.close()

    return {
        "monthly_expense": monthly_expense,
        "monthly_income": monthly_income,
        "net_savings": monthly_income - monthly_expense,
        "today_expense": today_expense,
        "monthly_upi": monthly_upi,
        "monthly_budget": monthly_budget,
        "budget_remaining": max(0.0, monthly_budget - monthly_expense),
        "budget_percent_used": round((monthly_expense / monthly_budget) * 100, 1) if monthly_budget > 0 else 0,
        "latest_balance": latest_balance,
        "total_tx_count": total_tx_count,
        "categories": categories,
        "daily_trend": daily_trend
    }

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
