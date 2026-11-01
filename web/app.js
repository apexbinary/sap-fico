/* FI/CO web client — vanilla JS SPA talking to the FastAPI backend at /api. */
"use strict";

const API = "/api";
const state = {
  companyCodes: [],
  bukrs: null,
  gjahr: new Date().getFullYear(),
  glAccounts: [],
  customers: [],
  vendors: [],
  docTypes: [],
  postingKeys: [],
  taxCodes: [],
};

// ---------- helpers ----------
async function api(path, opts) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || res.statusText || "Request failed");
  return body;
}
const $ = (sel, root = document) => root.querySelector(sel);
const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; };
const fmt = (n) => Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));
const todayISO = () => new Date().toISOString().slice(0, 10);

function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast show " + kind;
  setTimeout(() => (t.className = "toast"), 3200);
}

// ---------- bootstrap ----------
async function boot() {
  try {
    const health = await fetch("/health").then((r) => r.json());
    $("#dbBadge").textContent = (health && health.db) ? health.db : "db";
  } catch (_) {}
  state.companyCodes = await api("/master/company-codes");
  if (state.companyCodes.length) {
    state.bukrs = state.companyCodes[0].bukrs;
    $("#ccBadge").textContent = state.bukrs + " · " + state.companyCodes[0].butxt;
  }
  await loadMasterData();
  window.addEventListener("hashchange", route);
  $("#navToggle").onclick = () => $("#sidenav").classList.toggle("collapsed");
  if (!location.hash) location.hash = "#/dashboard";
  route();
}

async function loadMasterData() {
  if (!state.bukrs) return;
  const [gl, cust, vend, dt, pk, tx] = await Promise.all([
    api("/master/gl-accounts?bukrs=" + state.bukrs),
    api("/master/customers?bukrs=" + state.bukrs),
    api("/master/vendors?bukrs=" + state.bukrs),
    api("/master/document-types"),
    api("/master/posting-keys"),
    api("/master/tax-codes"),
  ]);
  Object.assign(state, { glAccounts: gl, customers: cust, vendors: vend, docTypes: dt, postingKeys: pk, taxCodes: tx });
}

// ---------- router ----------
const views = {};
function route() {
  const view = (location.hash.replace("#/", "") || "dashboard").split("?")[0];
  document.querySelectorAll(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  const render = views[view] || views.dashboard;
  const c = $("#content");
  c.innerHTML = '<div class="loading">Loading…</div>';
  Promise.resolve(render(c)).catch((e) => (c.innerHTML = `<div class="empty">Error: ${esc(e.message)}</div>`));
}

// ---------- Dashboard ----------
views.dashboard = async (c) => {
  const tb = await api(`/reports/trial-balance?bukrs=${state.bukrs}&gjahr=${state.gjahr}`);
  const docs = await api(`/master/documents?bukrs=${state.bukrs}&gjahr=${state.gjahr}&limit=8`);
  const assets = tb.lines.filter((l) => l.balance > 0).reduce((s, l) => s + Number(l.balance), 0);
  c.innerHTML = `
    <div class="page-head"><div><h1>Dashboard</h1>
      <div class="sub">Company code ${esc(state.bukrs)} · fiscal year ${state.gjahr}</div></div></div>
    <div class="tiles">
      <div class="tile"><div class="label">Total Debit</div><div class="value">${fmt(tb.total_debit)}</div><div class="foot">local currency</div></div>
      <div class="tile"><div class="label">Total Credit</div><div class="value">${fmt(tb.total_credit)}</div><div class="foot">local currency</div></div>
      <div class="tile"><div class="label">Ledger Status</div><div class="value ${tb.balanced ? "good" : "bad"}">${tb.balanced ? "In Balance" : "Out!"}</div><div class="foot">debits = credits</div></div>
      <div class="tile"><div class="label">G/L Accounts</div><div class="value">${state.glAccounts.length}</div><div class="foot">in company code</div></div>
      <div class="tile"><div class="label">Documents</div><div class="value">${docs.length ? docs.length + "+" : 0}</div><div class="foot">posted this year</div></div>
    </div>
    <div class="card"><div class="card-head">Recent Documents <a class="btn small secondary" href="#/post">Post new</a></div>
      <table><thead><tr><th>Document</th><th>Type</th><th>Posting date</th><th>Header text</th><th class="num">Amount</th><th>Curr</th></tr></thead>
      <tbody>${docs.length ? docs.map((d) => `<tr>
        <td class="mono"><a href="#/documents?doc=${d.belnr}:${d.gjahr}">${d.belnr}/${d.gjahr}</a></td>
        <td>${d.blart}</td><td>${d.budat}</td><td>${esc(d.bktxt)}</td>
        <td class="num">${fmt(d.amount)}</td><td>${d.waers}</td></tr>`).join("")
        : `<tr><td colspan="6" class="empty">No documents yet — post one.</td></tr>`}</tbody></table>
    </div>`;
};

// ---------- Post Document ----------
let lineSeq = 0;
views.post = async (c) => {
  c.innerHTML = `
    <div class="page-head"><div><h1>Post Document</h1><div class="sub">Enter G/L / customer / vendor line items (FB01)</div></div></div>
    <div class="card"><div class="card-body">
      <div class="form-grid">
        <div class="field"><label class="req">Document type</label><select id="f-blart">${state.docTypes.map((d) => `<option value="${d.blart}">${d.blart} — ${esc(d.ltext)}</option>`).join("")}</select></div>
        <div class="field"><label class="req">Document date</label><input id="f-bldat" type="date" value="${todayISO()}"></div>
        <div class="field"><label class="req">Posting date</label><input id="f-budat" type="date" value="${todayISO()}"></div>
        <div class="field"><label class="req">Currency</label><input id="f-waers" value="${esc(ccWaers())}"></div>
        <div class="field"><label>Reference (XBLNR)</label><input id="f-xblnr"></div>
        <div class="field"><label>Header text</label><input id="f-bktxt"></div>
      </div>
    </div></div>
    <div class="card"><div class="card-head">Line Items</div><div class="card-body">
      <table class="lines"><thead><tr>
        <th style="width:150px">Posting key</th><th>Account</th><th class="num w-amt">Amount</th>
        <th style="width:90px">Tax</th><th style="width:70px">Auto-tax</th><th>Cost center</th><th>Text</th><th></th>
      </tr></thead><tbody id="lines"></tbody></table>
      <button class="btn secondary small" id="addLine" style="margin-top:10px">+ Add line</button>
      <div class="balance-row">
        <span>Debits: <span class="amt" id="sumD">0.00</span></span>
        <span>Credits: <span class="amt" id="sumC">0.00</span></span>
        <span id="balChip" class="chip no">Not balanced</span>
      </div>
      <button class="btn" id="postBtn" disabled>Post Document</button>
    </div></div>`;

  $("#addLine").onclick = () => { addLine(); recalc(); };
  $("#postBtn").onclick = submitDoc;
  addLine("40"); addLine("50"); recalc();
};

function ccWaers() { const cc = state.companyCodes.find((c) => c.bukrs === state.bukrs); return cc ? cc.waers : "EUR"; }

function addLine(defaultBschl) {
  const id = ++lineSeq;
  const row = el(`<tr data-id="${id}">
    <td><select class="l-bschl">${state.postingKeys.map((p) => `<option value="${p.bschl}">${p.bschl} ${esc(p.ltext)} (${p.shkzg})</option>`).join("")}</select></td>
    <td><select class="l-acct"></select></td>
    <td class="num"><input class="l-amt" type="number" step="0.01" min="0" value="0.00"></td>
    <td><select class="l-tax"><option value="">—</option>${state.taxCodes.map((t) => `<option value="${t.mwskz}">${t.mwskz} ${esc(t.text1)}</option>`).join("")}</select></td>
    <td style="text-align:center"><input class="l-autotax" type="checkbox"></td>
    <td><input class="l-kostl" placeholder="cost ctr"></td>
    <td><input class="l-text" placeholder="item text"></td>
    <td><button class="btn ghost small l-del">✕</button></td>
  </tr>`);
  $("#lines").appendChild(row);
  const sel = $(".l-bschl", row);
  if (defaultBschl) sel.value = defaultBschl;
  sel.onchange = () => { fillAccounts(row); recalc(); };
  $(".l-amt", row).oninput = recalc;
  $(".l-del", row).onclick = () => { row.remove(); recalc(); };
  fillAccounts(row);
}

function koartOf(bschl) { const p = state.postingKeys.find((p) => p.bschl === bschl); return p ? p.koart : "S"; }
function shkzgOf(bschl) { const p = state.postingKeys.find((p) => p.bschl === bschl); return p ? p.shkzg : "S"; }

function fillAccounts(row) {
  const koart = koartOf($(".l-bschl", row).value);
  const sel = $(".l-acct", row);
  let opts = [];
  if (koart === "S") opts = state.glAccounts.map((a) => `<option value="${a.saknr}">${a.saknr} — ${esc(a.name)}</option>`);
  else if (koart === "D") opts = state.customers.map((a) => `<option value="${a.kunnr}">${a.kunnr} — ${esc(a.name1)}</option>`);
  else if (koart === "K") opts = state.vendors.map((a) => `<option value="${a.lifnr}">${a.lifnr} — ${esc(a.name1)}</option>`);
  sel.innerHTML = opts.join("") || `<option value="">(none)</option>`;
}

function recalc() {
  let d = 0, cr = 0;
  document.querySelectorAll("#lines tr").forEach((row) => {
    const amt = Number($(".l-amt", row).value || 0);
    if (shkzgOf($(".l-bschl", row).value) === "S") d += amt; else cr += amt;
  });
  $("#sumD").textContent = fmt(d);
  $("#sumC").textContent = fmt(cr);
  const balanced = d.toFixed(2) === cr.toFixed(2) && d > 0;
  const chip = $("#balChip");
  chip.className = "chip " + (balanced ? "ok" : "no");
  chip.textContent = balanced ? "Balanced" : "Not balanced";
  $("#postBtn").disabled = !balanced;
}

async function submitDoc() {
  const lines = [...document.querySelectorAll("#lines tr")].map((row) => ({
    bschl: $(".l-bschl", row).value,
    account: $(".l-acct", row).value,
    wrbtr: $(".l-amt", row).value,
    mwskz: $(".l-tax", row).value || null,
    calculate_tax: $(".l-autotax", row).checked,
    kostl: $(".l-kostl", row).value || null,
    sgtxt: $(".l-text", row).value || null,
  }));
  const payload = {
    bukrs: state.bukrs, blart: $("#f-blart").value, bldat: $("#f-bldat").value,
    budat: $("#f-budat").value, waers: $("#f-waers").value.toUpperCase(),
    xblnr: $("#f-xblnr").value || null, bktxt: $("#f-bktxt").value || null,
    kokrs: null, lines,
  };
  try {
    const doc = await api("/documents", { method: "POST", body: JSON.stringify(payload) });
    toast(`Document ${doc.belnr}/${doc.gjahr} posted`, "good");
    location.hash = `#/documents?doc=${doc.belnr}:${doc.gjahr}`;
  } catch (e) {
    toast(e.message, "bad");
  }
}

// ---------- Documents ----------
views.documents = async (c) => {
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  const open = q.get("doc");
  const docs = await api(`/master/documents?bukrs=${state.bukrs}&limit=100`);
  c.innerHTML = `
    <div class="page-head"><div><h1>Documents</h1><div class="sub">Company code ${esc(state.bukrs)}</div></div>
      <a class="btn" href="#/post">+ Post Document</a></div>
    <div class="card"><table><thead><tr><th>Document</th><th>Type</th><th>Doc date</th><th>Posting</th><th>Period</th><th>Text</th><th class="num">Amount</th><th>Curr</th><th>Items</th></tr></thead>
    <tbody>${docs.map((d) => `<tr style="cursor:pointer" onclick="location.hash='#/documents?doc=${d.belnr}:${d.gjahr}'">
      <td class="mono">${d.belnr}/${d.gjahr}</td><td>${d.blart}</td><td>${d.bldat}</td><td>${d.budat}</td>
      <td>${d.monat}</td><td>${esc(d.bktxt)}</td><td class="num">${fmt(d.amount)}</td><td>${d.waers}</td><td>${d.items}</td></tr>`).join("") || `<tr><td colspan="9" class="empty">No documents.</td></tr>`}</tbody></table></div>
    <div id="docDetail"></div>`;
  if (open) {
    const [belnr, gjahr] = open.split(":");
    const d = await api(`/documents/${state.bukrs}/${gjahr}/${belnr}`);
    $("#docDetail").appendChild(el(`<div class="card"><div class="card-head">Document ${d.belnr}/${d.gjahr} — ${d.blart} · period ${d.monat} · ${d.waers}</div>
      <table><thead><tr><th>Itm</th><th>PK</th><th>D/C</th><th>Account</th><th>Tax</th><th class="num">Doc amount</th><th class="num">Local amount</th><th>Text</th></tr></thead>
      <tbody>${d.items.map((i) => `<tr><td>${i.buzei}</td><td>${i.bschl}</td>
        <td><span class="chip ${i.shkzg === "S" ? "dr" : "cr"}">${i.shkzg === "S" ? "Debit" : "Credit"}</span></td>
        <td class="mono">${esc(i.kunnr || i.lifnr || i.hkont)}</td><td>${esc(i.mwskz || "")}</td>
        <td class="num">${fmt(i.wrbtr)}</td><td class="num">${fmt(i.dmbtr)}</td><td>${esc(i.sgtxt || "")}</td></tr>`).join("")}</tbody></table></div>`));
  }
};

// ---------- Trial Balance ----------
views["trial-balance"] = async (c) => {
  const tb = await api(`/reports/trial-balance?bukrs=${state.bukrs}&gjahr=${state.gjahr}`);
  c.innerHTML = `
    <div class="page-head"><div><h1>Trial Balance</h1><div class="sub">Company code ${esc(state.bukrs)} · FY ${tb.gjahr}</div></div>
      <span class="chip ${tb.balanced ? "ok" : "no"}">${tb.balanced ? "Balanced" : "Out of balance"}</span></div>
    <div class="card"><table><thead><tr><th>Account</th><th>Name</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance</th></tr></thead>
    <tbody>${tb.lines.map((l) => `<tr><td class="mono">${l.saknr}</td><td>${esc(l.name)}</td>
      <td class="num">${Number(l.debit) ? fmt(l.debit) : ""}</td><td class="num">${Number(l.credit) ? fmt(l.credit) : ""}</td>
      <td class="num" style="color:${Number(l.balance) >= 0 ? "var(--good)" : "var(--bad)"}">${fmt(l.balance)}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">No postings.</td></tr>`}</tbody>
    <tfoot><tr><td colspan="2">Total</td><td class="num">${fmt(tb.total_debit)}</td><td class="num">${fmt(tb.total_credit)}</td><td class="num">${fmt(Number(tb.total_debit) - Number(tb.total_credit))}</td></tr></tfoot></table></div>`;
};

// ---------- Open Items ----------
views["open-items"] = async (c) => {
  c.innerHTML = `
    <div class="page-head"><div><h1>Open Items</h1><div class="sub">Customer (A/R) and vendor (A/P) open items</div></div></div>
    <div class="toolbar">
      <div class="field"><label>Account type</label><select id="oi-koart"><option value="D">Customer (D)</option><option value="K">Vendor (K)</option></select></div>
      <div class="field"><label>Account</label><select id="oi-acct"></select></div>
      <label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="oi-open" checked> Only open</label>
      <button class="btn" id="oi-go">Show</button>
    </div>
    <div id="oi-result"></div>`;
  const fillAcct = () => {
    const koart = $("#oi-koart").value;
    const list = koart === "D" ? state.customers : state.vendors;
    $("#oi-acct").innerHTML = list.map((a) => `<option value="${a.kunnr || a.lifnr}">${a.kunnr || a.lifnr} — ${esc(a.name1)}</option>`).join("");
  };
  $("#oi-koart").onchange = fillAcct; fillAcct();
  $("#oi-go").onclick = async () => {
    const koart = $("#oi-koart").value, acct = $("#oi-acct").value, only = $("#oi-open").checked;
    const items = await api(`/reports/open-items?bukrs=${state.bukrs}&koart=${koart}&account=${acct}&only_open=${only}`);
    const total = items.reduce((s, i) => s + Number(i.amount), 0);
    $("#oi-result").innerHTML = `<div class="card"><table><thead><tr><th>Document</th><th>Posting date</th><th>Baseline</th><th>Assignment</th><th>Text</th><th class="num">Amount</th><th>Curr</th><th>Status</th></tr></thead>
      <tbody>${items.map((i) => `<tr><td class="mono">${i.belnr}/${i.gjahr}</td><td>${i.budat}</td><td>${i.zfbdt || ""}</td>
        <td>${esc(i.zuonr || "")}</td><td>${esc(i.sgtxt || "")}</td><td class="num">${fmt(i.amount)}</td><td>${i.waers}</td>
        <td><span class="chip ${i.cleared ? "ok" : "dr"}">${i.cleared ? "Cleared" : "Open"}</span></td></tr>`).join("") || `<tr><td colspan="8" class="empty">No items.</td></tr>`}</tbody>
      <tfoot><tr><td colspan="5">Balance</td><td class="num">${fmt(total)}</td><td colspan="2"></td></tr></tfoot></table></div>`;
  };
  $("#oi-go").click();
};

// ---------- G/L Accounts ----------
views["gl-accounts"] = async (c) => {
  c.innerHTML = `
    <div class="page-head"><div><h1>G/L Accounts</h1><div class="sub">Company code ${esc(state.bukrs)} · chart of accounts</div></div></div>
    <div class="card"><table><thead><tr><th>Account</th><th>Name</th><th>Recon. type</th><th>Tax cat.</th><th>Open item mgmt</th></tr></thead>
    <tbody>${state.glAccounts.map((a) => `<tr><td class="mono">${a.saknr}</td><td>${esc(a.name)}</td>
      <td>${a.mitkz ? ({ D: "Customers", K: "Vendors", A: "Assets" }[a.mitkz] || a.mitkz) : ""}</td>
      <td>${esc(a.mwskz || "")}</td><td>${a.xopvw ? "Yes" : ""}</td></tr>`).join("")}</tbody></table></div>`;
};

// ---------- Business Partners ----------
views.partners = async (c) => {
  c.innerHTML = `
    <div class="page-head"><div><h1>Business Partners</h1><div class="sub">Customers (A/R) and vendors (A/P)</div></div></div>
    <div class="card"><div class="card-head">Customers (KNA1 / KNB1)</div><table><thead><tr><th>Customer</th><th>Name</th><th>City</th><th>Country</th><th>Recon. acct</th></tr></thead>
      <tbody>${state.customers.map((a) => `<tr><td class="mono">${a.kunnr}</td><td>${esc(a.name1)}</td><td>${esc(a.ort01)}</td><td>${a.land1}</td><td class="mono">${a.akont || ""}</td></tr>`).join("")}</tbody></table></div>
    <div class="card"><div class="card-head">Vendors (LFA1 / LFB1)</div><table><thead><tr><th>Vendor</th><th>Name</th><th>City</th><th>Country</th><th>Recon. acct</th></tr></thead>
      <tbody>${state.vendors.map((a) => `<tr><td class="mono">${a.lifnr}</td><td>${esc(a.name1)}</td><td>${esc(a.ort01)}</td><td>${a.land1}</td><td class="mono">${a.akont || ""}</td></tr>`).join("")}</tbody></table></div>`;
};

// ---------- Fixed Assets ----------
views.assets = async (c) => {
  const assets = await api(`/assets?bukrs=${state.bukrs}`);
  c.innerHTML = `
    <div class="page-head"><div><h1>Fixed Assets</h1><div class="sub">Asset Accounting (FI-AA) · company code ${esc(state.bukrs)}</div></div></div>
    <div class="card"><div class="card-head">Asset Portfolio
      <button class="btn small secondary" id="depRun">Run Depreciation (period 1)</button></div>
      <table><thead><tr><th>Asset</th><th>Class</th><th>Description</th><th>Capitalized</th><th class="num">APC</th><th class="num">Depreciation</th><th class="num">Net book value</th></tr></thead>
      <tbody>${assets.map((a) => `<tr><td class="mono">${a.anln1}-${a.anln2}</td><td>${a.anlkl}</td><td>${esc(a.txt50)}</td>
        <td>${a.aktiv || "—"}</td><td class="num">${fmt(a.apc)}</td><td class="num">${fmt(a.depreciation)}</td><td class="num">${fmt(a.nbv)}</td></tr>`).join("") || `<tr><td colspan="7" class="empty">No assets yet.</td></tr>`}</tbody></table>
    </div>
    <div class="card"><div class="card-head">Create Asset</div><div class="card-body">
      <div class="form-grid">
        <div class="field"><label class="req">Asset number</label><input id="a-anln1" placeholder="000000002000"></div>
        <div class="field"><label>Class</label><input id="a-anlkl" value="00003000" readonly></div>
        <div class="field"><label class="req">Description</label><input id="a-txt"></div>
        <div class="field"><label>Useful life (years)</label><input id="a-life" type="number" value="5"></div>
        <div class="field"><label>Cost center</label><input id="a-kostl" value="0000001000"></div>
      </div>
      <button class="btn" id="a-create" style="margin-top:12px">Create Asset</button>
    </div></div>
    <div class="card"><div class="card-head">Post Acquisition (F-90)</div><div class="card-body">
      <div class="form-grid">
        <div class="field"><label class="req">Asset</label><select id="aq-asset">${assets.map((a) => `<option value="${a.anln1}">${a.anln1} — ${esc(a.txt50)}</option>`).join("")}</select></div>
        <div class="field"><label class="req">Amount</label><input id="aq-amt" type="number" step="0.01" value="0.00"></div>
        <div class="field"><label>Posting date</label><input id="aq-date" type="date" value="${todayISO()}"></div>
        <div class="field"><label>Offset vendor</label><select id="aq-vendor">${state.vendors.map((v) => `<option value="${v.lifnr}">${v.lifnr} — ${esc(v.name1)}</option>`).join("")}</select></div>
      </div>
      <button class="btn" id="aq-post" style="margin-top:12px">Post Acquisition</button>
    </div></div>`;

  $("#depRun").onclick = async () => {
    try { const r = await api("/assets/depreciation-run", { method: "POST", body: JSON.stringify({ bukrs: state.bukrs, gjahr: state.gjahr, period: 1 }) });
      toast(`Depreciation run ${r.run}: EUR ${r.total} over ${r.posted.length} asset(s)`, "good"); route(); }
    catch (e) { toast(e.message, "bad"); }
  };
  $("#a-create").onclick = async () => {
    try { await api("/assets", { method: "POST", body: JSON.stringify({ bukrs: state.bukrs, anln1: $("#a-anln1").value, txt50: $("#a-txt").value, useful_life_years: Number($("#a-life").value), kostl: $("#a-kostl").value || null }) });
      toast("Asset created", "good"); route(); }
    catch (e) { toast(e.message, "bad"); }
  };
  $("#aq-post").onclick = async () => {
    try { const r = await api("/assets/acquisition", { method: "POST", body: JSON.stringify({ bukrs: state.bukrs, anln1: $("#aq-asset").value, amount: $("#aq-amt").value, budat: $("#aq-date").value, offset_account: $("#aq-vendor").value, offset_is_vendor: true }) });
      toast(`Acquisition posted: FI doc ${r.belnr}/${r.gjahr}`, "good"); route(); }
    catch (e) { toast(e.message, "bad"); }
  };
};

// ---------- Bank Statements ----------
let bankItemSeq = 0;
views.bank = async (c) => {
  const [banks, statements] = await Promise.all([
    api(`/master/house-banks?bukrs=${state.bukrs}`),
    api(`/bank/statements?bukrs=${state.bukrs}`),
  ]);
  c.innerHTML = `
    <div class="page-head"><div><h1>Bank Statements</h1><div class="sub">Bank Accounting (FI-BL) · company code ${esc(state.bukrs)}</div></div></div>
    <div class="card"><div class="card-head">House Bank Accounts (T012K)</div>
      <table><thead><tr><th>House bank</th><th>Account ID</th><th>Bank key</th><th>Account no.</th><th>IBAN</th><th>Currency</th><th>G/L account</th></tr></thead>
      <tbody>${banks.map((b) => `<tr><td>${b.hbkid}</td><td>${b.hktid}</td><td>${b.bankl || ""}</td><td class="mono">${b.bankn}</td><td class="mono">${b.iban || ""}</td><td>${b.waers}</td><td class="mono">${b.hkont}</td></tr>`).join("")}</tbody></table></div>
    <div class="card"><div class="card-head">Statements</div>
      <table><thead><tr><th>Key</th><th>Date</th><th class="num">Opening</th><th class="num">Closing</th><th>Items</th><th>Status</th><th></th></tr></thead>
      <tbody>${statements.map((h) => `<tr><td class="mono">${h.kukey}</td><td>${h.adatu || ""}</td><td class="num">${fmt(h.opening)}</td><td class="num">${fmt(h.closing)}</td><td>${h.items}</td>
        <td><span class="chip ${h.posted ? "ok" : "dr"}">${h.posted ? "Posted" : "Open"}</span></td>
        <td>${h.posted ? "" : `<button class="btn small b-post" data-k="${h.kukey}">Post &amp; reconcile</button>`}</td></tr>`).join("") || `<tr><td colspan="7" class="empty">No statements.</td></tr>`}</tbody></table></div>
    <div class="card"><div class="card-head">Import Statement</div><div class="card-body">
      <div class="form-grid">
        <div class="field"><label>House bank</label><select id="s-hbk">${banks.map((b) => `<option value="${b.hbkid}:${b.hktid}">${b.hbkid}/${b.hktid}</option>`).join("")}</select></div>
        <div class="field"><label class="req">Statement key</label><input id="s-key" value="STMT${state.gjahr}001"></div>
        <div class="field"><label>Date</label><input id="s-date" type="date" value="${todayISO()}"></div>
        <div class="field"><label>Opening balance</label><input id="s-open" type="number" step="0.01" value="0.00"></div>
      </div>
      <table class="lines" style="margin-top:10px"><thead><tr><th class="num w-amt">Amount</th><th>D/C</th><th>Partner type</th><th>Partner</th><th>Note</th><th></th></tr></thead><tbody id="bankItems"></tbody></table>
      <button class="btn secondary small" id="addBankItem" style="margin-top:8px">+ Add line</button>
      <div style="margin-top:12px"><button class="btn" id="s-import">Import Statement</button></div>
    </div></div>`;

  document.querySelectorAll(".b-post").forEach((btn) => btn.onclick = async () => {
    try { const r = await api(`/bank/statements/${btn.dataset.k}/post?bukrs=${state.bukrs}`, { method: "POST", body: "{}" });
      toast(`Posted ${r.posted.length} item(s)`, "good"); route(); }
    catch (e) { toast(e.message, "bad"); }
  });
  $("#addBankItem").onclick = addBankItem;
  $("#s-import").onclick = async () => {
    const items = [...document.querySelectorAll("#bankItems tr")].map((row) => {
      const ptype = $(".bi-ptype", row).value;
      const pval = $(".bi-partner", row).value;
      return { amount: $(".bi-amt", row).value, shkzg: $(".bi-dc", row).value,
        kunnr: ptype === "D" ? pval : null, lifnr: ptype === "K" ? pval : null, note: $(".bi-note", row).value || null };
    });
    const [hbkid, hktid] = $("#s-hbk").value.split(":");
    try { await api("/bank/statements", { method: "POST", body: JSON.stringify({ bukrs: state.bukrs, hbkid, hktid, kukey: $("#s-key").value, statement_date: $("#s-date").value, opening: $("#s-open").value, items }) });
      toast("Statement imported", "good"); route(); }
    catch (e) { toast(e.message, "bad"); }
  };
  addBankItem();
};

function addBankItem() {
  const row = el(`<tr>
    <td class="num"><input class="bi-amt" type="number" step="0.01" value="0.00"></td>
    <td><select class="bi-dc"><option value="H">Credit (in)</option><option value="S">Debit (out)</option></select></td>
    <td><select class="bi-ptype"><option value="D">Customer</option><option value="K">Vendor</option></select></td>
    <td><select class="bi-partner"></select></td>
    <td><input class="bi-note" placeholder="note to payee"></td>
    <td><button class="btn ghost small bi-del">✕</button></td></tr>`);
  $("#bankItems").appendChild(row);
  const fill = () => {
    const t = $(".bi-ptype", row).value;
    const list = t === "D" ? state.customers : state.vendors;
    $(".bi-partner", row).innerHTML = list.map((a) => `<option value="${a.kunnr || a.lifnr}">${a.kunnr || a.lifnr} — ${esc(a.name1)}</option>`).join("");
  };
  $(".bi-ptype", row).onchange = fill; fill();
  $(".bi-del", row).onclick = () => row.remove();
}

boot();
