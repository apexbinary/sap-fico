/* Business One web client — vanilla JS single-page app on the /api REST endpoints. */
"use strict";

const API = "/api";
const state = { company: null, accounts: [], partners: [], lookups:{ currencies: [], tax_groups: [], payment_terms: [] } };
const today = () => new Date().toISOString().slice(0, 10);
const yearStart = () => `${new Date().getFullYear()}-01-01`;
const yearEnd = () => `${new Date().getFullYear()}-12-31`;

// ---------- helpers ----------
async function api(path, opts) {
  const res = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || res.statusText));
  return body;
}
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });
const patch = (path, body) => api(path, { method: "PATCH", body: JSON.stringify(body) });
const opt = (v, label, sel) => `<option value="${esc(v)}"${String(v) === String(sel) ? " selected" : ""}>${esc(label)}</option>`;
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const fmt = (n) => Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
const query = () => new URLSearchParams(location.hash.split("?")[1] || "");
function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast show " + kind;
  setTimeout(() => (t.className = "toast"), 3500);
}
async function act(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg, "good"); return r; }
  catch (e) { toast(e.message, "bad"); return null; }
}
const accountOptions = (filter = () => true) => state.accounts.filter((a) => a.postable === "Y" && filter(a))
  .map((a) => `<option value="${esc(a.acct_code)}">${esc(a.acct_code)} — ${esc(a.acct_name)}</option>`).join("");

// ---------- bootstrap ----------
async function boot() {
  try {
    const h = await fetch("/health").then((r) => r.json());
    $("#dbBadge").textContent = h.db;
  } catch (_) {}
  state.company = await api("/admin/company");
  $("#companyBadge").textContent = `${state.company.company_name} · ${state.company.main_curncy}`;
  await reloadMasterData();
  window.addEventListener("hashchange", route);
  $("#navToggle").onclick = () => $("#sidenav").classList.toggle("collapsed");
  if (!location.hash) location.hash = "#/cockpit";
  route();
}
async function reloadMasterData() {
  [state.accounts, state.lookups, state.partners] = await Promise.all([api("/accounts"), api("/admin/lookups"), api("/partners")]);
}

const views = {};
function route() {
  const view = (location.hash.replace("#/", "") || "cockpit").split("?")[0];
  const obj = query().get("obj");
  $$(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.obj ? a.dataset.obj === obj && view.startsWith("doc") : a.dataset.view === view));
  const c = $("#content");
  c.innerHTML = '<div class="loading">Loading…</div>';
  Promise.resolve((views[view] || views.cockpit)(c)).catch((e) => (c.innerHTML = `<div class="empty">Error: ${esc(e.message)}</div>`));
}

// ---------- Cockpit ----------
views.cockpit = async (c) => {
  const [pl, bs, jes] = await Promise.all([
    api(`/reports/profit-and-loss?date_from=${yearStart()}&date_to=${yearEnd()}`),
    api(`/reports/balance-sheet?as_of=${today()}`),
    api("/journal-entries?limit=8"),
  ]);
  const cash = state.accounts.filter((a) => a.cash).reduce((s, a) => s + Number(a.balance), 0);
  c.innerHTML = `
    <div class="page-head"><div><h1>Cockpit</h1><div class="sub">${esc(state.company.company_name)} · ${new Date().getFullYear()}</div></div></div>
    <div class="tiles">
      <div class="tile"><div class="label">Cash and bank</div><div class="value">${fmt(cash)}</div><div class="foot">${esc(state.company.main_curncy)}</div></div>
      <div class="tile"><div class="label">Total assets</div><div class="value">${fmt(bs.total_assets)}</div><div class="foot">as of today</div></div>
      <div class="tile"><div class="label">Gross profit</div><div class="value">${fmt(pl.gross_profit)}</div><div class="foot">this year</div></div>
      <div class="tile"><div class="label">Net profit</div><div class="value ${Number(pl.net_profit) >= 0 ? "good" : "bad"}">${fmt(pl.net_profit)}</div><div class="foot">this year</div></div>
    </div>
    <div class="card"><div class="card-head">Recent journal entries <a class="btn small secondary" href="#/journal-entry">New</a></div>
      ${jeTable(jes)}</div>`;
};

function jeTable(jes) {
  return `<table><thead><tr><th>No.</th><th>Posting date</th><th>Origin</th><th>Remarks</th><th class="num">Amount</th><th>Status</th></tr></thead>
    <tbody>${jes.map((e) => `<tr style="cursor:pointer" onclick="location.hash='#/journal?id=${e.trans_id}'">
      <td class="mono">${e.number}</td><td>${e.ref_date}</td><td>${docLink(e.trans_type, e.created_by, transTypeName(e.trans_type) + (e.base_ref ? ` ${e.base_ref}` : ""))}</td>
      <td>${esc(e.memo || "")}</td><td class="num">${fmt(e.loc_total)}</td>
      <td>${e.storno_to_tr ? `<span class="status X">${e.auto_storno ? "Reversal" : "Reversed"}</span>` : ""}</td></tr>`).join("")
      || `<tr><td colspan="6" class="empty">No journal entries yet.</td></tr>`}</tbody></table>`;
}
const TRANS_TYPES = { "30": "JE", "13": "IN", "14": "CN", "15": "DN", "16": "RE", "18": "PU", "19": "PC", "20": "PD",
  "21": "PR", "24": "RC", "46": "PS", "59": "SI", "60": "SO", "67": "IM", "23": "QT", "17": "OR", "22": "PO", "540000006": "PQ" };
const transTypeName = (t) => TRANS_TYPES[t] || t;
// origin of a journal entry -> the document that created it
const docLink = (type, entry, label) => (DOC_NAMES[type] && type !== "30" && entry
  ? `<a href="#/docs?obj=${type}&entry=${entry}" onclick="event.stopPropagation()">${esc(label)}</a>` : esc(label));
const DOC_NAMES = { "23": "Sales Quotation", "17": "Sales Order", "15": "Delivery", "16": "Return", "13": "A/R Invoice",
  "14": "A/R Credit Memo", "540000006": "Purchase Quotation", "22": "Purchase Order", "20": "Goods Receipt PO",
  "21": "Goods Return", "18": "A/P Invoice", "19": "A/P Credit Memo", "59": "Goods Receipt", "60": "Goods Issue",
  "67": "Inventory Transfer" };

// ---------- Chart of Accounts ----------
views.accounts = async (c) => {
  state.accounts = await api("/accounts");
  const byParent = {};
  state.accounts.forEach((a) => (byParent[a.father_num || "root"] ||= []).push(a));
  const rows = [];
  const walk = (parent, depth) => (byParent[parent] || []).forEach((a) => {
    rows.push(`<tr class="${a.postable === "N" ? "tree-title" : ""}"><td style="padding-left:${14 + depth * 22}px" class="mono">${esc(a.acct_code)}</td>
      <td>${esc(a.acct_name)}${a.control ? ' <span class="chip dr">control</span>' : ""}${a.cash ? ' <span class="chip ok">cash</span>' : ""}</td>
      <td>${a.postable === "Y" ? "Active" : "Title"}</td><td class="num">${a.postable === "Y" ? fmt(a.balance) : ""}</td></tr>`);
    walk(a.acct_code, depth + 1);
  });
  walk("root", 0);
  const titles = state.accounts.filter((a) => a.postable === "N");
  c.innerHTML = `
    <div class="page-head"><div><h1>Chart of Accounts</h1><div class="sub">Drawers, title accounts and active accounts (OACT)</div></div></div>
    <div class="card"><table><thead><tr><th>Account</th><th>Name</th><th>Type</th><th class="num">Balance</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>
    <div class="card"><div class="card-head">New G/L account</div><div class="card-body">
      <div class="form-grid">
        <div class="field"><label class="req">Under title account</label><select id="ac-parent">${titles.map((t) => `<option value="${esc(t.acct_code)}">${esc(t.acct_code)} — ${esc(t.acct_name)}</option>`).join("")}</select></div>
        <div class="field"><label class="req">Account code</label><input id="ac-code" maxlength="15"></div>
        <div class="field"><label class="req">Name</label><input id="ac-name" maxlength="100"></div>
        <div class="field"><label>Type</label><select id="ac-postable"><option value="1">Active account</option><option value="0">Title account</option></select></div>
      </div>
      <label style="display:inline-flex;gap:6px;margin-top:10px"><input type="checkbox" id="ac-control"> Control account</label>
      <label style="display:inline-flex;gap:6px;margin:10px 0 0 16px"><input type="checkbox" id="ac-cash"> Cash account</label>
      <div><button class="btn" id="ac-save" style="margin-top:12px">Add account</button></div>
    </div></div>`;
  $("#ac-save").onclick = async () => {
    const r = await act(() => post("/accounts", { father_num: $("#ac-parent").value, acct_code: $("#ac-code").value,
      acct_name: $("#ac-name").value, postable: $("#ac-postable").value === "1", control: $("#ac-control").checked,
      cash: $("#ac-cash").checked }), "Account created");
    if (r) { await reloadMasterData(); route(); }
  };
};

// ---------- Journal Entry ----------
views["journal-entry"] = async (c) => {
  c.innerHTML = `
    <div class="page-head"><div><h1>Journal Entry</h1><div class="sub">Manual journal entry (object 30) — G/L accounts and business partners (posted to their control account)</div></div></div>
    <div class="card"><div class="card-body"><div class="form-grid">
      <div class="field"><label class="req">Posting date</label><input id="je-date" type="date" value="${today()}"></div>
      <div class="field"><label>Document date</label><input id="je-tax" type="date" value="${today()}"></div>
      <div class="field"><label>Remarks</label><input id="je-memo" maxlength="50"></div>
      <div class="field"><label>Ref. 1</label><input id="je-ref1"></div>
      <div class="field"><label>Origin</label><input value="JE" readonly title="TransType — JE for manual entries"></div>
      <div class="field"><label>Origin No.</label><input readonly title="BaseRef — filled when the entry is added"></div>
      <div class="field"><label>Trans. No.</label><input readonly title="TransId — assigned when the entry is added"></div>
    </div></div></div>
    <div class="card"><div class="card-body">
      <table class="lines"><thead><tr><th>G/L account / BP code</th><th class="num w-amt">Debit</th><th class="num w-amt">Credit</th><th>Line remarks</th><th></th></tr></thead><tbody id="je-lines"></tbody></table>
      <button class="btn secondary small" id="je-add" style="margin-top:8px">+ Line</button>
      <div class="balance-row"><span>Debit <span class="amt" id="je-d">0.00</span></span><span>Credit <span class="amt" id="je-c">0.00</span></span><span id="je-chip" class="chip no">Not balanced</span></div>
      <button class="btn" id="je-post" disabled>Add</button>
    </div></div>`;
  const addLine = () => {
    const tr = document.createElement("tr");
    const bps = state.partners.filter((b) => b.card_type !== "L" && !b.frozen)
      .map((b) => `<option value="BP:${esc(b.card_code)}">${esc(b.card_code)} — ${esc(b.card_name)}</option>`).join("");
    tr.innerHTML = `<td><select class="je-acct"><optgroup label="G/L accounts">${accountOptions((a) => !a.control)}</optgroup>
      <optgroup label="Business partners">${bps}</optgroup></select></td>
      <td class="num"><input class="je-debit" type="number" step="0.01" min="0"></td><td class="num"><input class="je-credit" type="number" step="0.01" min="0"></td>
      <td><input class="je-lm" maxlength="50"></td><td><button class="btn ghost small je-del">✕</button></td>`;
    $("#je-lines").appendChild(tr);
    $$("input", tr).forEach((i) => (i.oninput = recalc));
    $(".je-del", tr).onclick = () => { tr.remove(); recalc(); };
  };
  const recalc = () => {
    let d = 0, cr = 0;
    $$("#je-lines tr").forEach((tr) => { d += Number($(".je-debit", tr).value || 0); cr += Number($(".je-credit", tr).value || 0); });
    $("#je-d").textContent = fmt(d); $("#je-c").textContent = fmt(cr);
    const ok = d > 0 && d.toFixed(2) === cr.toFixed(2);
    $("#je-chip").className = "chip " + (ok ? "ok" : "no"); $("#je-chip").textContent = ok ? "Balanced" : "Not balanced";
    $("#je-post").disabled = !ok;
  };
  $("#je-add").onclick = addLine;
  addLine(); addLine();
  $("#je-post").onclick = async () => {
    const target = (v) => (v.startsWith("BP:") ? { card_code: v.slice(3) } : { account: v });
    const lines = $$("#je-lines tr").map((tr) => ({ ...target($(".je-acct", tr).value), debit: $(".je-debit", tr).value || 0,
      credit: $(".je-credit", tr).value || 0, line_memo: $(".je-lm", tr).value || null }));
    const r = await act(() => post("/journal-entries", { ref_date: $("#je-date").value, tax_date: $("#je-tax").value,
      memo: $("#je-memo").value || null, ref1: $("#je-ref1").value || null, lines }), (e) => `Journal entry ${e.number} added`);
    if (r) { state.partners = await api("/partners"); location.hash = `#/journal?id=${r.trans_id}`; }
  };
};

// ---------- Journal Entries ----------
views.journal = async (c) => {
  const id = query().get("id");
  const jes = await api("/journal-entries?limit=100");
  c.innerHTML = `<div class="page-head"><div><h1>Journal Entries</h1><div class="sub">All postings (OJDT / JDT1)</div></div>
      <a class="btn" href="#/journal-entry">+ Journal Entry</a></div>
    <div class="card">${jeTable(jes)}</div><div id="je-detail"></div>`;
  if (!id) return;
  const e = await api(`/journal-entries/${id}`);
  const name = (code) => (state.accounts.find((a) => a.acct_code === code) || {}).acct_name || "";
  $("#je-detail").innerHTML = `<div class="card"><div class="card-head"><span>Journal entry ${e.number} · ${e.ref_date} · ${esc(transTypeName(e.trans_type))}
      ${e.storno_to_tr ? ` · ${e.auto_storno ? "reversal of" : "reversed by"} TransId ${e.storno_to_tr}` : ""}</span>
      ${e.storno_to_tr ? "" : `<button class="btn small secondary" id="je-rev">Reverse</button>`}</div>
    <div class="card-body"><div class="form-grid">
      ${[["Trans. No.", e.trans_id], ["Number", e.number], ["Origin", transTypeName(e.trans_type)], ["Origin No.", e.base_ref || e.number], ["Origin document", DOC_NAMES[e.trans_type] ? `${DOC_NAMES[e.trans_type]} ${e.base_ref}` : "Manual journal entry"],
         ["Posting date", e.ref_date], ["Due date", e.due_date], ["Document date", e.tax_date], ["Remarks", e.memo], ["Ref. 1", e.ref1], ["Ref. 2", e.ref2]]
        .map(([k, v]) => `<div class="field"><label>${k}</label><input value="${esc(v ?? "")}" readonly></div>`).join("")}
    </div></div>
    <table><thead><tr><th>#</th><th>G/L account / BP</th><th>Name</th><th>Contra account</th><th class="num">Debit</th><th class="num">Credit</th><th>Remarks</th></tr></thead>
    <tbody>${e.lines.map((l) => `<tr><td>${l.line_id + 1}</td><td class="mono">${esc(l.short_name)}${l.short_name !== l.account ? ` <span class="help">(${esc(l.account)})</span>` : ""}</td>
      <td>${esc(name(l.account))}</td><td class="mono help">${esc(l.contra_act || "")}</td>
      <td class="num">${Number(l.debit) ? fmt(l.debit) : ""}</td><td class="num">${Number(l.credit) ? fmt(l.credit) : ""}</td><td>${esc(l.line_memo || "")}</td></tr>`).join("")}</tbody></table></div>`;
  const rev = $("#je-rev");
  if (rev) rev.onclick = async () => {
    if (!confirm(`Reverse journal entry ${e.number}?`)) return;
    const r = await act(() => post(`/journal-entries/${e.trans_id}/reverse`, {}), (x) => `Reversed by journal entry ${x.number}`);
    if (r) location.hash = `#/journal?id=${r.trans_id}`;
  };
};

// ---------- Business Partner Master Data ----------
const CARD_TYPES = { C: "Customer", S: "Vendor", L: "Lead" };
views.partners = async (c) => {
  const code = query().get("code"), type = query().get("type") || "";
  const [list, groups, plists] = await Promise.all([api(`/partners${type ? `?card_type=${type}` : ""}`), api("/partner-groups"), api("/price-lists")]);
  const L = state.lookups;
  c.innerHTML = `<div class="page-head"><div><h1>Business Partner Master Data</h1><div class="sub">Customers, vendors and leads (OCRD)</div></div>
      <button class="btn" id="bp-new-btn">+ New business partner</button></div>
    <div class="toolbar"><div class="field"><label>Type</label><select id="bp-filter">${opt("", "All", type)}${Object.entries(CARD_TYPES).map(([k, v]) => opt(k, v, type)).join("")}</select></div></div>
    <div class="card"><table><thead><tr><th>BP code</th><th>Name</th><th>Type</th><th>Group</th><th>City</th><th>Control account</th><th class="num">Account balance</th><th>Status</th></tr></thead>
      <tbody>${list.map((b) => `<tr style="cursor:pointer" onclick="location.hash='#/partners?code=${encodeURIComponent(b.card_code)}'">
        <td class="mono">${esc(b.card_code)}</td><td>${esc(b.card_name)}</td><td>${CARD_TYPES[b.card_type]}</td>
        <td>${esc((groups.find((g) => g.group_code === b.group_code) || {}).group_name || "")}</td><td>${esc(b.city || "")}</td>
        <td class="mono">${esc(b.deb_pay_acct)}</td><td class="num">${fmt(b.balance)}</td>
        <td>${b.frozen ? '<span class="status X">Inactive</span>' : '<span class="status O">Active</span>'}</td></tr>`).join("")
        || `<tr><td colspan="8" class="empty">No business partners.</td></tr>`}</tbody></table></div>
    <div id="bp-detail"></div>
    <div class="card" id="bp-new" style="display:none"><div class="card-head">New business partner</div><div class="card-body">
      <div class="form-grid">
        <div class="field"><label class="req">BP code</label><input id="bp-code" maxlength="15"></div>
        <div class="field"><label class="req">Name</label><input id="bp-name" maxlength="100"></div>
        <div class="field"><label class="req">Type</label><select id="bp-type">${Object.entries(CARD_TYPES).map(([k, v]) => opt(k, v)).join("")}</select></div>
        <div class="field"><label>Group</label><select id="bp-group"></select></div>
        <div class="field"><label>Currency</label><select id="bp-cur">${opt("##", "All currencies")}${L.currencies.map((x) => opt(x.code, x.code)).join("")}</select></div>
        <div class="field"><label>Payment terms</label><select id="bp-terms">${L.payment_terms.map((p) => opt(p.group_num, p.name, 1)).join("")}</select></div>
        <div class="field"><label>Price list</label><select id="bp-plist">${plists.map((p) => opt(p.list_num, p.list_name)).join("")}</select></div>
        <div class="field"><label>Tax group</label><select id="bp-vat"></select></div>
        <div class="field"><label>Control account</label><select id="bp-ctrl">${accountOptions((a) => a.control)}</select></div>
        <div class="field"><label>Federal tax ID</label><input id="bp-tax" maxlength="32"></div>
        <div class="field"><label>Phone</label><input id="bp-phone" maxlength="20"></div>
        <div class="field"><label>E-mail</label><input id="bp-mail" maxlength="100"></div>
        <div class="field"><label>Street</label><input id="bp-street" maxlength="100"></div>
        <div class="field"><label>Zip code</label><input id="bp-zip" maxlength="20"></div>
        <div class="field"><label>City</label><input id="bp-city" maxlength="100"></div>
        <div class="field"><label>Credit limit</label><input id="bp-credit" type="number" step="0.01" min="0" value="0"></div>
      </div>
      <button class="btn" id="bp-save" style="margin-top:12px">Add</button></div></div>`;
  $("#bp-filter").onchange = (e) => (location.hash = `#/partners${e.target.value ? `?type=${e.target.value}` : ""}`);
  const syncType = () => {
    const vendor = $("#bp-type").value === "S";
    $("#bp-group").innerHTML = groups.filter((g) => g.group_type === (vendor ? "S" : "C")).map((g) => opt(g.group_code, g.group_name)).join("");
    $("#bp-vat").innerHTML = L.tax_groups.filter((x) => x.category === (vendor ? "I" : "O")).map((x) => opt(x.code, `${x.code} — ${x.name}`)).join("");
    $("#bp-plist").value = (vendor ? plists.find((p) => /purchase/i.test(p.list_name)) || plists[0] : plists[0]).list_num;
    $("#bp-ctrl").value = vendor ? "211000" : "114000";
  };
  $("#bp-type").onchange = syncType; syncType();
  $("#bp-new-btn").onclick = () => { $("#bp-new").style.display = ""; $("#bp-code").focus(); };
  $("#bp-save").onclick = async () => {
    const v = (id) => $(id).value || null;
    const r = await act(() => post("/partners", { card_code: $("#bp-code").value, card_name: $("#bp-name").value, card_type: $("#bp-type").value,
      group_code: Number(v("#bp-group")) || null, currency: $("#bp-cur").value, group_num: Number($("#bp-terms").value),
      list_num: Number($("#bp-plist").value), vat_group: v("#bp-vat"), deb_pay_acct: v("#bp-ctrl"), lic_trad_num: v("#bp-tax"),
      phone1: v("#bp-phone"), e_mail: v("#bp-mail"), address: v("#bp-street"), zip_code: v("#bp-zip"), city: v("#bp-city"),
      credit_line: $("#bp-credit").value || 0 }), (b) => `Business partner ${b.card_code} added`);
    if (r) { state.partners = await api("/partners"); location.hash = `#/partners?code=${encodeURIComponent(r.card_code)}`; }
  };
  if (!code) return;

  const b = await api(`/partners/${encodeURIComponent(code)}`);
  const terms = (L.payment_terms.find((p) => p.group_num === b.group_num) || {}).name || "";
  const plist = (plists.find((p) => p.list_num === b.list_num) || {}).list_name || "";
  const kv = (rows) => rows.map(([k, x]) => `<tr><td class="help">${k}</td><td>${esc(x || "")}</td></tr>`).join("");
  $("#bp-detail").innerHTML = `<div class="card"><div class="card-head"><span>${CARD_TYPES[b.card_type]} ${esc(b.card_code)} — ${esc(b.card_name)}</span>
      <button class="btn small secondary" id="bp-freeze">${b.frozen ? "Activate" : "Set inactive"}</button></div>
    <div class="grid-2"><table><tbody>${kv([["Control account", b.deb_pay_acct], ["Currency", b.currency === "##" ? "All currencies" : b.currency],
      ["Payment terms", terms], ["Price list", plist], ["Tax group", b.vat_group], ["Federal tax ID", b.lic_trad_num], ["Credit limit", fmt(b.credit_line)]])}</tbody></table>
    <table><tbody>${kv([["Address", [b.address, [b.zip_code, b.city].filter(Boolean).join(" "), b.country].filter(Boolean).join(", ")], ["Phone", b.phone1],
      ["E-mail", b.e_mail], ["Contact person", b.cntct_prsn], ["Account balance", fmt(b.balance)], ["Open deliveries", fmt(b.dnotes_bal)],
      ["Open orders", fmt(b.orders_bal)]])}</tbody></table></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Contact persons (OCPR)</div><table><thead><tr><th>Name</th><th>Position</th><th>Phone</th><th>E-mail</th></tr></thead><tbody>
        ${b.contacts.map((p) => `<tr><td>${esc(p.name)}</td><td>${esc(p.position || "")}</td><td>${esc(p.tel1 || "")}</td><td>${esc(p.e_mail || "")}</td></tr>`).join("")
          || `<tr><td colspan="4" class="empty">No contact persons.</td></tr>`}</tbody></table>
        <div class="card-body"><div class="toolbar" style="margin:0"><div class="field"><label>Name</label><input id="cp-name" maxlength="50"></div>
          <div class="field"><label>Position</label><input id="cp-pos" maxlength="90"></div><div class="field"><label>Phone</label><input id="cp-tel" maxlength="20"></div>
          <button class="btn secondary" id="cp-add">Add</button></div></div></div>
      <div class="card"><div class="card-head">Open items</div><table><thead><tr><th>Origin</th><th>Posting date</th><th>Due date</th><th>Remarks</th><th class="num">Open</th></tr></thead><tbody>
        ${b.open_items.map((o) => `<tr style="cursor:pointer" onclick="location.hash='#/journal?id=${o.trans_id}'"><td>${esc(transTypeName(o.trans_type))} ${o.trans_id}</td>
          <td>${o.ref_date}</td><td>${o.due_date}</td><td>${esc(o.line_memo || "")}</td><td class="num">${fmt(o.open)}</td></tr>`).join("")
          || `<tr><td colspan="5" class="empty">No open items.</td></tr>`}</tbody></table></div></div>`;
  $("#bp-freeze").onclick = async () => {
    if (await act(() => patch(`/partners/${encodeURIComponent(b.card_code)}`, { frozen: !b.frozen }), "Business partner updated")) {
      state.partners = await api("/partners"); route();
    }
  };
  $("#cp-add").onclick = async () => {
    if (await act(() => post(`/partners/${encodeURIComponent(b.card_code)}/contacts`, { name: $("#cp-name").value,
      position: $("#cp-pos").value || null, tel1: $("#cp-tel").value || null }), "Contact person added")) route();
  };
};

// ---------- Item Master Data ----------
views.items = async (c) => {
  const code = query().get("code");
  const [list, groups, whs, plists] = await Promise.all([api("/items"), api("/item-groups"), api("/warehouses"), api("/price-lists")]);
  const L = state.lookups;
  const yes = (b) => (b ? "&#10003;" : "");
  const qty = (i, n) => (i.invnt_item ? Number(n) : "");
  c.innerHTML = `<div class="page-head"><div><h1>Item Master Data</h1><div class="sub">Items (OITM) valued at moving average; G/L accounts by item group</div></div>
      <button class="btn" id="it-new-btn">+ New item</button></div>
    <div class="card"><table><thead><tr><th>Item No.</th><th>Description</th><th>Group</th><th>Inv.</th><th>Sales</th><th>Purch.</th><th class="num">In stock</th>
      <th class="num">Committed</th><th class="num">Ordered</th><th class="num">Available</th><th class="num">Item cost</th></tr></thead>
      <tbody>${list.map((i) => `<tr style="cursor:pointer" onclick="location.hash='#/items?code=${encodeURIComponent(i.item_code)}'">
        <td class="mono">${esc(i.item_code)}</td><td>${esc(i.item_name)}</td><td>${esc((groups.find((g) => g.itms_grp_cod === i.itms_grp_cod) || {}).itms_grp_nam || "")}</td>
        <td>${yes(i.invnt_item)}</td><td>${yes(i.sell_item)}</td><td>${yes(i.prchse_item)}</td>
        <td class="num">${qty(i, i.on_hand)}</td><td class="num">${qty(i, i.is_commited)}</td><td class="num">${qty(i, i.on_order)}</td>
        <td class="num">${qty(i, i.available)}</td><td class="num">${i.invnt_item ? fmt(i.avg_price) : ""}</td></tr>`).join("")
        || `<tr><td colspan="11" class="empty">No items.</td></tr>`}</tbody></table></div>
    <div id="it-detail"></div>
    <div class="card" id="it-new" style="display:none"><div class="card-head">New item</div><div class="card-body">
      <div class="form-grid">
        <div class="field"><label class="req">Item No.</label><input id="it-code" maxlength="50"></div>
        <div class="field"><label class="req">Description</label><input id="it-name" maxlength="100"></div>
        <div class="field"><label class="req">Item group</label><select id="it-group">${groups.map((g) => opt(g.itms_grp_cod, g.itms_grp_nam)).join("")}</select></div>
        <div class="field"><label>Inventory unit</label><input id="it-uom" maxlength="20" value="Each"></div>
        <div class="field"><label>Sales tax group</label><select id="it-vsa">${L.tax_groups.filter((x) => x.category === "O").map((x) => opt(x.code, `${x.code} — ${x.name}`)).join("")}</select></div>
        <div class="field"><label>Purchase tax group</label><select id="it-vpu">${L.tax_groups.filter((x) => x.category === "I").map((x) => opt(x.code, `${x.code} — ${x.name}`)).join("")}</select></div>
        <div class="field"><label>Default warehouse</label><select id="it-wh">${whs.map((w) => opt(w.whs_code, `${w.whs_code} — ${w.whs_name}`)).join("")}</select></div>
        <div class="field"><label>Preferred vendor</label><select id="it-vendor">${opt("", "—")}${state.partners.filter((b) => b.card_type === "S").map((b) => opt(b.card_code, `${b.card_code} — ${b.card_name}`)).join("")}</select></div>
        <div class="field"><label>Minimum stock</label><input id="it-min" type="number" step="1" min="0" value="0"></div>
        ${plists.filter((p) => p.base_num === p.list_num).map((p) => `<div class="field"><label>${esc(p.list_name)}</label><input class="it-price" data-list="${p.list_num}" type="number" step="0.01" min="0"></div>`).join("")}
      </div>
      <label style="display:inline-flex;gap:6px;margin-top:10px"><input type="checkbox" id="it-inv" checked> Inventory item</label>
      <label style="display:inline-flex;gap:6px;margin:10px 0 0 16px"><input type="checkbox" id="it-sell" checked> Sales item</label>
      <label style="display:inline-flex;gap:6px;margin:10px 0 0 16px"><input type="checkbox" id="it-buy" checked> Purchase item</label>
      <div><button class="btn" id="it-save" style="margin-top:12px">Add</button></div></div></div>`;
  $("#it-new-btn").onclick = () => { $("#it-new").style.display = ""; $("#it-code").focus(); };
  $("#it-save").onclick = async () => {
    const prices = {};
    $$(".it-price").forEach((i) => { if (i.value !== "") prices[i.dataset.list] = i.value; });
    const r = await act(() => post("/items", { item_code: $("#it-code").value, item_name: $("#it-name").value, itms_grp_cod: Number($("#it-group").value),
      invnt_item: $("#it-inv").checked, sell_item: $("#it-sell").checked, prchse_item: $("#it-buy").checked, invntry_uom: $("#it-uom").value || null,
      vat_gourp_sa: $("#it-vsa").value, vat_group_pu: $("#it-vpu").value, dflt_wh: $("#it-inv").checked ? $("#it-wh").value : null,
      card_code: $("#it-vendor").value || null, min_level: $("#it-min").value || 0, prices }), (i) => `Item ${i.item_code} added`);
    if (r) location.hash = `#/items?code=${encodeURIComponent(r.item_code)}`;
  };
  if (!code) return;

  const i = await api(`/items/${encodeURIComponent(code)}`);
  const g = groups.find((x) => x.itms_grp_cod === i.itms_grp_cod) || {};
  const kv = (rows, cls = "") => rows.map(([k, x]) => `<tr><td class="help">${k}</td><td class="${cls}">${esc(x || "")}</td></tr>`).join("");
  $("#it-detail").innerHTML = `<div class="card"><div class="card-head">${esc(i.item_code)} — ${esc(i.item_name)}</div>
    <div class="grid-2"><table><tbody>${kv([["Item group", g.itms_grp_nam], ["Inventory unit", i.invntry_uom],
      ["Sales / purchase tax", `${i.vat_gourp_sa || ""} / ${i.vat_group_pu || ""}`], ["Default warehouse", i.dflt_wh], ["Preferred vendor", i.card_code],
      ["Valuation", "Moving average"], ["Item cost", fmt(i.avg_price)], ["Last purchase price", fmt(i.last_pur_prc)]])}</tbody></table>
    <table><tbody>${kv([["Inventory account", g.bal_invnt_ac], ["Cost of goods sold", g.sale_cost_ac], ["Revenue account", g.revenues_ac],
      ["Expense account", g.expenses_ac], ["Price difference", g.price_dif_ac]], "mono")}</tbody></table></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Stock per warehouse (OITW)</div><table><thead><tr><th>Warehouse</th><th class="num">In stock</th><th class="num">Committed</th><th class="num">Ordered</th><th class="num">Available</th></tr></thead><tbody>
        ${i.warehouses.map((w) => `<tr><td>${esc(w.whs_code)} — ${esc((whs.find((x) => x.whs_code === w.whs_code) || {}).whs_name || "")}</td>
          <td class="num">${Number(w.on_hand)}</td><td class="num">${Number(w.is_commited)}</td><td class="num">${Number(w.on_order)}</td><td class="num">${Number(w.available)}</td></tr>`).join("")
          || `<tr><td colspan="5" class="empty">Not an inventory item.</td></tr>`}</tbody></table></div>
      <div class="card"><div class="card-head">Prices (ITM1)</div><table><thead><tr><th>Price list</th><th class="num">Price</th><th></th></tr></thead><tbody>
        ${i.prices.map((p) => `<tr><td>${esc(p.list_name)}${p.own ? "" : ' <span class="help">(from base list)</span>'}</td>
          <td class="num"><input class="pr-val" data-list="${p.list_num}" type="number" step="0.01" min="0" value="${Number(p.price).toFixed(2)}" style="width:110px;text-align:right"></td>
          <td><button class="btn small ghost pr-save" data-list="${p.list_num}">Save</button></td></tr>`).join("")}</tbody></table></div></div>`;
  $$(".pr-save").forEach((btn) => (btn.onclick = async () => {
    const val = $(`.pr-val[data-list="${btn.dataset.list}"]`).value;
    if (await act(() => api(`/items/${encodeURIComponent(i.item_code)}/prices/${btn.dataset.list}`, { method: "PUT", body: JSON.stringify({ price: val }) }), "Price saved")) route();
  }));
};

// ---------- Warehouses & Price Lists ----------
views.warehouses = async (c) => {
  const [whs, plists] = await Promise.all([api("/warehouses"), api("/price-lists")]);
  c.innerHTML = `<div class="page-head"><div><h1>Warehouses &amp; Price Lists</h1><div class="sub">Warehouses (OWHS) and price lists (OPLN)</div></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Warehouses</div><table><thead><tr><th>Code</th><th>Name</th><th>Street</th><th>City</th></tr></thead><tbody>
        ${whs.map((w) => `<tr><td class="mono">${esc(w.whs_code)}</td><td>${esc(w.whs_name)}</td><td>${esc(w.street || "")}</td><td>${esc(w.city || "")}</td></tr>`).join("")}</tbody></table>
        <div class="card-body"><div class="toolbar" style="margin:0"><div class="field"><label>Code</label><input id="wh-code" maxlength="8" style="width:80px"></div>
          <div class="field"><label>Name</label><input id="wh-name" maxlength="100"></div><div class="field"><label>City</label><input id="wh-city" maxlength="100"></div>
          <button class="btn secondary" id="wh-add">Add</button></div></div></div>
      <div class="card"><div class="card-head">Price lists</div><table><thead><tr><th>No.</th><th>Name</th><th>Base price list</th><th class="num">Factor</th></tr></thead><tbody>
        ${plists.map((p) => `<tr><td>${p.list_num}</td><td>${esc(p.list_name)}</td>
          <td>${p.base_num === p.list_num ? '<span class="help">own prices</span>' : esc((plists.find((x) => x.list_num === p.base_num) || {}).list_name || "")}</td>
          <td class="num">${Number(p.factor)}</td></tr>`).join("")}</tbody></table></div>
    </div>`;
  $("#wh-add").onclick = async () => {
    if (await act(() => post("/warehouses", { whs_code: $("#wh-code").value, whs_name: $("#wh-name").value, city: $("#wh-city").value || null }), "Warehouse added")) route();
  };
};

// ---------- Marketing and inventory documents ----------
let DOC_TYPES = null;
async function docTypes() {
  if (!DOC_TYPES) DOC_TYPES = Object.fromEntries((await api("/documents/types")).map((t) => [t.obj, t]));
  return DOC_TYPES;
}
const STATUS = (d) => (d.canceled ? '<span class="status X">Canceled</span>'
  : d.doc_status === "O" ? '<span class="status O">Open</span>' : '<span class="status C">Closed</span>');
const qtyFmt = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 3 });

views.docs = async (c) => {
  const obj = query().get("obj") || "13", entry = query().get("entry");
  const t = (await docTypes())[obj];
  const list = await api(`/documents/${obj}?limit=100`);
  const bp = t.side !== "I";
  c.innerHTML = `<div class="page-head"><div><h1>${esc(t.name)}</h1><div class="sub">${t.side === "S" ? "Sales — A/R" : t.side === "P" ? "Purchasing — A/P" : "Inventory"}
      ${t.bases.length ? ` · copy from ${t.bases.map((b) => esc(DOC_NAMES[b])).join(", ")}` : ""}</div></div>
      <a class="btn" href="#/doc?obj=${obj}">+ New ${esc(t.name)}</a></div>
    <div class="card"><table><thead><tr><th>No.</th><th>Posting date</th>${bp ? "<th>BP code</th><th>BP name</th>" : "<th>Remarks</th>"}
      ${t.side === "I" ? "" : "<th>Due date</th>"}<th class="num">Total</th>${t.kind === "invoice" || t.kind === "credit" ? '<th class="num">Paid / applied</th>' : ""}<th>Status</th></tr></thead>
      <tbody>${list.map((d) => `<tr style="cursor:pointer" onclick="location.hash='#/docs?obj=${obj}&entry=${d.doc_entry}'">
        <td class="mono">${d.doc_num}</td><td>${d.doc_date}</td>${bp ? `<td class="mono">${esc(d.card_code)}</td><td>${esc(d.card_name)}</td>` : `<td>${esc(d.comments || "")}</td>`}
        ${t.side === "I" ? "" : `<td>${d.doc_due_date}</td>`}<td class="num">${fmt(d.doc_total)}</td>
        ${t.kind === "invoice" || t.kind === "credit" ? `<td class="num">${fmt(d.paid_to_date)}</td>` : ""}<td>${STATUS(d)}</td></tr>`).join("")
        || `<tr><td colspan="8" class="empty">No documents yet.</td></tr>`}</tbody></table></div><div id="doc-detail"></div>`;
  if (entry) await docDetail($("#doc-detail"), t, entry);
};

async function docDetail(el, t, entry) {
  const d = await api(`/documents/${t.obj}/${entry}`);
  const types = await docTypes();
  const open = d.doc_status === "O" && !d.canceled;
  const targets = open || t.kind === "invoice" ? t.targets.filter((x) => !d.canceled && d.lines.some((l) => Number(l.open_qty) > 0)) : [];
  const item = t.side !== "I" && d.doc_type === "I";
  el.innerHTML = `<div class="card"><div class="card-head"><span>${esc(t.name)} ${d.doc_num} ${STATUS(d)}</span><span style="display:flex;gap:6px">
      ${targets.map((x) => `<a class="btn small" href="#/doc?obj=${x}&from=${t.obj}:${d.doc_entry}">Copy to ${esc(types[x].name)}</a>`).join("")}
      ${open && ["quotation", "order"].includes(t.kind) ? '<button class="btn small secondary" id="doc-close">Close</button>' : ""}
      ${!d.canceled ? '<button class="btn small secondary" id="doc-cancel">Cancel</button>' : ""}</span></div>
    <div class="card-body"><div class="form-grid">
      ${[...(t.side !== "I" ? [["Business partner", `${d.card_code} — ${d.card_name}`], ["BP ref. no.", d.num_at_card]] : []),
         ["Posting date", d.doc_date], [t.side === "I" ? "Document date" : t.kind === "invoice" || t.kind === "credit" ? "Due date" : "Delivery date", t.side === "I" ? d.tax_date : d.doc_due_date],
         ...(t.side !== "I" ? [["Document date", d.tax_date], ["Type", d.doc_type === "S" ? "Service" : "Item"]] : []),
         ...(t.kind === "transfer" ? [["From warehouse", d.filler], ["To warehouse", d.to_whs_code]] : []), ["Remarks", d.comments]]
        .map(([k, v]) => `<div class="field"><label>${k}</label><input value="${esc(v ?? "")}" readonly></div>`).join("")}
      ${d.trans_id ? `<div class="field"><label>Journal entry</label><a class="btn small ghost" href="#/journal?id=${d.trans_id}">Trans. No. ${d.trans_id} &#8599;</a></div>` : ""}
    </div></div>
    <table><thead><tr><th>#</th><th>${d.doc_type === "S" ? "Description" : "Item"}</th>${d.doc_type === "S" ? "<th>G/L account</th>" : "<th>Description</th><th class=\"num\">Qty</th>"}
      ${t.side !== "I" && d.doc_type === "I" ? '<th class="num">Open</th>' : ""}${t.kind === "transfer" ? "<th>From</th>" : ""}${d.doc_type === "I" ? "<th>Whs</th>" : ""}
      <th class="num">Price</th>${t.side !== "I" ? '<th class="num">Disc. %</th><th>Tax</th>' : ""}<th class="num">Total</th>${item || t.side === "I" ? '<th class="num">Item cost</th>' : ""}<th>Base</th><th></th></tr></thead>
    <tbody>${d.lines.map((l) => `<tr><td>${l.line_num + 1}</td>
      ${d.doc_type === "S" ? `<td>${esc(l.dscription)}</td><td class="mono">${esc(l.acct_code)}</td>` : `<td class="mono">${esc(l.item_code)}</td><td>${esc(l.dscription)}</td><td class="num">${qtyFmt(l.quantity)}</td>`}
      ${t.side !== "I" && d.doc_type === "I" ? `<td class="num">${qtyFmt(l.open_qty)}</td>` : ""}${t.kind === "transfer" ? `<td>${esc(l.from_whs_cod)}</td>` : ""}${d.doc_type === "I" ? `<td>${esc(l.whs_code || "")}</td>` : ""}
      <td class="num">${fmt(t.side === "I" ? l.stock_price : l.price_bef_di)}</td>${t.side !== "I" ? `<td class="num">${Number(l.disc_prcnt) ? Number(l.disc_prcnt) : ""}</td><td>${esc(l.vat_group || "")}</td>` : ""}
      <td class="num">${fmt(l.line_total)}</td>${item || t.side === "I" ? `<td class="num">${Number(l.stock_price) ? fmt(l.stock_price) : ""}</td>` : ""}
      <td>${l.base_type ? `<a href="#/docs?obj=${l.base_type}&entry=${l.base_entry}">${esc(transTypeName(l.base_type))} ${esc(l.base_ref)}</a>` : ""}</td>
      <td>${l.line_status === "C" && !d.canceled && t.side !== "I" ? '<span class="help">closed</span>' : ""}</td></tr>`).join("")}</tbody></table>
    ${t.side !== "I" ? `<div class="card-body"><div class="totals">
      <div><span>Total before discount</span><b>${fmt(d.lines.reduce((s, l) => s + Number(l.line_total), 0))}</b></div>
      <div><span>Discount ${Number(d.disc_prcnt) ? `${Number(d.disc_prcnt)} %` : ""}</span><b>${fmt(d.disc_sum)}</b></div>
      <div><span>Tax</span><b>${fmt(d.vat_sum)}</b></div><div class="grand"><span>Total</span><b>${fmt(d.doc_total)} ${esc(d.doc_cur)}</b></div>
      ${t.kind === "invoice" || t.kind === "credit" ? `<div><span>Paid / applied</span><b>${fmt(d.paid_to_date)}</b></div><div><span>Balance due</span><b>${fmt(d.doc_total - d.paid_to_date)}</b></div>` : ""}
    </div></div>` : `<div class="card-body"><div class="totals"><div class="grand"><span>Total value</span><b>${fmt(d.doc_total)}</b></div></div></div>`}</div>`;
  const reload = () => { location.hash = `#/docs?obj=${t.obj}&entry=${d.doc_entry}&r=${Date.now()}`; };
  const cl = $("#doc-close");
  if (cl) cl.onclick = async () => { if (await act(() => post(`/documents/${t.obj}/${d.doc_entry}/close`, {}), "Document closed")) reload(); };
  const cn = $("#doc-cancel");
  if (cn) cn.onclick = async () => {
    if (!confirm(`Cancel ${t.name} ${d.doc_num}? Stock and journal entry are reversed.`)) return;
    if (await act(() => post(`/documents/${t.obj}/${d.doc_entry}/cancel`, {}), "Document canceled")) { state.partners = await api("/partners"); reload(); }
  };
}

views.doc = async (c) => {
  const obj = query().get("obj") || "13", from = query().get("from");
  const t = (await docTypes())[obj];
  const [items, whs] = await Promise.all([api("/items"), api("/warehouses")]);
  const L = state.lookups, side = t.side;
  const taxes = L.tax_groups.filter((x) => x.category === (side === "S" ? "O" : "I"));
  const rate = (code) => Number((L.tax_groups.find((x) => x.code === code) || {}).rate || 0);
  const partners = state.partners.filter((b) => !b.frozen && (side === "S" ? (b.card_type === "C" || (b.card_type === "L" && t.kind === "quotation")) : b.card_type === "S"));
  const serviceOk = side !== "I" && !["delivery", "return"].includes(t.kind);
  const sellable = items.filter((i) => !i.frozen && (side === "S" ? i.sell_item : side === "P" ? i.prchse_item : i.invnt_item) && (["delivery", "return"].includes(t.kind) ? i.invnt_item : true));
  const whsOpts = (sel) => whs.map((w) => opt(w.whs_code, w.whs_code, sel)).join("");
  c.innerHTML = `<div class="page-head"><div><h1>${esc(t.name)}</h1><div class="sub">New document${t.bases.length ? ` · copy from ${t.bases.map((b) => esc(DOC_NAMES[b])).join(", ")}` : ""}</div></div>
      <a class="btn secondary" href="#/docs?obj=${obj}">Back to list</a></div>
    <div class="card"><div class="card-body"><div class="form-grid">
      ${side !== "I" ? `<div class="field"><label class="req">${side === "S" ? "Customer" : "Vendor"}</label><select id="d-bp">${opt("", "— select —")}${partners.map((b) => opt(b.card_code, `${b.card_code} — ${b.card_name}`)).join("")}</select></div>
        <div class="field"><label>BP ref. no.</label><input id="d-ref" maxlength="100"></div>` : ""}
      <div class="field"><label class="req">Posting date</label><input id="d-date" type="date" value="${today()}"></div>
      ${side !== "I" ? `<div class="field"><label>${t.kind === "invoice" || t.kind === "credit" ? "Due date" : "Delivery date"}</label><input id="d-due" type="date"></div>
        <div class="field"><label>Document date</label><input id="d-tax" type="date" value="${today()}"></div>` : ""}
      ${serviceOk ? `<div class="field"><label>Item / service type</label><select id="d-type">${opt("I", "Item")}${opt("S", "Service")}</select></div>` : ""}
      ${t.kind === "transfer" ? `<div class="field"><label class="req">From warehouse</label><select id="d-from">${whsOpts("01")}</select></div>
        <div class="field"><label class="req">To warehouse</label><select id="d-to">${whsOpts("02")}</select></div>` : ""}
      <div class="field" style="grid-column:span 2"><label>Remarks</label><input id="d-comments" maxlength="254"></div>
    </div></div></div>
    <div class="card"><div class="card-body">
      <table class="lines"><thead id="d-head"></thead><tbody id="d-lines"></tbody></table>
      <div style="display:flex;gap:8px;margin-top:8px"><button class="btn secondary small" id="d-add">+ Line</button>
        ${t.bases.length ? '<button class="btn secondary small" id="d-copy">Copy From…</button>' : ""}</div>
      <div id="d-sources"></div>
      ${side !== "I" ? `<div class="totals" style="margin-top:12px">
        <div><span>Total before discount</span><b id="t-before">0.00</b></div>
        <div><span>Discount %</span><input id="d-disc" type="number" min="0" max="99.99" step="0.01" value="0" style="width:80px;text-align:right"></div>
        <div><span>Tax</span><b id="t-vat">0.00</b></div><div class="grand"><span>Total</span><b id="t-total">0.00</b></div></div>` : ""}
      <button class="btn" id="d-post" style="margin-top:12px">Add</button>
    </div></div>`;

  const type = () => ($("#d-type") ? $("#d-type").value : "I");
  const head = () => {
    $("#d-head").innerHTML = type() === "S"
      ? `<tr><th>Description</th><th>G/L account</th><th>Tax</th><th class="num w-amt">Amount</th><th class="num">Total</th><th>Base</th><th></th></tr>`
      : `<tr><th>Item</th><th class="num">Qty</th>${t.kind === "transfer" ? "<th>From</th><th>To</th>" : "<th>Whs</th>"}
         ${t.kind === "issue" || t.kind === "transfer" ? "" : `<th class="num w-amt">${t.kind === "receipt" ? "Unit cost" : "Unit price"}</th>`}
         ${side !== "I" ? '<th class="num">Disc. %</th><th>Tax</th><th class="num">Total</th>' : ""}<th>Base</th><th></th></tr>`;
  };
  const addLine = (v = {}) => {
    const tr = document.createElement("tr");
    // tax group default: base line, else the business partner's (items override it with their own)
    v = { ...v, vat_group: v.vat_group || ((state.partners.find((b) => b.card_code === ($("#d-bp") || {}).value) || {}).vat_group) };
    tr.base = v.base_type ? { base_type: v.base_type, base_entry: v.base_entry, base_line: v.base_line } : null;
    const lock = tr.base ? "disabled" : "";
    const baseCell = `<td class="help">${tr.base ? `${esc(transTypeName(v.base_type))} ${esc(v.base_ref)}` : ""}</td><td><button class="btn ghost small l-del">✕</button></td>`;
    if (type() === "S") {
      tr.innerHTML = `<td><input class="l-desc" maxlength="100" value="${esc(v.dscription || "")}"></td>
        <td><select class="l-acct" ${lock}>${accountOptions((a) => !a.control).replace(`value="${esc(v.acct_code)}"`, `value="${esc(v.acct_code)}" selected`)}</select></td>
        <td><select class="l-vat">${taxes.map((x) => opt(x.code, x.code, v.vat_group)).join("")}</select></td>
        <td class="num"><input class="l-price" type="number" step="0.01" min="0" value="${v.price ?? ""}"></td><td class="num l-total">0.00</td>${baseCell}`;
    } else {
      const it = items.find((i) => i.item_code === v.item_code);
      tr.innerHTML = `<td><select class="l-item" ${lock}>${opt("", "— item —")}${sellable.map((i) => opt(i.item_code, `${i.item_code} — ${i.item_name}`, v.item_code)).join("")}</select></td>
        <td class="num"><input class="l-qty" type="number" step="1" min="0" value="${v.quantity ?? 1}" style="width:80px">${tr.base ? `<div class="help">open ${qtyFmt(v.quantity)}</div>` : ""}</td>
        ${t.kind === "transfer" ? `<td><select class="l-from">${whsOpts($("#d-from").value)}</select></td><td><select class="l-whs">${whsOpts($("#d-to").value)}</select></td>`
          : `<td><select class="l-whs">${whsOpts(v.whs_code || (it && it.dflt_wh) || "01")}</select></td>`}
        ${t.kind === "issue" || t.kind === "transfer" ? "" : `<td class="num"><input class="l-price" type="number" step="0.01" min="0" value="${v.price ?? ""}"></td>`}
        ${side !== "I" ? `<td class="num"><input class="l-disc" type="number" step="0.01" min="0" max="100" value="${Number(v.disc_prcnt || 0)}" style="width:70px"></td>
          <td><select class="l-vat">${taxes.map((x) => opt(x.code, x.code, v.vat_group)).join("")}</select></td><td class="num l-total">0.00</td>` : ""}${baseCell}`;
      const sel = $(".l-item", tr);
      sel.onchange = async () => {
        const i = items.find((x) => x.item_code === sel.value);
        if (!i) return;
        if ($(".l-vat", tr)) $(".l-vat", tr).value = (side === "S" ? i.vat_gourp_sa : i.vat_group_pu) || $(".l-vat", tr).value;
        if (i.dflt_wh && t.kind !== "transfer") $(".l-whs", tr).value = i.dflt_wh;
        const price = $(".l-price", tr);
        if (price) {
          if (side === "I") price.value = Number(i.avg_price || i.last_pur_prc).toFixed(2);
          else if ($("#d-bp").value) price.value = Number((await api(`/items/${encodeURIComponent(i.item_code)}/price?card_code=${encodeURIComponent($("#d-bp").value)}`)).price).toFixed(2);
        }
        recalc();
      };
    }
    $("#d-lines").appendChild(tr);
    $$("input,select", tr).forEach((i) => (i.oninput = recalc));
    $(".l-del", tr).onclick = () => { tr.remove(); recalc(); };
    recalc();
  };
  const recalc = () => {
    if (side === "I") return;
    let before = 0, vat = 0;
    const disc = Number($("#d-disc").value || 0) / 100;
    $$("#d-lines tr").forEach((tr) => {
      const qty = type() === "S" ? 1 : Number(($(".l-qty", tr) || {}).value || 0);
      const total = Math.round(qty * Number(($(".l-price", tr) || {}).value || 0) * (1 - Number(($(".l-disc", tr) || {}).value || 0) / 100) * 100) / 100;
      $(".l-total", tr).textContent = fmt(total);
      before += total;
      const net = Math.round(total * (1 - disc) * 100) / 100;
      vat += Math.round(net * rate($(".l-vat", tr).value)) / 100;
    });
    $("#t-before").textContent = fmt(before); $("#t-vat").textContent = fmt(vat);
    $("#t-total").textContent = fmt(before * (1 - disc) + vat);
  };
  const reset = () => { head(); $("#d-lines").innerHTML = ""; addLine(); };
  if ($("#d-type")) $("#d-type").onchange = reset;
  if ($("#d-disc")) $("#d-disc").oninput = recalc;
  $("#d-add").onclick = () => addLine();
  head();

  const addFromSource = (src, lineNums) => {
    if ($("#d-type") && $("#d-type").value !== src.doc_type) { $("#d-type").value = src.doc_type; head(); $("#d-lines").innerHTML = ""; }
    $$("#d-lines tr").forEach((tr) => { if (!tr.base && !(($(".l-item", tr) || {}).value || ($(".l-desc", tr) || {}).value)) tr.remove(); });
    if ($("#d-disc") && Number(src.disc_prcnt)) $("#d-disc").value = Number(src.disc_prcnt);
    src.lines.filter((l) => !lineNums || lineNums.includes(l.line_num)).forEach((l) => addLine({
      ...l, quantity: Number(l.open_qty), price: Number(l.price).toFixed(2), base_type: src.obj, base_entry: src.doc_entry,
      base_line: l.line_num, base_ref: src.doc_num }));
  };
  if ($("#d-copy")) $("#d-copy").onclick = async () => {
    const bp = $("#d-bp").value;
    if (!bp) return toast("Select the business partner first", "bad");
    const sources = await api(`/documents/${obj}/copy-sources?card_code=${encodeURIComponent(bp)}`);
    $("#d-sources").innerHTML = `<div class="card" style="margin-top:10px"><div class="card-head">Open documents of ${esc(bp)}</div>
      <table><thead><tr><th></th><th>Document</th><th>Date</th><th>Open lines</th><th class="num">Total</th></tr></thead><tbody>
      ${sources.map((src, k) => `<tr><td><input type="checkbox" class="src-pick" data-k="${k}"></td><td>${esc(src.name)} ${src.doc_num}</td><td>${src.doc_date}</td>
        <td>${src.lines.map((l) => `${esc(l.item_code || l.dscription)} × ${qtyFmt(l.open_qty)}`).join(", ")}</td><td class="num">${fmt(src.doc_total)}</td></tr>`).join("")
        || `<tr><td colspan="5" class="empty">No open documents to copy from.</td></tr>`}</tbody></table>
      ${sources.length ? '<div class="card-body"><button class="btn small" id="src-ok">Copy selected</button></div>' : ""}</div>`;
    const ok = $("#src-ok");
    if (ok) ok.onclick = () => { $$(".src-pick:checked").forEach((cb) => addFromSource(sources[cb.dataset.k])); $("#d-sources").innerHTML = ""; };
  };
  if ($("#d-bp")) $("#d-bp").onchange = () => {
    const vat = (state.partners.find((b) => b.card_code === $("#d-bp").value) || {}).vat_group;
    $$("#d-lines tr").forEach((tr) => {
      const s = $(".l-item", tr);
      if (tr.base) return;
      if (s && s.value) s.onchange();
      else if (vat && $(".l-vat", tr)) { $(".l-vat", tr).value = vat; recalc(); }
    });
  };

  if (from) {  // "Copy to" from a base document
    const [bobj, bentry] = from.split(":");
    const base = await api(`/documents/${bobj}/${bentry}`);
    $("#d-bp").value = base.card_code;
    addFromSource({ obj: bobj, doc_entry: base.doc_entry, doc_num: base.doc_num, doc_type: base.doc_type, disc_prcnt: base.disc_prcnt,
      lines: base.lines.filter((l) => l.line_status === "O" && Number(l.open_qty) > 0).map((l) => ({ ...l, price: l.price_bef_di })) });
  } else addLine();

  $("#d-post").onclick = async () => {
    const body = { doc_date: $("#d-date").value, doc_type: type(), comments: $("#d-comments").value || null, lines: [] };
    if (side !== "I") Object.assign(body, { card_code: $("#d-bp").value || null, num_at_card: $("#d-ref").value || null,
      doc_due_date: $("#d-due").value || null, tax_date: $("#d-tax").value || null, disc_prcnt: $("#d-disc").value || 0 });
    if (t.kind === "transfer") Object.assign(body, { from_whs: $("#d-from").value, to_whs: $("#d-to").value });
    $$("#d-lines tr").forEach((tr) => {
      const val = (cls) => { const e = $(cls, tr); return e && e.value !== "" ? e.value : null; };
      const line = { ...(tr.base || {}), vat_group: val(".l-vat"), disc_prcnt: val(".l-disc"), price: val(".l-price") };
      if (type() === "S") Object.assign(line, { dscription: val(".l-desc"), acct_code: val(".l-acct"), quantity: 1 });
      else Object.assign(line, { item_code: val(".l-item"), quantity: val(".l-qty") || 0, whs_code: val(".l-whs"), from_whs_cod: val(".l-from") });
      if (line.item_code || line.acct_code) body.lines.push(line);
    });
    const r = await act(() => post(`/documents/${obj}`, body), (d) => `${t.name} ${d.doc_num} added`);
    if (r) { state.partners = await api("/partners"); location.hash = `#/docs?obj=${obj}&entry=${r.doc_entry}`; }
  };
};

// ---------- Inventory audit report (OINM) ----------
views["inventory-audit"] = async (c) => {
  const code = query().get("item") || "";
  const [items, rows] = await Promise.all([api("/items"), api(`/inventory/journal?limit=300${code ? `&item_code=${encodeURIComponent(code)}` : ""}`)]);
  c.innerHTML = `<div class="page-head"><div><h1>Inventory Audit Report</h1><div class="sub">Warehouse journal (OINM): every stock movement and revaluation with its value</div></div></div>
    <div class="toolbar"><div class="field"><label>Item</label><select id="ia-item">${opt("", "All items", code)}${items.filter((i) => i.invnt_item).map((i) => opt(i.item_code, `${i.item_code} — ${i.item_name}`, code)).join("")}</select></div></div>
    <div class="card"><table><thead><tr><th>#</th><th>Date</th><th>Document</th><th>Item</th><th>Whs</th><th class="num">In</th><th class="num">Out</th>
      <th class="num">Price</th><th class="num">Value change</th><th class="num">Item cost after</th><th>BP</th><th>JE</th></tr></thead>
      <tbody>${rows.map((r) => `<tr><td class="mono">${r.trans_num}</td><td>${r.doc_date}</td><td><a href="#/docs?obj=${r.trans_type}&entry=${r.doc_entry}">${esc(r.name)} ${esc(r.doc_num)}</a></td>
        <td class="mono">${esc(r.item_code)}</td><td>${esc(r.warehouse)}</td><td class="num">${Number(r.in_qty) ? qtyFmt(r.in_qty) : ""}</td><td class="num">${Number(r.out_qty) ? qtyFmt(r.out_qty) : ""}</td>
        <td class="num">${fmt(r.price)}</td><td class="num">${fmt(r.trans_value)}</td><td class="num">${fmt(r.calc_price)}</td><td class="mono">${esc(r.card_code || "")}</td>
        <td>${r.trans_id ? `<a href="#/journal?id=${r.trans_id}">${r.trans_id}</a>` : ""}</td></tr>`).join("") || `<tr><td colspan="12" class="empty">No stock movements yet.</td></tr>`}</tbody></table></div>`;
  $("#ia-item").onchange = (e) => (location.hash = `#/inventory-audit${e.target.value ? `?item=${encodeURIComponent(e.target.value)}` : ""}`);
};

// ---------- Financial reports ----------
function periodToolbar(from, to, single = false) {
  return `<div class="toolbar">
    ${single ? "" : `<div class="field"><label>From</label><input id="rp-from" type="date" value="${from}"></div>`}
    <div class="field"><label>${single ? "As of" : "To"}</label><input id="rp-to" type="date" value="${to}"></div>
    <button class="btn" id="rp-go">Show</button></div>`;
}
function bindToolbar(view, single = false) {
  $("#rp-go").onclick = () => { location.hash = `#/${view}?to=${$("#rp-to").value}${single ? "" : `&from=${$("#rp-from").value}`}`; };
}

views["trial-balance"] = async (c) => {
  const from = query().get("from") || yearStart(), to = query().get("to") || yearEnd();
  const tb = await api(`/reports/trial-balance?date_from=${from}&date_to=${to}`);
  c.innerHTML = `<div class="page-head"><div><h1>Trial Balance</h1><div class="sub">${from} – ${to}</div></div>
      <span class="chip ${tb.balanced ? "ok" : "no"}">${tb.balanced ? "Balanced" : "Out of balance"}</span></div>
    ${periodToolbar(from, to)}
    <div class="card"><table><thead><tr><th>Account</th><th>Name</th><th class="num">Opening</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Closing</th></tr></thead>
    <tbody>${tb.lines.map((l) => `<tr><td class="mono">${esc(l.acct_code)}</td><td>${esc(l.acct_name)}</td><td class="num">${Number(l.opening) ? fmt(l.opening) : ""}</td>
      <td class="num">${Number(l.debit) ? fmt(l.debit) : ""}</td><td class="num">${Number(l.credit) ? fmt(l.credit) : ""}</td><td class="num">${fmt(l.closing)}</td></tr>`).join("")
      || `<tr><td colspan="6" class="empty">No postings in this period.</td></tr>`}</tbody>
    <tfoot><tr><td colspan="3">Total</td><td class="num">${fmt(tb.total_debit)}</td><td class="num">${fmt(tb.total_credit)}</td><td></td></tr></tfoot></table></div>`;
  bindToolbar("trial-balance");
};

function treeRows(nodes, rows = []) {
  nodes.forEach((n) => {
    if (!Number(n.raw) && !n.children.some((k) => Number(k.raw))) return;
    rows.push(`<tr class="${n.postable ? "" : "tree-title"}"><td style="padding-left:${14 + n.depth * 22}px">${esc(n.acct_name)}</td>
      <td class="mono help">${esc(n.acct_code)}</td><td class="num">${fmt(n.amount)}</td></tr>`);
    treeRows(n.children, rows);
  });
  return rows;
}

views["balance-sheet"] = async (c) => {
  const to = query().get("to") || today();
  const bs = await api(`/reports/balance-sheet?as_of=${to}`);
  const section = (title, nodes, extra = "", total) => `<div class="card"><div class="card-head">${title}<span>${fmt(total)}</span></div>
    <table><tbody>${treeRows(nodes).join("")}${extra}</tbody></table></div>`;
  c.innerHTML = `<div class="page-head"><div><h1>Balance Sheet</h1><div class="sub">As of ${to}</div></div>
      <span class="chip ${bs.balanced ? "ok" : "no"}">${bs.balanced ? "Assets = liabilities + capital" : "Out of balance"}</span></div>
    ${periodToolbar(null, to, true)}
    <div class="grid-2"><div>${section("Assets", bs.assets, "", bs.total_assets)}</div>
    <div>${section("Liabilities", bs.liabilities, "", bs.total_liabilities)}
      ${section("Capital and Reserves", bs.capital,
        `<tr><td style="padding-left:14px">Profit of previous years</td><td></td><td class="num">${fmt(bs.retained_profit)}</td></tr>
         <tr><td style="padding-left:14px">Profit for the period</td><td></td><td class="num">${fmt(bs.current_profit)}</td></tr>`, bs.total_capital)}</div></div>`;
  bindToolbar("balance-sheet", true);
};

views["profit-loss"] = async (c) => {
  const from = query().get("from") || yearStart(), to = query().get("to") || yearEnd();
  const pl = await api(`/reports/profit-and-loss?date_from=${from}&date_to=${to}`);
  c.innerHTML = `<div class="page-head"><div><h1>Profit and Loss Statement</h1><div class="sub">${from} – ${to}</div></div></div>
    ${periodToolbar(from, to)}
    <div class="tiles"><div class="tile"><div class="label">Gross profit</div><div class="value">${fmt(pl.gross_profit)}</div></div>
      <div class="tile"><div class="label">Net profit</div><div class="value ${Number(pl.net_profit) >= 0 ? "good" : "bad"}">${fmt(pl.net_profit)}</div></div></div>
    ${pl.drawers.filter((d) => Number(d.amount)).map((d) => `<div class="card"><div class="card-head">${esc(d.name)}<span>${fmt(d.amount)}</span></div>
      <table><tbody>${treeRows(d.accounts).join("")}</tbody></table></div>`).join("") || `<div class="card"><div class="empty">No revenue or costs in this period.</div></div>`}`;
  bindToolbar("profit-loss");
};

// ---------- Administration ----------
views.setup = async (c) => {
  const periods = await api("/admin/periods");
  const rates = await api(`/admin/exchange-rates?rate_date=${today()}`);
  const L = state.lookups;
  c.innerHTML = `<div class="page-head"><div><h1>Company &amp; Periods</h1><div class="sub">Company details, currencies, tax groups, payment terms and posting periods</div></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Company details (OADM)</div><table><tbody>
        ${[["Company", state.company.company_name], ["Local currency", state.company.main_curncy], ["System currency", state.company.sys_curncy],
           ["Country", state.company.country], ["Tax ID", state.company.tax_id], ["Address", state.company.address]]
          .map(([k, v]) => `<tr><td class="help">${k}</td><td>${esc(v || "")}</td></tr>`).join("")}</tbody></table></div>
      <div class="card"><div class="card-head">Exchange rates today (ORTT)</div><table><tbody>
        ${rates.map((r) => `<tr><td>${esc(r.currency)}</td><td class="num">${Number(r.rate).toFixed(4)} ${esc(state.company.main_curncy)}</td></tr>`).join("") || `<tr><td class="empty">No rates for today.</td></tr>`}</tbody></table>
        <div class="card-body"><div class="toolbar" style="margin:0"><div class="field"><label>Currency</label><select id="rt-cur">${L.currencies.filter((x) => x.code !== state.company.main_curncy).map((x) => `<option>${x.code}</option>`).join("")}</select></div>
          <div class="field"><label>Date</label><input id="rt-date" type="date" value="${today()}"></div>
          <div class="field"><label>Rate</label><input id="rt-rate" type="number" step="0.0001"></div><button class="btn secondary" id="rt-save">Save</button></div></div></div>
      <div class="card"><div class="card-head">Tax groups (OVTG)</div><table><thead><tr><th>Code</th><th>Name</th><th>Type</th><th class="num">Rate</th><th>Account</th></tr></thead><tbody>
        ${L.tax_groups.map((t) => `<tr><td class="mono">${esc(t.code)}</td><td>${esc(t.name)}</td><td>${t.category === "O" ? "Output" : "Input"}</td><td class="num">${Number(t.rate)}%</td><td class="mono">${esc(t.account)}</td></tr>`).join("")}</tbody></table></div>
      <div class="card"><div class="card-head">Payment terms (OCTG)</div><table><thead><tr><th>Code</th><th>Name</th><th class="num">Months</th><th class="num">Days</th></tr></thead><tbody>
        ${L.payment_terms.map((p) => `<tr><td>${p.group_num}</td><td>${esc(p.name)}</td><td class="num">${p.extra_month}</td><td class="num">${p.extra_days}</td></tr>`).join("")}</tbody></table></div>
    </div>
    <div class="card"><div class="card-head">Posting periods (OFPR)</div><table><thead><tr><th>Period</th><th>From</th><th>To</th><th>Status</th><th></th></tr></thead><tbody>
      ${periods.filter((p) => p.category === String(new Date().getFullYear())).map((p) => `<tr><td class="mono">${esc(p.code)}</td><td>${p.from}</td><td>${p.to}</td>
        <td><span class="status ${p.status === "N" ? "O" : "C"}">${{ N: "Unlocked", Y: "Locked", C: "Closing" }[p.status]}</span></td>
        <td><button class="btn small ghost pe-toggle" data-id="${p.abs_entry}" data-s="${p.status === "N" ? "Y" : "N"}">${p.status === "N" ? "Lock" : "Unlock"}</button></td></tr>`).join("")}</tbody></table></div>`;
  $("#rt-save").onclick = async () => { if (await act(() => post("/admin/exchange-rates", { currency: $("#rt-cur").value, rate_date: $("#rt-date").value, rate: $("#rt-rate").value }), "Rate saved")) route(); };
  $$(".pe-toggle").forEach((b) => (b.onclick = async () => {
    if (await act(() => api(`/admin/periods/${b.dataset.id}`, { method: "PUT", body: JSON.stringify({ status: b.dataset.s }) }), "Period updated")) route();
  }));
};

boot();
