# AutoLedger ⚡
### Autonomous UPI, Bank SMS & Email Transaction Ingestion & Personal Expense Tracker

AutoLedger is a modern, privacy-first personal finance application that automatically reads incoming bank messages, UPI payment alerts, and transaction emails, extracts financial metadata in real-time, and logs them into a cyber-noir dashboard.

---

## 🌟 Key Features

1. **Intelligent Financial NLP Parser (India-Focused)**
   - Automatically parses Indian bank SMS, UPI debit/credit notifications, ATM withdrawals, and card spends.
   - Detects:
     - **Transaction Type**: Debit (Expense) vs Credit (Income / Refund).
     - **Amount (₹)** with precise float extraction.
     - **Mode**: UPI, Debit/Credit Card, Net Banking (NEFT/IMPS), ATM, Auto-Debit.
     - **Merchant / Counterparty**: Cleans up VPAs (e.g. `swiggy@icici` -> `Swiggy`) and removes boilerplate.
     - **Category Auto-Tagging**: Food & Dining, Shopping, Travel & Fuel, Bills & Utilities, Subscriptions & Tech, Health & Fitness, Salary & Income, Transfers.
     - **Account Mask & Balance After**: Tracks available balance and `A/C **4091`.
     - **Reference / UTR ID**: Captures UPI reference IDs for proof and deduplication.

2. **Automated Multi-Channel Ingestion Feeds**
   - **macOS Messages (iMessage & SMS Forwarding)**:
     - Watches `~/Library/Messages/chat.db` for forwarded bank texts from HDFC, SBI, ICICI, Axis, Paytm, etc.
   - **Bank Email (IMAP Sync)**:
     - Connects via secure IMAP (Gmail App Password / Outlook / iCloud) to process incoming bank transaction receipts.
   - **Real-Time iPhone & Mac Shortcut Webhook**:
     - `POST http://localhost:5050/api/ingest/webhook`
     - Allows iOS Automations to push bank notifications immediately on arrival.
   - **Smart Paste & Test Drop Zone**:
     - Instant UI box to paste raw SMS or email with 1-click test samples.

3. **High-Performance Cyber-Noir Dashboard**
   - Real-time spend metrics: Monthly Expenses, Monthly Inflow, Net Savings, Today's Spend, UPI digital share.
   - Monthly Budget Tracker with visual burn-rate progress bar.
   - Spending by Category breakdown bars with color coding.
   - Inflow vs. Outflow ratio gauge.
   - Searchable, filterable transaction ledger with inline category editing and deletion.

4. **100% Local, Private & Lightweight**
   - Zero cloud database dependency. All data is saved locally in SQLite (`data/ledger.db`).
   - Runs with ~0.1% CPU and <65MB RAM.

---

## 🚀 Quick Start

```bash
# 1. Navigate to directory
cd ~/Projects/AutoLedger

# 2. Run the start script
./start.sh
```

Open your browser to: **[http://localhost:5050](http://localhost:5050)**

---

## 📱 How to Enable Automated Feeds

### 1. macOS Messages (SMS) Auto-Sync
If you have an iPhone with **Text Message Forwarding** enabled to your Mac (in *iPhone Settings > Messages > Text Message Forwarding*):
1. Open **System Settings** on your Mac.
2. Go to **Privacy & Security > Full Disk Access**.
3. Enable Full Disk Access for **Terminal** (or your terminal emulator).
4. AutoLedger will automatically read incoming SMS from `chat.db` in the background.

### 2. iPhone Real-Time Webhook (Apple Shortcuts)
1. Open the **Shortcuts** app on your iPhone.
2. Tap **Automation > New Automation**.
3. Choose **Message** (e.g. when message contains `debited` or `Rs`).
4. Set action: **Get Contents of URL** `http://<your-mac-local-ip>:5050/api/ingest/webhook` (Method: POST, Body: JSON with message text).
5. Every time you make a UPI transaction, it logs itself in real-time!

---

## 🛠️ Tech Stack
- **Backend**: Python 3.12, FastAPI, Uvicorn (ASGI)
- **Database**: SQLite3 (Local file)
- **Frontend**: Vanilla HTML5, Modern CSS, Plus Jakarta Sans & JetBrains Mono
- **Ingestion**: Regex NLP Engine, `imaplib` (Email), `sqlite3` URI mode (macOS Messages), REST Webhook
