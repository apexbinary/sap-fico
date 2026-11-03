/* Period-end closing: profit and loss accounts of a year to the closing account (retained earnings). */
"use strict";

views.closing = async (c) => {
  const year = Number(query().get("year") || new Date().getFullYear() - 1);
  const p = await api(`/period-end-closing?year=${year}`);
  const defs = [
    { k: "year", label: "Financial year", type: "number", step: 1, min: 2000, maxv: 2100 },
    { k: "closing_account", label: "Closing account (retained earnings)", type: "select", blank: false,
      options: O.accounts((a) => a.group_mask === 3 && !a.control), value: "312000" },
    { k: "lock", label: "Lock the periods of the year", type: "check", value: true },
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Period-End Closing</h1><div class="sub">Closes the profit and loss accounts of ${year} on 31-12-${year}
      ${p.closed ? ` — <span class="status C">closed</span> (journal entry ${p.closing_trans})` : ""}</div></div></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(defs, { year }, "pe")}
      <div class="field"><label>&nbsp;</label><button class="btn secondary" id="pe-show">Show</button></div></div></div></div>
    <div class="tiles"><div class="tile"><div class="label">Net result ${year}</div><div class="value ${Number(p.net_profit) >= 0 ? "good" : "bad"}">${fmt(p.net_profit)}</div>
      <div class="foot">${Number(p.net_profit) >= 0 ? "profit" : "loss"} to the closing account</div></div></div>
    <div class="card"><table><thead><tr><th>Account</th><th>Name</th><th class="num">Balance (debit - credit)</th></tr></thead><tbody>
      ${p.accounts.map((a) => `<tr><td class="mono">${esc(a.acct_code)}</td><td>${esc(a.acct_name)}</td><td class="num">${fmt(a.balance)}</td></tr>`).join("")
        || '<tr><td colspan="3" class="empty">No profit and loss balances in this year.</td></tr>'}</tbody></table>
      <div class="card-body">${p.closed ? '<button class="btn secondary" id="pe-cancel">Cancel the closing</button>'
        : `<button class="btn" id="pe-run"${p.accounts.length ? "" : " disabled"}>Close ${year}</button>`}</div></div>`;
  $("#pe-show").onclick = () => { location.hash = `#/closing?year=${readFields(defs, "pe").year}`; };
  if ($("#pe-run")) $("#pe-run").onclick = async () => {
    const f = readFields(defs, "pe");
    if (await act(() => post("/period-end-closing", { year, closing_account: f.closing_account, lock: f.lock }), `Year ${year} closed`)) views.closing(c);
  };
  if ($("#pe-cancel")) $("#pe-cancel").onclick = async () => {
    if (await act(() => post(`/period-end-closing/${year}/cancel`, {}), "Closing canceled")) views.closing(c);
  };
};
