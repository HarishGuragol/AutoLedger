import re
from datetime import datetime
from typing import Dict, Any, Optional

CATEGORIES = [
    "Food & Dining",
    "Shopping",
    "Travel & Fuel",
    "Bills & Utilities",
    "Subscriptions & Tech",
    "Health & Fitness",
    "Salary & Income",
    "Transfers",
    "General"
]

CATEGORY_KEYWORDS = {
    "Subscriptions & Tech": [
        "netflix", "spotify", "prime", "youtube", "hotstar", "disney", "github", "chatgpt",
        "openai", "apple.com", "apple bill", "itunes", "icloud", "google storage", "google play",
        "steam", "playstation", "claude", "notion", "figma", "digitalocean", "aws", "gcp",
        "subscription", "membership"
    ],
    "Food & Dining": [
        "swiggy", "zomato", "starbucks", "mcdonald", "burger king", "kfc", "domino", "pizza",
        "chai", "tea", "coffee", "cafe", "restaurant", "dine", "blinkit", "zepto", "instamart",
        "bigbasket", "grofers", "dmart", "haldiram", "subway", "blue tokai", "third wave",
        "bakery", "kitchen", "biryani", "dhaba", "food", "eatclub", "box8"
    ],
    "Shopping": [
        "amazon", "flipkart", "myntra", "ajio", "meesho", "zara", "h&m", "croma", "reliance",
        "tata cliq", "nykaa", "apple store", "uniqlo", "decathlon", "lifestyle", "westside",
        "retail", "mart", "store", "supermarket", "shoppers stop", "pantaloons"
    ],
    "Travel & Fuel": [
        "uber", "ola", "rapido", "irctc", "makemytrip", "goibibo", "cleartrip", "indigo",
        "air india", "metro", "petrol", "fuel", "indian oil", "ioc", "hpcl", "bpcl",
        "shell", "fastag", "toll", "redbus", "auto rickshaw", "auto fare", "cab", "ride", "parking"
    ],
    "Bills & Utilities": [
        "electricity", "bescom", "tneb", "mahavitaran", "cesc", "gas", "indane", "hp gas",
        "bharat gas", "water", "broadband", "act fibernet", "airtel", "jio", "vi", "vodafone",
        "tata play", "dth", "recharge", "billdesk", "rent", "maintenance", "society"
    ],
    "Health & Fitness": [
        "apollo", "pharmeasy", "1mg", "netmeds", "cult", "cult.fit", "gym", "fitness",
        "hospital", "clinic", "pharmacy", "medplus", "diagnostic", "dr.", "doctor", "health"
    ],
    "Salary & Income": [
        "salary", "payroll", "dividend", "interest", "cash deposit", "stipend", "bonus",
        "payout", "cdm deposit", "salary credit"
    ]
}

def clean_amount(val_str: str) -> float:
    cleaned = val_str.replace(",", "").strip()
    return float(cleaned)

def classify_category(text: str, merchant: str, tx_type: str) -> str:
    combined = f"{text.lower()} {merchant.lower()}"
    
    if tx_type == "INCOME":
        for kw in CATEGORY_KEYWORDS["Salary & Income"]:
            if kw in combined:
                return "Salary & Income"
        return "Transfers"

    for category, keywords in CATEGORY_KEYWORDS.items():
        if category == "Salary & Income":
            continue
        for kw in keywords:
            if kw in combined:
                return category

    if "vpa" in combined or "@" in merchant or "trf" in combined or "upi" in combined:
        return "Transfers"

    return "General"

def clean_merchant_name(name: str) -> str:
    name = re.sub(r'^(to\s+(?:vpa\s+)?|at\s+|towards\s+|for\s+|trf\s+to\s+|info:\s*|from\s+)', '', name, flags=re.IGNORECASE).strip()
    name = re.sub(r'(\s+(via|using|through|processed)\s+.*|\s+from\s+a/c.*|\s+on\s+\d{1,2}[-/.]\d{1,2}.*|\s+on\s+\d{1,2}[a-zA-Z]{3}.*|\s+ref.*|\s+upi.*|\s+avl.*|\s+bal.*|\.+$)', '', name, flags=re.IGNORECASE).strip()
    if "@" in name:
        vpa_prefix = name.split("@")[0]
        if re.match(r'^[a-zA-Z._-]+$', vpa_prefix):
            name = vpa_prefix.replace(".", " ").replace("-", " ").title()
    return name.strip().title() if name else "Unknown Merchant"

def parse_transaction_text(text: str, source: str = "MANUAL") -> Optional[Dict[str, Any]]:
    """
    Parses SMS, Email, or Bank push alert text into structured transaction dictionary.
    Returns None if text does not appear to be a transaction alert.
    """
    if not text or len(text.strip()) < 8:
        return None

    norm = text.strip()
    lower = norm.lower()

    # 1. Determine Transaction Type (DEBIT vs CREDIT)
    is_credit = False
    is_debit = False

    credit_match = re.search(r'\b(credited|received|deposited|refund|added to a/c|cashback)\b', lower)
    debit_match = re.search(r'\b(debited|spent|paid|withdrawn|sent|deducted|payment of|auto-?debit|used for|purchase of|charged)\b', lower)

    if credit_match and not debit_match:
        is_credit = True
    elif debit_match and not credit_match:
        is_debit = True
    elif credit_match and debit_match:
        if credit_match.start() < debit_match.start():
            is_credit = True
        else:
            is_debit = True
    else:
        if "credit" in lower or "refund" in lower:
            is_credit = True
        elif "debit" in lower or "spent" in lower or "paid" in lower:
            is_debit = True
        else:
            return None

    tx_type = "INCOME" if is_credit else "EXPENSE"

    # 2. Extract Amount
    amount = None
    amt_patterns = [
        r'(?:inr|rs\.?|₹)\s*([\d,]+\.?\d*)',
        r'([\d,]+\.?\d*)\s*(?:inr|rs\.?|₹)',
        r'debited\s*(?:by|for|with)?\s*([\d,]+\.?\d*)',
        r'credited\s*(?:by|for|with)?\s*([\d,]+\.?\d*)',
        r'paid\s*([\d,]+\.?\d*)',
        r'spent\s*([\d,]+\.?\d*)',
        r'used for\s*(?:inr|rs\.?|₹)?\s*([\d,]+\.?\d*)'
    ]
    for pat in amt_patterns:
        m = re.search(pat, norm, re.IGNORECASE)
        if m:
            try:
                cand = clean_amount(m.group(1))
                if cand > 0 and cand < 100000000:
                    amount = cand
                    break
            except ValueError:
                continue

    if amount is None:
        return None

    # 3. Detect Mode
    mode = "UPI"
    if "card" in lower or "pos" in lower:
        mode = "CARD"
    elif "atm" in lower or "cash" in lower:
        mode = "ATM"
    elif "neft" in lower or "imps" in lower or "rtgs" in lower:
        mode = "NETBANKING"
    elif "auto-debit" in lower or "autodebit" in lower or "standing instruction" in lower:
        mode = "AUTO_DEBIT"
    elif "upi" in lower or "vpa" in lower or "gpay" in lower or "phonepe" in lower or "paytm" in lower:
        mode = "UPI"

    # 4. Extract Merchant / Beneficiary / VPA
    merchant = "Unknown"
    merchant_patterns = [
        r'(?:info:\s*|trf to\s*)([a-zA-Z0-9.\-_@\s]{2,35}?)(?:\s+on|\s+ref|\s+upi|\s+via|\.|\,|$|\s+avl|\s+bal)',
        r'(?:to\s+vpa|to)\s+([a-zA-Z0-9.\-_@\s]{2,35}?)(?:\s+on|\s+at|\s+ref|\s+upi|\s+via|\.|\,|$|\s+avl|\s+bal)',
        r'(?:at|towards)\s+([a-zA-Z0-9.\-_@\s]{2,35}?)(?:\s+on|\s+ref|\s+upi|\s+via|\.|\,|$|\s+avl|\s+bal)',
        r'(?:from|by)\s+([a-zA-Z0-9.\-_@\s]{2,35}?)(?:\s+on|\s+ref|\s+upi|\s+via|\.|\,|$|\s+avl|\s+bal)',
        r'(?:for\s+)(?!(?:inr|rs|₹|\d))\s*([a-zA-Z0-9.\-_@\s]{2,35}?)(?:\s+processed|\s+from|\s+on|\s+at|\s+ref|\s+upi|\s+via|\.|\,|$|\s+avl|\s+bal)'
    ]
    for pat in merchant_patterns:
        m = re.search(pat, norm, re.IGNORECASE)
        if m:
            extracted = m.group(1).strip()
            # Ensure it's not capturing numbers or currency indicators
            if not re.match(r'^(?:inr|rs|₹|\d)', extracted.lower()) and len(extracted) >= 2 and extracted.lower() not in ["a/c", "card", "vpa"]:
                merchant = clean_merchant_name(extracted)
                break

    # If merchant is still unknown or generic, try category keywords in text
    if merchant in ["Unknown", "Rs 1", "Rs 2"] or len(merchant) <= 2:
        for cat, kws in CATEGORY_KEYWORDS.items():
            for kw in kws:
                if re.search(r'\b' + re.escape(kw) + r'\b', lower):
                    merchant = kw.title()
                    break
            if merchant not in ["Unknown", "Rs 1", "Rs 2"]:
                break

    # 5. Extract Account Mask
    account_ref = None
    acct_match = re.search(r'(?:a/c|acct|card|ending|account)\s*(?:no\.?)?\s*[\*Xx]*(\d{3,5})', norm, re.IGNORECASE)
    if acct_match:
        account_ref = f"**{acct_match.group(1)}"

    # 6. Extract Balance After Transaction
    balance_after = None
    bal_match = re.search(r'(?:bal|balance|avail bal|avl bal)\s*(?:is|:)?\s*(?:inr|rs\.?|₹)?\s*([\d,]+\.?\d*)', norm, re.IGNORECASE)
    if bal_match:
        try:
            balance_after = clean_amount(bal_match.group(1))
        except ValueError:
            pass

    # 7. Extract Reference / UTR / UPI Ref ID
    reference_id = None
    ref_match = re.search(r'(?:upi ref|ref no|ref|txn id|txn|utr|rrn|upi)\s*(?:no\.?|:)\s*([A-Za-z0-9]{6,24})', norm, re.IGNORECASE)
    if ref_match:
        reference_id = ref_match.group(1)

    # 8. Date Parsing
    tx_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_match = re.search(r'(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}[-/\s][a-zA-Z]{3}[-/\s]\d{2,4})', norm)
    if date_match:
        raw_dt = date_match.group(1)
        for fmt in ("%d-%m-%y", "%d-%m-%Y", "%d/%m/%y", "%d/%m/%Y", "%d-%b-%y", "%d-%b-%Y", "%d %b %Y"):
            try:
                parsed_dt = datetime.strptime(raw_dt, fmt)
                tx_date = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
                break
            except ValueError:
                continue

    # 9. Classify Category
    category = classify_category(norm, merchant, tx_type)

    return {
        "amount": amount,
        "type": tx_type,
        "date": tx_date,
        "category": category,
        "merchant": merchant,
        "mode": mode,
        "account_ref": account_ref,
        "balance_after": balance_after,
        "reference_id": reference_id,
        "raw_text": norm,
        "source": source
    }
