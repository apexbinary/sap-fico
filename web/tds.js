/* Withholding tax (India): TDS / TCS codes (OWHT), the TDS / TCS register, challans (deposit with the government),
   quarterly returns (Form 26Q / 27EQ) and certificates (Form 16A / 27D). */
"use strict";

const WT_KIND = { D: "TDS (deducted on purchases)", C: "TCS (collected on sales)" };
const fyNow = () => { const d = new Date(); return d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1; };

views["withholding-tax"] = async (c) => {
  const rows = await api("/withholding-tax");
  state.wtCodes = rows;
  const code = query().get("code");
  const edit = code && rows.find((w) => w.wt_code === code);
  const defs = [
    { k: "wt_code", label: "Code", req: true, max: 4, ro: !!edit }, { k: "wt_name", label: "Name", req: true, max: 50 },
    { k: "wt_kind", label: "Kind", type: "select", blank: false, options: Object.entries(WT_KIND), value: "D" },
    { k: "section", label: "Section", req: true, max: 10 }, { k: "rate", label: "Rate %", type: "number", step: "0.001", min: 0, maxv: 100, req: true },
    { k: "rate_no_pan", label: "Rate without PAN % (206AA / 206CC)", type: "number", step: "0.001", min: 0, maxv: 100, value: 20 },
    { k: "base_type", label: "Base", type: "select", blank: false, options: [["N", "Net (excl. GST)"], ["G", "Gross (incl. GST)"]], value: "N" },
    { k: "account", label: "TDS / TCS account", type: "select", blank: false, options: O.accounts((a) => !a.control), value: "217000" },
    { k: "thr_single", label: "Threshold per invoice", type: "number", step: "0.01", min: 0, value: 0 },
    { k: "thr_annual", label: "Threshold per financial year", type: "number", step: "0.01", min: 0, value: 0 },
    { k: "thr_type", label: "Above the threshold", type: "select", blank: false, options: [["A", "Whole amount (earlier invoices caught up)"], ["E", "Only the excess (194Q)"]], value: "A" },
    ...(edit ? [{ k: "inactive", label: "Inactive", type: "check" }] : []),
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Withholding Tax (TDS / TCS)</h1><div class="sub">Codes (OWHT): TDS deducted on A/P invoices and advances, TCS collected on A/R invoices</div></div>
      <a class="btn" href="#/withholding-tax?new=1">+ New code</a></div>
    <div class="card"><table><thead><tr><th>Code</th><th>Name</th><th>Kind</th><th>Section</th><th class="num">Rate %</th><th class="num">No PAN %</th><th>Base</th><th class="num">Per invoice</th>
      <th class="num">Per year</th><th>Above threshold</th><th>Account</th><th>Active</th></tr></thead><tbody>
      ${rows.map((w) => `<tr style="cursor:pointer" onclick="location.hash='#/withholding-tax?code=${encodeURIComponent(w.wt_code)}'"><td class="mono">${esc(w.wt_code)}</td>
        <td>${esc(w.wt_name)}</td><td>${w.wt_kind === "C" ? "TCS" : "TDS"}</td><td>${esc(w.section)}</td><td class="num">${Number(w.rate)}</td><td class="num">${Number(w.rate_no_pan)}</td>
        <td>${w.base_type === "G" ? "gross" : "net"}</td><td class="num">${Number(w.thr_single) ? fmt(w.thr_single) : ""}</td><td class="num">${Number(w.thr_annual) ? fmt(w.thr_annual) : ""}</td>
        <td>${w.thr_type === "E" ? "excess" : "whole"}</td><td class="mono">${esc(w.account)}</td><td>${yesNo(!w.inactive)}</td></tr>`).join("")
        || '<tr><td colspan="12" class="empty">No codes.</td></tr>'}</tbody></table></div>
    <div class="card"><div class="card-head">${edit ? `Code ${esc(edit.wt_code)}` : "New code"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(defs, edit || {}, "wt")}</div>
      <div class="help">TDS / TCS in whole rupees. Assign codes to vendors (TDS) and customers (TCS) in the business partner master data (Accounting).</div>
      <button class="btn" id="wt-save" style="margin-top:8px">${edit ? "Update" : "Add"}</button></div></div>`;
  $("#wt-save").onclick = async () => {
    const body = readFields(defs, "wt");
    const r = edit ? await act(() => patch(`/withholding-tax/${encodeURIComponent(edit.wt_code)}`, body), "Code updated")
      : await act(() => post("/withholding-tax", body), (w) => `Code ${w.wt_code} added`);
    if (r) location.hash = `#/withholding-tax?code=${encodeURIComponent(r.wt_code)}&r=${Date.now()}`;
  };
};

const WT_DOC = { "18": "A/P Invoice", "19": "A/P Credit Memo", "13": "A/R Invoice", "14": "A/R Credit Memo", "46": "Outgoing Payment (advance)" };
const wtDocLink = (x) => (x.obj === "46" ? `<a href="#/payments?kind=outgoing&entry=${x.doc_entry}">${x.doc_num}</a>` : `<a href="#/docs?obj=${x.obj}&entry=${x.doc_entry}">${x.doc_num}</a>`);

views["tds-report"] = async (c) => {
  const now = new Date(), from = query().get("from") || `${now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1}-04-01`;
  const to = query().get("to") || new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
  const r = await api(`/reports/tds?date_from=${from}&date_to=${to}`);
  const out = r.summary.reduce((s, x) => s + Number(x.outstanding), 0);
  c.innerHTML = `<div class="page-head"><div><h1>TDS / TCS Report</h1><div class="sub">${from} – ${to} · tax deducted / collected at source, deposits (challans)</div></div>
      <span style="display:flex;gap:8px"><a class="btn secondary" href="#/tds-challans">Challans</a><a class="btn secondary" href="#/tds-returns">Quarterly returns</a></span></div>
    ${periodToolbar(from, to)}
    <div class="tiles"><div class="tile"><div class="label">TDS deducted</div><div class="value">${fmt(r.total)}</div></div>
      <div class="tile"><div class="label">TCS collected</div><div class="value">${fmt(r.total_tcs)}</div></div>
      <div class="tile"><div class="label">Not deposited yet</div><div class="value">${fmt(out)}</div><div class="foot">${r.rows.length} deductions</div></div></div>
    <div class="card"><div class="card-head">Summary by kind, section and month (deposit by the due date, challan ITNS 281)</div><table><thead><tr><th>Month</th><th>Kind</th><th>Section</th>
      <th class="num">Rows</th><th class="num">Base</th><th class="num">Tax</th><th class="num">Deposited</th><th class="num">Outstanding</th><th>Due date</th></tr></thead><tbody>
      ${r.summary.map((x) => `<tr><td>${x.month}</td><td>${x.kind === "C" ? "TCS" : "TDS"}</td><td>${esc(x.section)}</td><td class="num">${x.documents}</td><td class="num">${fmt(x.base)}</td>
        <td class="num">${fmt(x.tds)}</td><td class="num">${fmt(x.deposited)}</td><td class="num">${Number(x.outstanding) ? `<b>${fmt(x.outstanding)}</b>` : fmt(0)}</td><td>${x.due_date}</td></tr>`).join("")
        || '<tr><td colspan="9" class="empty">No TDS / TCS in this period.</td></tr>'}</tbody></table></div>
    <div class="card"><div class="card-head">Register</div><div style="overflow-x:auto"><table><thead><tr><th>Document</th><th>No.</th><th>Date</th><th>Partner</th><th>PAN</th>
      <th>Code</th><th>Section</th><th class="num">Rate %</th><th class="num">Base</th><th class="num">Tax</th><th class="num">Adjusted from advance</th><th>Challan</th></tr></thead><tbody>
      ${r.rows.map((x) => `<tr><td>${WT_DOC[x.obj]}</td><td>${wtDocLink(x)}</td>
        <td>${x.doc_date}</td><td>${esc(x.card_name || x.card_code)}</td><td class="mono">${esc(x.pan || "")}${x.no_pan ? ' <span class="status X">no PAN</span>' : ""}</td>
        <td class="mono">${esc(x.wt_code)}</td><td>${esc(x.section)}</td><td class="num">${Number(x.rate)}</td><td class="num">${fmt(x.base)}</td><td class="num">${fmt(x.tds)}</td>
        <td class="num">${Number(x.adv_adj) ? fmt(x.adv_adj) : ""}</td><td>${esc(x.challan || "")}</td></tr>`).join("")
        || '<tr><td colspan="12" class="empty">No TDS / TCS in this period.</td></tr>'}</tbody></table></div></div>`;
  bindToolbar("tds-report");
};

views["tds-challans"] = async (c) => {
  const r = await api(`/reports/tds?date_from=2000-01-01&date_to=2100-12-31`);
  const sections = [...new Set([...r.rows.map((x) => `${x.kind}|${x.section}`), ...(state.wtCodes || []).map((w) => `${w.wt_kind}|${w.section}`)])];
  const defs = [
    { k: "wt_kind", label: "Kind", type: "select", blank: false, options: [["D", "TDS"], ["C", "TCS"]] },
    { k: "section", label: "Section", type: "select", blank: false, req: true, options: [...new Set(sections.map((s) => s.split("|")[1]))].map((s) => [s, s]) },
    { k: "period_to", label: "Deductions up to", type: "date", req: true, value: today() },
    { k: "dep_date", label: "Deposit date", type: "date", req: true, value: today() },
    { k: "bsr_code", label: "BSR code (7 digits)", max: 7, req: true }, { k: "challan_no", label: "Challan serial no.", max: 5, req: true },
    { k: "bank_acct", label: "Paid from (bank account)", type: "select", blank: false, options: O.accounts((a) => !a.control), value: "112000" },
    { k: "interest", label: "Interest (empty: calculated)", type: "number", step: "1", min: 0 }, { k: "fee", label: "Late fee (234E)", type: "number", step: "1", min: 0 },
  ];
  c.innerHTML = `<div class="page-head"><div><h1>TDS / TCS Challans</h1><div class="sub">Deposit of the tax deducted / collected (ITNS 281): bank journal entry and the deductions it covers</div></div>
      <a class="btn secondary" href="#/tds-report">Register</a></div>
    <div class="card"><div class="card-head">New challan</div><div class="card-body"><div class="form-grid">${fieldsHtml(defs, {}, "ch")}</div>
      <div style="display:flex;gap:8px;margin-top:8px"><button class="btn secondary" id="ch-prev">Preview</button><button class="btn" id="ch-add">Post challan</button></div>
      <div id="ch-out" style="margin-top:10px"></div>
      <p class="help">Interest for late deposit: TDS 1.5 % / TCS 1 % per month or part of a month from the date of deduction. The journal entry debits the TDS / TCS
        payable accounts (and 619000 interest / fee) and credits the bank.</p></div></div>
    <div class="card"><table><thead><tr><th>No.</th><th>Kind</th><th>Section</th><th>Up to</th><th>Deposited</th><th>BSR / challan</th><th class="num">Tax</th><th class="num">Interest</th>
      <th class="num">Fee</th><th class="num">Total</th><th>JE</th><th>Status</th><th></th></tr></thead><tbody>
      ${r.challans.map((x) => `<tr><td>${x.abs_entry}</td><td>${x.wt_kind === "C" ? "TCS" : "TDS"}</td><td>${esc(x.section)}</td><td>${x.period_to}</td><td>${x.dep_date}</td>
        <td class="mono">${esc(x.bsr_code)} / ${esc(x.challan_no)}</td><td class="num">${fmt(x.tax_amnt)}</td><td class="num">${fmt(x.interest)}</td><td class="num">${fmt(x.fee)}</td>
        <td class="num">${fmt(x.total)}</td><td>${x.trans_id ? `<a href="#/journal?id=${x.trans_id}">${x.trans_id}</a>` : ""}</td>
        <td>${x.canceled ? '<span class="status C">canceled</span>' : '<span class="status O">deposited</span>'}</td>
        <td>${x.canceled ? "" : `<button class="btn small ghost ch-cancel" data-id="${x.abs_entry}">Cancel</button>`}</td></tr>`).join("")
        || '<tr><td colspan="13" class="empty">No challans.</td></tr>'}</tbody></table></div>`;
  const read = () => readFields(defs, "ch");
  $("#ch-prev").onclick = async () => {
    const b = read();
    const p = await act(() => api(`/withholding-tax/challans/preview?wt_kind=${b.wt_kind}&section=${encodeURIComponent(b.section)}&period_to=${b.period_to}&dep_date=${b.dep_date}`));
    if (!p) return;
    $("#ch-out").innerHTML = `<b>${p.rows.length} deductions: tax ${fmt(p.tax)}, interest ${fmt(p.interest)}</b>
      <table><tbody>${p.rows.map((x) => `<tr><td>${WT_DOC[x.obj]} ${wtDocLink(x)}</td><td>${x.doc_date}</td><td>${esc(x.card_name || x.card_code)}</td><td class="num">${fmt(x.tds)}</td><td>due ${x.due_date}</td></tr>`).join("")}</tbody></table>`;
  };
  $("#ch-add").onclick = async () => {
    if (await act(() => post("/withholding-tax/challans", read()), (x) => `Challan ${x.challan_no} posted: ${fmt(x.total)}`)) location.hash = `#/tds-challans?r=${Date.now()}`;
  };
  $$(".ch-cancel").forEach((b) => (b.onclick = async () => {
    if (!confirm("Cancel this challan? Its journal entry is reversed and the deductions are open again.")) return;
    if (await act(() => post(`/withholding-tax/challans/${b.dataset.id}/cancel`, {}), "Challan canceled")) location.hash = `#/tds-challans?r=${Date.now()}`;
  }));
};

views["tds-returns"] = async (c) => {
  const q = query(), fy = Number(q.get("fy") || fyNow()), quarter = Number(q.get("quarter") || 1), kind = q.get("kind") || "D";
  const defs = [
    { k: "kind", label: "Return", type: "select", blank: false, options: [["D", "Form 26Q (TDS, non-salary)"], ["C", "Form 27EQ (TCS)"]] },
    { k: "fy", label: "Financial year (starting April)", type: "number", step: 1, min: 2000, maxv: 2100, req: true },
    { k: "quarter", label: "Quarter", type: "select", blank: false, int: true, options: [[1, "Q1 Apr-Jun"], [2, "Q2 Jul-Sep"], [3, "Q3 Oct-Dec"], [4, "Q4 Jan-Mar"]] },
  ];
  const args = `fy=${fy}&quarter=${quarter}&kind=${kind}`;
  const r = await api(`/withholding-tax/returns?${args}`);
  const parties = [...new Map(r.deductees.map((d) => [d.card_code, d])).values()];
  c.innerHTML = `<div class="page-head"><div><h1>TDS / TCS Returns</h1><div class="sub">Form ${r.form} for ${r.fy} Q${quarter} (${r.date_from} – ${r.date_to}) · TAN ${esc(r.deductor.tan || "missing")}</div></div>
      <a class="btn" href="/api/withholding-tax/returns/csv?${args}" download>Download deductee records (CSV)</a></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(defs, { kind, fy, quarter }, "rt")}
      <div class="field"><label>&nbsp;</label><button class="btn" id="rt-go">Show</button></div></div></div></div>
    ${r.issues.length ? `<div class="card"><div class="card-head">Check before filing (${r.issues.length})</div><div class="card-body"><ul class="gr-issues">${r.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div></div>` : ""}
    <div class="tiles"><div class="tile"><div class="label">Amount paid / credited</div><div class="value">${fmt(r.total_amount)}</div></div>
      <div class="tile"><div class="label">Tax</div><div class="value">${fmt(r.total_tax)}</div><div class="foot">${r.deductees.length} records</div></div></div>
    <div class="card"><div class="card-head">Challans</div><table><thead><tr><th>BSR / challan</th><th>Deposited</th><th>Section</th><th class="num">Tax</th><th class="num">Interest</th><th class="num">Fee</th><th class="num">Booked in this quarter</th></tr></thead><tbody>
      ${r.challans.map((x) => `<tr><td class="mono">${esc(x.bsr_code)} / ${esc(x.challan_no)}</td><td>${x.dep_date}</td><td>${esc(x.section)}</td><td class="num">${fmt(x.tax_amnt)}</td>
        <td class="num">${fmt(x.interest)}</td><td class="num">${fmt(x.fee)}</td><td class="num">${fmt(x.booked)}</td></tr>`).join("") || '<tr><td colspan="7" class="empty">No challans.</td></tr>'}</tbody></table></div>
    <div class="card"><div class="card-head">Deductee / collectee records</div><div style="overflow-x:auto"><table><thead><tr><th>#</th><th>PAN</th><th>Name</th><th>Section</th><th>Paid / credited</th>
      <th class="num">Amount</th><th class="num">Rate %</th><th class="num">Tax</th><th>Challan</th><th>Deposited</th><th>Document</th><th></th></tr></thead><tbody>
      ${r.deductees.map((d) => `<tr><td>${d.record}</td><td class="mono">${esc(d.pan)}</td><td>${esc(d.name || "")}</td><td>${esc(d.section)}</td><td>${d.date_paid_credited}</td>
        <td class="num">${fmt(d.amount)}</td><td class="num">${Number(d.rate)}</td><td class="num">${fmt(d.tax)}</td><td class="mono">${esc(d.challan || "")}</td><td>${d.deposit_date || ""}</td>
        <td>${esc(d.document)}</td><td></td></tr>`).join("") || '<tr><td colspan="12" class="empty">No records in this quarter.</td></tr>'}</tbody></table></div></div>
    <div class="card"><div class="card-head">Certificates (Form ${kind === "D" ? "16A" : "27D"})</div><div class="card-body">
      ${parties.map((d) => `<a class="btn small secondary" href="#/tds-certificate?${args}&card=${encodeURIComponent(d.card_code)}" style="margin:2px">${esc(d.name || d.card_code)}</a>`).join("") || '<span class="help">No deductees.</span>'}</div></div>`;
  $("#rt-go").onclick = () => { const f = readFields(defs, "rt"); location.hash = `#/tds-returns?fy=${f.fy}&quarter=${f.quarter}&kind=${f.kind}`; };
};

views["tds-certificate"] = async (c) => {
  const q = query();
  const r = await api(`/withholding-tax/certificate?fy=${q.get("fy")}&quarter=${q.get("quarter")}&kind=${q.get("kind") || "D"}&card_code=${encodeURIComponent(q.get("card") || "")}`);
  const tds = r.form === "16A";
  c.innerHTML = `<div class="page-head no-print"><div><h1>Form ${r.form}</h1><div class="sub">${esc(r.deductee.name)} · ${r.fy} Q${r.quarter}</div></div>
      <span style="display:flex;gap:8px"><a class="btn secondary" href="#/tds-returns?fy=${q.get("fy")}&quarter=${q.get("quarter")}&kind=${q.get("kind") || "D"}">Back</a>
      <button class="btn" onclick="window.print()">Print / PDF</button></span></div>
    <div class="card print-page"><div class="card-body">
      <h2 style="text-align:center;margin:0">FORM NO. ${r.form}</h2>
      <p style="text-align:center;margin:4px 0 14px">Certificate under section ${tds ? "203 of the Income-tax Act, 1961 for tax deducted at source" : "206C of the Income-tax Act, 1961 for tax collected at source"}</p>
      <table><tbody>
        <tr><td><b>${tds ? "Deductor" : "Collector"}</b><br>${esc(r.deductor.name)}<br>TAN ${esc(r.deductor.tan || "-")} · PAN ${esc(r.deductor.pan || "-")}</td>
            <td><b>${tds ? "Deductee" : "Collectee"}</b><br>${esc(r.deductee.name)}<br>${esc(r.deductee.address || "")}<br>PAN ${esc(r.deductee.pan)}</td></tr>
        <tr><td>Financial year ${r.fy} · Quarter ${r.quarter}</td><td>Period ${r.date_from} – ${r.date_to}</td></tr></tbody></table>
      <h3 class="section">Amounts paid / credited and tax ${tds ? "deducted" : "collected"}</h3>
      <table><thead><tr><th>#</th><th>Section</th><th>Date</th><th class="num">Amount</th><th class="num">Rate %</th><th class="num">Tax</th><th>BSR / challan</th><th>Deposited on</th></tr></thead><tbody>
        ${r.rows.map((d, i) => `<tr><td>${i + 1}</td><td>${esc(d.section)}</td><td>${d.date_paid_credited}</td><td class="num">${fmt(d.amount)}</td><td class="num">${Number(d.rate)}</td>
          <td class="num">${fmt(d.tax)}</td><td class="mono">${esc(d.challan || "not deposited")}</td><td>${d.deposit_date || ""}</td></tr>`).join("")}
        <tr class="total"><td colspan="3">Total</td><td class="num">${fmt(r.total_amount)}</td><td></td><td class="num">${fmt(r.total_tax)}</td><td colspan="2">deposited ${fmt(r.deposited)}</td></tr></tbody></table>
      <p class="help" style="margin-top:14px">Prepared from the books. The certificate to be issued is the one downloaded from TRACES after the quarterly return is processed.</p>
    </div></div>`;
};
