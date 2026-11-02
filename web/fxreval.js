/* Exchange rate differences: revaluation of open foreign-currency items. */
"use strict";

views["exchange-rate-differences"] = async (c) => {
  const runs = await api("/exchange-rate-differences");
  const end = new Date(); end.setDate(0);  // last day of the previous month
  const defs = [
    { k: "run_date", label: "Execution date", type: "date", req: true, value: end.toISOString().slice(0, 10) },
    { k: "category", label: "Revalue", type: "select", blank: false, options: [["B", "Business partner open items (unrealized, reversed)"], ["G", "G/L accounts in foreign currency (permanent)"]] },
    { k: "storno_date", label: "Reversal date (business partners)", type: "date" },
    { k: "currencies", label: "Currencies", type: "select", blank: "All foreign currencies", options: () => O.currencies().filter(([v]) => v !== state.company.main_curncy) },
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Exchange Rate Differences</h1><div class="sub">Revaluation of open foreign-currency items at the rate of a date</div></div></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(defs, {}, "fx")}</div>
      <div style="display:flex;gap:8px;margin-top:10px"><button class="btn secondary" id="fx-preview">Preview</button><button class="btn" id="fx-run" disabled>Execute</button></div></div></div>
    <div id="fx-lines"></div>
    <div class="card"><div class="card-head">Runs</div><table><thead><tr><th>No.</th><th>Date</th><th>Revalued</th><th class="num">Gain</th><th class="num">Loss</th><th>Lines</th><th>Journal entry</th><th>Reversal date</th></tr></thead><tbody>
      ${runs.map((r) => `<tr><td class="mono">${r.abs_entry}</td><td>${r.run_date}</td><td>${r.category === "B" ? "Business partners" : "G/L accounts"}</td>
        <td class="num">${fmt(r.total_gain)}</td><td class="num">${fmt(r.total_loss)}</td><td>${r.lines_count}</td>
        <td>${r.trans_id ? `<a href="#/journal?id=${r.trans_id}">${r.trans_id}</a>` : "—"}</td><td>${r.storno_date || ""}</td></tr>`).join("")
        || `<tr><td colspan="8" class="empty">No runs yet.</td></tr>`}</tbody></table></div>`;
  const params = () => readFields(defs, "fx");
  $("#fx-preview").onclick = async () => {
    const p = params();
    const lines = await act(() => api(`/exchange-rate-differences/preview?on=${p.run_date}&category=${p.category}${p.currencies ? `&currencies=${p.currencies}` : ""}`));
    if (!lines) return;
    const total = (sign) => lines.reduce((s, x) => s + (Math.sign(Number(x.difference)) === sign ? Number(x.difference) : 0), 0);
    $("#fx-lines").innerHTML = `<div class="card"><div class="card-head">Preview: ${lines.length} ${p.category === "B" ? "open items" : "accounts"} ·
        gain ${fmt(total(1))} · loss ${fmt(-total(-1))}</div><div style="overflow-x:auto"><table><thead><tr><th>${p.category === "B" ? "BP" : "G/L account"}</th><th>Posted on</th>
        ${p.category === "B" ? "<th>Document</th>" : ""}<th>Currency</th><th class="num">Open (FC)</th><th class="num">Open (LC)</th><th class="num">Rate</th><th class="num">New (LC)</th><th class="num">Difference</th></tr></thead><tbody>
      ${lines.map((x) => `<tr><td class="mono">${esc(x.short_name)}</td><td class="mono">${esc(x.account)}</td>
        ${p.category === "B" ? `<td>${x.trans_type ? `${esc(transTypeName(x.trans_type))} ${esc(x.base_ref || x.trans_id)}` : ""}</td>` : ""}<td>${esc(x.currency)}</td>
        <td class="num">${fmt(x.open_fc)}</td><td class="num">${fmt(x.open_lc)}</td><td class="num">${Number(x.rate)}</td><td class="num">${fmt(x.new_lc)}</td>
        <td class="num ${Number(x.difference) > 0 ? "good" : Number(x.difference) < 0 ? "bad" : ""}">${fmt(x.difference)}</td></tr>`).join("")
        || `<tr><td colspan="9" class="empty">Nothing to revalue.</td></tr>`}</tbody></table></div></div>`;
    $("#fx-run").disabled = !lines.some((x) => Number(x.difference));
  };
  $("#fx-run").onclick = async () => {
    const p = params();
    if (!confirm(`Post the exchange rate differences of ${p.run_date}?`)) return;
    const body = { run_date: p.run_date, category: p.category, storno_date: p.storno_date, currencies: p.currencies ? [p.currencies] : null };
    if (await act(() => post("/exchange-rate-differences", body), (r) => `Run ${r.abs_entry} posted (JE ${r.trans_id || "—"})`)) route();
  };
};
