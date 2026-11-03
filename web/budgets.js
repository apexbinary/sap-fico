/* Budgets: budget scenarios (OBGS), account budgets with monthly amounts (OBGT / BGT1) and budget vs. actual. */
"use strict";

const MONTHS3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

views.budgets = async (c) => {
  const q = query(), now = new Date();
  const year = Number(q.get("year") || now.getFullYear()), sc = q.get("scenario") || "", upto = Number(q.get("upto") || 12);
  const r = await api(`/budgets?year=${year}${sc ? `&scenario_id=${sc}` : ""}&upto_month=${upto}`);
  const yearScen = r.scenarios.filter((x) => x.financ_year === year);
  const defs = [
    { k: "year", label: "Financial year", type: "number", step: 1, min: 2000, maxv: 2100 },
    { k: "scenario", label: "Scenario", type: "select", int: true, blank: "Main Budget", options: yearScen.filter((x) => !x.main).map((x) => [x.abs_id, `${x.name} (${Number(x.init_ratio)} %)`]) },
    { k: "upto", label: "Up to month", type: "select", int: true, blank: false, options: MONTHS3.map((m, i) => [i + 1, m]) },
  ];
  const bDefs = [
    { k: "acct_code", label: "G/L account", type: "select", blank: false, options: O.accounts((a) => !a.control) },
    { k: "annual", label: "Annual amount (split equally)", type: "number", step: "0.01", min: 0 },
  ];
  const sDefs = [{ k: "name", label: "Scenario name", max: 30 }, { k: "init_ratio", label: "% of the main budget", type: "number", step: "0.01", min: 0, value: 100 }];
  const cls = (x) => (x.pct == null ? "" : (x.side === "debit" ? Number(x.pct) > 100 : Number(x.pct) < 100) ? "bad" : "good");
  c.innerHTML = `<div class="page-head"><div><h1>Budgets</h1><div class="sub">Budget vs. actual ${year} · ${esc(r.scenario ? r.scenario.name : "no budget yet")} · up to ${MONTHS3[upto - 1]}</div></div>
      <label class="pp-pick">Budget check <select id="bg-check">${opt("N", "No check", r.check)}${opt("B", "Block postings over the expense budget", r.check)}</select></label></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(defs, { year, scenario: sc, upto }, "bf")}
      <div class="field"><label>&nbsp;</label><button class="btn" id="bf-go">Show</button></div></div></div></div>
    <div class="tiles"><div class="tile"><div class="label">Budget</div><div class="value">${fmt(r.total_budget)}</div></div>
      <div class="tile"><div class="label">Actual</div><div class="value">${fmt(r.total_actual)}</div></div></div>
    <div class="card"><div style="overflow-x:auto"><table><thead><tr><th>Account</th><th>Name</th><th class="num">Annual budget</th><th class="num">Budget to date</th>
      <th class="num">Actual to date</th><th class="num">Deviation</th><th class="num">%</th>${MONTHS3.map((m) => `<th class="num">${m}</th>`).join("")}</tr></thead><tbody>
      ${r.accounts.map((x) => `<tr><td class="mono">${esc(x.acct_code)}</td><td>${esc(x.acct_name)}</td><td class="num">${fmt(x.annual_budget)}</td><td class="num">${fmt(x.budget)}</td>
        <td class="num">${fmt(x.actual)}</td><td class="num">${fmt(x.deviation)}</td><td class="num ${cls(x)}">${x.pct == null ? "" : Number(x.pct)}</td>
        ${x.months.map((m) => `<td class="num" title="budget ${fmt(m.budget)}">${fmt(m.actual)}<div class="help">${fmt(m.budget)}</div></td>`).join("")}</tr>`).join("")
        || '<tr><td colspan="19" class="empty">No budgets for this year.</td></tr>'}</tbody></table></div>
      <div class="card-body help">Each month: actual, below it the budget. Expense / asset accounts are budgeted on the debit side, revenue / liability accounts on the credit side.</div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Set an account budget (${esc(r.scenario ? r.scenario.name : "Main Budget")} ${year})</div><div class="card-body">
        <div class="form-grid">${fieldsHtml(bDefs, {}, "bb")}</div>
        <h3 class="section">or monthly amounts</h3><div class="form-grid">${MONTHS3.map((m, i) => `<div class="field"><label>${m}</label><input type="number" step="0.01" min="0" class="bb-m" data-m="${i}"></div>`).join("")}</div>
        <button class="btn" id="bb-save" style="margin-top:8px">Save budget</button></div></div>
      <div class="card"><div class="card-head">New scenario for ${year}</div><div class="card-body">
        <div class="form-grid">${fieldsHtml(sDefs, {}, "bs")}</div><div class="help">Copies the main budget of the year at the given percentage.</div>
        <button class="btn secondary" id="bs-save" style="margin-top:8px">Add scenario</button></div></div></div>`;
  $("#bf-go").onclick = () => { const f = readFields(defs, "bf"); location.hash = `#/budgets?year=${f.year}&upto=${f.upto}${f.scenario ? `&scenario=${f.scenario}` : ""}`; };
  $("#bg-check").onchange = async (e) => { await act(() => api("/admin/budget-check", { method: "PUT", body: JSON.stringify({ check: e.target.value }) }), "Budget check updated"); };
  $("#bb-save").onclick = async () => {
    const f = readFields(bDefs, "bb");
    const ms = $$(".bb-m").map((x) => x.value);
    const body = { acct_code: f.acct_code, year, scenario_id: sc ? Number(sc) : null };
    if (ms.some((v) => v !== "")) body.months = ms.map((v) => Number(v || 0)); else body.annual = f.annual;
    if (await act(() => post("/budgets", body), "Budget saved")) views.budgets(c);
  };
  $("#bs-save").onclick = async () => {
    const f = readFields(sDefs, "bs");
    if (await act(() => post("/budgets/scenarios", { name: f.name, year, init_ratio: f.init_ratio || 100 }), "Scenario added")) views.budgets(c);
  };
};
