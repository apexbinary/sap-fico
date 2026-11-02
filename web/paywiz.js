/* Payment wizard: recommendation of due items, selection, one payment per business partner. */
"use strict";

views["payment-wizard"] = async (c) => {
  const id = query().get("id");
  const runs = await api("/payment-wizard");
  const defs = [
    { k: "name", label: "Run name", max: 50 },
    { k: "pmnt_date", label: "Payment date", type: "date", req: true, value: today() },
    { k: "due_date_to", label: "Due date up to", type: "date", req: true, value: today() },
    { k: "pay_type", label: "Pay", type: "select", blank: false, options: [["V", "Vendors (outgoing payments)"], ["C", "Customers (incoming, direct debit)"]] },
    { k: "pay_means", label: "Payment means", type: "select", blank: false, options: [["T", "Bank transfer"], ["C", "Check"]] },
    { k: "bank_acct", label: "Bank G/L account", type: "select", blank: false, options: () => O.accounts((a) => a.cash)(), value: "112000" },
    { k: "first_check", label: "First check no.", type: "number", step: 1, min: 1 },
    { k: "card_code", label: "Business partner", type: "select", blank: "All", options: () => state.partners.filter((b) => !b.frozen && b.card_type !== "L").map((b) => [b.card_code, `${b.card_code} — ${b.card_name}`]) },
    { k: "take_disc", label: "Take cash discount", type: "check", value: true },
  ];
  const status = { S: '<span class="status O">Saved</span>', E: '<span class="status C">Executed</span>', C: '<span class="status X">Canceled</span>' };
  c.innerHTML = `<div class="page-head"><div><h1>Payment Wizard</h1><div class="sub">Pay due vendor items (or collect from customers) in one run: one payment per business partner</div></div></div>
    <div class="card"><div class="card-head">New run</div><div class="card-body"><div class="form-grid">${fieldsHtml(defs, {}, "pw")}</div>
      <button class="btn" id="pw-create" style="margin-top:10px">Create recommendation</button></div></div>
    <div id="pw-run"></div>
    <div class="card"><div class="card-head">Runs (OPWZ)</div><table><thead><tr><th>No.</th><th>Name</th><th>Payment date</th><th>Due up to</th><th>Type</th><th>Means</th><th class="num">Total</th><th>Status</th></tr></thead><tbody>
      ${runs.map((r) => `<tr style="cursor:pointer" onclick="location.hash='#/payment-wizard?id=${r.id_entry}'"><td class="mono">${r.id_entry}</td><td>${esc(r.wizard_name)}</td>
        <td>${r.pmnt_date}</td><td>${r.due_date_to}</td><td>${r.pay_type === "V" ? "Vendors" : "Customers"}</td><td>${r.pay_means === "T" ? "Transfer" : "Check"}</td>
        <td class="num">${fmt(r.total)}</td><td>${status[r.status]}</td></tr>`).join("") || `<tr><td colspan="8" class="empty">No payment runs yet.</td></tr>`}</tbody></table></div>`;
  $("#pw-create").onclick = async () => {
    const p = readFields(defs, "pw");
    const r = await act(() => post("/payment-wizard", { ...p, card_codes: p.card_code ? [p.card_code] : null, name: p.name || null }),
      (x) => `Run ${x.id_entry}: ${x.items_count} items recommended`);
    if (r) location.hash = `#/payment-wizard?id=${r.id_entry}`;
  };
  if (!id) return;
  const r = await api(`/payment-wizard/${id}`);
  const saved = r.status === "S";
  const byBp = {};
  r.items.forEach((i) => (byBp[i.card_code] ||= []).push(i));
  const name = (code) => nameOf(state.partners, "card_code", code, "card_name");
  $("#pw-run").innerHTML = `<div class="card"><div class="card-head"><span>Run ${r.id_entry} — ${esc(r.wizard_name)} ${status[r.status]}</span>
      <span>${saved ? '<button class="btn small secondary" id="pw-cancel">Cancel run</button> <button class="btn small" id="pw-exec">Execute</button>' : ""}</span></div>
    <div class="card-body help">Payment date ${r.pmnt_date} · due up to ${r.due_date_to} · ${r.pay_means === "T" ? "bank transfer" : `checks from no. ${r.first_check}`} from ${esc(r.bank_acct)}
      · cash discount ${r.take_disc ? "taken" : "not taken"} · total to pay <b>${fmt(r.total)}</b></div>
    ${Object.entries(byBp).map(([code, items]) => `<div class="card-body"><b>${esc(code)} — ${esc(name(code))}</b> · net ${fmt(r.partners[code] || 0)}
      ${Number(r.partners[code] || 0) <= 0 ? ' <span class="help">(not paid: no positive amount)</span>' : ""}
      <table style="margin-top:6px"><thead><tr><th></th><th>Document</th><th>Due date</th><th class="num">Open</th><th class="num">Cash discount</th><th class="num">To pay</th><th>Payment</th></tr></thead><tbody>
      ${items.map((i) => `<tr><td><input type="checkbox" class="pw-sel" data-n="${i.line_num}"${i.selected ? " checked" : ""}${saved ? "" : " disabled"}></td>
        <td>${esc(transTypeName(i.trans_type))} ${esc(i.doc_num || i.trans_id)}${i.direction < 0 ? ' <span class="help">(offset)</span>' : ""}</td><td>${i.due_date}</td>
        <td class="num">${fmt(i.direction * i.open_amount)}</td><td class="num">${Number(i.discount) ? fmt(i.discount) : ""}</td>
        <td class="num">${fmt(i.direction * (i.open_amount - i.discount))}</td>
        <td>${i.pay_entry ? `<a href="#/payments?kind=${r.pay_type === "V" ? "outgoing" : "incoming"}&entry=${i.pay_entry}">${i.pay_entry}</a>` : ""}</td></tr>`).join("")}</tbody></table></div>`).join("")}</div>`;
  if (!saved) return;
  const reload = () => { location.hash = `#/payment-wizard?id=${r.id_entry}&r=${Date.now()}`; };
  $$(".pw-sel").forEach((cb) => (cb.onchange = async () => {
    if (await act(() => post(`/payment-wizard/${r.id_entry}/select`, { line_nums: [Number(cb.dataset.n)], selected: cb.checked }))) reload();
  }));
  $("#pw-exec").onclick = async () => {
    if (!confirm(`Execute payment run ${r.id_entry}? One payment per business partner will be posted.`)) return;
    if (await act(() => post(`/payment-wizard/${r.id_entry}/execute`, {}), "Payment run executed")) { state.partners = await api("/partners"); reload(); }
  };
  $("#pw-cancel").onclick = async () => { if (await act(() => post(`/payment-wizard/${r.id_entry}/cancel`, {}), "Run canceled")) reload(); };
};
