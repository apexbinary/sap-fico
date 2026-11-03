/* Aging (customers / vendors), business partner statement, cash flow. */
"use strict";

views.aging = async (c) => {
  const q = query(), on = q.get("on") || today(), type = q.get("type") || "C";
  const r = await api(`/reports/aging?on=${on}&card_type=${type}`);
  const LABEL = { current: "Not due", "1-30": "1-30", "31-60": "31-60", "61-90": "61-90", "91-120": "91-120", "120+": "Over 120" };
  c.innerHTML = `<div class="page-head"><div><h1>${type === "C" ? "Customer" : "Vendor"} Aging</h1><div class="sub">Open items on ${on} by days overdue</div></div>
      <span style="display:flex;gap:8px;align-items:center"><select id="ag-type">${opt("C", "Customers", type)}${opt("S", "Vendors", type)}</select>
      <input type="date" id="ag-on" value="${esc(on)}"></span></div>
    <div class="card"><div style="overflow-x:auto"><table><thead><tr><th>Business partner</th><th>Name</th>${r.buckets.map((b) => `<th class="num">${LABEL[b]}</th>`).join("")}<th class="num">Total</th></tr></thead><tbody>
      ${r.partners.map((p, n) => `<tr style="cursor:pointer" onclick="document.getElementById('ag-${n}').classList.toggle('hidden')"><td class="mono">${esc(p.card_code)}</td><td>${esc(p.card_name)}</td>
        ${r.buckets.map((b) => `<td class="num">${Number(p[b]) ? fmt(p[b]) : ""}</td>`).join("")}<td class="num"><b>${fmt(p.total)}</b></td></tr>
        <tr id="ag-${n}" class="hidden"><td></td><td colspan="${r.buckets.length + 2}"><table><thead><tr><th>Document</th><th>Posting</th><th>Due</th><th class="num">Days</th><th class="num">Open</th></tr></thead><tbody>
          ${p.items.map((i) => `<tr><td>${docLink(i.trans_type, i.doc_entry, `${transTypeName(i.trans_type)} ${i.base_ref || ""}`)}</td><td>${i.ref_date}</td><td>${i.due_date}</td>
            <td class="num">${i.days > 0 ? i.days : ""}</td><td class="num">${fmt(i.open)}</td></tr>`).join("")}</tbody></table>
          <a class="btn small ghost" href="#/statement?code=${encodeURIComponent(p.card_code)}&to=${on}">Statement</a></td></tr>`).join("")
        || `<tr><td colspan="${r.buckets.length + 3}" class="empty">No open items.</td></tr>`}</tbody>
      <tfoot><tr><td colspan="2">Total</td>${r.buckets.map((b) => `<td class="num">${fmt(r.totals[b])}</td>`).join("")}<td class="num">${fmt(r.totals.total)}</td></tr></tfoot></table></div></div>`;
  const go = () => { location.hash = `#/aging?type=${$("#ag-type").value}&on=${$("#ag-on").value}`; };
  $("#ag-type").onchange = go; $("#ag-on").onchange = go;
};

views.statement = async (c) => {
  const q = query(), code = q.get("code") || "", from = q.get("from") || yearStart(), to = q.get("to") || today();
  const defs = [{ k: "code", label: "Business partner", type: "select", blank: false, options: state.partners.map((p) => [p.card_code, `${p.card_code} — ${p.card_name}`]) },
    { k: "from", label: "From", type: "date" }, { k: "to", label: "To", type: "date" }];
  const r = code ? await api(`/reports/statement?card_code=${encodeURIComponent(code)}&date_from=${from}&date_to=${to}`) : null;
  c.innerHTML = `<div class="page-head no-print"><div><h1>Account Statement</h1><div class="sub">Business partner movements with running balance and open items</div></div>
      ${r ? '<button class="btn secondary" onclick="window.print()">Print / PDF</button>' : ""}</div>
    <div class="card no-print"><div class="card-body"><div class="form-grid">${fieldsHtml(defs, { code, from, to }, "st")}
      <div class="field"><label>&nbsp;</label><button class="btn" id="st-go">Show</button></div></div></div></div>
    ${r ? `<div class="card"><div class="card-head"><span>${esc(state.company.company_name)} · Statement of account: <b>${esc(r.card_name)}</b> (${esc(r.card_code)})</span>
        <span>${r.date_from} – ${r.date_to}</span></div>
      <table><thead><tr><th>Date</th><th>Document</th><th>Remarks</th><th>Due</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance</th></tr></thead><tbody>
        <tr><td>${r.date_from}</td><td colspan="5">Opening balance</td><td class="num">${fmt(r.opening)}</td></tr>
        ${r.lines.map((l) => `<tr><td>${l.ref_date}</td><td>${docLink(l.trans_type, l.doc_entry, `${esc(l.origin)} ${esc(l.base_ref || "")}`)}</td><td>${esc(l.memo || "")}</td>
          <td>${l.due_date}</td><td class="num">${Number(l.debit) ? fmt(l.debit) : ""}</td><td class="num">${Number(l.credit) ? fmt(l.credit) : ""}</td><td class="num">${fmt(l.balance)}</td></tr>`).join("")}
        <tr class="total"><td>${r.date_to}</td><td colspan="3">Closing balance</td><td class="num">${fmt(r.debits)}</td><td class="num">${fmt(r.credits)}</td><td class="num">${fmt(r.closing)}</td></tr></tbody></table>
      <div class="card-body"><h3 class="section">Open items on ${r.date_to}</h3><table><thead><tr><th>Document</th><th>Date</th><th>Due</th><th class="num">Days overdue</th><th class="num">Open</th></tr></thead><tbody>
        ${r.open_items.map((i) => `<tr><td>${docLink(i.trans_type, i.doc_entry, `${transTypeName(i.trans_type)} ${i.base_ref || ""}`)}</td><td>${i.ref_date}</td><td>${i.due_date}</td>
          <td class="num">${i.days > 0 ? i.days : ""}</td><td class="num">${fmt(i.open)}</td></tr>`).join("") || '<tr><td colspan="5" class="empty">No open items.</td></tr>'}</tbody></table></div></div>` : ""}`;
  $("#st-go").onclick = () => { const f = readFields(defs, "st"); location.hash = `#/statement?code=${encodeURIComponent(f.code)}&from=${f.from}&to=${f.to}`; };
};

views["cash-flow"] = async (c) => {
  const from = query().get("from") || yearStart(), to = query().get("to") || yearEnd();
  const r = await api(`/reports/cash-flow?date_from=${from}&date_to=${to}`);
  c.innerHTML = `<div class="page-head"><div><h1>Cash Flow</h1><div class="sub">${from} – ${to} · cash and bank accounts by origin of the movement</div></div></div>
    ${periodToolbar(from, to)}
    <div class="tiles"><div class="tile"><div class="label">Opening cash</div><div class="value">${fmt(r.opening)}</div></div>
      <div class="tile"><div class="label">Receipts</div><div class="value good">${fmt(r.total_in)}</div></div>
      <div class="tile"><div class="label">Payments</div><div class="value bad">${fmt(r.total_out)}</div></div>
      <div class="tile"><div class="label">Closing cash</div><div class="value">${fmt(r.closing)}</div></div></div>
    <div class="grid-2"><div class="card"><div class="card-head">By origin</div><table><thead><tr><th>Origin</th><th class="num">Receipts</th><th class="num">Payments</th><th class="num">Net</th></tr></thead><tbody>
      ${r.flows.map((f) => `<tr><td>${esc(f.origin)}</td><td class="num">${fmt(f.in)}</td><td class="num">${fmt(f.out)}</td><td class="num">${fmt(f.net)}</td></tr>`).join("")
        || '<tr><td colspan="4" class="empty">No cash movements.</td></tr>'}</tbody></table></div>
      <div class="card"><div class="card-head">By account</div><table><thead><tr><th>Account</th><th>Name</th><th class="num">Movement</th></tr></thead><tbody>
      ${r.accounts.map((a) => `<tr><td class="mono">${esc(a.acct_code)}</td><td>${esc(a.acct_name)}</td><td class="num">${fmt(a.movement)}</td></tr>`).join("")}</tbody></table></div></div>`;
  bindToolbar("cash-flow");
};
