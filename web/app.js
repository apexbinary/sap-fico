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
      <button class="btn secondary" id="parkBtn" disabled>Park</button>
    </div></div>
    <details class="card"><summary class="card-head" style="cursor:pointer">Save as recurring entry (FBD1)</summary><div class="card-body">
      <div class="form-grid">
        <div class="field"><label class="req">First run</label><input id="rc-from" type="date" value="${todayISO()}"></div>
        <div class="field"><label class="req">Last run</label><input id="rc-to" type="date" value="${todayISO().slice(0, 4)}-12-31"></div>
        <div class="field"><label>Interval (months)</label><input id="rc-mon" type="number" min="1" max="12" value="1"></div>
        <div class="field"><label>Run day</label><input id="rc-day" type="number" min="1" max="31" placeholder="day of first run"></div>
      </div>
      <button class="btn secondary" id="recurBtn" style="margin-top:12px" disabled>Save recurring entry</button>
      <div class="help">Enter tax lines explicitly (auto-tax is not used for recurring entries). Post the copies under Recurring Entries.</div>
    </div></details>`;

  $("#addLine").onclick = () => { addLine(); recalc(); };
  const editRef = new URLSearchParams(location.hash.split("?")[1] || "").get("edit");
  if (editRef) return loadParked(editRef);
  $("#postBtn").onclick = () => submitDoc(false);
  $("#parkBtn").onclick = () => submitDoc(true);
  $("#recurBtn").onclick = submitRecurring;
  addLine("40"); addLine("50"); recalc();
};

// Document status chip: parked, deleted, reversed, reversal.
function docStatus(d) {
  if (d.bstat === "V") return `<span class="chip dr">Parked</span>`;
  if (d.bstat === "Z") return `<span class="chip no">Deleted</span>`;
  if (d.bstat === "D") return `<span class="chip dr">Recurring original</span>`;
  if (d.stblg) return `<span class="chip cr">${d.tcode === "FB08" ? "Reversal" : "Reversed"}</span>`;
  return "";
}

// FBV2: load a parked document into the entry form; auto-tax lines are regenerated on save.
async function loadParked(ref) {
  const [belnr, gjahr] = ref.split(":");
  const d = await api(`/documents/${state.bukrs}/${gjahr}/${belnr}`);
  if (d.bstat !== "V") { toast(`Document ${belnr} is not parked`, "bad"); return; }
  $(".page-head h1").textContent = `Change Parked Document ${d.belnr}/${d.gjahr}`;
  Object.entries({ "#f-blart": d.blart, "#f-bldat": d.bldat, "#f-budat": d.budat, "#f-waers": d.waers,
    "#f-xblnr": d.xblnr || "", "#f-bktxt": d.bktxt || "" }).forEach(([sel, v]) => ($(sel).value = v));
  $("#lines").innerHTML = "";
  const taxed = new Set(d.items.filter((i) => i.buzid === "T").map((i) => i.mwskz));
  d.items.filter((i) => i.buzid !== "T").forEach((i) => {
    addLine(i.bschl);
    const row = $("#lines").lastElementChild;
    $(".l-acct", row).value = i.kunnr || i.lifnr || i.hkont;
    $(".l-amt", row).value = Number(i.wrbtr).toFixed(2);
    $(".l-tax", row).value = i.mwskz || "";
    $(".l-autotax", row).checked = !!(i.mwskz && taxed.has(i.mwskz));
    $(".l-kostl", row).value = i.kostl || "";
    $(".l-text", row).value = i.sgtxt || "";
  });
  recalc();
  $("#postBtn").style.display = "none";
  $("#parkBtn").textContent = "Save parked document";
  $("#parkBtn").onclick = async () => {
    try {
      await api(`/documents/${state.bukrs}/${d.gjahr}/${d.belnr}`, { method: "PUT", body: JSON.stringify(docPayload()) });
      toast(`Parked document ${d.belnr} changed`, "good");
      location.hash = `#/documents?doc=${d.belnr}:${d.gjahr}`;
    } catch (e) { toast(e.message, "bad"); }
  };
}

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

// Options for a customer (D), vendor (K) or open-item-managed G/L account (S) dropdown.
function accountOptions(koart) {
  if (koart === "S") return state.glAccounts.filter((a) => a.xopvw && !a.mitkz).map((a) => `<option value="${a.saknr}">${a.saknr} — ${esc(a.name)}</option>`).join("");
  const list = koart === "D" ? state.customers : state.vendors;
  return list.map((a) => `<option value="${a.kunnr || a.lifnr}">${a.kunnr || a.lifnr} — ${esc(a.name1)}</option>`).join("");
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
  $("#parkBtn").disabled = !balanced;
  $("#recurBtn").disabled = !balanced;
}

function docPayload() {
  const lines = [...document.querySelectorAll("#lines tr")].map((row) => ({
    bschl: $(".l-bschl", row).value,
    account: $(".l-acct", row).value,
    wrbtr: $(".l-amt", row).value,
    mwskz: $(".l-tax", row).value || null,
    calculate_tax: $(".l-autotax", row).checked,
    kostl: $(".l-kostl", row).value || null,
    sgtxt: $(".l-text", row).value || null,
  }));
  return {
    bukrs: state.bukrs, blart: $("#f-blart").value, bldat: $("#f-bldat").value,
    budat: $("#f-budat").value, waers: $("#f-waers").value.toUpperCase(),
    xblnr: $("#f-xblnr").value || null, bktxt: $("#f-bktxt").value || null,
    kokrs: null, lines,
  };
}

async function submitRecurring() {
  const body = { document: docPayload(), dbbdt: $("#rc-from").value, dbedt: $("#rc-to").value,
    dbmon: Number($("#rc-mon").value || 1), dbtag: $("#rc-day").value ? Number($("#rc-day").value) : null };
  try {
    const r = await api("/recurring", { method: "POST", body: JSON.stringify(body) });
    toast(`Recurring entry ${r.belnr}/${r.gjahr} saved`, "good");
    location.hash = "#/recurring";
  } catch (e) { toast(e.message, "bad"); }
}

async function submitDoc(park) {
  const payload = docPayload();
  try {
    const doc = await api(park ? "/documents/park" : "/documents", { method: "POST", body: JSON.stringify(payload) });
    toast(`Document ${doc.belnr}/${doc.gjahr} ${park ? "parked" : "posted"}`, "good");
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
      <span style="display:flex;gap:8px"><button class="btn secondary" id="massRev" disabled>Reverse selected (F.80)</button>
      <a class="btn" href="#/post">+ Post Document</a></span></div>
    <div class="card"><table><thead><tr><th></th><th>Document</th><th>Type</th><th>Doc date</th><th>Posting</th><th>Period</th><th>Text</th><th class="num">Amount</th><th>Curr</th><th>Items</th><th>Status</th></tr></thead>
    <tbody>${docs.map((d) => `<tr style="cursor:pointer" onclick="location.hash='#/documents?doc=${d.belnr}:${d.gjahr}'">
      <td onclick="event.stopPropagation()">${d.bstat === " " && !d.stblg ? `<input type="checkbox" class="rev-pick" value="${d.belnr}/${d.gjahr}">` : ""}</td>
      <td class="mono">${d.belnr}/${d.gjahr}</td><td>${d.blart}</td><td>${d.bldat}</td><td>${d.budat}</td>
      <td>${d.monat}</td><td>${esc(d.bktxt)}</td><td class="num">${fmt(d.amount)}</td><td>${d.waers}</td><td>${d.items}</td><td>${docStatus(d)}</td></tr>`).join("") || `<tr><td colspan="11" class="empty">No documents.</td></tr>`}</tbody></table></div>
    <div id="docDetail"></div>`;
  const picks = () => [...document.querySelectorAll(".rev-pick:checked")].map((cb) => cb.value);
  document.querySelectorAll(".rev-pick").forEach((cb) => (cb.onchange = () => ($("#massRev").disabled = !picks().length)));
  $("#massRev").onclick = async () => {
    const sel = picks();
    if (!confirm(`Reverse ${sel.length} document(s)?`)) return;
    try {
      const res = await api(`/documents/${state.bukrs}/mass-reverse`, { method: "POST", body: JSON.stringify({ documents: sel }) });
      const failed = res.filter((r) => r.error);
      toast(`${res.length - failed.length} reversed${failed.length ? `, ${failed.length} failed: ${failed[0].error}` : ""}`, failed.length ? "bad" : "good");
      route();
    } catch (e) { toast(e.message, "bad"); }
  };
  if (open) {
    const [belnr, gjahr] = open.split(":");
    const d = await api(`/documents/${state.bukrs}/${gjahr}/${belnr}`);
    const actions = d.bstat === "V"
      ? `<a class="btn small secondary" href="#/post?edit=${d.belnr}:${d.gjahr}">Change</a><button class="btn small" data-act="post">Post</button><button class="btn small ghost" data-act="delete">Delete</button>`
      : d.bstat === " " ? `${d.stblg ? "" : `<button class="btn small secondary" data-act="reverse">Reverse (FB08)</button>`}
          <button class="btn small ghost" data-act="reset">Reset clearing</button>
          ${d.items.length && !d.stblg ? `<button class="btn small ghost" data-act="reset-reverse">Reset clearing &amp; reverse</button>` : ""}` : "";
    $("#docDetail").appendChild(el(`<div class="card"><div class="card-head">
      <span>Document ${d.belnr}/${d.gjahr} — ${d.blart} · period ${d.monat} · ${d.waers} ${docStatus(d)}
        ${d.stblg ? ` · ${d.tcode === "FB08" ? "reverses" : "reversed by"} <a href="#/documents?doc=${d.stblg}:${d.stjah}">${d.stblg}</a>` : ""}</span>
      <span style="display:flex;gap:8px">${actions}</span></div>
      <table><thead><tr><th>Itm</th><th>PK</th><th>D/C</th><th>Account</th><th>Tax</th><th>Terms</th><th class="num">Doc amount</th><th class="num">Local amount</th><th>Text</th><th>Clearing</th></tr></thead>
      <tbody>${d.items.map((i) => `<tr><td>${i.buzei}</td><td>${i.bschl}</td>
        <td><span class="chip ${i.shkzg === "S" ? "dr" : "cr"}">${i.shkzg === "S" ? "Debit" : "Credit"}</span></td>
        <td class="mono">${esc(i.kunnr || i.lifnr || i.hkont)}</td><td>${esc(i.mwskz || "")}</td><td>${esc(i.zterm || "")}</td>
        <td class="num">${fmt(i.wrbtr)}</td><td class="num">${fmt(i.dmbtr)}</td><td>${esc(i.sgtxt || "")}</td>
        <td class="mono">${i.augbl ? `<a href="#/documents?doc=${i.augbl}:${d.gjahr}">${i.augbl}</a>` : ""}</td></tr>`).join("")
        || `<tr><td colspan="10" class="empty">Clearing document without line items (zero-balance clearing).</td></tr>`}</tbody></table></div>`));
    const base = `/documents/${state.bukrs}/${d.gjahr}/${d.belnr}`;
    const act = async (fn, okMsg) => { try { const r = await fn(); toast(okMsg(r), "good"); route(); } catch (e) { toast(e.message, "bad"); } };
    document.querySelectorAll("#docDetail [data-act]").forEach((b) => (b.onclick = () => {
      if (b.dataset.act === "post") act(() => api(`${base}/post`, { method: "POST", body: "{}" }), () => "Parked document posted");
      if (b.dataset.act === "delete") act(() => api(base, { method: "DELETE" }), () => "Parked document deleted");
      if (b.dataset.act === "reverse") {
        if (!confirm(`Reverse document ${d.belnr}? A reversal document will be posted.`)) return;
        act(() => api(`${base}/reverse`, { method: "POST", body: JSON.stringify({ stgrd: "01" }) }),
          (r) => { setTimeout(() => (location.hash = `#/documents?doc=${r.belnr}:${r.gjahr}`), 0); return `Reversed by ${r.belnr}`; });
      }
      if (b.dataset.act === "reset" || b.dataset.act === "reset-reverse") {
        const reverse = b.dataset.act === "reset-reverse";
        if (!confirm(`Reopen the items cleared by ${d.belnr}${reverse ? " and reverse it" : ""}?`)) return;
        act(() => api(`${base}/reset-clearing`, { method: "POST", body: JSON.stringify({ reverse }) }),
          (r) => `${r.reset_items} item(s) reopened${r.reversal ? `, reversed by ${r.reversal.belnr}` : ""}`);
      }
    }));
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

// ---------- Balance Sheet / P&L (financial statement version) ----------
views["financial-statement"] = async (c) => {
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  const gjahr = Number(q.get("gjahr") || state.gjahr), cmp = Number(q.get("cmp") || gjahr - 1), per = Number(q.get("per") || 16);
  const fs = await api(`/reports/financial-statement?bukrs=${state.bukrs}&gjahr=${gjahr}&compare_gjahr=${cmp}&period_to=${per}`);
  const amt = (v) => `<td class="num">${Number(v) ? fmt(v) : ""}</td>`;
  const rows = [];
  const walk = (nodes) => nodes.forEach((n) => {
    const strong = n.depth === 0 ? "font-weight:700" : n.children.length ? "font-weight:600" : "";
    rows.push(`<tr class="fs-node" data-id="${n.id}" style="cursor:${n.accounts.length ? "pointer" : "default"};${strong}">
      <td style="padding-left:${14 + n.depth * 22}px">${n.accounts.length ? "▸ " : ""}${esc(n.text)}</td>
      ${amt(n.current)}${amt(n.previous)}${amt(n.difference)}<td class="num">${n.pct == null ? "" : n.pct + "%"}</td></tr>`);
    n.accounts.forEach((a) => rows.push(`<tr class="sub-row fs-acct" data-parent="${n.id}" hidden>
      <td class="help" style="padding-left:${36 + n.depth * 22}px"><span class="mono">${a.saknr}</span> ${esc(a.name || "")}</td>
      ${amt(a.current)}${amt(a.previous)}${amt(Number(a.current) - Number(a.previous))}<td></td></tr>`));
    walk(n.children);
  });
  walk(fs.tree);
  c.innerHTML = `
    <div class="page-head"><div><h1>Balance Sheet / P&amp;L</h1>
      <div class="sub">${esc(fs.vstxt)} (FSV ${esc(fs.versn)}) · company code ${esc(fs.bukrs)} · ${esc(fs.waers)}</div></div>
      <span class="chip ${fs.balanced ? "ok" : "no"}">${fs.balanced ? "Assets = Liabilities + Equity" : "Out of balance"}</span></div>
    <div class="toolbar">
      <div class="field"><label>Fiscal year</label><input id="fs-gjahr" type="number" value="${gjahr}"></div>
      <div class="field"><label>Comparison year</label><input id="fs-cmp" type="number" value="${cmp}"></div>
      <div class="field"><label>Up to period</label><input id="fs-per" type="number" min="1" max="16" value="${per}"></div>
      <button class="btn" id="fs-go">Show</button>
      <button class="btn secondary" id="fs-cf">Carry forward ${gjahr} → ${gjahr + 1}</button>
    </div>
    <div class="tiles">
      <div class="tile"><div class="label">Total assets</div><div class="value">${fmt(fs.total_assets)}</div></div>
      <div class="tile"><div class="label">Liabilities &amp; equity</div><div class="value">${fmt(fs.total_liabilities_equity)}</div></div>
      <div class="tile"><div class="label">Net result ${gjahr}</div><div class="value ${Number(fs.net_result) >= 0 ? "good" : "bad"}">${fmt(fs.net_result)}</div><div class="foot">${Number(fs.net_result) >= 0 ? "profit" : "loss"}</div></div>
    </div>
    ${fs.unassigned.length ? `<div class="card"><div class="card-body" style="color:var(--bad)">Accounts not assigned to the FSV: ${fs.unassigned.map(esc).join(", ")}</div></div>` : ""}
    <div class="card"><table><thead><tr><th>Item</th><th class="num">${gjahr}</th><th class="num">${cmp}</th><th class="num">Difference</th><th class="num">%</th></tr></thead>
      <tbody>${rows.join("")}</tbody></table></div>
    <div class="help">Click an item to show its accounts. Balance sheet accounts include balances carried forward from the previous year.</div>`;

  document.querySelectorAll(".fs-node").forEach((tr) => (tr.onclick = () => {
    document.querySelectorAll(`.fs-acct[data-parent="${tr.dataset.id}"]`).forEach((r) => (r.hidden = !r.hidden));
  }));
  $("#fs-go").onclick = () => { location.hash = `#/financial-statement?gjahr=${$("#fs-gjahr").value}&cmp=${$("#fs-cmp").value}&per=${$("#fs-per").value}`; };
  $("#fs-cf").onclick = async () => {
    try { const r = await api("/closing/carry-forward", { method: "POST", body: JSON.stringify({ bukrs: state.bukrs, gjahr }) });
      toast(`Carried ${r.accounts} account(s) into ${r.to_gjahr}; retained earnings ${fmt(r.retained_earnings)}`, "good"); route(); }
    catch (e) { toast(e.message, "bad"); }
  };
};

// ---------- Open Items ----------
views["open-items"] = async (c) => {
  c.innerHTML = `
    <div class="page-head"><div><h1>Open Items</h1><div class="sub">Customer (A/R) and vendor (A/P) open items</div></div></div>
    <div class="toolbar">
      <div class="field"><label>Account type</label><select id="oi-koart"><option value="D">Customer (D)</option><option value="K">Vendor (K)</option><option value="S">G/L account (S)</option></select></div>
      <div class="field"><label>Account</label><select id="oi-acct"></select></div>
      <label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="oi-open" checked> Only open</label>
      <button class="btn" id="oi-go">Show</button>
    </div>
    <div id="oi-result"></div>`;
  const fillAcct = () => { $("#oi-acct").innerHTML = accountOptions($("#oi-koart").value); };
  $("#oi-koart").onchange = fillAcct; fillAcct();
  $("#oi-go").onclick = async () => {
    const koart = $("#oi-koart").value, acct = $("#oi-acct").value, only = $("#oi-open").checked;
    const items = await api(`/reports/open-items?bukrs=${state.bukrs}&koart=${koart}&account=${acct}&only_open=${only}`);
    const total = items.reduce((s, i) => s + Number(i.amount), 0);
    $("#oi-result").innerHTML = `<div class="card"><table><thead><tr><th>Document</th><th>Posting date</th><th>Baseline</th><th>Net due</th><th>Terms</th><th>Assignment</th><th>Text</th><th class="num">Amount</th><th>Curr</th><th>Status</th></tr></thead>
      <tbody>${items.map((i) => `<tr><td class="mono">${i.belnr}/${i.gjahr}</td><td>${i.budat}</td><td>${i.zfbdt || ""}</td>
        <td style="${!i.cleared && i.faedt < todayISO() ? "color:var(--bad)" : ""}">${i.faedt || ""}</td><td>${esc(i.zterm || "")}</td>
        <td>${esc(i.zuonr || "")}</td><td>${esc(i.sgtxt || "")}</td><td class="num">${fmt(i.amount)}</td><td>${i.waers}</td>
        <td><span class="chip ${i.cleared ? "ok" : "dr"}">${i.cleared ? "Cleared " + esc(i.augbl) : "Open"}</span></td></tr>`).join("") || `<tr><td colspan="10" class="empty">No items.</td></tr>`}</tbody>
      <tfoot><tr><td colspan="7">Balance</td><td class="num">${fmt(total)}</td><td colspan="2"></td></tr></tfoot></table></div>`;
  };
  $("#oi-go").click();
};

// ---------- Payments & Clearing ----------
views.payments = async (c) => {
  const banks = await api(`/master/house-banks?bukrs=${state.bukrs}`);
  let items = [];
  c.innerHTML = `
    <div class="page-head"><div><h1>Payments &amp; Clearing</h1>
      <div class="sub">Incoming / outgoing payment with clearing (F-28 / F-53) · clear open items against each other (F-32 / F-44 / F-03)</div></div></div>
    <div class="card"><div class="card-body">
      <div class="form-grid">
        <div class="field"><label>Account type</label><select id="p-koart"><option value="D">Customer — incoming payment</option><option value="K">Vendor — outgoing payment</option><option value="S">G/L account — clear open items (F-03)</option></select></div>
        <div class="field"><label class="req">Account</label><select id="p-acct"></select></div>
        <div class="field"><label class="req">Posting date</label><input id="p-budat" type="date" value="${todayISO()}"></div>
        <div class="field"><label>House bank</label><select id="p-bank"><option value="">— none (clearing only) —</option>${banks.map((b) => `<option value="${b.hbkid}:${b.hktid}">${b.hbkid}/${b.hktid} · G/L ${b.hkont}</option>`).join("")}</select></div>
        <div class="field"><label>Amount paid</label><input id="p-amt" type="number" step="0.01" min="0" value="0.00"></div>
        <div class="field"><label>Mode</label><select id="p-mode">
          <option value="clear">Clear in full</option>
          <option value="residual">Clear and carry a residual item</option>
          <option value="partial">Partial payment (one item stays open)</option>
          <option value="on_account">Payment on account (no items)</option></select></div>
      </div>
      <label style="display:flex;gap:6px;align-items:center;margin-top:12px"><input type="checkbox" id="p-disc" checked> Take cash discount per terms of payment</label>
    </div></div>
    <div class="card"><div class="card-head">Open Items <button class="btn small secondary" id="p-fill">Amount = selected net</button></div><div id="p-items"></div></div>
    <div class="card"><div class="card-body">
      <div class="balance-row">
        <span>Selected: <span class="amt" id="p-sel">0.00</span></span>
        <span>Cash discount: <span class="amt" id="p-dsum">0.00</span></span>
        <span>Paid: <span class="amt" id="p-paid">0.00</span></span>
        <span>Difference: <span class="amt" id="p-diff">0.00</span></span>
        <span id="p-chip" class="chip no">—</span>
      </div>
      <button class="btn" id="p-post" disabled>Post</button>
    </div></div>`;

  let tol = null;  // permitted payment differences (T043G) of the selected partner
  const isGL = () => $("#p-koart").value === "S";
  const fillAcct = () => {
    $("#p-acct").innerHTML = accountOptions($("#p-koart").value);
    // G/L open items are cleared without a payment
    ["#p-amt", "#p-bank", "#p-disc"].forEach((s) => ($(s).disabled = isGL()));
    if (isGL()) { $("#p-amt").value = "0.00"; $("#p-bank").value = ""; }
  };
  const selected = () => [...document.querySelectorAll(".p-pick:checked")].map((cb) => items[Number(cb.dataset.i)]);
  const usesDiscount = () => $("#p-disc").checked && ["clear", "residual"].includes($("#p-mode").value);

  const load = async () => {
    const q = `bukrs=${state.bukrs}&koart=${$("#p-koart").value}&account=${$("#p-acct").value}&budat=${$("#p-budat").value}`;
    [items, tol] = await Promise.all([
      api(`/payments/open-items?${q}`),
      isGL() ? null : api(`/payments/tolerance?bukrs=${state.bukrs}&koart=${$("#p-koart").value}&account=${$("#p-acct").value}`),
    ]);
    $("#p-items").innerHTML = `<table><thead><tr><th></th><th>Document</th><th>PK</th><th>Posting date</th><th>Net due</th><th>Terms</th><th>Text</th><th class="num">Open</th><th class="num">Disc. %</th><th class="num">Discount</th><th class="num">Net</th></tr></thead>
      <tbody>${items.map((i, n) => `<tr><td><input type="checkbox" class="p-pick" data-i="${n}"></td>
        <td class="mono"><a href="#/documents?doc=${i.belnr}:${i.gjahr}">${i.belnr}/${i.gjahr}</a></td><td>${i.bschl}</td><td>${i.budat}</td>
        <td style="${i.overdue_days ? "color:var(--bad)" : ""}">${i.faedt}${i.overdue_days ? ` (+${i.overdue_days}d)` : ""}</td>
        <td>${esc(i.zterm || "")}</td><td>${esc(i.sgtxt || "")}${i.rebzg ? ` <span class="help">ref ${i.rebzg}</span>` : ""}</td>
        <td class="num">${fmt(i.open)}</td><td class="num">${Number(i.discount_pct) ? Number(i.discount_pct) + "%" : ""}</td>
        <td class="num">${Number(i.discount) ? fmt(i.discount) : ""}</td><td class="num">${fmt(i.net)}</td></tr>`).join("")
        || `<tr><td colspan="11" class="empty">No open items for this account.</td></tr>`}</tbody></table>`;
    document.querySelectorAll(".p-pick").forEach((cb) => (cb.onchange = recalc));
    recalc();
  };

  const recalc = () => {
    const sel = selected(), mode = $("#p-mode").value;
    const open = sel.reduce((s, i) => s + Number(i.open), 0);
    const disc = usesDiscount() ? sel.reduce((s, i) => s + Number(i.discount), 0) : 0;
    const paid = Number($("#p-amt").value || 0);
    const diff = Math.round((open - disc - (open >= 0 ? paid : -paid)) * 100) / 100;
    $("#p-sel").textContent = fmt(open); $("#p-dsum").textContent = fmt(disc);
    $("#p-paid").textContent = fmt(paid); $("#p-diff").textContent = fmt(diff);
    let ok = false, msg;
    const tolerated = () => {
      if (!tol || !diff) return false;
      const gain = (diff > 0) === ($("#p-koart").value === "K");
      const [amt, pct] = gain ? [tol.gain_amount, tol.gain_pct] : [tol.loss_amount, tol.loss_pct];
      return Math.abs(diff) <= Math.min(Number(amt), Math.round(Math.abs(open) * Number(pct)) / 100);
    };
    if (paid > 0 && !$("#p-bank").value) msg = "Choose a house bank";
    else if (isGL() && !["clear", "residual"].includes(mode)) msg = "G/L accounts: clear or residual only";
    else if (mode === "clear") {
      ok = sel.length > 0 && (diff === 0 || tolerated());
      msg = !sel.length ? "Select items" : diff === 0 ? "Balanced — ready to clear"
        : ok ? `Difference ${fmt(diff)} within tolerance — posted as payment difference` : "Difference exceeds tolerance";
    }
    else if (mode === "residual") { ok = sel.length > 0; msg = ok ? (diff ? `Residual item ${fmt(diff)}` : "Balanced — ready to clear") : "Select items"; }
    else if (mode === "partial") { ok = sel.length === 1 && paid > 0 && paid < Math.abs(open); msg = ok ? "Partial payment" : "Select one item and pay less than its open amount"; }
    else { ok = sel.length === 0 && paid > 0; msg = ok ? "Payment on account" : "Enter an amount and select no items"; }
    const chip = $("#p-chip");
    chip.className = "chip " + (ok ? "ok" : "no"); chip.textContent = msg;
    $("#p-post").disabled = !ok;
  };

  const post = async () => {
    const sel = selected().map((i) => ({ belnr: i.belnr, gjahr: i.gjahr, buzei: i.buzei }));
    const paid = Number($("#p-amt").value || 0);
    const base = { bukrs: state.bukrs, koart: $("#p-koart").value, account: $("#p-acct").value, budat: $("#p-budat").value, items: sel, mode: $("#p-mode").value };
    try {
      let r;
      if (paid > 0) {
        const [hbkid, hktid] = $("#p-bank").value.split(":");
        r = await api("/payments", { method: "POST", body: JSON.stringify({ ...base, amount: paid, hbkid, hktid, apply_discount: $("#p-disc").checked }) });
      } else {
        r = await api("/clearing", { method: "POST", body: JSON.stringify(base) });
      }
      toast(`Document ${r.belnr}/${r.gjahr} posted · ${r.cleared.length} item(s) cleared`, "good");
      location.hash = `#/documents?doc=${r.belnr}:${r.gjahr}`;
    } catch (e) {
      toast(e.message, "bad");
    }
  };

  $("#p-koart").onchange = () => { fillAcct(); load(); };
  $("#p-acct").onchange = load;
  $("#p-budat").onchange = load;
  ["#p-amt", "#p-mode", "#p-disc", "#p-bank"].forEach((s) => ($(s).oninput = $(s).onchange = recalc));
  $("#p-fill").onclick = () => {
    const sel = selected();
    const net = sel.reduce((s, i) => s + Number(i.open) - (usesDiscount() ? Number(i.discount) : 0), 0);
    $("#p-amt").value = Math.abs(net).toFixed(2);
    if (!$("#p-bank").value && banks.length) $("#p-bank").value = `${banks[0].hbkid}:${banks[0].hktid}`;
    recalc();
  };
  $("#p-post").onclick = post;
  fillAcct();
  if (banks.length) $("#p-bank").value = `${banks[0].hbkid}:${banks[0].hktid}`;
  await load();
};

// ---------- Recurring Entries (FBD1 / F.14) ----------
views.recurring = async (c) => {
  const list = await api(`/recurring?bukrs=${state.bukrs}`);
  c.innerHTML = `
    <div class="page-head"><div><h1>Recurring Entries</h1>
      <div class="sub">Originals (FBD1) are created on Post Document → "Save as recurring entry"; the run (F.14) posts the due copies</div></div>
      <a class="btn secondary" href="#/post">+ New recurring entry</a></div>
    <div class="toolbar">
      <div class="field"><label>Settlement date</label><input id="rr-to" type="date" value="${todayISO()}"></div>
      <button class="btn" id="rr-run">Run recurring entries (F.14)</button>
    </div>
    <div id="rr-result"></div>
    <div class="card"><table><thead><tr><th>Original</th><th>Type</th><th>Text</th><th class="num">Amount</th><th>First run</th><th>Last run</th><th>Every</th><th>Next run</th><th class="num">Posted</th><th></th></tr></thead>
      <tbody>${list.map((r) => `<tr>
        <td class="mono"><a href="#/documents?doc=${r.belnr}:${r.gjahr}">${r.belnr}/${r.gjahr}</a></td><td>${r.blart}</td><td>${esc(r.bktxt || "")}</td>
        <td class="num">${fmt(r.amount)} ${esc(r.waers)}</td><td>${r.dbbdt}</td><td>${r.dbedt}</td>
        <td>${r.dbmon} month(s), day ${r.dbtag}</td>
        <td>${r.deleted ? `<span class="chip no">Deleted</span>` : r.dbatr || `<span class="chip ok">Finished</span>`}</td>
        <td class="num">${r.runs}</td>
        <td>${r.deleted ? "" : `<button class="btn small ghost rr-del" data-k="${r.gjahr}/${r.belnr}">Delete</button>`}</td></tr>`).join("")
        || `<tr><td colspan="10" class="empty">No recurring entries yet.</td></tr>`}</tbody></table></div>`;

  $("#rr-run").onclick = async () => {
    try {
      const r = await api("/recurring/run", { method: "POST", body: JSON.stringify({ bukrs: state.bukrs, settle_to: $("#rr-to").value }) });
      toast(`${r.posted.length} document(s) posted`, "good");
      await views.recurring(c);
      $("#rr-result").innerHTML = r.posted.length ? `<div class="card"><div class="card-head">Posted up to ${r.settle_to}</div><table><tbody>${r.posted.map((p) =>
        `<tr><td class="mono"><a href="#/documents?doc=${p.belnr}:${p.gjahr}">${p.belnr}/${p.gjahr}</a></td><td>${p.budat}</td><td>${esc(p.bktxt || "")}</td><td class="help">from ${p.recurring}</td></tr>`).join("")}</tbody></table></div>` : "";
    } catch (e) { toast(e.message, "bad"); }
  };
  document.querySelectorAll(".rr-del").forEach((b) => (b.onclick = async () => {
    if (!confirm("Delete this recurring entry? No further copies will be posted.")) return;
    try { await api(`/recurring/${state.bukrs}/${b.dataset.k}`, { method: "DELETE" }); toast("Recurring entry deleted", "good"); route(); }
    catch (e) { toast(e.message, "bad"); }
  }));
};

// ---------- Dunning (F150) ----------
views.dunning = async (c) => {
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  const runs = await api(`/dunning-runs?bukrs=${state.bukrs}`);
  c.innerHTML = `
    <div class="page-head"><div><h1>Dunning</h1>
      <div class="sub">F150 · proposal → dunning run (sets item and account dunning levels) → notices</div></div></div>
    <div class="card"><div class="card-head">Dunning Runs</div>
      <table><thead><tr><th>Run date</th><th>Identification</th><th>Dunning date</th><th>Status</th><th class="num">Notices</th><th class="num">Overdue</th><th class="num">Charges</th><th class="num">Listed only</th></tr></thead>
      <tbody>${runs.map((r) => `<tr style="cursor:pointer" onclick="location.hash='#/dunning?run=${r.laufd}:${r.laufi}'">
        <td>${r.laufd}</td><td class="mono">${esc(r.laufi)}</td><td>${r.ausdt}</td>
        <td><span class="chip ${r.xecht ? "ok" : "dr"}">${esc(r.status)}</span></td>
        <td class="num">${r.notices}</td><td class="num">${fmt(r.total)}</td><td class="num">${fmt(r.charges)}</td><td class="num">${r.listed || ""}</td></tr>`).join("")
        || `<tr><td colspan="8" class="empty">No dunning runs yet.</td></tr>`}</tbody></table></div>
    <div class="card"><div class="card-head">Parameters</div><div class="card-body">
      <div class="form-grid">
        <div class="field"><label class="req">Run date</label><input id="d-laufd" type="date" value="${todayISO()}"></div>
        <div class="field"><label class="req">Identification</label><input id="d-laufi" maxlength="6" value="M${runs.filter((r) => r.laufd === todayISO()).length + 1}"></div>
        <div class="field"><label class="req">Dunning date</label><input id="d-ausdt" type="date" value="${todayISO()}"></div>
        <div class="field"><label>Customer from</label><input id="d-low" placeholder="all"></div>
        <div class="field"><label>Customer to</label><input id="d-high" placeholder="all"></div>
      </div>
      <button class="btn" id="d-propose" style="margin-top:12px">Create Proposal</button>
      <div class="help">Customers with dunning data (procedure 0001 for the demo customer). A level rises by at most one per run; the dunning interval is 14 days.</div>
    </div></div>
    <div id="d-detail"></div>`;

  $("#d-propose").onclick = async () => {
    const body = { laufd: $("#d-laufd").value, laufi: $("#d-laufi").value, ausdt: $("#d-ausdt").value, bukrs: state.bukrs,
      kunnr_low: $("#d-low").value || null, kunnr_high: $("#d-high").value || null };
    try {
      const r = await api("/dunning-runs/proposal", { method: "POST", body: JSON.stringify(body) });
      toast(`Proposal ${r.laufi}: ${r.notices} notice(s), ${r.listed} listed only`, "good");
      location.hash = `#/dunning?run=${r.laufd}:${r.laufi}`;
    } catch (e) { toast(e.message, "bad"); }
  };

  const sel = q.get("run");
  if (!sel) return;
  const [laufd, laufi] = sel.split(":");
  const path = `/dunning-runs/${laufd}/${encodeURIComponent(laufi)}`;
  const r = await api(path);
  const name = (k) => (state.customers.find((x) => x.kunnr === k) || {}).name1 || "";
  $("#d-detail").innerHTML = `<div class="card"><div class="card-head">
      <span>Run ${r.laufd} / ${esc(r.laufi)} · dunning date ${r.ausdt} · <span class="chip ${r.xecht ? "ok" : "dr"}">${esc(r.status)}</span></span>
      <span style="display:flex;gap:8px">${r.xecht ? "" : `<button class="btn small secondary" id="d-del">Delete proposal</button>
        <button class="btn small" id="d-exec" ${r.notices ? "" : "disabled"}>Execute dunning run</button>`}</span></div>
    <table><thead><tr><th>Customer</th><th>Name</th><th>Level</th><th class="num">Overdue</th><th class="num">Charge</th><th>Notice</th></tr></thead>
    <tbody>${r.accounts.map((a) => `<tr>
        <td class="mono">${a.kunnr}</td><td>${esc(name(a.kunnr))}</td><td>${a.mahnv} → <strong>${a.mahns}</strong></td>
        <td class="num">${fmt(a.salhw)}</td><td class="num">${Number(a.mahng) ? fmt(a.mahng) : ""}</td>
        <td>${a.xmflg ? `<a class="btn small ghost" target="_blank" href="/api${path}/notice/${a.kunnr}">Open notice</a>` : `<span class="help">${esc(a.reason || "")}</span>`}</td></tr>
      ${a.items.map((i) => `<tr class="sub-row"><td></td><td class="mono help">↳ <a href="#/documents?doc=${i.belnr}:${i.gjahr}">${i.belnr}/${i.gjahr}</a> ${esc(i.xblnr || "")}</td>
        <td class="help">${i.shkzg === "S" ? `${i.manst} → ${i.mahnn}` : "credit"}${i.mansp ? ` · block ${esc(i.mansp)}` : ""}</td>
        <td class="num help">${fmt(i.dmshb)}</td><td class="help">${i.shkzg === "S" ? `due ${i.faedt} · ${i.verzn} days` : ""}</td><td></td></tr>`).join("")}`).join("")
      || `<tr><td colspan="6" class="empty">No overdue items.</td></tr>`}</tbody></table></div>`;

  if (!r.xecht) {
    $("#d-del").onclick = async () => {
      try { await api(path, { method: "DELETE" }); toast("Proposal deleted", "good"); location.hash = "#/dunning"; }
      catch (e) { toast(e.message, "bad"); }
    };
    $("#d-exec").onclick = async () => {
      if (!confirm(`Issue ${r.notices} notice(s) and raise the dunning levels? This cannot be undone.`)) return;
      try { await api(`${path}/execute`, { method: "POST", body: "{}" }); toast("Dunning run executed", "good"); route(); }
      catch (e) { toast(e.message, "bad"); }
    };
  }
};

// ---------- Exchange rates & FX valuation (OB08 / FAGL_FCV) ----------
views.fx = async (c) => {
  const rates = await api("/exchange-rates");
  c.innerHTML = `
    <div class="page-head"><div><h1>Exchange Rates &amp; FX Valuation</h1>
      <div class="sub">Foreign-currency documents translate at the rate of their posting date; open items are revalued at a key date</div></div></div>
    <div class="card"><div class="card-head">FX Valuation of Open Items (FAGL_FCV)</div><div class="card-body">
      <div class="toolbar" style="margin:0">
        <div class="field"><label class="req">Key date</label><input id="fx-key" type="date" value="${todayISO()}"></div>
        <button class="btn secondary" id="fx-test">Test run</button>
        <button class="btn" id="fx-post">Post valuation</button>
      </div>
      <div class="help">The posting is reversed automatically on the day after the key date. A key date can be posted once.</div>
    </div><div id="fx-result"></div></div>
    <div class="card"><div class="card-head">Exchange Rates (TCURR, type M)</div>
      <table><thead><tr><th>Type</th><th>From</th><th>To</th><th>Valid from</th><th class="num">Rate</th></tr></thead>
      <tbody>${rates.map((r) => `<tr><td>${esc(r.kurst)}</td><td>${esc(r.fcurr)}</td><td>${esc(r.tcurr)}</td><td>${r.gdatu}</td><td class="num">${Number(r.ukurs).toFixed(5)}</td></tr>`).join("")
        || `<tr><td colspan="5" class="empty">No exchange rates.</td></tr>`}</tbody></table>
      <div class="card-body"><div class="form-grid">
        <div class="field"><label>From currency</label><input id="xr-from" value="USD"></div>
        <div class="field"><label>To currency</label><input id="xr-to" value="${esc(ccWaers())}"></div>
        <div class="field"><label>Valid from</label><input id="xr-date" type="date" value="${todayISO()}"></div>
        <div class="field"><label>Rate (1 from = x to)</label><input id="xr-rate" type="number" step="0.00001" min="0"></div>
      </div><button class="btn secondary" id="xr-save" style="margin-top:12px">Save rate</button></div></div>`;

  const run = async (post) => {
    if (post && !confirm(`Post the FX valuation for ${$("#fx-key").value}? It is reversed on the next day.`)) return;
    try {
      const r = await api("/fx-valuation", { method: "POST", body: JSON.stringify({ bukrs: state.bukrs, key_date: $("#fx-key").value, post }) });
      if (post) toast(r.document ? `Valuation ${r.document.belnr} posted, reversed by ${r.reversal.belnr}` : "Nothing to post", "good");
      $("#fx-result").innerHTML = `<table><thead><tr><th>Document</th><th>Account</th><th class="num">Amount</th><th>Curr</th><th class="num">Hist. rate</th><th class="num">Key-date rate</th><th class="num">Local before</th><th class="num">Local after</th><th class="num">Difference</th></tr></thead>
        <tbody>${r.items.map((i) => `<tr><td class="mono"><a href="#/documents?doc=${i.belnr}:${i.gjahr}">${i.belnr}/${i.gjahr}</a></td>
          <td class="mono">${esc(i.account)}</td><td class="num">${fmt(i.wrbtr)}</td><td>${esc(i.waers)}</td>
          <td class="num">${i.rate_hist ?? ""}</td><td class="num">${i.rate_key}</td><td class="num">${fmt(i.local_before)}</td>
          <td class="num">${fmt(i.local_after)}</td><td class="num" style="color:${Number(i.difference) >= 0 ? "var(--good)" : "var(--bad)"}">${fmt(i.difference)}</td></tr>`).join("")
          || `<tr><td colspan="9" class="empty">No open items in foreign currency on this key date.</td></tr>`}</tbody>
        <tfoot><tr><td colspan="8">Total valuation difference (${esc(r.waers)})</td><td class="num">${fmt(r.total)}</td></tr></tfoot></table>
        ${r.postings.length ? `<div class="card-body help">Postings: ${r.postings.map((p) => `${esc(p.hkont)}: Dr ${esc(p.debit)} / Cr ${esc(p.credit)} ${fmt(Math.abs(p.difference))}`).join(" · ")}
          ${r.document ? ` — document <a href="#/documents?doc=${r.document.belnr}:${r.document.gjahr}">${r.document.belnr}</a>, reversal <a href="#/documents?doc=${r.reversal.belnr}:${r.reversal.gjahr}">${r.reversal.belnr}</a>` : " (test run, nothing posted)"}</div>` : ""}`;
    } catch (e) { toast(e.message, "bad"); }
  };
  $("#fx-test").onclick = () => run(false);
  $("#fx-post").onclick = () => run(true);
  $("#xr-save").onclick = async () => {
    try {
      await api("/exchange-rates", { method: "POST", body: JSON.stringify({ kurst: "M", fcurr: $("#xr-from").value, tcurr: $("#xr-to").value, gdatu: $("#xr-date").value, ukurs: $("#xr-rate").value }) });
      toast("Exchange rate saved", "good"); route();
    } catch (e) { toast(e.message, "bad"); }
  };
};

// ---------- Controlling: actual costs and CO documents ----------
const KOKRS = "1000";
views.controlling = async (c) => {
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  const gjahr = Number(q.get("gjahr") || state.gjahr), pf = Number(q.get("pf") || 1), pt = Number(q.get("pt") || 16);
  const params = `kokrs=${KOKRS}&gjahr=${gjahr}&perio_from=${pf}&perio_to=${pt}`;
  const [ks, or, docs, cycles] = await Promise.all([
    api(`/co/actuals?${params}&kind=KS`), api(`/co/actuals?${params}&kind=OR`), api(`/co/documents?kokrs=${KOKRS}&limit=15`),
    api(`/co/cycles?kokrs=${KOKRS}`),
  ]);
  const table = (title, rows, label) => `<div class="card"><div class="card-head">${title}</div>
    <table><thead><tr><th>${label}</th><th>Description</th><th>Cost element</th><th class="num">Actual</th></tr></thead>
    <tbody>${rows.map((o) => `<tr style="font-weight:600"><td class="mono">${esc(o.object)}</td><td>${esc(o.text || "")}</td><td></td><td class="num">${fmt(o.total)}</td></tr>
      ${o.elements.map((e) => `<tr class="sub-row"><td></td><td></td><td class="help"><span class="mono">${esc(e.kstar)}</span> ${esc(e.text || "")}${e.katyp ? ` · cat. ${esc(e.katyp)}` : ""}</td>
        <td class="num help">${fmt(e.amount)}</td></tr>`).join("")}`).join("")
      || `<tr><td colspan="4" class="empty">No objects.</td></tr>`}</tbody></table></div>`;
  c.innerHTML = `
    <div class="page-head"><div><h1>Cost Centers &amp; Internal Orders</h1>
      <div class="sub">Controlling area ${KOKRS} · actual costs (value type 04) from CO documents</div></div></div>
    <div class="toolbar">
      <div class="field"><label>Fiscal year</label><input id="co-gjahr" type="number" value="${gjahr}"></div>
      <div class="field"><label>From period</label><input id="co-pf" type="number" min="1" max="16" value="${pf}"></div>
      <div class="field"><label>To period</label><input id="co-pt" type="number" min="1" max="16" value="${pt}"></div>
      <button class="btn" id="co-go">Show</button>
    </div>
    ${table("Cost Centers", ks, "Cost center")}
    <div class="card"><div class="card-head">Assessment &amp; Distribution Cycles (KSU5 / KSV5)</div>
      <table><thead><tr><th>Cycle</th><th>Type</th><th>Segments</th><th>Runs</th><th></th></tr></thead>
      <tbody>${cycles.map((cy) => `<tr>
        <td><strong class="mono">${esc(cy.cycle)}</strong><div class="help">${esc(cy.txt || "")}</div></td>
        <td>${cy.ttype === "A" ? "Assessment" : "Distribution"}</td>
        <td class="help" style="white-space:normal">${cy.segments.map((g) => `${g.seg}: ${esc(g.senders)} sends ${esc(g.elements)}${g.askst ? ` as ${esc(g.askst)}` : ""} → ${g.receivers.map((r) => `${esc(r.kostl)} (${Number(r.faktor)})`).join(", ")}`).join("<br>")}</td>
        <td class="help">${cy.runs.map((r) => `${String(r.perio).padStart(2, "0")}/${r.gjahr} ${r.belnr}${r.reversed ? " (reversed)" : ""}`).join("<br>") || "—"}</td>
        <td style="white-space:nowrap">
          <input class="cy-per" data-c="${esc(cy.cycle)}" type="number" min="1" max="16" value="${new Date().getMonth() + 1}" style="width:60px" title="Period">
          <button class="btn small secondary cy-act" data-c="${esc(cy.cycle)}" data-a="test">Test</button>
          <button class="btn small cy-act" data-c="${esc(cy.cycle)}" data-a="run">Run</button>
          <button class="btn small ghost cy-act" data-c="${esc(cy.cycle)}" data-a="reverse">Reverse</button></td></tr>`).join("")
        || `<tr><td colspan="5" class="empty">No cycles.</td></tr>`}</tbody></table>
      <div id="cy-result"></div></div>
    ${table("Internal Orders", or, "Order")}
    <div class="card"><div class="card-head">Settle Internal Orders (KO88)</div><div class="card-body">
      <div class="toolbar" style="margin:0">
        <div class="field"><label>Order</label><select id="st-order">${or.map((o) => `<option value="${esc(o.object)}">${esc(o.object)} — ${esc(o.text || "")}</option>`).join("")}</select></div>
        <div class="field"><label>Period</label><input id="st-per" type="number" min="1" max="16" value="${new Date().getMonth() + 1}"></div>
        <button class="btn secondary" id="st-test">Test</button><button class="btn" id="st-run">Settle</button>
      </div><div id="st-result"></div></div></div>
    <div class="card"><div class="card-head">Recent CO Documents</div>
      <table><thead><tr><th>CO document</th><th>Transaction</th><th>Posting date</th><th>Text</th><th>FI reference</th><th>Lines</th></tr></thead>
      <tbody>${docs.map((d) => `<tr><td class="mono">${d.belnr}</td><td>${esc(d.vrgng)}${d.kscyc ? ` · ${esc(d.kscyc)}` : ""}${d.stokz ? ` <span class="chip cr">Reversed</span>` : ""}${d.stflg ? ` <span class="chip cr">Reversal</span>` : ""}</td>
        <td>${d.budat}</td><td>${esc(d.bltxt || "")}</td>
        <td class="mono">${d.refbn ? `<a href="#/documents?doc=${d.refbn}:${d.refgj}">${d.refbn}</a>` : ""}</td>
        <td class="help">${d.lines.map((l) => `${esc(l.objnr)} ${esc(l.kstar)} ${fmt(l.amount)}`).join("<br>")}</td></tr>`).join("")
        || `<tr><td colspan="6" class="empty">No CO documents yet.</td></tr>`}</tbody></table></div>`;
  $("#co-go").onclick = () => { location.hash = `#/controlling?gjahr=${$("#co-gjahr").value}&pf=${$("#co-pf").value}&pt=${$("#co-pt").value}`; };
  const settle = async (test) => {
    const aufnr = $("#st-order").value, perio = Number($("#st-per").value);
    if (!aufnr) return;
    if (!test && !confirm(`Settle order ${aufnr} up to period ${perio}/${gjahr}?`)) return;
    try {
      const [rules, r] = await Promise.all([
        api(`/co/orders/${aufnr}/settlement-rule`),
        api(`/co/orders/${aufnr}/settle`, { method: "POST", body: JSON.stringify({ kokrs: KOKRS, gjahr, perio, test }) }),
      ]);
      if (!test) { toast(r.co_document ? `Settled ${fmt(r.settled)} (CO ${r.co_document}${r.fi_document ? `, FI ${r.fi_document}` : ""})` : "Nothing to settle", "good"); return route(); }
      $("#st-result").innerHTML = `<p class="help">Rule: ${rules.map((x) => `${x.konty} ${esc(x.receiver)} ${Number(x.prozs)}%`).join(" · ")} — order balance ${fmt(r.balance)}</p>
        <table><thead><tr><th>Receiver</th><th>Type</th><th class="num">%</th><th>Cost element</th><th class="num">Amount</th></tr></thead>
        <tbody>${r.lines.map((l) => `<tr><td class="mono">${esc(l.receiver)}</td><td>${l.konty === "KS" ? "Cost center" : "G/L account"}</td><td class="num">${Number(l.prozs)}</td><td class="mono">${esc(l.kstar)}</td><td class="num">${fmt(l.amount)}</td></tr>`).join("")
          || `<tr><td colspan="5" class="empty">Nothing to settle.</td></tr>`}</tbody></table>`;
    } catch (e) { toast(e.message, "bad"); }
  };
  $("#st-test").onclick = () => settle(true);
  $("#st-run").onclick = () => settle(false);
  document.querySelectorAll(".cy-act").forEach((b) => (b.onclick = async () => {
    const cycle = b.dataset.c, act = b.dataset.a;
    const perio = Number(document.querySelector(`.cy-per[data-c="${cycle}"]`).value);
    const body = JSON.stringify({ kokrs: KOKRS, gjahr, perio, test: act === "test" });
    if (act !== "test" && !confirm(`${act === "run" ? "Run" : "Reverse"} cycle ${cycle} for period ${perio}/${gjahr}?`)) return;
    try {
      const r = await api(`/co/cycles/${encodeURIComponent(cycle)}/${act === "reverse" ? "reverse" : "run"}`, { method: "POST", body });
      if (act === "reverse") { toast(`Run ${r.reversed} reversed by ${r.reversal}`, "good"); return route(); }
      if (act === "run") { toast(r.document ? `CO document ${r.document} posted` : "Nothing to allocate", "good"); return route(); }
      $("#cy-result").innerHTML = `<div class="card-body"><strong>Test run ${esc(cycle)} ${perio}/${gjahr}</strong> — sends ${fmt(r.sent)}
        <table><thead><tr><th>Segment</th><th>Cost center</th><th>Role</th><th>Cost element</th><th class="num">Amount</th></tr></thead>
        <tbody>${r.lines.map((l) => `<tr><td>${l.seg}</td><td class="mono">${esc(l.kostl)}</td><td>${l.role}</td><td class="mono">${esc(l.kstar)}</td><td class="num">${fmt(l.amount)}</td></tr>`).join("")
          || `<tr><td colspan="5" class="empty">No sender costs in this period.</td></tr>`}</tbody></table></div>`;
    } catch (e) { toast(e.message, "bad"); }
  }));
};

// ---------- Profitability analysis (CO-PA) ----------
views.copa = async (c) => {
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  const by = q.get("by") || "kndnr", gjahr = Number(q.get("gjahr") || state.gjahr);
  const r = await api(`/co/pa/contribution?kokrs=${KOKRS}&gjahr=${gjahr}&by=${by}`);
  const opts = { kndnr: "Customer", land1: "Country", brsch: "Industry", kukla: "Customer class" };
  c.innerHTML = `
    <div class="page-head"><div><h1>Profitability Analysis</h1>
      <div class="sub">Account-based CO-PA · operating concern IDEA · revenue and sales deductions by profitability segment</div></div></div>
    <div class="toolbar">
      <div class="field"><label>Characteristic</label><select id="pa-by">${Object.entries(opts).map(([k, v]) => `<option value="${k}" ${k === by ? "selected" : ""}>${v}</option>`).join("")}</select></div>
      <div class="field"><label>Fiscal year</label><input id="pa-gjahr" type="number" value="${gjahr}"></div>
      <button class="btn" id="pa-go">Show</button>
    </div>
    <div class="tiles">
      <div class="tile"><div class="label">Revenue</div><div class="value">${fmt(r.revenue)}</div></div>
      <div class="tile"><div class="label">Sales deductions</div><div class="value">${fmt(r.deductions)}</div></div>
      <div class="tile"><div class="label">Net revenue</div><div class="value good">${fmt(r.net)}</div></div>
    </div>
    <div class="card"><table><thead><tr><th>${esc(r.label)}</th><th class="num">Revenue</th><th class="num">Sales deductions</th><th class="num">Net revenue</th><th class="num">Share</th></tr></thead>
      <tbody>${r.lines.map((l) => `<tr><td><span class="mono">${esc(l.value ?? "—")}</span> ${esc(l.name || "")}</td>
        <td class="num">${fmt(l.revenue)}</td><td class="num">${Number(l.deductions) ? fmt(l.deductions) : ""}</td><td class="num">${fmt(l.net)}</td>
        <td class="num">${Number(r.net) ? (Number(l.net) / Number(r.net) * 100).toFixed(1) + "%" : ""}</td></tr>`).join("")
        || `<tr><td colspan="5" class="empty">No revenue in profitability segments yet.</td></tr>`}</tbody></table></div>`;
  $("#pa-go").onclick = () => { location.hash = `#/copa?by=${$("#pa-by").value}&gjahr=${$("#pa-gjahr").value}`; };
};

// ---------- Automatic Payment Program (F110) ----------
const addDays = (iso, n) => { const d = new Date(iso); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

views["payment-run"] = async (c) => {
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  const runs = await api(`/payment-runs?zbukr=${state.bukrs}`);
  c.innerHTML = `
    <div class="page-head"><div><h1>Automatic Payment Program</h1>
      <div class="sub">F110 · parameters → proposal → payment run → SEPA files (transfers pain.001, direct debits pain.008)</div></div></div>
    <div class="card"><div class="card-head">Payment Runs</div>
      <table><thead><tr><th>Run date</th><th>Identification</th><th>Posting date</th><th>Next run</th><th>Status</th><th class="num">Payments</th><th class="num">Amount</th><th class="num">Exceptions</th></tr></thead>
      <tbody>${runs.map((r) => `<tr style="cursor:pointer" onclick="location.hash='#/payment-run?run=${r.laufd}:${r.laufi}'">
        <td>${r.laufd}</td><td class="mono">${esc(r.laufi)}</td><td>${r.zaldt}</td><td>${r.nedat}</td>
        <td><span class="chip ${r.xecht ? "ok" : "dr"}">${esc(r.status)}</span></td>
        <td class="num">${r.payments}</td><td class="num">${fmt(r.total)}</td><td class="num">${r.exceptions || ""}</td></tr>`).join("")
        || `<tr><td colspan="8" class="empty">No payment runs yet.</td></tr>`}</tbody></table></div>
    <div class="card"><div class="card-head">Parameters</div><div class="card-body">
      <div class="form-grid">
        <div class="field"><label class="req">Run date</label><input id="r-laufd" type="date" value="${todayISO()}"></div>
        <div class="field"><label class="req">Identification</label><input id="r-laufi" maxlength="6" value="F${runs.filter((r) => r.laufd === todayISO()).length + 1}"></div>
        <div class="field"><label class="req">Posting date</label><input id="r-zaldt" type="date" value="${todayISO()}"></div>
        <div class="field"><label class="req">Next payment date</label><input id="r-nedat" type="date" value="${addDays(todayISO(), 14)}"></div>
        <div class="field"><label>Docs entered up to</label><input id="r-cpudt" type="date" value="${todayISO()}"></div>
        <div class="field"><label class="req">Payment methods</label><input id="r-zwels" value="TE" title="T = SEPA transfer to vendors, E = SEPA direct debit from customers"></div>
        <div class="field"><label>Vendor from</label><input id="r-low" placeholder="all"></div>
        <div class="field"><label>Vendor to</label><input id="r-high" placeholder="all"></div>
        <div class="field"><label>Customer from</label><input id="r-klow" placeholder="all"></div>
        <div class="field"><label>Customer to</label><input id="r-khigh" placeholder="all"></div>
      </div>
      <button class="btn" id="r-propose" style="margin-top:12px">Create Proposal</button>
      <div class="help">Settles items that would be overdue by the next payment date, or whose cash discount would shrink by then. Credit memos are offset. Payments post to the bank clearing account; the bank statement clears it.</div>
    </div></div>
    <div id="r-detail"></div>`;

  $("#r-propose").onclick = async () => {
    const body = {
      laufd: $("#r-laufd").value, laufi: $("#r-laufi").value, zbukr: state.bukrs, zwels: $("#r-zwels").value,
      zaldt: $("#r-zaldt").value, nedat: $("#r-nedat").value, cpudt: $("#r-cpudt").value || null,
      lifnr_low: $("#r-low").value || null, lifnr_high: $("#r-high").value || null,
      kunnr_low: $("#r-klow").value || null, kunnr_high: $("#r-khigh").value || null,
    };
    try {
      const r = await api("/payment-runs/proposal", { method: "POST", body: JSON.stringify(body) });
      toast(`Proposal ${r.laufi}: ${r.payments} payment(s), ${r.exceptions} exception(s)`, "good");
      location.hash = `#/payment-run?run=${r.laufd}:${r.laufi}`;
    } catch (e) { toast(e.message, "bad"); }
  };

  const sel = q.get("run");
  if (!sel) return;
  const [laufd, laufi] = sel.split(":");
  const path = `/payment-runs/${laufd}/${encodeURIComponent(laufi)}`;
  const r = await api(path);
  $("#r-detail").innerHTML = `<div class="card"><div class="card-head">
      <span>Run ${r.laufd} / ${esc(r.laufi)} · <span class="chip ${r.xecht ? "ok" : "dr"}">${esc(r.status)}</span>
        · ${r.payments} payment(s) · ${fmt(r.total)} · discount ${fmt(r.discount)}</span>
      <span style="display:flex;gap:8px">
        ${r.xecht ? `${r.has_transfers ? `<a class="btn small" href="/api${path}/sepa">SEPA transfers (pain.001)</a>` : ""}
          ${r.has_direct_debits ? `<a class="btn small" href="/api${path}/sepa-dd">SEPA direct debits (pain.008)</a>` : ""}`
          : `<button class="btn small secondary" id="r-del">Delete proposal</button>
             <button class="btn small" id="r-exec" ${r.payments ? "" : "disabled"}>Execute payment run</button>`}
      </span></div>
    <table><thead><tr><th>Partner</th><th>Name</th><th>Method</th><th>House bank</th><th>IBAN / mandate</th><th class="num">Discount</th><th class="num">Amount</th><th>Payment doc</th><th>Exception</th></tr></thead>
    <tbody>${r.payees.map((p) => `<tr>
        <td class="mono"><span class="chip ${p.koart === "D" ? "cr" : "dr"}">${p.koart === "D" ? "Customer" : "Vendor"}</span> ${p.partner}</td>
        <td>${esc(p.name1)}</td><td>${esc(p.zlsch || "—")}</td>
        <td>${p.hbkid ? `${esc(p.hbkid)}/${esc(p.hktid)}` : ""}</td>
        <td class="mono">${esc(p.ziban || "")}${p.mndid ? `<div class="help">${esc(p.mndid)}</div>` : ""}</td>
        <td class="num">${Number(p.rskon) ? fmt(p.rskon) : ""}</td><td class="num">${fmt(p.rwbtr)}</td>
        <td class="mono">${p.vblnr ? `<a href="#/documents?doc=${p.vblnr}:${p.gjahr}">${p.vblnr}</a>` : ""}</td>
        <td style="color:var(--bad);white-space:normal">${esc(p.exception || "")}</td></tr>
      ${p.items.map((i) => `<tr class="sub-row"><td></td><td colspan="2" class="mono help">↳ <a href="#/documents?doc=${i.belnr}:${i.gjahr}">${i.belnr}/${i.gjahr}</a></td>
        <td class="help">${esc(i.xblnr || i.sgtxt || "")}</td><td class="help">due ${i.faedt || ""}${i.zlspr ? ` · block ${esc(i.zlspr)}` : ""}</td>
        <td class="num help">${Number(i.wskto) ? fmt(i.wskto) : ""}</td><td class="num help">${fmt(i.wrbtr)}</td><td colspan="2"></td></tr>`).join("")}`).join("")
      || `<tr><td colspan="9" class="empty">Nothing due for payment.</td></tr>`}</tbody></table></div>`;

  if (!r.xecht) {
    $("#r-del").onclick = async () => {
      try { await api(path, { method: "DELETE" }); toast("Proposal deleted", "good"); location.hash = "#/payment-run"; }
      catch (e) { toast(e.message, "bad"); }
    };
    $("#r-exec").onclick = async () => {
      if (!confirm(`Post ${r.payments} payment document(s) for ${fmt(r.total)}? This cannot be undone.`)) return;
      try { const x = await api(`${path}/execute`, { method: "POST", body: "{}" });
        toast(`Payment run executed: ${x.payments} payment(s), ${fmt(x.total)}`, "good"); route(); }
      catch (e) { toast(e.message, "bad"); }
    };
  }
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
