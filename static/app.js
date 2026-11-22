// AutoLedger Client Application Logic (Multi-Bank & Monthly Tracker)

const CATEGORY_COLORS = {
  "Food & Dining": "#f97316",
  "Shopping": "#ec4899",
  "Travel & Fuel": "#06b6d4",
  "Bills & Utilities": "#eab308",
  "Subscriptions & Tech": "#8b5cf6",
  "Health & Fitness": "#10b981",
  "Salary & Income": "#22c55e",
  "CRED & Wallet": "#a855f7",
  "Investments & FD": "#3b82f6",
  "Self Transfer": "#64748b",
  "General": "#94a3b8"
};

let currentMonth = "2026-11";
let currentBank = "All";
let availableMonthsList = [];
let debounceTimer = null;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  refreshAll();
  fetchIngestStatus();
  setInterval(() => {
    fetchStats();
  }, 30000);
});

function refreshAll() {
  fetchStats();
  fetchTransactions();
  fetchIngestStatus();
}

function formatINR(num) {
  if (num === null || num === undefined) return "₹0.00";
  return "₹" + Number(num).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function monthLabel(ym) {
  if (!ym) return "";
  const parts = ym.split("-");
  const year = parts[0];
  const mIdx = parseInt(parts[1], 10) - 1;
  const mNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  return `${mNames[mIdx] || ym} ${year}`;
}

// Fetch Monthly Analysis & Stats
async function fetchStats() {
  try {
    const res = await fetch(`/api/monthly-analysis?month=${currentMonth}`);
    const data = await res.json();

    currentMonth = data.month;
    availableMonthsList = data.available_months || [currentMonth];

    // Populate Month Dropdown
    const sel = document.getElementById("select-month");
    sel.innerHTML = "";
    availableMonthsList.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = monthLabel(m);
      if (m === currentMonth) opt.selected = true;
      sel.appendChild(opt);
    });

    // Top Metric HUD
    document.getElementById("val-monthly-expense").textContent = formatINR(data.real_expenses);
    document.getElementById("val-monthly-income").textContent = formatINR(data.total_income);
    document.getElementById("val-monthly-cred").textContent = formatINR(data.cred_loaded);
    document.getElementById("val-net-surplus").textContent = formatINR(data.net_surplus);
    document.getElementById("val-net-savings").textContent = `Net Surplus: ${formatINR(data.net_surplus)}`;
    document.getElementById("val-savings-rate-badge").textContent = `${data.savings_rate}% Retained`;

    // Retention Progress Bar
    const fill = document.getElementById("budget-bar-fill");
    const rate = Math.max(0, Math.min(100, data.savings_rate));
    fill.style.width = `${rate}%`;
    fill.style.background = rate > 30 ? "linear-gradient(90deg, #10b981, #06b6d4)" : "linear-gradient(90deg, #f59e0b, #f43f5e)";

    // Ratio Circle
    document.getElementById("val-savings-rate").textContent = `${rate}%`;
    document.getElementById("ratio-income").textContent = formatINR(data.total_income);
    document.getElementById("ratio-expense").textContent = formatINR(data.real_expenses);

    // 4 Banks & CRED Breakdown Cards
    data.bank_stats.forEach(b => {
      if (b.bank === "Standard Chartered") {
        document.getElementById("sc-inflow").textContent = formatINR(b.inflow);
        document.getElementById("sc-spent").textContent = formatINR(b.spent);
        document.getElementById("sc-count").textContent = `${b.tx_count} txns`;
      } else if (b.bank === "CRED") {
        document.getElementById("cred-loaded-val").textContent = formatINR(data.cred_loaded);
        document.getElementById("cred-spent-val").textContent = formatINR(b.spent);
        document.getElementById("cred-count").textContent = `${b.tx_count} txns`;
      } else if (b.bank === "HDFC") {
        document.getElementById("hdfc-spent").textContent = formatINR(b.spent);
        document.getElementById("hdfc-inflow").textContent = formatINR(b.inflow);
        document.getElementById("hdfc-count").textContent = `${b.tx_count} txns`;
      } else if (b.bank === "ICICI") {
        document.getElementById("icici-spent").textContent = formatINR(b.spent);
        document.getElementById("icici-inflow").textContent = formatINR(b.inflow);
        document.getElementById("icici-count").textContent = `${b.tx_count} txns`;
      } else if (b.bank === "IDFC FIRST") {
        document.getElementById("idfc-inflow").textContent = formatINR(b.inflow);
        document.getElementById("idfc-spent").textContent = formatINR(b.spent);
        document.getElementById("idfc-count").textContent = `${b.tx_count} txns`;
      }
    });

    // Render Category Breakdown Bars
    renderCategoryBars(data.categories, data.real_expenses);
  } catch (err) {
    console.error("Failed to fetch monthly stats:", err);
  }
}

function renderCategoryBars(categories, totalExpense) {
  const container = document.getElementById("category-bars-container");
  container.innerHTML = "";

  if (!categories || categories.length === 0) {
    container.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:10px 0;">No expenses recorded for this month.</div>';
    return;
  }

  categories.slice(0, 6).forEach(cat => {
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

// Fetch Transactions Ledger with Month & Bank filters
async function fetchTransactions() {
  const typeFilter = document.getElementById("filter-type").value;
  const catFilter = document.getElementById("filter-category").value;
  const bankFilter = document.getElementById("filter-bank").value;
  const searchFilter = document.getElementById("filter-search").value.trim();

  let url = `/api/transactions?limit=150&month=${currentMonth}`;
  if (bankFilter !== "All") url += `&bank=${encodeURIComponent(bankFilter)}`;
  if (typeFilter !== "All") url += `&type=${encodeURIComponent(typeFilter)}`;
  if (catFilter !== "All") url += `&category=${encodeURIComponent(catFilter)}`;
  if (searchFilter) url += `&search=${encodeURIComponent(searchFilter)}`;

  try {
    const res = await fetch(url);
    const data = await res.json();
    const tbody = document.getElementById("transactions-tbody");
    const emptyState = document.getElementById("empty-state");
    const countBadge = document.getElementById("ledger-count-badge");

    countBadge.textContent = `${data.count} Transactions (${monthLabel(currentMonth)})`;
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
      const bankBadgeClass = tx.bank === "Standard Chartered" ? "sc-tag" : tx.bank === "CRED" ? "cred-tag" : tx.bank === "HDFC" ? "hdfc-tag" : tx.bank === "ICICI" ? "icici-tag" : "idfc-tag";

      tr.innerHTML = `
        <td class="table-date">${dateDisplay}</td>
        <td><span class="bank-tag ${bankBadgeClass}">${tx.bank || 'Other'}</span></td>
        <td class="table-merchant">${escapeHtml(tx.merchant || "Unknown")}</td>
        <td>
          <select class="filter-select" style="font-size:11px;padding:3px 6px;color:${catColor};border-color:rgba(255,255,255,0.1);" onchange="updateTxCategory(${tx.id}, this.value)">
            ${renderCategoryOptions(tx.category)}
          </select>
        </td>
        <td><span class="table-badge badge-mode">${tx.mode || 'UPI'}</span></td>
        <td class="table-amount ${amtClass}">${amtPrefix}${formatINR(tx.amount)}</td>
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
    "Subscriptions & Tech", "Health & Fitness", "Salary & Income", "CRED & Wallet",
    "Investments & FD", "Self Transfer", "General"
  ];
  return cats.map(c => `<option value="${c}" ${c === selected ? 'selected' : ''}>${c}</option>`).join("");
}

function debounceFetchTransactions() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(fetchTransactions, 300);
}

// Month Navigation
function onMonthSelected(newMonth) {
  currentMonth = newMonth;
  refreshAll();
}

function changeMonth(delta) {
  if (!availableMonthsList || availableMonthsList.length === 0) return;
  const idx = availableMonthsList.indexOf(currentMonth);
  if (idx === -1) return;
  const newIdx = idx - delta; // availableMonthsList is DESC (newest at 0)
  if (newIdx >= 0 && newIdx < availableMonthsList.length) {
    currentMonth = availableMonthsList[newIdx];
    refreshAll();
  }
}

// Filter by clicking Bank Card
function filterByBank(bankName) {
  const bankSelect = document.getElementById("filter-bank");
  bankSelect.value = bankName;
  fetchTransactions();
  showToast(`Filtered by ${bankName}`);
}

// Ingestion Status Check
async function fetchIngestStatus() {
  try {
    const res = await fetch("/api/ingest/status");
    const data = await res.json();

    const smsVal = document.getElementById("val-sms-status");
    const smsPill = document.getElementById("pill-sms");
    const smsDot = smsPill.querySelector(".indicator-dot");

    if (data.sms.fda_granted) {
      smsVal.textContent = "Listening";
      smsDot.className = "indicator-dot live";
    } else {
      smsVal.textContent = "FDA Required";
      smsDot.className = "indicator-dot warn";
    }

    const emailVal = document.getElementById("val-email-status");
    const emailPill = document.getElementById("pill-email");
    const emailDot = emailPill.querySelector(".indicator-dot");

    if (data.email.configured) {
      emailVal.textContent = "Connected";
      emailDot.className = "indicator-dot live";
    } else {
      emailVal.textContent = "Setup Needed";
      emailDot.className = "indicator-dot off";
    }
  } catch (err) {
    console.error("Failed to fetch ingest status:", err);
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
            <strong style="color:var(--accent-emerald);font-size:14px;">✓ Recorded</strong>: 
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

// Trigger Local SMS Sync
async function syncSMS() {
  showToast("Scanning local Messages database...");
  try {
    const res = await fetch("/api/ingest/sms/sync", { method: "POST" });
    const data = await res.json();
    showToast(data.message || `Found ${data.processed || 0} new transactions`);
    refreshAll();
  } catch (err) {
    showToast("Scan failed: " + err.message);
  }
}

// Modal Helpers
function openModal(id, targetTab) {
  document.getElementById(id).classList.remove("hidden");
}

function closeModal(id) {
  document.getElementById(id).classList.add("hidden");
}

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
