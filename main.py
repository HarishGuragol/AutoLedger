import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from engine.db import (
    init_db, get_stats, get_transactions, insert_transaction,
    delete_transaction, update_transaction_category, get_settings,
    update_setting, get_ingest_logs, log_ingest_event
)
from engine.parser import parse_transaction_text, CATEGORIES
from engine.sms_reader import scan_sms_messages, check_sms_permission
from engine.email_reader import scan_email_inbox

# Background background ingestion worker
async def background_ingestion_loop():
    while True:
        try:
            settings = get_settings()
            # 1. Check SMS if FDA is granted
            if settings.get("sms_sync_enabled", "true") == "true" and check_sms_permission():
                scan_sms_messages()

            # 2. Check Email if configured and enabled
            if settings.get("email_sync_enabled", "false") == "true" and settings.get("email_user"):
                scan_email_inbox()
        except Exception as e:
            pass
        await asyncio.sleep(45)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    bg_task = asyncio.create_task(background_ingestion_loop())
    yield
    bg_task.cancel()

app = FastAPI(title="AutoLedger", description="Autonomous Banking & UPI Transaction Tracker", lifespan=lifespan)

# --- Pydantic Models ---
class ParseRequest(BaseModel):
    text: str
    auto_save: bool = True
    source: str = "MANUAL"

class ManualTransaction(BaseModel):
    amount: float
    type: str # EXPENSE or INCOME
    merchant: str
    category: str = "General"
    mode: str = "UPI"
    date: Optional[str] = None
    account_ref: Optional[str] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None

class WebhookPayload(BaseModel):
    text: str
    source: Optional[str] = "WEBHOOK"

class CategoryUpdate(BaseModel):
    category: str

class SettingsUpdate(BaseModel):
    monthly_budget: Optional[str] = None
    currency_symbol: Optional[str] = None
    email_host: Optional[str] = None
    email_port: Optional[str] = None
    email_user: Optional[str] = None
    email_pass: Optional[str] = None
    email_sync_enabled: Optional[str] = None
    sms_sync_enabled: Optional[str] = None

# --- API Routes ---

@app.get("/api/stats")
def api_get_stats():
    return get_stats()

@app.get("/api/transactions")
def api_get_transactions(
    limit: int = 100,
    offset: int = 0,
    category: Optional[str] = None,
    type: Optional[str] = None,
    search: Optional[str] = None
):
    txs = get_transactions(limit=limit, offset=offset, category=category, tx_type=type, search=search)
    return {"transactions": txs, "count": len(txs)}

@app.post("/api/transactions/parse")
def api_parse_text(req: ParseRequest):
    parsed = parse_transaction_text(req.text, source=req.source)
    if not parsed:
        return {"success": False, "message": "Could not identify a debit/credit or amount in the provided text."}
    
    saved_id = None
    if req.auto_save:
        saved_id = insert_transaction(
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
            source=req.source
        )
        if saved_id is None:
            return {"success": True, "parsed": parsed, "saved": False, "duplicate": True, "message": "Transaction already recorded (duplicate detected)."}

    return {"success": True, "parsed": parsed, "saved": saved_id is not None, "id": saved_id}

@app.post("/api/ingest/webhook")
def api_webhook_ingest(payload: WebhookPayload):
    """
    Webhook endpoint for iOS Shortcuts, Mac Automator, or curl.
    Sends raw SMS / notification text directly into AutoLedger.
    """
    parsed = parse_transaction_text(payload.text, source=payload.source or "WEBHOOK")
    if not parsed:
        log_ingest_event(payload.source or "WEBHOOK", "SKIPPED", "No transaction pattern detected in webhook payload.")
        return {"status": "skipped", "reason": "No financial transaction detected"}
    
    saved_id = insert_transaction(
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
        source=payload.source or "WEBHOOK"
    )
    
    status = "recorded" if saved_id else "duplicate_ignored"
    log_ingest_event(payload.source or "WEBHOOK", "SUCCESS", f"{status}: {parsed['merchant']} ₹{parsed['amount']}")
    return {"status": status, "id": saved_id, "transaction": parsed}

@app.post("/api/transactions")
def api_add_transaction(tx: ManualTransaction):
    from datetime import datetime
    saved_id = insert_transaction(
        amount=tx.amount,
        tx_type=tx.type.upper(),
        date=tx.date or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        category=tx.category,
        merchant=tx.merchant,
        mode=tx.mode,
        account_ref=tx.account_ref,
        reference_id=tx.reference_id,
        raw_text=tx.notes,
        source="MANUAL"
    )
    if saved_id is None:
        raise HTTPException(status_code=400, detail="Transaction appears to be a duplicate")
    return {"success": True, "id": saved_id}

@app.put("/api/transactions/{tx_id}/category")
def api_update_category(tx_id: int, payload: CategoryUpdate):
    updated = update_transaction_category(tx_id, payload.category)
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"success": True}

@app.delete("/api/transactions/{tx_id}")
def api_delete_transaction(tx_id: int):
    deleted = delete_transaction(tx_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"success": True}

@app.get("/api/ingest/status")
def api_get_ingest_status():
    settings = get_settings()
    sms_fda = check_sms_permission()
    email_user = settings.get("email_user", "")
    
    return {
        "sms": {
            "fda_granted": sms_fda,
            "last_scan": settings.get("sms_last_scan", "Never"),
            "enabled": settings.get("sms_sync_enabled", "true") == "true"
        },
        "email": {
            "configured": bool(email_user),
            "email_user": email_user,
            "last_scan": settings.get("email_last_scan", "Never"),
            "enabled": settings.get("email_sync_enabled", "false") == "true"
        },
        "webhook": {
            "url": "http://localhost:5050/api/ingest/webhook",
            "active": True
        },
        "logs": get_ingest_logs(limit=10)
    }

@app.post("/api/ingest/sms/sync")
def api_sync_sms():
    res = scan_sms_messages()
    return res

@app.post("/api/ingest/email/sync")
def api_sync_email():
    res = scan_email_inbox()
    return res

@app.get("/api/settings")
def api_get_settings():
    s = get_settings()
    # Mask password for safety
    if s.get("email_pass"):
        s["email_pass"] = "••••••••••••"
    return {"settings": s, "categories": CATEGORIES}

@app.post("/api/settings")
def api_update_settings(payload: SettingsUpdate):
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            # If masked password came back, don't overwrite
            if k == "email_pass" and "•" in v:
                continue
            update_setting(k, str(v))
    return {"success": True}

@app.post("/api/seed")
def api_seed_samples():
    """Seed realistic initial Indian UPI, bank & salary transactions"""
    samples = [
        ("HDFC Bank: Rs 85,000.00 credited to a/c **4091 on 01-11-26 by SALARY / NEFT (UTR: HDFC00019283). Avl bal: Rs 112,250.00", "SMS"),
        ("Paid Rs. 340.00 to Swiggy via UPI on 18-11-26. (UPI Ref: 432190812345)", "SMS"),
        ("SBI: A/C **9876 debited by Rs 40.00 on 20-11-26 trf to Chai Point Ref No 49128301293", "SMS"),
        ("ICICI Bank: Acct **124 debited for Rs 1,499.00 on 15-11-26. UPI:532187654. Info: AMAZON PAY INDIA. Avail Bal: Rs 42,300.00", "EMAIL"),
        ("Paid Rs 850.00 at SHELL PETROL PUMP via PhonePe on 12-11-26 (UPI: 98127391823)", "WEBHOOK"),
        ("Auto-debit: Rs 119.00 debited from A/c **4091 towards Spotify India on 05-11-26", "SMS"),
        ("Auto-debit of Rs 75.00 for Apple iCloud Storage processed from card ending 5678 on 08-11-26", "SMS"),
        ("Bescom Electricity Bill: Rs 1,280.00 debited from A/C **4091 on 10-11-26 via UPI", "EMAIL"),
        ("Paid Rs. 140.00 to Blue Tokai Coffee via UPI on 21-11-26 (Ref: 4321987654)", "SMS"),
        ("Dear Customer, card ending 5678 was used for Rs 2,450.00 at ZARA BENGALURU on 14-11-26. Bal: Rs 36,000", "SMS"),
        ("Received Rs. 1,200.00 from Rohan via UPI on 17-11-26 (Ref: 987654321098)", "SMS"),
        ("Paid Rs. 280.00 to Uber India via UPI on 19-11-26 (Ref: 431092817263)", "SMS"),
        ("Paid Rs. 650.00 to Cult.fit Gym Membership on 03-11-26 via UPI", "WEBHOOK")
    ]
    added = 0
    for text, src in samples:
        p = parse_transaction_text(text, source=src)
        if p:
            tx_id = insert_transaction(
                amount=p["amount"],
                tx_type=p["type"],
                date=p["date"],
                category=p["category"],
                merchant=p["merchant"],
                mode=p["mode"],
                account_ref=p["account_ref"],
                balance_after=p["balance_after"],
                reference_id=p["reference_id"],
                raw_text=p["raw_text"],
                source=src
            )
            if tx_id:
                added += 1
    return {"success": True, "added": added}

# Static files for UI
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "AutoLedger API is running. UI file loading..."}
