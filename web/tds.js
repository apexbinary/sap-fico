/* Withholding tax (India TDS): codes (OWHT) and the TDS report (register, summary per section and month). */
"use strict";

views["withholding-tax"] = async (c) => {
  const rows = await api("/withholding-tax");
  state.wtCodes = rows;
  const code = query().get("code");
  const edit = code && rows.find((w) => w.wt_code === code);
  const defs = [
    { k: "wt_code", label: "Code", req: true, max: 4, ro: !!edit }, { k: "wt_name", label: "Name", req: true, max: 50 },
    { k: "section", label: "Section", req: true, max: 10 }, { k: "rate", label: "Rate %", type: "number", step: "0.001", min: 0, maxv: 100, req: true },
    { k: "rate_no_pan", label: "Rate without PAN % (206AA)", type: "number", step: "0.001", min: 0, maxv: 100, value: 20 },
    { k: "account", label: "TDS account", type: "select", blank: false, options: O.accounts((a) => !a.control), value: "217000" },
    { k: "thr_single", label: "Threshold per invoice", type: "number", step: "0.01", min: 0, value: 0 },
    { k: "thr_annual", label: "Threshold per financial year", type: "number", step: "0.01", min: 0, value: 0 },
    { k: "thr_type", label: "Above the threshold", type: "select", blank: false, options: [["A", "Whole amount (earlier invoices caught up)"], ["E", "Only the excess (194Q)"]], value: "A" },
    ...(edit ? [{ k: "inactive", label: "Inactive", type: "check" }] : []),
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Withholding Tax (TDS)</h1><div class="sub">Withholding tax codes (OWHT): deducted on A/P invoices of vendors subject to withholding tax</div></div>
      <a class="btn" href="#/withholding-tax?new=1">+ New code</a></div>
    <div class="card"><table><thead><tr><th>Code</th><th>Name</th><th>Section</th><th class="num">Rate %</th><th class="num">No PAN %</th><th class="num">Per invoice</th>
      <th class="num">Per year</th><th>Above threshold</th><th>Account</th><th>Active</th></tr></thead><tbody>
      ${rows.map((w) => `<tr style="cursor:pointer" onclick="location.hash='#/withholding-tax?code=${encodeURIComponent(w.wt_code)}'"><td class="mono">${esc(w.wt_code)}</td>
        <td>${esc(w.wt_name)}</td><td>${esc(w.section)}</td><td class="num">${Number(w.rate)}</td><td class="num">${Number(w.rate_no_pan)}</td>
        <td class="num">${Number(w.thr_single) ? fmt(w.thr_single) : ""}</td><td class="num">${Number(w.thr_annual) ? fmt(w.thr_annual) : ""}</td>
        <td>${w.thr_type === "E" ? "excess" : "whole"}</td><td class="mono">${esc(w.account)}</td><td>${yesNo(!w.inactive)}</td></tr>`).join("")
        || '<tr><td colspan="10" class="empty">No codes.</td></tr>'}</tbody></table></div>
    <div class="card"><div class="card-head">${edit ? `Code ${esc(edit.wt_code)}` : "New code"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(defs, edit || {}, "wt")}</div>
      <div class="help">Base = net amount excl. GST; TDS in whole rupees. Assign codes to vendors in the business partner master data (Accounting).</div>
      <button class="btn" id="wt-save" style="margin-top:8px">${edit ? "Update" : "Add"}</button></div></div>`;
  $("#wt-save").onclick = async () => {
    const body = readFields(defs, "wt");
    const r = edit ? await act(() => patch(`/withholding-tax/${encodeURIComponent(edit.wt_code)}`, body), "Code updated")
      : await act(() => post("/withholding-tax", body), (w) => `Code ${w.wt_code} added`);
    if (r) location.hash = `#/withholding-tax?code=${encodeURIComponent(r.wt_code)}&r=${Date.now()}`;
  };
};

views["tds-report"] = async (c) => {
  const now = new Date(), from = query().get("from") || `${now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1}-04-01`;
  const to = query().get("to") || new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
  const r = await api(`/reports/tds?date_from=${from}&date_to=${to}`);
  c.innerHTML = `<div class="page-head"><div><h1>TDS Report</h1><div class="sub">${from} – ${to} · tax deducted at source on A/P invoices less A/P credit memos</div></div></div>
    ${periodToolbar(from, to)}
    <div class="tiles"><div class="tile"><div class="label">TDS deducted</div><div class="value">${fmt(r.total)}</div><div class="foot">${r.rows.length} documents</div></div></div>
    <div class="card"><div class="card-head">Summary by section and month (deposit by the due date, challan ITNS 281)</div><table><thead><tr><th>Month</th><th>Section</th>
      <th class="num">Documents</th><th class="num">Base</th><th class="num">TDS</th><th>Due date</th></tr></thead><tbody>
      ${r.summary.map((x) => `<tr><td>${x.month}</td><td>${esc(x.section)}</td><td class="num">${x.documents}</td><td class="num">${fmt(x.base)}</td>
        <td class="num">${fmt(x.tds)}</td><td>${x.due_date}</td></tr>`).join("") || '<tr><td colspan="6" class="empty">No TDS in this period.</td></tr>'}</tbody></table></div>
    <div class="card"><div class="card-head">Register</div><div style="overflow-x:auto"><table><thead><tr><th>Document</th><th>No.</th><th>Date</th><th>Vendor</th><th>PAN</th>
      <th>Code</th><th>Section</th><th class="num">Rate %</th><th class="num">Base</th><th class="num">TDS</th></tr></thead><tbody>
      ${r.rows.map((x) => `<tr><td>${x.obj === "18" ? "A/P Invoice" : "A/P Credit Memo"}</td><td><a href="#/docs?obj=${x.obj}&entry=${x.doc_entry}">${x.doc_num}</a></td>
        <td>${x.doc_date}</td><td>${esc(x.card_name || x.card_code)}</td><td class="mono">${esc(x.pan || "")}${x.no_pan ? ' <span class="status X">no PAN</span>' : ""}</td>
        <td class="mono">${esc(x.wt_code)}</td><td>${esc(x.section)}</td><td class="num">${Number(x.rate)}</td><td class="num">${fmt(x.base)}</td><td class="num">${fmt(x.tds)}</td></tr>`).join("")
        || '<tr><td colspan="10" class="empty">No TDS in this period.</td></tr>'}</tbody></table></div></div>`;
  bindToolbar("tds-report");
};
