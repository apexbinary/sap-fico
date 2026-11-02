/* Banking: incoming / outgoing payments, deposits and the checks register. */
"use strict";

const PAY_KINDS = { incoming: { obj: "24", name: "Incoming Payment", list: "Incoming Payments" },
  outgoing: { obj: "46", name: "Outgoing Payment", list: "Outgoing Payments" } };
const PAY_TYPES = [["C", "Customer"], ["S", "Vendor"], ["A", "Account"]];
const cashAccounts = () => O.accounts((a) => a.cash)();

views.payments = async (c) => {
  const kind = query().get("kind") || "incoming", entry = query().get("entry");
  const k = PAY_KINDS[kind];
  const list = await api(`/payments/${kind}?limit=100`);
  c.innerHTML = `<div class="page-head"><div><h1>${k.list}</h1><div class="sub">Banking — ${kind === "incoming" ? "ORCT" : "OVPM"}</div></div>
      <a class="btn" href="#/payment?kind=${kind}">+ New ${k.name}</a></div>
    <div class="card"><table><thead><tr><th>No.</th><th>Posting date</th><th>Type</th><th>BP code</th><th>BP name</th><th>Currency</th>
      <th class="num">Total (LC)</th><th class="num">On account</th><th>Reference</th><th>Status</th></tr></thead>
      <tbody>${list.map((p) => `<tr style="cursor:pointer" onclick="location.hash='#/payments?kind=${kind}&entry=${p.doc_entry}'">
        <td class="mono">${p.doc_num}</td><td>${p.doc_date}</td><td>${esc(nameOf(PAY_TYPES.map(([v, l]) => ({ v, l })), "v", p.doc_type, "l"))}</td>
        <td class="mono">${esc(p.card_code || "")}</td><td>${esc(p.card_name || "")}</td><td>${esc(p.doc_curr)}</td>
        <td class="num">${fmt(p.doc_total)}</td><td class="num">${Number(p.no_doc_sum) ? fmt(p.no_doc_sum) : ""}</td><td>${esc(p.counter_ref || "")}</td>
        <td>${p.canceled ? '<span class="status X">Canceled</span>' : '<span class="status C">Closed</span>'}</td></tr>`).join("")
        || `<tr><td colspan="10" class="empty">No payments yet.</td></tr>`}</tbody></table></div><div id="pay-detail"></div>`;
  if (entry) await paymentDetail($("#pay-detail"), kind, entry);
};

function paymentHeaderDefs(kind, ro = false) {
  return [
    { k: "doc_type", label: "Type", type: "select", blank: false, options: PAY_TYPES, ro, value: kind === "incoming" ? "C" : "S" },
    { k: "card_code", label: "Code", type: "select", options: [], ro, blank: "— select —" },
    { k: "cntct_code", label: "Contact person", type: "select", int: true, options: [], ro },
    { k: "doc_num", label: "No.", ro: true },
    { k: "series", label: "Series", type: "select", options: [["1", "Primary"]], blank: false, ro: true },
    { k: "doc_date", label: "Posting date", type: "date", req: true, value: today(), ro },
    { k: "doc_due_date", label: "Due date", type: "date", value: today(), ro },
    { k: "tax_date", label: "Document date", type: "date", value: today(), ro },
    { k: "doc_curr", label: "Currency", type: "select", blank: false, options: () => O.currencies(), value: state.company.main_curncy, ro },
    { k: "counter_ref", label: "Reference", max: 8, ro },
    { k: "ref2", label: "Ref. 2", max: 11, ro },
    { k: "prj_code", label: "Project", type: "select", options: () => O.projects(), ro },
    { k: "jrnl_memo", label: "Journal remarks", max: 50, ro, span: 2 },
    { k: "comments", label: "Remarks", type: "textarea", max: 254, ro, span: 2 },
    { k: "pay_no_doc", label: "Payment on account", type: "check", ro },
  ];
}
const MEANS_TRANSFER = [
  { k: "trsfr_acct", label: "G/L account", type: "select", options: cashAccounts, value: "112000" },
  { k: "trsfr_date", label: "Transfer date", type: "date", value: today() },
  { k: "trsfr_ref", label: "Reference", max: 27 },
  { k: "trsfr_sum", label: "Total", type: "number", step: "0.01", min: 0 },
  { k: "bank_chrg", label: "Bank charges (LC)", type: "number", step: "0.01", min: 0 },
];
const MEANS_CASH = [
  { k: "cash_acct", label: "G/L account", type: "select", options: cashAccounts, value: "111000" },
  { k: "cash_sum", label: "Total", type: "number", step: "0.01", min: 0 },
];

async function paymentDetail(el, kind, entry) {
  const p = await api(`/payments/${kind}/${entry}`);
  const bp = p.card_code ? await api(`/partners/${encodeURIComponent(p.card_code)}`) : { contacts: [] };
  const name = (code) => nameOf(state.accounts, "acct_code", code, "acct_name");
  const defs = paymentHeaderDefs(kind, true).map((f) => f.k === "card_code" ? { ...f, options: p.card_code ? [[p.card_code, `${p.card_code} — ${p.card_name}`]] : [] }
    : f.k === "cntct_code" ? { ...f, options: bp.contacts.map((x) => [x.cntct_code, x.name]) } : f);
  el.innerHTML = `<div class="card"><div class="card-head"><span>${PAY_KINDS[kind].name} ${p.doc_num} ${p.canceled ? '<span class="status X">Canceled</span>' : ""}</span>
      <span style="display:flex;gap:6px">${p.canceled ? "" : '<button class="btn small secondary" id="pay-cancel">Cancel</button>'}
      ${p.trans_id ? `<a class="btn small ghost" href="#/journal?id=${p.trans_id}">Journal entry ${p.trans_id} &#8599;</a>` : ""}</span></div>
    <div class="card-body"><div class="form-grid">${fieldsHtml(defs, { ...p, series: String(p.series || 1) }, "pv")}</div></div>
    ${p.invoices.length ? `<table><thead><tr><th>Document</th><th>No. / Trans. No.</th><th class="num">Amount applied (LC)</th>${p.doc_curr !== state.company.main_curncy ? '<th class="num">Applied (FC)</th>' : ""}</tr></thead><tbody>
      ${p.invoices.map((i) => `<tr><td>${docLink(i.inv_type, i.doc_entry, DOC_NAMES[i.inv_type] || PAY_KINDS[i.inv_type === "24" ? "incoming" : "outgoing"]?.name || "Journal entry")}</td>
        <td><a href="#/journal?id=${i.doc_trans_id}">${i.doc_trans_id}</a></td><td class="num">${fmt(i.sum_applied)}</td>
        ${p.doc_curr !== state.company.main_curncy ? `<td class="num">${fmt(i.applied_fc)}</td>` : ""}</tr>`).join("")}</tbody></table>` : ""}
    ${p.accounts.length ? `<table><thead><tr><th>G/L account</th><th>Name</th><th>Description</th><th>Project</th><th class="num">Amount (LC)</th></tr></thead><tbody>
      ${p.accounts.map((a) => `<tr><td class="mono">${esc(a.acct_code)}</td><td>${esc(name(a.acct_code))}</td><td>${esc(a.descrip || "")}</td><td>${esc(a.prj_code || "")}</td><td class="num">${fmt(a.sum_applied)}</td></tr>`).join("")}</tbody></table>` : ""}
    <div class="card-body"><h3 class="section">Payment means</h3><div style="overflow-x:auto"><table><thead><tr><th>Means</th><th>G/L account</th><th>Details</th><th class="num">Amount (LC)</th>${p.doc_curr !== state.company.main_curncy ? `<th class="num">Amount (${esc(p.doc_curr)})</th>` : ""}</tr></thead><tbody>
      ${Number(p.cash_sum) ? `<tr><td>Cash</td><td class="mono">${esc(p.cash_acct)}</td><td></td><td class="num">${fmt(p.cash_sum)}</td>${p.doc_curr !== state.company.main_curncy ? `<td class="num">${fmt(p.cash_sum_fc)}</td>` : ""}</tr>` : ""}
      ${Number(p.trsfr_sum) ? `<tr><td>Bank transfer</td><td class="mono">${esc(p.trsfr_acct)}</td><td>${esc(p.trsfr_date || "")} ${esc(p.trsfr_ref || "")}${Number(p.bank_chrg) ? ` · bank charges ${fmt(p.bank_chrg)}` : ""}</td>
        <td class="num">${fmt(p.trsfr_sum)}</td>${p.doc_curr !== state.company.main_curncy ? `<td class="num">${fmt(p.trsfr_sum_fc)}</td>` : ""}</tr>` : ""}
      ${p.checks.map((ch) => `<tr><td>Check ${ch.check_num}</td><td class="mono">${esc(ch.check_act)}</td><td>due ${ch.due_date} · ${esc([ch.bank_code, ch.branch, ch.acct_num, ch.country_cod].filter(Boolean).join(" / "))}${ch.trnsfrable ? " · endorsable" : ""}</td>
        <td class="num"></td>${p.doc_curr !== state.company.main_curncy ? "<td></td>" : ""}</tr>`).join("")}
      ${Number(p.check_sum) ? `<tr><td colspan="3">Checks total</td><td class="num">${fmt(p.check_sum)}</td>${p.doc_curr !== state.company.main_curncy ? `<td class="num">${fmt(p.check_sum_fc)}</td>` : ""}</tr>` : ""}
    </tbody></table></div>
    <div class="totals" style="margin-top:10px"><div><span>Overall amount (LC)</span><b>${fmt(p.doc_total)}</b></div>
      ${p.doc_curr !== state.company.main_curncy ? `<div><span>Overall amount (${esc(p.doc_curr)}) at ${Number(p.doc_rate)}</span><b>${fmt(p.doc_total_fc)}</b></div>` : ""}
      <div><span>On account</span><b>${fmt(p.no_doc_sum)}</b></div><div><span>Still open on account</span><b>${fmt(p.open_bal)}</b></div></div></div></div>`;
  const cn = $("#pay-cancel");
  if (cn) cn.onclick = async () => {
    if (!confirm(`Cancel ${PAY_KINDS[kind].name} ${p.doc_num}? The paid items are reopened.`)) return;
    if (await act(() => post(`/payments/${kind}/${p.doc_entry}/cancel`, {}), "Payment canceled")) {
      state.partners = await api("/partners"); location.hash = `#/payments?kind=${kind}&entry=${p.doc_entry}&r=${Date.now()}`;
    }
  };
}

views.payment = async (c) => {
  const kind = query().get("kind") || "incoming";
  const k = PAY_KINDS[kind], incoming = kind === "incoming";
  const head = paymentHeaderDefs(kind);
  const main = state.company.main_curncy;
  c.innerHTML = `<div class="page-head"><div><h1>${k.name}</h1><div class="sub">New payment — select the open items to pay, then the payment means</div></div>
      <a class="btn secondary" href="#/payments?kind=${kind}">Back to list</a></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(head, {}, "p")}</div></div></div>
    <div class="card"><div class="card-head" id="p-items-head">Open items</div><div style="overflow-x:auto" id="p-items"></div></div>
    <div class="card"><div class="card-head">Payment means <span class="help" id="p-rate"></span></div><div class="card-body">
      <h3 class="section">Check</h3>
      <div class="form-grid">${fieldHtml({ k: "check_acct", label: "G/L account", type: "select", options: O.accounts((a) => !a.control), value: incoming ? "117000" : "112000" }, undefined, "p")}</div>
      <div style="overflow-x:auto"><table class="lines"><thead><tr><th>Due date</th><th class="num">Amount</th><th>Country</th><th>Bank name</th><th>Branch</th><th>Account</th><th class="num">Check no.</th><th>Endorse</th><th></th></tr></thead><tbody id="p-checks"></tbody></table></div>
      <button class="btn secondary small" id="p-check-add" style="margin-top:6px">+ Check</button>
      <h3 class="section">Bank transfer</h3><div class="form-grid">${fieldsHtml(MEANS_TRANSFER, {}, "p")}</div>
      <h3 class="section">Cash</h3><div class="form-grid">${fieldsHtml(MEANS_CASH, {}, "p")}</div>
      <div class="totals" style="margin-top:12px">
        <div><span>Total amount due (LC)</span><b id="p-due">0.00</b></div>
        <div><span>Overall amount (<span id="p-cur">${esc(main)}</span>)</span><b id="p-overall">0.00</b></div>
        <div><span>Overall amount (LC)</span><b id="p-overall-lc">0.00</b></div>
        <div class="grand"><span>Balance due (LC)</span><b id="p-balance">0.00</b></div></div>
      <button class="btn" id="p-post" style="margin-top:12px">Add</button></div></div>`;

  let rate = 1;
  const type = () => $("#p-doc_type").value;
  const fillPartners = () => {
    const t = type();
    $("#p-card_code").innerHTML = opt("", t === "A" ? "— account payment —" : "— select —") + (t === "A" ? "" : state.partners
      .filter((b) => b.card_type === t && !b.frozen).map((b) => opt(b.card_code, `${b.card_code} — ${b.card_name}`)).join(""));
    $("#p-card_code").disabled = t === "A";
    loadItems();
  };
  const loadRate = async () => {
    const cur = $("#p-doc_curr").value;
    $("#p-cur").textContent = cur;
    if (cur === main) { rate = 1; $("#p-rate").textContent = ""; }
    else {
      const rates = await api(`/admin/exchange-rates?rate_date=${$("#p-doc_date").value}`);
      const r = rates.find((x) => x.currency === cur);
      rate = r ? Number(r.rate) : 0;
      $("#p-rate").textContent = r ? `1 ${cur} = ${Number(r.rate).toFixed(4)} ${main}` : `no exchange rate for ${cur} on this date`;
    }
    recalc();
  };
  const loadItems = async () => {
    const t = type(), code = $("#p-card_code").value;
    if (t === "A") {
      $("#p-items-head").textContent = "G/L account lines";
      $("#p-items").innerHTML = `<table class="lines"><thead><tr><th>G/L account</th><th>Description</th><th>Project</th><th class="num w-amt">Amount</th><th></th></tr></thead><tbody id="p-acct"></tbody></table>
        <div class="card-body"><button class="btn secondary small" id="p-acct-add">+ Line</button></div>`;
      const addAcct = () => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td><select class="a-acct">${opt("", "— account —")}${accountOptions((a) => !a.control)}</select></td><td><input class="a-desc" maxlength="254"></td>
          <td><select class="a-prj">${opt("", "")}${O.projects().map(([v, l]) => opt(v, l)).join("")}</select></td>
          <td class="num"><input class="a-sum" type="number" step="0.01" min="0"></td><td><button class="btn ghost small a-del">✕</button></td>`;
        $("#p-acct").appendChild(tr);
        $(".a-sum", tr).oninput = recalc;
        $(".a-del", tr).onclick = () => { tr.remove(); recalc(); };
      };
      $("#p-acct-add").onclick = addAcct;
      addAcct();
      recalc();
      return;
    }
    $("#p-items-head").textContent = "Open items";
    if (!code) { $("#p-items").innerHTML = '<div class="empty">Select a business partner.</div>'; recalc(); return; }
    const [items, bp] = await Promise.all([api(`/payments/open-items?card_code=${encodeURIComponent(code)}`), api(`/partners/${encodeURIComponent(code)}`)]);
    $("#p-cntct_code").innerHTML = opt("", "") + bp.contacts.filter((x) => x.active).map((x) => opt(x.cntct_code, x.name, bp.cntct_prsn === x.name ? x.cntct_code : "")).join("");
    // payable direction: incoming pays debit items (invoices), outgoing pays credit items (vendor invoices); the others offset
    $("#p-items").innerHTML = `<table class="lines"><thead><tr><th></th><th>Document</th><th>No.</th><th>Posting date</th><th>Due date</th><th>Remarks</th>
      <th class="num">Total</th><th class="num">Balance due</th><th class="num w-amt">Total payment (LC)</th></tr></thead><tbody>
      ${items.map((it, n) => {
        const sign = (it.side === "D") === incoming ? 1 : -1;
        return `<tr data-n="${n}" data-sign="${sign}"><td><input type="checkbox" class="i-pick"></td>
        <td>${esc(DOC_NAMES[it.inv_type] || (it.inv_type === "24" ? "Incoming Payment" : it.inv_type === "46" ? "Outgoing Payment" : "Journal Entry"))}</td>
        <td>${docLink(it.inv_type, it.doc_entry, it.doc_num)}</td><td>${it.ref_date}</td><td>${it.due_date}</td><td>${esc(it.memo || "")}</td>
        <td class="num">${fmt(sign * it.amount)}</td><td class="num">${fmt(sign * it.open)}</td>
        <td class="num"><input class="i-sum" type="number" step="0.01" min="0" max="${Number(it.open)}" value="${Number(it.open).toFixed(2)}" disabled></td></tr>`;
      }).join("") || `<tr><td colspan="9" class="empty">No open items — the payment will be on account.</td></tr>`}</tbody></table>`;
    $$("#p-items tr[data-n]").forEach((tr) => {
      const pick = $(".i-pick", tr), sum = $(".i-sum", tr);
      tr.item = items[Number(tr.dataset.n)];
      pick.onchange = () => { sum.disabled = !pick.checked; recalc(); };
      sum.oninput = recalc;
    });
    recalc();
  };
  const addCheck = () => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><input class="c-due" type="date" value="${$("#p-doc_due_date").value || today()}"></td><td class="num"><input class="c-sum" type="number" step="0.01" min="0" style="width:100px"></td>
      <td><select class="c-country">${opt("", "")}${O.countries().map(([v, l]) => opt(v, l, state.company.country)).join("")}</select></td>
      <td><input class="c-bank" maxlength="30" style="width:110px"></td><td><input class="c-branch" maxlength="50" style="width:90px"></td>
      <td><input class="c-acct" maxlength="50" style="width:110px"></td><td class="num"><input class="c-num" type="number" step="1" min="1" style="width:90px"></td>
      <td><input class="c-endorse" type="checkbox"></td><td><button class="btn ghost small c-del">✕</button></td>`;
    $("#p-checks").appendChild(tr);
    $(".c-sum", tr).oninput = recalc;
    $(".c-del", tr).onclick = () => { tr.remove(); recalc(); };
  };
  const round = (n) => Math.round(n * 100) / 100;
  const recalc = () => {
    let due = 0;
    if (type() === "A") $$("#p-acct tr").forEach((tr) => { due += round(Number($(".a-sum", tr).value || 0) * rate); });
    else $$("#p-items tr[data-n]").forEach((tr) => { if ($(".i-pick", tr).checked) due += Number(tr.dataset.sign) * Number($(".i-sum", tr).value || 0); });
    const checks = $$("#p-checks tr").reduce((s, tr) => s + Number($(".c-sum", tr).value || 0), 0);
    const means = round(checks) + Number($("#p-trsfr_sum").value || 0) + Number($("#p-cash_sum").value || 0);
    const meansLc = round(round(checks) * rate) + round(Number($("#p-trsfr_sum").value || 0) * rate) + round(Number($("#p-cash_sum").value || 0) * rate);
    $("#p-due").textContent = fmt(due); $("#p-overall").textContent = fmt(means); $("#p-overall-lc").textContent = fmt(meansLc);
    $("#p-balance").textContent = fmt(due - meansLc);
  };
  $("#p-doc_type").onchange = fillPartners;
  $("#p-card_code").onchange = loadItems;
  $("#p-doc_curr").onchange = loadRate;
  $("#p-doc_date").addEventListener("change", loadRate);
  ["#p-trsfr_sum", "#p-cash_sum"].forEach((s) => ($(s).oninput = recalc));
  $("#p-check-add").onclick = addCheck;
  fillPartners();

  $("#p-post").onclick = async () => {
    const h = readFields(head, "p");
    const means = readFields([...MEANS_TRANSFER, ...MEANS_CASH, { k: "check_acct", type: "select" }], "p");
    const body = { ...h, ...means, trsfr_sum: means.trsfr_sum || 0, cash_sum: means.cash_sum || 0, bank_chrg: means.bank_chrg || 0,
      card_code: type() === "A" ? null : h.card_code, checks: [], items: [], accounts: [] };
    $$("#p-checks tr").forEach((tr) => {
      const v = (cls) => $(cls, tr).value || null;
      if (v(".c-sum")) body.checks.push({ due_date: v(".c-due"), check_sum: Number(v(".c-sum")), country_cod: v(".c-country"), bank_code: v(".c-bank"),
        branch: v(".c-branch"), acct_num: v(".c-acct"), check_num: Number(v(".c-num") || 0), trnsfrable: $(".c-endorse", tr).checked });
    });
    if (type() === "A") $$("#p-acct tr").forEach((tr) => {
      const acct = $(".a-acct", tr).value;
      if (acct) body.accounts.push({ acct_code: acct, sum_applied: Number($(".a-sum", tr).value || 0), descrip: $(".a-desc", tr).value || null, prj_code: $(".a-prj", tr).value || null });
    });
    else $$("#p-items tr[data-n]").forEach((tr) => {
      if ($(".i-pick", tr).checked) body.items.push({ trans_id: tr.item.trans_id, line_id: tr.item.line_id, sum_applied: Number($(".i-sum", tr).value || 0) });
    });
    if (!body.trsfr_sum) { body.trsfr_acct = null; body.trsfr_date = null; }
    if (!body.cash_sum) body.cash_acct = null;
    if (!body.checks.length) body.check_acct = null;
    const r = await act(() => post(`/payments/${kind}`, body), (p) => `${k.name} ${p.doc_num} added`);
    if (r) { state.partners = await api("/partners"); location.hash = `#/payments?kind=${kind}&entry=${r.doc_entry}`; }
  };
};

// ---------- Deposits ----------
const DEPOSIT_FIELDS = [
  { k: "depos_date", label: "Deposit date", type: "date", value: today(), req: true },
  { k: "banck_acct", label: "Bank G/L account", type: "select", blank: false, options: cashAccounts, value: "112000" },
  { k: "bank_acc_num", label: "Bank account no.", max: 50 },
  { k: "project", label: "Project", type: "select", options: () => O.projects() },
  { k: "memo", label: "Journal remarks", max: 254, span: 2 },
];
views.deposits = async (c) => {
  const [checks, deps] = await Promise.all([api("/checks?deposited=false"), api("/deposits")]);
  c.innerHTML = `<div class="page-head"><div><h1>Deposits</h1><div class="sub">Deposit received checks (OCHH) or cash to a bank account (ODPS)</div></div></div>
    <div class="card"><div class="card-head">Check deposit</div><div class="card-body"><div class="form-grid">${fieldsHtml(DEPOSIT_FIELDS, {}, "dk")}</div></div>
      <table><thead><tr><th></th><th class="num">Check no.</th><th>Due date</th><th>Bank</th><th>Branch</th><th>Account</th><th>Customer</th><th>Incoming payment</th><th>G/L account</th><th class="num">Amount</th></tr></thead><tbody>
      ${checks.map((ch) => `<tr><td><input type="checkbox" class="dk-pick" data-k="${ch.check_key}"></td><td class="num">${ch.check_num}</td><td>${ch.check_date}</td>
        <td>${esc(ch.bank_code || "")}</td><td>${esc(ch.branch || "")}</td><td>${esc(ch.acct_num || "")}</td><td class="mono">${esc(ch.card_code || "")}</td>
        <td><a href="#/payments?kind=incoming&entry=${ch.rcpt_num}">${ch.rcpt_num}</a></td><td class="mono">${esc(ch.check_act)}</td><td class="num">${fmt(ch.check_sum)}</td></tr>`).join("")
        || `<tr><td colspan="10" class="empty">No checks waiting for deposit.</td></tr>`}</tbody></table>
      <div class="card-body"><b>Selected: <span id="dk-total">0.00</span></b> <button class="btn" id="dk-save" style="margin-left:12px">Deposit checks</button></div></div>
    <div class="card"><div class="card-head">Cash deposit</div><div class="card-body"><div class="form-grid">${fieldsHtml([...DEPOSIT_FIELDS,
      { k: "alloc_acct", label: "Cash G/L account", type: "select", blank: false, options: cashAccounts, value: "111000" },
      { k: "amount", label: "Amount", type: "number", step: "0.01", min: 0, req: true }], {}, "dc")}</div>
      <button class="btn" id="dc-save" style="margin-top:8px">Deposit cash</button></div></div>
    <div class="card"><div class="card-head">Deposits</div><table><thead><tr><th>No.</th><th>Date</th><th>Type</th><th>Bank account</th><th>From</th><th class="num">Amount</th><th>Remarks</th><th>Journal entry</th><th>Status</th><th></th></tr></thead><tbody>
      ${deps.map((d) => `<tr><td class="mono">${d.depos_num}</td><td>${d.depos_date}</td><td>${d.depos_type === "K" ? "Checks" : "Cash"}</td><td class="mono">${esc(d.banck_acct)}</td>
        <td class="mono">${esc(d.alloc_acct || (d.depos_type === "K" ? "checks" : ""))}</td><td class="num">${fmt(d.loc_total)}</td><td>${esc(d.memo || "")}</td>
        <td>${d.trans_abs ? `<a href="#/journal?id=${d.trans_abs}">${d.trans_abs}</a>` : ""}</td>
        <td>${d.canceled ? '<span class="status X">Canceled</span>' : '<span class="status C">Closed</span>'}</td>
        <td>${d.canceled ? "" : `<button class="btn small ghost dp-cancel" data-id="${d.depos_id}">Cancel</button>`}</td></tr>`).join("")
        || `<tr><td colspan="10" class="empty">No deposits yet.</td></tr>`}</tbody></table></div>`;
  const total = () => { $("#dk-total").textContent = fmt($$(".dk-pick:checked").reduce((s, cb) => s + Number(checks.find((x) => String(x.check_key) === cb.dataset.k).check_sum), 0)); };
  $$(".dk-pick").forEach((cb) => (cb.onchange = total));
  $("#dk-save").onclick = async () => {
    const body = { ...readFields(DEPOSIT_FIELDS, "dk"), depos_type: "K", check_keys: $$(".dk-pick:checked").map((cb) => Number(cb.dataset.k)) };
    if (await act(() => post("/deposits", body), (d) => `Deposit ${d.depos_num} added`)) route();
  };
  $("#dc-save").onclick = async () => {
    const body = { ...readFields([...DEPOSIT_FIELDS, { k: "alloc_acct", type: "select" }, { k: "amount", type: "number" }], "dc"), depos_type: "C" };
    if (await act(() => post("/deposits", body), (d) => `Deposit ${d.depos_num} added`)) route();
  };
  $$(".dp-cancel").forEach((b) => (b.onclick = async () => {
    if (!confirm("Cancel this deposit? The journal entry is reversed and checks return to the register.")) return;
    if (await act(() => post(`/deposits/${b.dataset.id}/cancel`, {}), "Deposit canceled")) route();
  }));
};
