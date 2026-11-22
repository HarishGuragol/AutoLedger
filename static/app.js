// AutoLedger Client Application Logic

const SAMPLES = {
  swiggy: "Paid Rs. 340.00 to Swiggy via UPI on 22-Nov-26 (Ref: 432190812345). Avl bal: Rs 14,250.00",
  chai: "SBI: A/C **9876 debited by Rs 40.00 on 22-Nov-26 trf to Chai Point Ref No 49128301293",
  salary: "HDFC Bank: Rs 85,000.00 credited to a/c **4091 on 22-11-26 by SALARY / NEFT (UTR: HDFC00019283). Avl bal: Rs 99,250.00",
  amazon: "ICICI Bank: Acct **124 debited for Rs 1,499.00 on 22-Nov-26. UPI:532187654. Info: AMAZON PAY INDIA. Avail Bal: Rs 42,300.00",
  zara: "Dear Customer, card ending 5678 was used for Rs 2,450.00 at ZARA BENGALURU on 22-Nov-26. Bal: Rs 36,000",
  spotify: "Auto-debit of Rs 119.00 for Spotify Premium processed from A/c **4091 on 22-Nov-26"
};

const CATEGORY_COLORS = {
  "Food & Dining": "#f97316",
  "Shopping": "#ec4899",
  "Travel & Fuel": "#06b6d4",
  "Bills & Utilities": "#eab308",
  "Subscriptions & Tech": "#8b5cf6",
  "Health & Fitness": "#10b981",
  "Salary & Income": "#22c55e",
  "Transfers": "#3b82f6",
  "General": "#64748b"
};

let debounceTimer = null;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  refreshAll();
  fetchIngestStatus();
  // Periodic poll every 30 seconds
  setInterval(() => {
    fetchStats();
    fetchIngestStatus();
  }, 30000);
});

function refreshAll() {
  fetchStats();
  fetchTransactions();
  fetchIngestStatus();
}

// Format Currency
function formatINR(num) {
  if (num === null || num === undefined) return "₹0.00";
  return "₹" + Number(num).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Fetch Stats and Analytics
async function fetchStats() {
  try {
    const res = await fetch("/api/stats");
    const data = await res.json();

    document.getElementById("val-monthly-expense").textContent = formatINR(data.monthly_expense);
    document.getElementById("val-monthly-income").textContent = formatINR(data.monthly_income);
    document.getElementById("val-monthly-upi").textContent = formatINR(data.monthly_upi);
    document.getElementById("val-today-expense").textContent = `Today: ${formatINR(data.today_expense)}`;
    document.getElementById("val-net-savings").textContent = `Net Savings: ${formatINR(data.net_savings)}`;
    document.getElementById("val-tx-count").textContent = `${data.total_tx_count} Recorded Txns`;

    // Budget Tracker
    document.getElementById("val-budget-remaining").textContent = formatINR(data.budget_remaining);
    document.getElementById("val-budget-pct").textContent = `${data.budget_percent_used}% Used`;
    document.getElementById("val-budget-total").textContent = `Limit: ${formatINR(data.monthly_budget)}`;
    
    const fill = document.getElementById("budget-bar-fill");
    const pct = Math.min(100, data.budget_percent_used);
    fill.style.width = `${pct}%`;
    if (pct > 85) {
      fill.style.background = "linear-gradient(90deg, #f59e0b, #f43f5e)";
    } else {
      fill.style.background = "linear-gradient(90deg, #10b981, #06b6d4)";
    }

    // Ratio Card
    const totalFlow = data.monthly_income + data.monthly_expense;
    let savingsRate = 0;
    if (data.monthly_income > 0) {
      savingsRate = Math.max(0, Math.round(((data.monthly_income - data.monthly_expense) / data.monthly_income) * 100));
    }
    document.getElementById("val-savings-rate").textContent = `${savingsRate}%`;
    document.getElementById("ratio-income").textContent = formatINR(data.monthly_income);
    document.getElementById("ratio-expense").textContent = formatINR(data.monthly_expense);

    // Render Category Breakdown Bars
    renderCategoryBars(data.categories, data.monthly_expense);
  } catch (err) {
    console.error("Failed to fetch stats:", err);
  }
}

function renderCategoryBars(categories, totalExpense) {
  const container = document.getElementById("category-bars-container");
  container.innerHTML = "";

  if (!categories || categories.length === 0 || totalExpense === 0) {
    container.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:10px 0;">No expense categories recorded this month yet.</div>';
    return;
  }

  categories.slice(0, 5).forEach(cat => {
    const pct = totalExpense > 0 ? Math.round((cat.total / totalExpense) * 100) : 0;
    const color = CATEGORY_COLORS[cat.category] || "#64748b";

    const row = document.createElement("div");
    row.className = "cat-row";
    row.innerHTML = `
      <div class="cat-row-top">
        <span class="cat-name"><span style="color:${color};margin-right:6px;">●</span>${cat.category}</span>
        <span class="cat-val">${formatINR(cat.total)} (${pct}%)</span>
      </div>
      <div class="cat-bar-bg">
        <div class="cat-bar-fill" style="width: ${pct}%; background-color: ${color};"></div>
      </div>
    `;
    container.appendChild(row);
  });
}

// Fetch Transactions Ledger
async function fetchTransactions() {
  const typeFilter = document.getElementById("filter-type").value;
  const catFilter = document.getElementById("filter-category").value;
  const searchFilter = document.getElementById("filter-search").value.trim();

  let url = `/api/transactions?limit=100`;
  if (typeFilter !== "All") url += `&type=${encodeURIComponent(typeFilter)}`;
  if (catFilter !== "All") url += `&category=${encodeURIComponent(catFilter)}`;
  if (searchFilter) url += `&search=${encodeURIComponent(searchFilter)}`;

  try {
    const res = await fetch(url);
    const data = await res.json();
    const tbody = document.getElementById("transactions-tbody");
    const emptyState = document.getElementById("empty-state");
    const countBadge = document.getElementById("ledger-count-badge");

    countBadge.textContent = `${data.count} Transactions`;
    tbody.innerHTML = "";

    if (!data.transactions || data.transactions.length === 0) {
      emptyState.classList.remove("hidden");
      return;
    }

    emptyState.classList.add("hidden");

    data.transactions.forEach(tx => {
      const tr = document.createElement("tr");
      const isExpense = tx.type === "EXPENSE";
      const amtClass = isExpense ? "expense" : "income";
      const amtPrefix = isExpense ? "- " : "+ ";
      const dateDisplay = tx.date ? tx.date.substring(0, 16) : "Just now";
      const catColor = CATEGORY_COLORS[tx.category] || "#64748b";

      tr.innerHTML = `
        <td class="table-date">${dateDisplay}</td>
        <td class="table-merchant">${escapeHtml(tx.merchant || "Unknown")}</td>
        <td>
          <select class="filter-select" style="font-size:11px;padding:3px 6px;color:${catColor};border-color:rgba(255,255,255,0.1);" onchange="updateTxCategory(${tx.id}, this.value)">
            ${renderCategoryOptions(tx.category)}
          </select>
        </td>
        <td><span class="table-badge badge-mode">${tx.mode || 'UPI'}</span></td>
        <td><span class="table-badge badge-source">${tx.source || 'MANUAL'}</span></td>
        <td class="table-amount ${amtClass}">${amtPrefix}${formatINR(tx.amount)}</td>
        <td class="table-ref">${tx.account_ref || ''} ${tx.reference_id ? 'Ref:' + tx.reference_id.substring(0, 10) : ''}</td>
        <td>
          <button class="btn-del" onclick="deleteTx(${tx.id})" title="Delete entry">✕</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Failed to fetch transactions:", err);
  }
}

function renderCategoryOptions(selected) {
  const cats = [
    "Food & Dining", "Shopping", "Travel & Fuel", "Bills & Utilities",
    "Subscriptions & Tech", "Health & Fitness", "Salary & Income", "Transfers", "General"
  ];
  return cats.map(c => `<option value="${c}" ${c === selected ? 'selected' : ''}>${c}</option>`).join("");
}

function debounceFetchTransactions() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(fetchTransactions, 300);
}

// Ingestion Status Check
async function fetchIngestStatus() {
  try {
    const res = await fetch("/api/ingest/status");
    const data = await res.json();

    // SMS Pill
    const smsPill = document.getElementById("pill-sms");
    const smsVal = document.getElementById("val-sms-status");
    const smsDot = smsPill.querySelector(".indicator-dot");

    if (data.sms.fda_granted) {
      smsVal.textContent = "Listening";
      smsDot.className = "indicator-dot live";
    } else {
      smsVal.textContent = "FDA Required";
      smsDot.className = "indicator-dot warn";
    }

    // Email Pill
    const emailPill = document.getElementById("pill-email");
    const emailVal = document.getElementById("val-email-status");
    const emailDot = emailPill.querySelector(".indicator-dot");

    if (data.email.configured) {
      emailVal.textContent = "Connected";
      emailDot.className = "indicator-dot live";
    } else {
      emailVal.textContent = "Setup Needed";
      emailDot.className = "indicator-dot off";
    }

    // Modal Status Box
    const fdaBox = document.getElementById("sms-fda-status-box");
    if (data.sms.fda_granted) {
      fdaBox.className = "setup-status-card status-ok";
      fdaBox.innerHTML = `<strong>● Full Disk Access Granted</strong><br>AutoLedger can actively scan your macOS Messages for incoming bank SMS. Last scan: ${data.sms.last_scan}`;
    } else {
      fdaBox.className = "setup-status-card status-warn";
      fdaBox.innerHTML = `<strong>⚠️ Full Disk Access Not Granted Yet</strong><br>macOS protects ~/Library/Messages/chat.db. Follow the 4-step instructions below to grant permission.`;
    }

    // Render Logs
    const logsTbody = document.getElementById("logs-tbody");
    logsTbody.innerHTML = "";
    if (data.logs && data.logs.length > 0) {
      data.logs.forEach(l => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td class="table-date">${l.timestamp}</td>
          <td><span class="table-badge badge-source">${l.source}</span></td>
          <td><span class="table-badge ${l.status === 'SUCCESS' ? 'badge-income' : 'badge-expense'}">${l.status}</span></td>
          <td style="font-size:12px;color:var(--text-muted);">${escapeHtml(l.details)}</td>
        `;
        logsTbody.appendChild(row);
      });
    }
  } catch (err) {
    console.error("Failed to fetch ingest status:", err);
  }
}

// Quick Sample Loader
function loadSample(key) {
  if (SAMPLES[key]) {
    document.getElementById("raw-input-text").value = SAMPLES[key];
    parseAndSave();
  }
}

// Smart Parse and Save
async function parseAndSave() {
  const text = document.getElementById("raw-input-text").value.trim();
  if (!text) {
    showToast("Please paste a transaction message first!");
    return;
  }

  try {
    const res = await fetch("/api/transactions/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, auto_save: true, source: "SMART_PASTE" })
    });
    const result = await res.json();

    const banner = document.getElementById("parse-result-banner");
    const content = document.getElementById("result-details-content");

    if (result.success && result.parsed) {
      const p = result.parsed;
      banner.classList.remove("hidden");
      banner.style.border = "1px solid var(--accent-emerald)";
      banner.style.background = "rgba(16, 185, 129, 0.1)";

      content.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
          <div>
            <strong style="color:var(--accent-emerald);font-size:14px;">✓ ${result.saved ? 'Successfully Recorded' : 'Detected (Duplicate Ignored)'}</strong>: 
            <span style="font-weight:700;color:#fff;">${p.merchant}</span>
            <span style="margin-left:6px;font-family:var(--font-mono);font-size:14px;color:${p.type === 'EXPENSE' ? 'var(--accent-rose)' : 'var(--accent-emerald)'};">
              ${p.type === 'EXPENSE' ? '-' : '+'} ${formatINR(p.amount)}
            </span>
          </div>
          <div style="display:flex;gap:6px;">
            <span class="table-badge badge-mode">${p.mode}</span>
            <span class="table-badge badge-income" style="background:rgba(255,255,255,0.08);color:#fff;">${p.category}</span>
          </div>
        </div>
        <div style="font-size:11px;color:var(--text-dim);margin-top:4px;font-family:var(--font-mono);">
          ${p.account_ref ? 'Account: ' + p.account_ref : ''} ${p.balance_after ? '| Balance After: ' + formatINR(p.balance_after) : ''} ${p.reference_id ? '| Ref: ' + p.reference_id : ''}
        </div>
      `;

      showToast(`Logged ${p.merchant} (${formatINR(p.amount)})`);
      refreshAll();
    } else {
      banner.classList.remove("hidden");
      banner.style.border = "1px solid var(--accent-rose)";
      banner.style.background = "rgba(244, 63, 94, 0.1)";
      content.innerHTML = `<span style="color:var(--accent-rose);">⚠️ Could not detect transaction pattern in text.</span>`;
    }
  } catch (err) {
    showToast("Failed to process transaction: " + err.message);
  }
}

// Inline Category Update
async function updateTxCategory(txId, newCategory) {
  try {
    const res = await fetch(`/api/transactions/${txId}/category`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: newCategory })
    });
    if (res.ok) {
      showToast(`Updated to ${newCategory}`);
      fetchStats();
    }
  } catch (err) {
    showToast("Update failed: " + err.message);
  }
}

// Delete Transaction
async function deleteTx(txId) {
  if (!confirm("Delete this transaction entry?")) return;
  try {
    const res = await fetch(`/api/transactions/${txId}`, { method: "DELETE" });
    if (res.ok) {
      showToast("Transaction removed");
      refreshAll();
    }
  } catch (err) {
    showToast("Delete failed: " + err.message);
  }
}

// Seed Sample Data
async function seedSampleData() {
  try {
    const res = await fetch("/api/seed", { method: "POST" });
    const data = await res.json();
    showToast(`Seeded ${data.added} realistic Indian bank & UPI transactions!`);
    refreshAll();
  } catch (err) {
    showToast("Seed failed: " + err.message);
  }
}

// Manual Transaction Submission
async function submitManualTransaction() {
  const amt = parseFloat(document.getElementById("man-amount").value);
  const type = document.getElementById("man-type").value;
  const merchant = document.getElementById("man-merchant").value.trim();
  const category = document.getElementById("man-category").value;
  const mode = document.getElementById("man-mode").value;
  const notes = document.getElementById("man-notes").value.trim();

  if (!amt || !merchant) {
    showToast("Please enter both amount and merchant name!");
    return;
  }

  try {
    const res = await fetch("/api/transactions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amount: amt,
        type: type,
        merchant: merchant,
        category: category,
        mode: mode,
        notes: notes
      })
    });
    if (res.ok) {
      showToast("Manual transaction saved");
      closeModal("modal-manual-add");
      document.getElementById("man-amount").value = "";
      document.getElementById("man-merchant").value = "";
      document.getElementById("man-notes").value = "";
      refreshAll();
    }
  } catch (err) {
    showToast("Failed to save: " + err.message);
  }
}

// Sync SMS
async function syncSMS() {
  showToast("Scanning macOS Messages...");
  try {
    const res = await fetch("/api/ingest/sms/sync", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast(`Scan complete: ${data.processed} new transactions found.`);
      refreshAll();
    } else {
      showToast(data.message || "SMS scan error");
      fetchIngestStatus();
    }
  } catch (err) {
    showToast("Scan failed: " + err.message);
  }
}

// Sync Email
async function syncEmail() {
  showToast("Connecting to IMAP...");
  try {
    const res = await fetch("/api/ingest/email/sync", { method: "POST" });
    const data = await res.json();
    showToast(data.message);
    if (data.success) refreshAll();
  } catch (err) {
    showToast("Email check failed: " + err.message);
  }
}

// Save Email Settings
async function saveEmailSettings() {
  const host = document.getElementById("cfg-email-host").value.trim();
  const port = document.getElementById("cfg-email-port").value.trim();
  const user = document.getElementById("cfg-email-user").value.trim();
  const pass = document.getElementById("cfg-email-pass").value.trim();

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email_host: host,
        email_port: port,
        email_user: user,
        email_pass: pass,
        email_sync_enabled: "true"
      })
    });
    if (res.ok) {
      showToast("Email credentials saved");
      fetchIngestStatus();
    }
  } catch (err) {
    showToast("Failed to save credentials: " + err.message);
  }
}

// Save Settings
async function saveSettings() {
  const budget = document.getElementById("set-budget").value.trim();
  const currency = document.getElementById("set-currency").value.trim();

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        monthly_budget: budget,
        currency_symbol: currency
      })
    });
    if (res.ok) {
      showToast("Preferences saved");
      closeModal("modal-settings");
      fetchStats();
    }
  } catch (err) {
    showToast("Failed to save preferences: " + err.message);
  }
}

// Modal Helpers
function openModal(id, targetTab) {
  document.getElementById(id).classList.remove("hidden");
  if (targetTab) {
    switchTab(targetTab);
  }
}

function closeModal(id) {
  document.getElementById(id).classList.add("hidden");
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-pane").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));

  const target = document.getElementById(tabId);
  const btn = document.getElementById(tabId + "-btn");
  if (target) target.classList.add("active");
  if (btn) btn.classList.add("active");
}

// Toast Notification
function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 3500);
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
