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
const fmt = (n) => Number(n || 0).toLocaleString(state.company && state.company.main_curncy === "INR" ? "en-IN" : undefined,
  { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

// ---------- typed form fields ----------
// Every input keeps its B1 field type: text, number, date, dropdown (select) or checkbox.
// def: { k, label, type: "text" | "number" | "date" | "select" | "check" | "textarea", options: [[value, label]] or
//        () => [...], int (select value is a number), blank (label of the empty choice, false = none), req, max,
//        step, min, ro (read-only), span (grid columns) }
function fieldHtml(d, v, p = "f") {
  const id = `${p}-${d.k}`, val = v ?? d.value ?? "";
  const ro = d.ro ? (d.type === "select" || d.type === "check" ? " disabled" : " readonly") : "";
  if (d.type === "check") {
    return `<div class="field check"><label><input id="${id}" type="checkbox"${val === true || val === "Y" ? " checked" : ""}${ro}> ${esc(d.label)}</label></div>`;
  }
  let input;
  if (d.type === "number") {
    input = `<input id="${id}" type="number" step="${d.step ?? "any"}"${d.min != null ? ` min="${d.min}"` : ""}${d.maxv != null ? ` max="${d.maxv}"` : ""} value="${val === "" || val == null ? "" : Number(val)}"${ro}>`;
  } else if (d.type === "date") {
    input = `<input id="${id}" type="date" value="${esc(val)}"${ro}>`;
  } else if (d.type === "select") {
    const o = typeof d.options === "function" ? d.options() : d.options;
    input = `<select id="${id}"${ro}>${d.blank === false ? "" : opt("", d.blank || "")}${o.map(([ov, ol]) => opt(ov, ol, val)).join("")}</select>`;
  } else if (d.type === "textarea") {
    input = `<textarea id="${id}" maxlength="${d.max || 254}" rows="2"${ro}>${esc(val)}</textarea>`;
  } else {
    input = `<input id="${id}"${d.max ? ` maxlength="${d.max}"` : ""} value="${esc(val)}"${ro}>`;
  }
  return `<div class="field"${d.span ? ` style="grid-column:span ${d.span}"` : ""}><label${d.req ? ' class="req"' : ""}>${esc(d.label)}</label>${input}</div>`;
}
const fieldsHtml = (defs, values = {}, p = "f") => defs.map((d) => fieldHtml(d, values[d.k], p)).join("");
function readFields(defs, p = "f") {
  const out = {};
  defs.filter((d) => !d.ro).forEach((d) => {
    const e = $(`#${p}-${d.k}`);
    if (!e) return;
    if (d.type === "check") out[d.k] = e.checked;
    else if (d.type === "number") out[d.k] = e.value === "" ? null : Number(e.value);
    else if (d.type === "select") out[d.k] = e.value === "" ? null : d.int ? Number(e.value) : e.value;
    else out[d.k] = e.value === "" ? null : e.value;
  });
  return out;
}
// state dropdown follows the country dropdown (OCST by OCRY)
function bindCountryState(p, countryKey = "country", stateKey = "state") {
  const c = $(`#${p}-${countryKey}`), st = $(`#${p}-${stateKey}`);
  if (!c || !st) return;
  const fill = () => { const v = st.value; st.innerHTML = opt("", "") + O.states(c.value).map(([k, l]) => opt(k, l, v)).join(""); };
  c.addEventListener("change", fill);
  fill();
}
// dropdown sources (B1 dropdowns and choose-from lists)
const O = {
  currencies: () => state.lookups.currencies.map((c) => [c.code, `${c.code} — ${c.name}`]),
  countries: () => state.master.countries.map((c) => [c.code, c.name]),
  states: (country) => state.master.states.filter((x) => x.country === country).map((x) => [x.code, x.name]),
  salesEmployees: () => state.master.sales_employees.filter((e) => e.active).map((e) => [e.slp_code, e.slp_name]),
  projects: () => state.master.projects.filter((x) => x.active).map((x) => [x.prj_code, `${x.prj_code} — ${x.prj_name}`]),
  manufacturers: () => state.master.manufacturers.map((m) => [m.firm_code, m.firm_name]),
  transCodes: () => state.master.transaction_codes.map((t) => [t.trns_code, `${t.trns_code} — ${t.trns_cod_dsc}`]),
  itemTypes: () => state.master.item_types.map((t) => [t.code, t.name]),
  terms: () => state.lookups.payment_terms.map((t) => [t.group_num, t.name]),
  taxes: (cat) => () => state.lookups.tax_groups.filter((t) => t.category === cat && !t.inactive).map((t) => [t.code, `${t.code} — ${t.name}`]),
  hsn: () => state.taxSetup.hsn.map((h) => [h.chapter_id, `${h.chapter_id} — ${h.dscription}`]),
  priceLists: () => state.priceLists.filter((p) => p.active).map((p) => [p.list_num, p.list_name]),
  warehouses: () => state.warehouses.map((w) => [w.whs_code, `${w.whs_code} — ${w.whs_name}`]),
  vendors: () => state.partners.filter((b) => b.card_type === "S" && !b.frozen).map((b) => [b.card_code, `${b.card_code} — ${b.card_name}`]),
  accounts: (filter = () => true) => () => state.accounts.filter((a) => a.postable === "Y" && !a.frozen && filter(a)).map((a) => [a.acct_code, `${a.acct_code} — ${a.acct_name}`]),
};
async function rateOf(cur, day) {
  if (!cur || cur === state.company.main_curncy) return 1;
  const r = (await api(`/admin/exchange-rates?rate_date=${day || today()}`)).find((x) => x.currency === cur);
  if (!r) throw new Error(`No exchange rate for ${cur} on ${day || today()}`);
  return Number(r.rate);
}
const nameOf = (list, key, val, label) => ((list.find((x) => String(x[key]) === String(val)) || {})[label] ?? "");

// ---------- bootstrap ----------
async function boot() {
  try {
    const h = await fetch("/health").then((r) => r.json());
    $("#dbBadge").textContent = h.db;
  } catch (_) {}
  state.company = await api("/admin/company");
  $("#companyBadge").textContent = `${state.company.company_name} · ${state.company.main_curncy}`;
  document.title = `Business One — ${state.company.company_name}`;
  await reloadMasterData();
  window.addEventListener("hashchange", route);
  $("#navToggle").onclick = () => $("#sidenav").classList.toggle("collapsed");
  if (!location.hash) location.hash = "#/cockpit";
  route();
}
async function reloadMasterData() {
  [state.accounts, state.lookups, state.partners, state.master, state.priceLists, state.warehouses, state.taxSetup] = await Promise.all([
    api("/accounts"), api("/admin/lookups"), api("/partners"), api("/master/lookups"), api("/price-lists"), api("/warehouses"),
    api("/tax/setup")]);
}

const views = {};
function route() {
  const view = (location.hash.replace("#/", "") || "cockpit").split("?")[0];
  const obj = query().get("obj");
  const kind = query().get("kind");
  $$(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.obj ? a.dataset.obj === obj && view.startsWith("doc")
    : a.dataset.kind ? a.dataset.kind === kind && view.startsWith("payment") : a.dataset.view === view));
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
      <td>${e.storno_to_tr ? `<span class="status X">${e.is_reversal ? "Reversal" : "Reversed"}</span>` : ""}</td></tr>`).join("")
      || `<tr><td colspan="6" class="empty">No journal entries yet.</td></tr>`}</tbody></table>`;
}
const TRANS_TYPES = { "25": "DP", "30": "JE", "13": "IN", "14": "CN", "15": "DN", "16": "RE", "18": "PU", "19": "PC", "20": "PD",
  "21": "PR", "24": "RC", "46": "PS", "59": "SI", "60": "SO", "67": "IM", "23": "QT", "17": "OR", "22": "PO", "540000006": "PQ" };
const transTypeName = (t) => TRANS_TYPES[t] || t;
// origin of a journal entry -> the document that created it
const docLink = (type, entry, label) => (type === "24" || type === "46") && entry
  ? `<a href="#/payments?kind=${type === "24" ? "incoming" : "outgoing"}&entry=${entry}" onclick="event.stopPropagation()">${esc(label)}</a>`
  : type === "25" ? `<a href="#/deposits" onclick="event.stopPropagation()">${esc(label)}</a>`
  : (DOC_NAMES[type] && type !== "30" && entry
    ? `<a href="#/docs?obj=${type}&entry=${entry}" onclick="event.stopPropagation()">${esc(label)}</a>` : esc(label));
const DOC_NAMES = { "23": "Sales Quotation", "17": "Sales Order", "15": "Delivery", "16": "Return", "13": "A/R Invoice",
  "14": "A/R Credit Memo", "540000006": "Purchase Quotation", "22": "Purchase Order", "20": "Goods Receipt PO",
  "21": "Goods Return", "18": "A/P Invoice", "19": "A/P Credit Memo", "59": "Goods Receipt", "60": "Goods Issue",
  "67": "Inventory Transfer" };

// ---------- Journal Entry ----------
const JE_HEADER = [
  { k: "ref_date", label: "Posting date", type: "date", req: true, value: today() },
  { k: "due_date", label: "Due date", type: "date", value: today() },
  { k: "tax_date", label: "Document date", type: "date", value: today() },
  { k: "memo", label: "Remarks", max: 50, span: 2 },
  { k: "ref1", label: "Ref. 1", max: 100 },
  { k: "ref2", label: "Ref. 2", max: 100 },
  { k: "ref3", label: "Ref. 3", max: 27 },
  { k: "trans_code", label: "Trans. code", type: "select", options: () => O.transCodes() },
  { k: "project", label: "Project", type: "select", options: () => O.projects() },
  { k: "series", label: "Series", type: "select", options: [["1", "Primary"]], blank: false, ro: true },
  { k: "origin", label: "Origin", ro: true, value: "JE" },
  { k: "origin_no", label: "Origin No.", ro: true },
  { k: "trans_no", label: "Trans. No.", ro: true },
  { k: "auto_storno", label: "Reverse", type: "check" },
  { k: "storno_date", label: "Reversal date", type: "date" },
];
views["journal-entry"] = async (c) => {
  c.innerHTML = `
    <div class="page-head"><div><h1>Journal Entry</h1><div class="sub">Manual journal entry (object 30) — G/L accounts and business partners (posted to their control account)</div></div></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(JE_HEADER, {}, "je")}</div></div></div>
    <div class="card"><div class="card-body" style="overflow-x:auto">
      <table class="lines"><thead><tr><th>G/L acct / BP code</th><th>Control acct</th><th>Currency</th><th class="num">Debit (FC)</th><th class="num">Credit (FC)</th><th class="num w-amt">Debit</th><th class="num w-amt">Credit</th>
        <th>Due date</th><th>Line remarks</th><th>Ref. 1</th><th>Ref. 2</th><th>Project</th><th></th></tr></thead><tbody id="je-lines"></tbody></table>
      <button class="btn secondary small" id="je-add" style="margin-top:8px">+ Line</button>
      <div class="balance-row"><span>Debit <span class="amt" id="je-d">0.00</span></span><span>Credit <span class="amt" id="je-c">0.00</span></span><span id="je-chip" class="chip no">Not balanced</span></div>
      <button class="btn" id="je-post" disabled>Add</button>
    </div></div>`;
  const projects = O.projects().map(([v, l]) => opt(v, l)).join("");
  const addLine = () => {
    const tr = document.createElement("tr");
    const bps = state.partners.filter((b) => b.card_type !== "L" && !b.frozen)
      .map((b) => `<option value="BP:${esc(b.card_code)}">${esc(b.card_code)} — ${esc(b.card_name)}</option>`).join("");
    tr.innerHTML = `<td><select class="je-acct"><optgroup label="G/L accounts">${accountOptions((a) => !a.control && !a.bloc_man_pos && !a.frozen)}</optgroup>
      <optgroup label="Business partners">${bps}</optgroup></select></td><td class="mono help je-ctrl"></td>
      <td><select class="je-cur">${opt("", "LC")}${O.currencies().filter(([v]) => v !== state.company.main_curncy).map(([v]) => opt(v, v)).join("")}</select></td>
      <td class="num"><input class="je-fcd" type="number" step="0.01" min="0" style="width:90px" disabled></td>
      <td class="num"><input class="je-fcc" type="number" step="0.01" min="0" style="width:90px" disabled></td>
      <td class="num"><input class="je-debit" type="number" step="0.01" min="0"></td><td class="num"><input class="je-credit" type="number" step="0.01" min="0"></td>
      <td><input class="je-due" type="date"></td><td><input class="je-lm" maxlength="50"></td>
      <td><input class="je-r1" maxlength="100" style="width:90px"></td><td><input class="je-r2" maxlength="100" style="width:90px"></td>
      <td><select class="je-prj">${opt("", "")}${projects}</select></td><td><button class="btn ghost small je-del">✕</button></td>`;
    $("#je-lines").appendChild(tr);
    const sel = $(".je-acct", tr);
    sel.onchange = () => {  // a BP line shows the control account it posts to
      const bp = sel.value.startsWith("BP:") && state.partners.find((b) => b.card_code === sel.value.slice(3));
      $(".je-ctrl", tr).textContent = bp ? bp.deb_pay_acct : "";
    };
    $$("input", tr).forEach((i) => (i.oninput = recalc));
    // a foreign-currency line: the local amounts follow from the rate of the posting date
    const fcSync = async () => {
      const cur = $(".je-cur", tr).value;
      $(".je-fcd", tr).disabled = $(".je-fcc", tr).disabled = !cur;
      $(".je-debit", tr).readOnly = $(".je-credit", tr).readOnly = !!cur;
      if (!cur) return recalc();
      let r;
      try { r = await rateOf(cur, $("#je-ref_date").value); } catch (e) { toast(e.message, "bad"); return; }
      const lc = (v) => (v === "" ? "" : (Math.round(Number(v) * r * 100) / 100).toFixed(2));
      $(".je-debit", tr).value = lc($(".je-fcd", tr).value); $(".je-credit", tr).value = lc($(".je-fcc", tr).value);
      recalc();
    };
    $(".je-cur", tr).onchange = fcSync;
    $(".je-fcd", tr).oninput = fcSync; $(".je-fcc", tr).oninput = fcSync;
    tr.fcSync = fcSync;
    $(".je-del", tr).onclick = () => { tr.remove(); recalc(); };
  };
  $("#je-ref_date").addEventListener("change", () => $$("#je-lines tr").forEach((tr) => tr.fcSync()));
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
    const val = (tr, cls) => $(cls, tr).value || null;
    const lines = $$("#je-lines tr").map((tr) => ({ ...target($(".je-acct", tr).value), fc_currency: val(tr, ".je-cur"),
      fc_debit: Number($(".je-fcd", tr).value || 0), fc_credit: Number($(".je-fcc", tr).value || 0), debit: Number($(".je-debit", tr).value || 0),
      credit: Number($(".je-credit", tr).value || 0), due_date: val(tr, ".je-due"), line_memo: val(tr, ".je-lm"),
      ref1: val(tr, ".je-r1"), ref2: val(tr, ".je-r2"), project: val(tr, ".je-prj") }));
    const head = readFields(JE_HEADER, "je");
    const r = await act(() => post("/journal-entries", { ...head, lines }), (e) => `Journal entry ${e.number} added`);
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
  const name = (code) => (state.accounts.find((a) => a.acct_code === code) || {}).acct_name
    || (state.partners.find((b) => b.card_code === code) || {}).card_name || "";
  const values = { ...e, origin: transTypeName(e.trans_type), origin_no: e.base_ref || e.number, trans_no: e.trans_id,
    series: String(e.series || 1) };
  $("#je-detail").innerHTML = `<div class="card"><div class="card-head"><span>Journal entry ${e.number} · ${e.ref_date} · ${esc(transTypeName(e.trans_type))}
      ${DOC_NAMES[e.trans_type] ? ` · ${docLink(e.trans_type, e.created_by, `${DOC_NAMES[e.trans_type]} ${e.base_ref}`)}` : ""}
      ${e.storno_to_tr ? ` · ${e.is_reversal ? "reversal of" : "reversed by"} <a href="#/journal?id=${e.storno_to_tr}">Trans. No. ${e.storno_to_tr}</a>` : ""}</span>
      ${e.storno_to_tr ? "" : `<button class="btn small secondary" id="je-rev">Reverse</button>`}</div>
    <div class="card-body"><div class="form-grid">${fieldsHtml(JE_HEADER.map((d) => ({ ...d, ro: true, value: undefined })), values, "jd")}</div></div>
    <div style="overflow-x:auto"><table><thead><tr><th>#</th><th>G/L acct / BP code</th><th>Name</th><th>Control acct</th><th>Contra account</th><th class="num">Debit</th><th class="num">Credit</th>
      <th>Currency</th><th class="num">Debit (FC)</th><th class="num">Credit (FC)</th><th class="num">Open (FC)</th>
      <th>Due date</th><th>Remarks</th><th>Ref. 1</th><th>Ref. 2</th><th>Project</th><th>Tax group</th></tr></thead>
    <tbody>${e.lines.map((l) => `<tr><td>${l.line_id + 1}</td><td class="mono">${esc(l.short_name)}</td><td>${esc(name(l.short_name))}</td>
      <td class="mono help">${l.short_name !== l.account ? esc(l.account) : ""}</td><td class="mono help">${esc(l.contra_act || "")}</td>
      <td class="num">${Number(l.debit) ? fmt(l.debit) : ""}</td><td class="num">${Number(l.credit) ? fmt(l.credit) : ""}</td>
      <td>${esc(l.fc_currency || "")}</td><td class="num">${Number(l.fc_debit) ? fmt(l.fc_debit) : ""}</td><td class="num">${Number(l.fc_credit) ? fmt(l.fc_credit) : ""}</td>
      <td class="num">${Number(l.bal_fc_deb) || Number(l.bal_fc_cred) ? fmt(Number(l.bal_fc_deb) - Number(l.bal_fc_cred)) : ""}</td>
      <td>${esc(l.due_date || "")}</td><td>${esc(l.line_memo || "")}</td><td>${esc(l.ref1 || "")}</td><td>${esc(l.ref2 || "")}</td>
      <td>${esc(l.project || "")}</td><td>${esc(l.vat_group || "")}</td></tr>`).join("")}</tbody></table></div></div>`;
  const rev = $("#je-rev");
  if (rev) rev.onclick = async () => {
    if (!confirm(`Reverse journal entry ${e.number}?`)) return;
    const r = await act(() => post(`/journal-entries/${e.trans_id}/reverse`, {}), (x) => `Reversed by journal entry ${x.number}`);
    if (r) location.hash = `#/journal?id=${r.trans_id}`;
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
const isAR = (t) => t.kind === "invoice" || t.kind === "credit";

// header fields of a document type (B1: header, Logistics and Accounting tabs, footer)
function docHeaderDefs(t, mode) {
  const ro = mode === "view";
  if (t.side === "I") {
    return [
      { k: "doc_num", label: "No.", ro: true },
      { k: "series", label: "Series", type: "select", options: [["1", "Primary"]], blank: false, ro: true },
      { k: "doc_date", label: "Posting date", type: "date", req: true, value: today(), ro },
      { k: "tax_date", label: "Document date", type: "date", value: today(), ro },
      ...(t.kind === "transfer" ? [
        { k: "from_whs", label: "From warehouse", type: "select", options: () => O.warehouses(), blank: false, req: true, ro },
        { k: "to_whs", label: "To warehouse", type: "select", options: () => O.warehouses(), blank: false, req: true, ro }]
        : [{ k: "price_list", label: "Price list", type: "select", options: () => O.priceLists(), blank: "Item cost", ro }]),
      { k: "ref2", label: "Ref. 2", max: 11, ro },
      { k: "jrnl_memo", label: "Journal remark", max: 50, ro, span: 2 },
      { k: "comments", label: "Remarks", type: "textarea", max: 254, ro, span: 2 },
    ];
  }
  const sales = t.side === "S";
  return [
    { k: "card_code", label: sales ? "Customer" : "Vendor", type: "select", req: true, ro: ro || mode === "copy", options: () => state.partners
      .filter((b) => !b.frozen && (sales ? b.card_type === "C" || (b.card_type === "L" && t.kind === "quotation") : b.card_type === "S"))
      .map((b) => [b.card_code, `${b.card_code} — ${b.card_name}`]), blank: "— select —" },
    { k: "cntct_code", label: "Contact person", type: "select", int: true, options: [], ro },
    { k: "num_at_card", label: sales ? "Customer ref. no." : "Vendor ref. no.", max: 100, ro },
    { k: "doc_cur", label: "Currency", type: "select", blank: false, options: () => O.currencies(), value: state.company.main_curncy,
      ro: ro || mode === "copy" },
    { k: "doc_rate", label: "Rate", type: "number", ro: true, value: 1 },
    { k: "doc_num", label: "No.", ro: true },
    { k: "series", label: "Series", type: "select", options: [["1", "Primary"]], blank: false, ro: true },
    { k: "doc_date", label: "Posting date", type: "date", req: true, value: today(), ro },
    { k: "doc_due_date", label: isAR(t) ? "Due date" : sales ? "Delivery date" : "Delivery date", type: "date", ro },
    { k: "tax_date", label: "Document date", type: "date", value: today(), ro },
    { k: "doc_type", label: "Item/Service type", type: "select", blank: false, options: [["I", "Item"], ["S", "Service"]],
      ro: ro || ["delivery", "return"].includes(t.kind) },
    { k: "slp_code", label: sales ? "Sales employee" : "Buyer", type: "select", int: true, options: () => O.salesEmployees(), blank: false, ro },
    { k: "project", label: "Project", type: "select", options: () => O.projects(), ro },
    { k: "pay_to_code", label: "Bill to", type: "select", options: [], ro },
    { k: "address", label: "Bill-to address", type: "textarea", ro: true },
    { k: "ship_to_code", label: "Ship to", type: "select", options: [], ro },
    { k: "address2", label: "Ship-to address", type: "textarea", ro: true },
    { k: "group_num", label: "Payment terms", type: "select", int: true, options: () => O.terms(), ro: true },
    { k: "lic_trad_num", label: "Federal tax ID", ro: true },
    { k: "jrnl_memo", label: "Journal remark", max: 50, ro, span: 2 },
    { k: "comments", label: "Remarks", type: "textarea", max: 254, ro, span: 2 },
  ];
}

views.docs = async (c) => {
  const obj = query().get("obj") || "13", entry = query().get("entry");
  const t = (await docTypes())[obj];
  const list = await api(`/documents/${obj}?limit=100`);
  const bp = t.side !== "I";
  c.innerHTML = `<div class="page-head"><div><h1>${esc(t.name)}</h1><div class="sub">${t.side === "S" ? "Sales — A/R" : t.side === "P" ? "Purchasing — A/P" : "Inventory"}
      ${t.bases.length ? ` · copy from ${t.bases.map((b) => esc(DOC_NAMES[b])).join(", ")}` : ""}</div></div>
      <a class="btn" href="#/doc?obj=${obj}">+ New ${esc(t.name)}</a></div>
    <div class="card"><table><thead><tr><th>No.</th><th>Posting date</th>${bp ? "<th>BP code</th><th>BP name</th><th>Sales employee</th>" : "<th>Remarks</th>"}
      ${t.side === "I" ? "" : "<th>Due date</th>"}<th class="num">Total</th>${isAR(t) ? '<th class="num">Paid / applied</th>' : ""}<th>Status</th></tr></thead>
      <tbody>${list.map((d) => `<tr style="cursor:pointer" onclick="location.hash='#/docs?obj=${obj}&entry=${d.doc_entry}'">
        <td class="mono">${d.doc_num}</td><td>${d.doc_date}</td>${bp ? `<td class="mono">${esc(d.card_code)}</td><td>${esc(d.card_name)}</td>
        <td>${esc(nameOf(state.master.sales_employees, "slp_code", d.slp_code, "slp_name"))}</td>` : `<td>${esc(d.comments || "")}</td>`}
        ${t.side === "I" ? "" : `<td>${d.doc_due_date}</td>`}<td class="num">${fmt(d.doc_total)}</td>
        ${isAR(t) ? `<td class="num">${fmt(d.paid_to_date)}</td>` : ""}<td>${STATUS(d)}</td></tr>`).join("")
        || `<tr><td colspan="9" class="empty">No documents yet.</td></tr>`}</tbody></table></div><div id="doc-detail"></div>`;
  if (entry) await docDetail($("#doc-detail"), t, entry);
};

async function partnerDetail(code) {
  return code ? api(`/partners/${encodeURIComponent(code)}`) : { contacts: [], addresses: [] };
}

async function docDetail(el, t, entry) {
  const d = await api(`/documents/${t.obj}/${entry}`);
  const types = await docTypes();
  const open = d.doc_status === "O" && !d.canceled;
  const targets = open || t.kind === "invoice" ? t.targets.filter(() => !d.canceled && d.lines.some((l) => Number(l.open_qty) > 0)) : [];
  const svc = d.doc_type === "S";
  const bp = t.side !== "I" ? await partnerDetail(d.card_code) : { contacts: [], addresses: [] };
  const defs = docHeaderDefs(t, "view").map((f) => f.k === "cntct_code" ? { ...f, options: bp.contacts.map((x) => [x.cntct_code, x.name]) }
    : f.k === "pay_to_code" ? { ...f, options: bp.addresses.filter((a) => a.adres_type === "B").map((a) => [a.address, a.address]) }
    : f.k === "ship_to_code" ? { ...f, options: bp.addresses.filter((a) => a.adres_type === "S").map((a) => [a.address, a.address]) } : f);
  const values = { ...d, series: String(d.series || 1), from_whs: d.filler, to_whs: d.to_whs_code };
  const fcDoc = d.doc_cur !== state.company.main_curncy;
  const cols = t.side === "I"
    ? [["Item No.", (l) => `<span class="mono">${esc(l.item_code)}</span>`], ["Description", (l) => esc(l.dscription)], ["Quantity", (l) => qtyFmt(l.quantity), 1],
       ["UoM", (l) => esc(l.unit_msr || "")], ...(t.kind === "transfer" ? [["From whs", (l) => esc(l.from_whs_cod)], ["To whs", (l) => esc(l.whs_code)]] : [["Whs", (l) => esc(l.whs_code)]]),
       ["Item cost", (l) => fmt(l.stock_price), 1], ["Total", (l) => fmt(l.line_total), 1], ...(t.kind === "transfer" ? [] : [["G/L account", (l) => esc(l.acct_code || "default")]]),
       ["Project", (l) => esc(l.project || "")]]
    : [...(svc ? [["Description", (l) => esc(l.dscription)], ["G/L account", (l) => `<span class="mono">${esc(l.acct_code)}</span>`]]
         : [["Item No.", (l) => `<span class="mono">${esc(l.item_code)}</span>`], ["Description", (l) => esc(l.dscription)], ["Quantity", (l) => qtyFmt(l.quantity), 1],
            ["Open qty", (l) => qtyFmt(l.open_qty), 1], ["UoM", (l) => esc(l.unit_msr || "")]]),
       ["Unit price", (l) => fmt(l.price_bef_di), 1], ["Disc. %", (l) => (Number(l.disc_prcnt) ? Number(l.disc_prcnt) : ""), 1],
       ["Price after disc.", (l) => fmt(l.price), 1], ["Tax code", (l) => esc(l.vat_group || "")], ["Tax amount", (l) => fmt(l.vat_sum), 1],
       ...(fcDoc ? [["Total (FC)", (l) => fmt(l.total_frgn), 1]] : []),
       ["Total (LC)", (l) => fmt(l.line_total), 1], ["Gross price", (l) => fmt(l.price_af_vat), 1],
       ...(fcDoc ? [["Gross total (FC)", (l) => fmt(l.gtotal_fc), 1]] : []), ["Gross total (LC)", (l) => fmt(l.gtotal), 1],
       ...(svc ? [] : [["Whs", (l) => esc(l.whs_code || "")], ["Item cost", (l) => (Number(l.stock_price) ? fmt(l.stock_price) : ""), 1]]),
       ["Del. date", (l) => esc(l.ship_date || "")], ["Project", (l) => esc(l.project || "")], ["Free text", (l) => esc(l.free_txt || "")]];
  el.innerHTML = `<div class="card"><div class="card-head"><span>${esc(t.name)} ${d.doc_num} ${STATUS(d)}</span><span style="display:flex;gap:6px;flex-wrap:wrap">
      ${targets.map((x) => `<a class="btn small" href="#/doc?obj=${x}&from=${t.obj}:${d.doc_entry}">Copy to ${esc(types[x].name)}</a>`).join("")}
      ${open && ["quotation", "order"].includes(t.kind) ? '<button class="btn small secondary" id="doc-close">Close</button>' : ""}
      ${!d.canceled ? '<button class="btn small secondary" id="doc-cancel">Cancel</button>' : ""}
      ${d.trans_id ? `<a class="btn small ghost" href="#/journal?id=${d.trans_id}">Journal entry ${d.trans_id} &#8599;</a>` : ""}</span></div>
    <div class="card-body"><div class="form-grid">${fieldsHtml(defs, values, "dv")}</div></div>
    <div style="overflow-x:auto"><table><thead><tr><th>#</th>${cols.map(([h, , n]) => `<th${n ? ' class="num"' : ""}>${h}</th>`).join("")}<th>Base</th><th>Status</th></tr></thead>
    <tbody>${d.lines.map((l) => `<tr><td>${l.line_num + 1}</td>${cols.map(([, f, n]) => `<td${n ? ' class="num"' : ""}>${f(l)}</td>`).join("")}
      <td>${l.base_type ? `<a href="#/docs?obj=${l.base_type}&entry=${l.base_entry}">${esc(transTypeName(l.base_type))} ${esc(l.base_ref)}</a>` : ""}</td>
      <td>${t.side !== "I" ? (l.line_status === "O" ? "Open" : "Closed") : ""}</td></tr>`).join("")}</tbody></table></div>
    ${t.side !== "I" ? `<div class="card-body"><div class="totals">
      <div><span>Total before discount</span><b>${fmt(d.lines.reduce((s, l) => s + Number(l.line_total), 0))}</b></div>
      <div><span>Discount ${Number(d.disc_prcnt) ? `${Number(d.disc_prcnt)} %` : ""}</span><b>${fmt(d.disc_sum)}</b></div>
      <div><span>Tax</span><b>${fmt(d.vat_sum)}</b></div><div class="grand"><span>Total (LC)</span><b>${fmt(d.doc_total)} ${esc(state.company.main_curncy)}</b></div>
      ${fcDoc ? `<div><span>Tax (FC)</span><b>${fmt(d.vat_sum_fc)}</b></div><div class="grand"><span>Total (${esc(d.doc_cur)}) at ${Number(d.doc_rate)}</span><b>${fmt(d.doc_total_fc)} ${esc(d.doc_cur)}</b></div>` : ""}
      ${isAR(t) ? `<div><span>Applied amount</span><b>${fmt(d.paid_to_date)}</b></div><div><span>Balance due</span><b>${fmt(d.doc_total - d.paid_to_date)}</b></div>
        ${fcDoc ? `<div><span>Applied amount (FC)</span><b>${fmt(d.paid_fc)}</b></div><div><span>Balance due (FC)</span><b>${fmt(d.doc_total_fc - d.paid_fc)}</b></div>` : ""}` : ""}
    </div></div>` : `<div class="card-body"><div class="totals"><div class="grand"><span>Total value</span><b>${fmt(d.doc_total)}</b></div></div></div>`}
    ${(d.installments || []).length ? `<div class="card-body"><h3 class="section">Installments</h3><table><thead><tr><th>#</th><th>Due date</th><th class="num">Share %</th>
      <th class="num">Amount</th><th class="num">Paid</th><th>Status</th></tr></thead><tbody>${d.installments.map((i) => `<tr><td>${i.instlmnt_id}</td><td>${i.due_date}</td>
      <td class="num">${Number(i.inst_prcnt)}</td><td class="num">${fmt(i.ins_total)}</td><td class="num">${fmt(i.paid_to_date)}</td>
      <td>${i.status === "O" ? '<span class="status O">Open</span>' : '<span class="status C">Closed</span>'}</td></tr>`).join("")}</tbody></table></div>` : ""}</div>`;
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
  const items = await api("/items");
  const L = state.lookups, side = t.side;
  const taxes = L.tax_groups.filter((x) => x.category === (side === "S" ? "O" : "I"));
  const rate = (code) => Number((L.tax_groups.find((x) => x.code === code) || {}).rate || 0);
  const sellable = items.filter((i) => !i.frozen && (side === "S" ? i.sell_item : side === "P" ? i.prchse_item : i.invnt_item)
    && (["delivery", "return"].includes(t.kind) ? i.invnt_item : true));
  const whsOpts = (sel) => state.warehouses.map((w) => opt(w.whs_code, w.whs_code, sel)).join("");
  const prjOpts = (sel) => opt("", "") + O.projects().map(([v, l]) => opt(v, v, sel)).join("");
  const defs = docHeaderDefs(t, from ? "copy" : "new");
  c.innerHTML = `<div class="page-head"><div><h1>${esc(t.name)}</h1><div class="sub">New document${t.bases.length ? ` · copy from ${t.bases.map((b) => esc(DOC_NAMES[b])).join(", ")}` : ""}</div></div>
      <a class="btn secondary" href="#/docs?obj=${obj}">Back to list</a></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(defs, {}, "d")}</div></div></div>
    <div class="card"><div class="card-body">
      <div style="overflow-x:auto"><table class="lines"><thead id="d-head"></thead><tbody id="d-lines"></tbody></table></div>
      <div style="display:flex;gap:8px;margin-top:8px"><button class="btn secondary small" id="d-add">+ Line</button>
        ${t.bases.length ? '<button class="btn secondary small" id="d-copy">Copy From…</button>' : ""}</div>
      <div id="d-sources"></div>
      ${side !== "I" ? `<div class="totals" style="margin-top:12px">
        <div><span>Total before discount</span><b id="t-before">0.00</b></div>
        <div><span>Discount %</span><input id="d-disc" type="number" min="0" max="99.99" step="0.01" value="0" style="width:80px;text-align:right"></div>
        <div><span>Discount</span><b id="t-disc">0.00</b></div>
        <div><span>Tax</span><b id="t-vat">0.00</b></div><div class="grand"><span>Total (<span id="t-cur">${esc(state.company.main_curncy)}</span>)</span><b id="t-total">0.00</b></div>
        <div id="t-lc-row" style="display:none"><span>Total (LC)</span><b id="t-lc">0.00</b></div></div>` : ""}
      <button class="btn" id="d-post" style="margin-top:12px">Add</button>
    </div></div>`;

  const type = () => ($("#d-doc_type") ? $("#d-doc_type").value : "I");
  const bpCode = () => ($("#d-card_code") ? $("#d-card_code").value : "");
  const bpRow = () => state.partners.find((b) => b.card_code === bpCode());
  let bpInfo = { contacts: [], addresses: [] };
  let docRate = 1;
  const docCur = () => ($("#d-doc_cur") ? $("#d-doc_cur").value : state.company.main_curncy);
  // currency -> rate of the posting date; prices of not copied lines are converted from the local currency
  const loadRate = async (reprice = true) => {
    if (!$("#d-doc_cur")) return;
    try { docRate = await rateOf(docCur(), $("#d-doc_date").value); } catch (e) { toast(e.message, "bad"); docRate = 0; }
    $("#d-doc_rate").value = docRate;
    if ($("#t-cur")) $("#t-cur").textContent = docCur();
    if ($("#t-lc-row")) $("#t-lc-row").style.display = docCur() === state.company.main_curncy ? "none" : "";
    if (reprice) $$("#d-lines tr").forEach((tr) => { const s = $(".l-item", tr); if (s && s.value && !tr.base) s.onchange(); });
    recalc();
  };
  // business partner -> defaults of contact, sales employee, project, addresses, payment terms, tax ID, discount
  const applyPartner = async (keep = {}) => {
    const b = bpRow();
    bpInfo = await partnerDetail(b && b.card_code);
    const fill = (k, options, value) => { const e = $(`#d-${k}`); if (e) e.innerHTML = opt("", "") + options.map(([v, l]) => opt(v, l, value)).join(""); };
    const def = (k, v) => (keep[k] !== undefined && keep[k] !== null ? keep[k] : v);
    const contact = bpInfo.contacts.find((x) => x.name === (b || {}).cntct_prsn);
    fill("cntct_code", bpInfo.contacts.filter((x) => x.active).map((x) => [x.cntct_code, x.name]), def("cntct_code", contact && contact.cntct_code));
    fill("pay_to_code", bpInfo.addresses.filter((a) => a.adres_type === "B").map((a) => [a.address, a.address]), def("pay_to_code", (b || {}).bill_to_def));
    fill("ship_to_code", bpInfo.addresses.filter((a) => a.adres_type === "S").map((a) => [a.address, a.address]), def("ship_to_code", (b || {}).ship_to_def));
    if (b) {
      $("#d-slp_code").value = def("slp_code", b.slp_code ?? -1) ?? -1;
      $("#d-project").value = def("project", b.project_cod) || "";
      $("#d-group_num").value = b.group_num ?? "";
      $("#d-lic_trad_num").value = b.lic_trad_num || "";
      $("#d-disc").value = Number(def("disc_prcnt", b.discount) || 0);
      if ($("#d-doc_cur")) $("#d-doc_cur").value = def("doc_cur", b.currency !== "##" ? b.currency : state.company.main_curncy);
      await loadRate(false);
    }
    showAddresses();
    $$("#d-lines tr").forEach((tr) => { const s = $(".l-item", tr); if (s && s.value && !tr.base) s.onchange(); else if (!tr.base && b && b.vat_group && $(".l-vat", tr) && type() === "S") $(".l-vat", tr).value = b.vat_group; });
    recalc();
  };
  const addrText = (a) => (a ? [a.street, a.block, [a.zip_code, a.city].filter(Boolean).join(" "), a.county, a.state, a.country].filter(Boolean).join(", ") : "");
  const showAddresses = () => {
    if (!$("#d-address")) return;
    $("#d-address").value = addrText(bpInfo.addresses.find((a) => a.adres_type === "B" && a.address === $("#d-pay_to_code").value));
    $("#d-address2").value = addrText(bpInfo.addresses.find((a) => a.adres_type === "S" && a.address === $("#d-ship_to_code").value));
  };
  if ($("#d-pay_to_code")) { $("#d-pay_to_code").onchange = showAddresses; $("#d-ship_to_code").onchange = showAddresses; }

  const head = () => {
    const S = type() === "S";
    $("#d-head").innerHTML = side === "I"
      ? `<tr><th>Item No.</th><th>Description</th><th class="num">Quantity</th><th>UoM</th>${t.kind === "transfer" ? "<th>From whs</th><th>To whs</th>" : "<th>Whs</th>"}
         ${t.kind === "receipt" ? '<th class="num w-amt">Unit cost</th><th class="num">Total</th>' : ""}${t.kind === "transfer" ? "" : "<th>G/L account</th>"}<th>Project</th><th></th></tr>`
      : `<tr>${S ? "<th>Description</th><th>G/L account</th>" : '<th>Item No.</th><th>Description</th><th class="num">Quantity</th><th>UoM</th>'}
         <th class="num w-amt">${S ? "Amount" : "Unit price"}</th>${S ? "" : '<th class="num">Disc. %</th><th class="num">Price after disc.</th>'}<th>Tax code</th>
         <th class="num">Tax amount</th><th class="num">Total (LC)</th><th class="num">Gross total</th>${S ? "" : "<th>Whs</th>"}<th>Del. date</th><th>Project</th><th>Free text</th><th>Base</th><th></th></tr>`;
  };
  const addLine = (v = {}) => {
    const tr = document.createElement("tr");
    tr.base = v.base_type ? { base_type: v.base_type, base_entry: v.base_entry, base_line: v.base_line } : null;
    const lock = tr.base ? " disabled" : "";
    const vat = v.vat_group || ((bpRow() || {}).vat_group);
    const tail = `<td><input class="l-ship" type="date" value="${esc(v.ship_date || "")}"></td><td><select class="l-prj">${prjOpts(v.project)}</select></td>
      <td><input class="l-free" maxlength="100" value="${esc(v.free_txt || "")}"></td>
      <td class="help">${tr.base ? `${esc(transTypeName(v.base_type))} ${esc(v.base_ref)}` : ""}</td><td><button class="btn ghost small l-del">✕</button></td>`;
    const amounts = `<td><select class="l-vat">${taxes.map((x) => opt(x.code, x.code, vat)).join("")}</select></td>
      <td class="num l-vatsum">0.00</td><td class="num l-total">0.00</td><td class="num l-gross">0.00</td>`;
    if (side === "I") {
      const it = items.find((i) => i.item_code === v.item_code);
      tr.innerHTML = `<td><select class="l-item">${opt("", "— item —")}${sellable.map((i) => opt(i.item_code, `${i.item_code} — ${i.item_name}`, v.item_code)).join("")}</select></td>
        <td><input class="l-desc" maxlength="100" value="${esc(v.dscription || (it && it.item_name) || "")}"></td>
        <td class="num"><input class="l-qty" type="number" step="any" min="0" value="${v.quantity ?? 1}" style="width:80px"></td><td class="l-uom">${esc((it && it.invntry_uom) || "")}</td>
        ${t.kind === "transfer" ? `<td><select class="l-from">${whsOpts($("#d-from_whs").value)}</select></td><td><select class="l-whs">${whsOpts($("#d-to_whs").value)}</select></td>`
          : `<td><select class="l-whs">${whsOpts(v.whs_code || (it && it.dflt_wh) || "01")}</select></td>`}
        ${t.kind === "receipt" ? '<td class="num"><input class="l-price" type="number" step="0.01" min="0"></td><td class="num l-total">0.00</td>' : ""}
        ${t.kind === "transfer" ? "" : `<td><select class="l-acct">${opt("", "default (inventory offset)")}${accountOptions((a) => !a.control)}</select></td>`}
        <td><select class="l-prj">${prjOpts(v.project)}</select></td><td><button class="btn ghost small l-del">✕</button></td>`;
    } else if (type() === "S") {
      tr.innerHTML = `<td><input class="l-desc" maxlength="100" value="${esc(v.dscription || "")}"></td>
        <td><select class="l-acct"${lock}>${opt("", "— account —")}${accountOptions((a) => !a.control).replace(`value="${esc(v.acct_code)}"`, `value="${esc(v.acct_code)}" selected`)}</select></td>
        <td class="num"><input class="l-price" type="number" step="0.01" min="0" value="${v.price ?? ""}"></td>${amounts}${tail}`;
    } else {
      const it = items.find((i) => i.item_code === v.item_code);
      tr.innerHTML = `<td><select class="l-item"${lock}>${opt("", "— item —")}${sellable.map((i) => opt(i.item_code, `${i.item_code} — ${i.item_name}`, v.item_code)).join("")}</select></td>
        <td><input class="l-desc" maxlength="100" value="${esc(v.dscription || (it && it.item_name) || "")}"></td>
        <td class="num"><input class="l-qty" type="number" step="any" min="0" value="${v.quantity ?? 1}" style="width:80px">${tr.base ? `<div class="help">open ${qtyFmt(v.quantity)}</div>` : ""}</td>
        <td class="l-uom">${esc((it && (side === "S" ? it.sal_unit_msr : it.buy_unit_msr)) || (it && it.invntry_uom) || "")}</td>
        <td class="num"><input class="l-price" type="number" step="0.01" min="0" value="${v.price ?? ""}"></td>
        <td class="num"><input class="l-disc" type="number" step="0.01" min="0" max="100" value="${Number(v.disc_prcnt || 0)}" style="width:70px"></td>
        <td class="num l-after">0.00</td>${amounts}<td><select class="l-whs">${whsOpts(v.whs_code || (it && it.dflt_wh) || "01")}</select></td>${tail}`;
    }
    const sel = $(".l-item", tr);
    if (sel) sel.onchange = async () => {
      const i = items.find((x) => x.item_code === sel.value);
      if (!i) return;
      $(".l-desc", tr).value = i.item_name;
      $(".l-uom", tr).textContent = (side === "S" ? i.sal_unit_msr : side === "P" ? i.buy_unit_msr : null) || i.invntry_uom || "";
      if ($(".l-vat", tr)) $(".l-vat", tr).value = (side === "S" ? i.vat_gourp_sa : i.vat_group_pu) || $(".l-vat", tr).value;
      if (i.dflt_wh && t.kind !== "transfer") $(".l-whs", tr).value = i.dflt_wh;
      const price = $(".l-price", tr);
      if (price) {
        const pl = $("#d-price_list") && $("#d-price_list").value;
        if (side === "I") price.value = pl ? Number((await api(`/items/${encodeURIComponent(i.item_code)}/price?list_num=${pl}`)).price).toFixed(2)
          : Number(i.avg_price || i.last_pur_prc).toFixed(2);
        else if (bpCode()) price.value = (Number((await api(`/items/${encodeURIComponent(i.item_code)}/price?card_code=${encodeURIComponent(bpCode())}`)).price) / (docRate || 1)).toFixed(2);
      }
      recalc();
    };
    $("#d-lines").appendChild(tr);
    $$("input,select", tr).forEach((i) => i.addEventListener("input", recalc));
    $(".l-del", tr).onclick = () => { tr.remove(); recalc(); };
    recalc();
  };
  const round = (n) => Math.round(n * 100) / 100;
  const recalc = () => {
    let before = 0, vat = 0;
    const disc = side === "I" ? 0 : Number($("#d-disc").value || 0) / 100;
    $$("#d-lines tr").forEach((tr) => {
      const qty = side !== "I" && type() === "S" ? 1 : Number(($(".l-qty", tr) || {}).value || 0);
      const after = Number(($(".l-price", tr) || {}).value || 0) * (1 - Number(($(".l-disc", tr) || {}).value || 0) / 100);
      const total = round(qty * after);
      if ($(".l-after", tr)) $(".l-after", tr).textContent = fmt(after);
      if ($(".l-total", tr)) $(".l-total", tr).textContent = fmt(total);
      if (side === "I") return;
      const net = round(total * (1 - disc)), tax = round(net * rate($(".l-vat", tr).value) / 100);
      $(".l-vatsum", tr).textContent = fmt(tax);
      $(".l-gross", tr).textContent = fmt(net + tax);
      before += total; vat += tax;
    });
    if (side === "I") return;
    const discount = round(before * disc);
    $("#t-before").textContent = fmt(before); $("#t-disc").textContent = fmt(discount); $("#t-vat").textContent = fmt(vat);
    $("#t-total").textContent = fmt(before - discount + vat);
    if ($("#t-lc")) $("#t-lc").textContent = fmt($$("#d-lines tr").reduce((s, tr) => {
      const net = round(Number(($(".l-total", tr) || {}).textContent?.replace(/[^0-9.-]/g, "") || 0) * (1 - disc));
      return s + round(net * docRate) + round(round(net * rate($(".l-vat", tr).value) / 100) * docRate);
    }, 0));
  };
  const reset = () => { head(); $("#d-lines").innerHTML = ""; addLine(); };
  if ($("#d-doc_type")) $("#d-doc_type").onchange = reset;
  if ($("#d-disc")) $("#d-disc").oninput = recalc;
  if ($("#d-card_code")) $("#d-card_code").onchange = () => applyPartner();
  if ($("#d-doc_cur")) { $("#d-doc_cur").onchange = () => loadRate(); $("#d-doc_date").addEventListener("change", () => loadRate()); }
  $("#d-add").onclick = () => addLine();
  head();

  const addFromSource = (src) => {
    if ($("#d-doc_type") && $("#d-doc_type").value !== src.doc_type) { $("#d-doc_type").value = src.doc_type; head(); $("#d-lines").innerHTML = ""; }
    $$("#d-lines tr").forEach((tr) => { if (!tr.base && !(($(".l-item", tr) || {}).value || ($(".l-acct", tr) || {}).value)) tr.remove(); });
    src.lines.forEach((l) => addLine({ ...l, quantity: Number(l.open_qty), price: Number(l.price).toFixed(2), base_type: src.obj,
      base_entry: src.doc_entry, base_line: l.line_num, base_ref: src.doc_num }));
  };
  if ($("#d-copy")) $("#d-copy").onclick = async () => {
    if (!bpCode()) return toast("Select the business partner first", "bad");
    const sources = await api(`/documents/${obj}/copy-sources?card_code=${encodeURIComponent(bpCode())}`);
    $("#d-sources").innerHTML = `<div class="card" style="margin-top:10px"><div class="card-head">Open documents of ${esc(bpCode())}</div>
      <table><thead><tr><th></th><th>Document</th><th>Date</th><th>Open lines</th><th class="num">Total</th></tr></thead><tbody>
      ${sources.map((src, k) => `<tr><td><input type="checkbox" class="src-pick" data-k="${k}"></td><td>${esc(src.name)} ${src.doc_num}</td><td>${src.doc_date}</td>
        <td>${src.lines.map((l) => `${esc(l.item_code || l.dscription)} × ${qtyFmt(l.open_qty)}`).join(", ")}</td><td class="num">${fmt(src.doc_total)}</td></tr>`).join("")
        || `<tr><td colspan="5" class="empty">No open documents to copy from.</td></tr>`}</tbody></table>
      ${sources.length ? '<div class="card-body"><button class="btn small" id="src-ok">Copy selected</button></div>' : ""}</div>`;
    const ok = $("#src-ok");
    if (ok) ok.onclick = async () => {
      const picked = $$(".src-pick:checked").map((cb) => sources[cb.dataset.k]);
      if (picked.length) {  // like B1, the header (contact, sales employee, project, addresses, discount) comes from the base
        const base = await api(`/documents/${picked[0].obj}/${picked[0].doc_entry}`);
        await applyPartner(base);
        $("#d-disc").value = Number(base.disc_prcnt || 0);
      }
      picked.forEach(addFromSource);
      $("#d-sources").innerHTML = "";
      recalc();
    };
  };

  if (from) {  // "Copy to" from a base document
    const [bobj, bentry] = from.split(":");
    const base = await api(`/documents/${bobj}/${bentry}`);
    $("#d-card_code").value = base.card_code;
    await applyPartner(base);
    addFromSource({ obj: bobj, doc_entry: base.doc_entry, doc_num: base.doc_num, doc_type: base.doc_type,
      lines: base.lines.filter((l) => l.line_status === "O" && Number(l.open_qty) > 0).map((l) => ({ ...l, price: l.price_bef_di })) });
    recalc();
  } else addLine();

  $("#d-post").onclick = async () => {
    const h = readFields(defs.filter((f) => !["doc_type", "price_list", "address", "address2", "group_num", "lic_trad_num"].includes(f.k)), "d");
    const body = { ...h, doc_type: type(), lines: [] };
    if ($("#d-card_code")) body.card_code = bpCode() || null;
    if (side !== "I") body.disc_prcnt = Number($("#d-disc").value || 0);
    $$("#d-lines tr").forEach((tr) => {
      const val = (cls) => { const e = $(cls, tr); return e && e.value !== "" ? e.value : null; };
      const num = (cls) => { const v = val(cls); return v === null ? null : Number(v); };
      const line = { ...(tr.base || {}), vat_group: val(".l-vat"), disc_prcnt: num(".l-disc"), price: num(".l-price"),
        dscription: val(".l-desc"), ship_date: val(".l-ship"), free_txt: val(".l-free"), project: val(".l-prj"), acct_code: val(".l-acct") };
      if (side !== "I" && type() === "S") line.quantity = 1;
      else Object.assign(line, { item_code: val(".l-item"), quantity: num(".l-qty") || 0, whs_code: val(".l-whs"), from_whs_cod: val(".l-from") });
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

views["tax-report"] = async (c) => {
  const from = query().get("from") || yearStart(), to = query().get("to") || yearEnd();
  const r = await api(`/reports/tax?date_from=${from}&date_to=${to}`);
  c.innerHTML = `<div class="page-head"><div><h1>Tax Report (GST)</h1><div class="sub">${from} – ${to} · output and input tax by component</div></div></div>
    ${periodToolbar(from, to)}
    <div class="tiles"><div class="tile"><div class="label">Output tax</div><div class="value">${fmt(r.total_output)}</div></div>
      <div class="tile"><div class="label">Input tax credit</div><div class="value">${fmt(r.total_input)}</div></div>
      <div class="tile"><div class="label">Net tax payable</div><div class="value ${Number(r.net_payable) > 0 ? "bad" : "good"}">${fmt(r.net_payable)}</div></div></div>
    <div class="card"><div class="card-head">Summary by component</div><table><thead><tr><th>Component</th><th class="num">Output tax</th><th class="num">Input tax credit</th><th class="num">Net payable</th></tr></thead>
      <tbody>${r.summary.map((x) => `<tr><td>${esc(x.component)}</td><td class="num">${fmt(x.output)}</td><td class="num">${fmt(x.input)}</td><td class="num">${fmt(x.net_payable)}</td></tr>`).join("")
        || `<tr><td colspan="4" class="empty">No tax postings in this period.</td></tr>`}</tbody>
      <tfoot><tr><td>Total</td><td class="num">${fmt(r.total_output)}</td><td class="num">${fmt(r.total_input)}</td><td class="num">${fmt(r.net_payable)}</td></tr></tfoot></table></div>
    <div class="card"><div class="card-head">By tax code</div><table><thead><tr><th>Tax code</th><th>Name</th><th>Component</th><th>G/L account</th><th class="num">Output</th><th class="num">Input</th></tr></thead>
      <tbody>${r.lines.map((x) => `<tr><td class="mono">${esc(x.tax_code)}</td><td>${esc(x.tax_name)}</td><td>${esc(x.component)}</td><td class="mono">${esc(x.account)}</td>
        <td class="num">${Number(x.output) ? fmt(x.output) : ""}</td><td class="num">${Number(x.input) ? fmt(x.input) : ""}</td></tr>`).join("")
        || `<tr><td colspan="6" class="empty">No tax postings in this period.</td></tr>`}</tbody></table></div>`;
  bindToolbar("tax-report");
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

document.addEventListener("DOMContentLoaded", boot);
