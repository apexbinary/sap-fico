/* Bank statements, house banks and external (bank) reconciliation. */
"use strict";

const bankAccounts = () => O.accounts((a) => a.cash)();
const acctSelect = (id, sel) => `<select id="${id}">${bankAccounts().map(([v, l]) => opt(v, l, sel)).join("")}</select>`;

views["bank-statements"] = async (c) => {
  const acct = query().get("acct") || "112000", id = query().get("id");
  const [hb, list, next] = await Promise.all([api("/house-banks"), api(`/bank-statements?acct_code=${acct}`), api(`/bank-statements/next?acct_code=${acct}`)]);
  c.innerHTML = `<div class="page-head"><div><h1>Bank Statements</h1><div class="sub">House banks (ODSC / DSC1) and bank statements (OBNK) of a G/L bank account</div></div>
      <a class="btn secondary" href="#/bank-reconciliation?acct=${acct}">Reconcile &#8599;</a></div>
    <div class="toolbar"><div class="field"><label>G/L bank account</label>${acctSelect("bs-acct", acct)}</div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Statements</div><table><thead><tr><th>No.</th><th>Date</th><th class="num">Opening</th><th class="num">Closing</th><th>Rows open</th><th>Source</th></tr></thead><tbody>
        ${list.map((st) => `<tr style="cursor:pointer" onclick="location.hash='#/bank-statements?acct=${acct}&id=${st.abs_entry}'"><td class="mono">${st.statem_no}</td><td>${st.stat_date}</td>
          <td class="num">${fmt(st.start_bal)}</td><td class="num">${fmt(st.end_bal)}</td><td>${st.rows_open} / ${st.rows_total}</td><td>${st.data_source === "I" ? "Imported" : "Manual"}</td></tr>`).join("")
          || `<tr><td colspan="6" class="empty">No statements for this account yet.</td></tr>`}</tbody></table></div>
      <div class="card"><div class="card-head">House bank accounts</div><table><thead><tr><th>Bank</th><th>Account no.</th><th>Branch / IFSC</th><th>G/L account</th></tr></thead><tbody>
        ${hb.accounts.map((a) => `<tr><td>${esc(nameOf(hb.banks, "bank_code", a.bank_code, "bank_name"))}</td><td class="mono">${esc(a.account)}</td><td>${esc(a.branch || "")}</td><td class="mono">${esc(a.gl_account)}</td></tr>`).join("")
          || `<tr><td colspan="4" class="empty">No house bank accounts.</td></tr>`}</tbody></table>
        <div class="card-body"><h3 class="section">New bank</h3><div class="form-grid">${fieldsHtml([
          { k: "bank_code", label: "Bank code", req: true, max: 30 }, { k: "bank_name", label: "Bank name", req: true, max: 250 },
          { k: "country_cod", label: "Country", type: "select", options: () => O.countries(), value: "IN" }, { k: "swift_num", label: "SWIFT / BIC", max: 50 }], {}, "bk")}</div>
          <button class="btn secondary small" id="bk-save" style="margin-top:6px">Add bank</button>
          <h3 class="section">New house bank account</h3><div class="form-grid">${fieldsHtml([
          { k: "bank_code", label: "Bank", type: "select", blank: false, options: hb.banks.map((b) => [b.bank_code, b.bank_name]) },
          { k: "account", label: "Account no.", req: true, max: 50 }, { k: "branch", label: "Branch / IFSC", max: 50 },
          { k: "gl_account", label: "G/L bank account", type: "select", blank: false, options: bankAccounts },
          { k: "acct_name", label: "Account name", max: 250 }, { k: "iban", label: "IBAN", max: 50 },
          { k: "currency", label: "Currency", type: "select", options: () => O.currencies(), value: state.company.main_curncy }], {}, "ha")}</div>
          <button class="btn secondary small" id="ha-save" style="margin-top:6px">Add account</button></div></div>
    </div>
    <div id="bs-detail"></div>
    <div class="card"><div class="card-head">New statement ${next.statem_no}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml([
        { k: "stat_date", label: "Statement date", type: "date", req: true, value: today() },
        { k: "start_bal", label: "Opening balance", type: "number", step: "0.01", value: Number(next.start_bal), ro: !next.first },
        { k: "end_bal", label: "Closing balance", type: "number", step: "0.01", req: true },
        { k: "house_bank", label: "House bank account", type: "select", int: true, options: hb.accounts.filter((a) => a.gl_account === acct).map((a) => [a.abs_entry, `${a.bank_code} ${a.account}`]) }], {}, "ns")}</div>
      <div class="toolbar" style="margin-top:10px"><div class="field"><label>Import bank export (CSV: date, reference, narration, amount or withdrawal / deposit)</label><input type="file" id="ns-file" accept=".csv,text/csv"></div></div>
      <div style="overflow-x:auto"><table class="lines"><thead><tr><th>Date</th><th>Reference</th><th>Narration</th><th class="num">Money in</th><th class="num">Money out</th><th></th></tr></thead><tbody id="ns-rows"></tbody></table></div>
      <button class="btn secondary small" id="ns-add" style="margin-top:6px">+ Row</button>
      <div class="totals" style="margin-top:10px"><div><span>Opening + in - out</span><b id="ns-calc">0.00</b></div><div class="grand"><span>Difference to closing</span><b id="ns-diff">0.00</b></div></div>
      <button class="btn" id="ns-save" style="margin-top:10px">Add statement</button></div></div>`;
  $("#bs-acct").onchange = (e) => (location.hash = `#/bank-statements?acct=${e.target.value}`);
  let source = "M";
  const addRow = (r = {}) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><input class="r-date" type="date" value="${esc(r.due_date || today())}"></td><td><input class="r-ref" maxlength="100" value="${esc(r.ref || "")}"></td>
      <td><input class="r-memo" maxlength="254" value="${esc(r.memo || "")}"></td>
      <td class="num"><input class="r-in" type="number" step="0.01" min="0" value="${Number(r.amount_in) || ""}" style="width:110px"></td>
      <td class="num"><input class="r-out" type="number" step="0.01" min="0" value="${Number(r.amount_out) || ""}" style="width:110px"></td>
      <td><button class="btn ghost small r-del">✕</button></td>`;
    $("#ns-rows").appendChild(tr);
    $$("input", tr).forEach((i) => (i.oninput = calc));
    $(".r-del", tr).onclick = () => { tr.remove(); calc(); };
  };
  const calc = () => {
    const v = (tr, cls) => Number($(cls, tr).value || 0);
    const total = $$("#ns-rows tr").reduce((s, tr) => s + v(tr, ".r-in") - v(tr, ".r-out"), Number($("#ns-start_bal").value || 0));
    $("#ns-calc").textContent = fmt(total);
    $("#ns-diff").textContent = fmt(Number($("#ns-end_bal").value || 0) - total);
  };
  $("#ns-end_bal").oninput = calc; $("#ns-start_bal").oninput = calc;
  $("#ns-add").onclick = () => addRow();
  addRow();
  $("#ns-file").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const rows = await act(async () => post("/bank-statements/parse", { csv: await file.text() }), (r) => `${r.length} rows read`);
    if (!rows) return;
    $("#ns-rows").innerHTML = ""; rows.forEach(addRow); source = "I"; calc();
  };
  $("#ns-save").onclick = async () => {
    const h = readFields([{ k: "stat_date", type: "date" }, { k: "start_bal", type: "number", ro: !next.first }, { k: "end_bal", type: "number" },
      { k: "house_bank", type: "select", int: true }], "ns");
    const rows = $$("#ns-rows tr").map((tr) => ({ due_date: $(".r-date", tr).value, ref: $(".r-ref", tr).value || null, memo: $(".r-memo", tr).value || null,
      amount_in: Number($(".r-in", tr).value || 0), amount_out: Number($(".r-out", tr).value || 0) })).filter((r) => r.amount_in || r.amount_out);
    const r = await act(() => post("/bank-statements", { acct_code: acct, ...h, rows }), (st) => `Statement ${st.statem_no} added (${source === "I" ? "imported" : "manual"})`);
    if (r) location.hash = `#/bank-statements?acct=${acct}&id=${r.abs_entry}`;
  };
  $("#bk-save").onclick = async () => { if (await act(() => post("/banks", readFields([{ k: "bank_code" }, { k: "bank_name" }, { k: "country_cod", type: "select" }, { k: "swift_num" }], "bk")), "Bank added")) route(); };
  $("#ha-save").onclick = async () => {
    if (await act(() => post("/house-bank-accounts", readFields([{ k: "bank_code", type: "select" }, { k: "account" }, { k: "branch" }, { k: "gl_account", type: "select" },
      { k: "acct_name" }, { k: "iban" }, { k: "currency", type: "select" }], "ha")), "House bank account added")) route();
  };
  if (!id) return;
  const st = await api(`/bank-statements/${id}`);
  $("#bs-detail").innerHTML = `<div class="card"><div class="card-head">Statement ${st.statem_no} · ${st.stat_date} · opening ${fmt(st.start_bal)} · closing ${fmt(st.end_bal)}</div>
    <div style="overflow-x:auto"><table><thead><tr><th>#</th><th>Date</th><th>Reference</th><th>Narration</th><th class="num">Money in</th><th class="num">Money out</th><th>Reconciliation</th><th>Posted as</th></tr></thead><tbody>
    ${st.rows.map((r) => `<tr><td>${r.vis_order + 1}</td><td>${r.due_date}</td><td>${esc(r.ref || "")}</td><td>${esc(r.memo || "")}</td>
      <td class="num">${Number(r.amount_in) ? fmt(r.amount_in) : ""}</td><td class="num">${Number(r.amount_out) ? fmt(r.amount_out) : ""}</td>
      <td>${r.bank_match ? `<span class="status C">No. ${r.bank_match}</span>` : '<span class="status O">Open</span>'}</td>
      <td>${r.doc_num ? (r.doc_num_type === "30" ? `<a href="#/journal?id=${r.doc_num}">JE ${r.doc_num}</a>` : docLink(r.doc_num_type, r.doc_num, `${transTypeName(r.doc_num_type)} ${r.doc_num}`)) : ""}</td></tr>`).join("")}</tbody></table></div></div>`;
};

views["bank-reconciliation"] = async (c) => {
  const acct = query().get("acct") || "112000";
  const [open, hist, rep] = await Promise.all([api(`/bank-reconciliation/open?acct_code=${acct}`), api(`/bank-reconciliation/history?acct_code=${acct}`),
    api(`/reports/bank-reconciliation?acct_code=${acct}`)]);
  c.innerHTML = `<div class="page-head"><div><h1>Bank Reconciliation</h1><div class="sub">External reconciliation (OMTH): statement rows against the journal lines of the G/L bank account</div></div>
      <a class="btn secondary" href="#/bank-statements?acct=${acct}">Bank statements &#8599;</a></div>
    <div class="toolbar"><div class="field"><label>G/L bank account</label>${acctSelect("br-acct", acct)}</div>
      <div class="field"><label>Days around the date</label><input id="br-days" type="number" min="0" max="31" value="3" style="width:80px"></div>
      <button class="btn secondary" id="br-auto">Automatic reconciliation</button></div>
    <div class="tiles">
      <div class="tile"><div class="label">Balance per bank${rep.statement ? ` (statement ${rep.statement})` : ""}</div><div class="value">${fmt(rep.balance_per_bank)}</div>
        <div class="foot">+ in transit ${fmt(rep.deposits_in_transit)} − outstanding ${fmt(rep.outstanding_payments)} = ${fmt(rep.adjusted_bank)}</div></div>
      <div class="tile"><div class="label">Balance per books</div><div class="value">${fmt(rep.balance_per_books)}</div>
        <div class="foot">+ bank credits ${fmt(rep.bank_credits_not_booked)} − bank debits ${fmt(rep.bank_debits_not_booked)} = ${fmt(rep.adjusted_books)}</div></div>
      <div class="tile"><div class="label">Difference</div><div class="value ${Number(rep.difference) ? "bad" : "good"}">${fmt(rep.difference)}</div><div class="foot">adjusted bank − adjusted books</div></div>
    </div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Bank statement rows (not reconciled)</div><div style="overflow-x:auto"><table><thead><tr><th></th><th>Date</th><th>Reference</th><th>Narration</th><th class="num">Amount</th><th></th></tr></thead><tbody>
        ${open.rows.map((r) => `<tr><td><input type="checkbox" class="br-row" data-seq="${r.sequence}" data-amt="${r.amount}"></td><td>${r.due_date}</td><td>${esc(r.ref || "")}</td>
          <td>${esc(r.memo || "")}</td><td class="num">${fmt(r.amount)}</td><td><button class="btn small ghost br-proc" data-seq="${r.sequence}" data-amt="${r.amount}">Process…</button></td></tr>`).join("")
          || `<tr><td colspan="6" class="empty">All statement rows are reconciled.</td></tr>`}</tbody></table></div></div>
      <div class="card"><div class="card-head">Journal lines of ${esc(acct)} (not reconciled)</div><div style="overflow-x:auto"><table><thead><tr><th></th><th>Date</th><th>Origin</th><th>Reference / remarks</th><th class="num">Amount</th></tr></thead><tbody>
        ${open.lines.map((l) => `<tr><td><input type="checkbox" class="br-line" data-k="${l.trans_id}:${l.line_id}" data-amt="${l.amount}"></td><td>${l.ref_date}</td>
          <td>${docLink(l.trans_type, l.created_by, `${transTypeName(l.trans_type)} ${l.base_ref || l.trans_id}`)}</td><td>${esc([l.ref1, l.line_memo].filter(Boolean).join(" · "))}</td>
          <td class="num">${fmt(l.amount)}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">All journal lines are reconciled.</td></tr>`}</tbody></table></div></div>
    </div>
    <div class="card"><div class="card-body" style="display:flex;gap:18px;align-items:center;flex-wrap:wrap">
      <span>Selected rows <b id="br-srows">0.00</b></span><span>Selected lines <b id="br-slines">0.00</b></span><span>Difference <b id="br-sdiff">0.00</b></span>
      <button class="btn" id="br-rec" disabled>Reconcile</button></div></div>
    <div id="br-process"></div>
    <div class="card"><div class="card-head">Reconciliations</div><table><thead><tr><th>No.</th><th>Date</th><th class="num">Amount</th><th>Lines</th><th>Type</th><th>Status</th><th></th></tr></thead><tbody>
      ${hist.map((m) => `<tr><td class="mono">${m.mth_num}</td><td>${m.mth_date}</td><td class="num">${fmt(m.total)}</td>
        <td>${m.lines.filter((x) => x.bank_seq).length} rows · ${m.lines.filter((x) => x.trans_id).length} journal lines</td><td>${m.auto ? "Automatic" : "Manual"}</td>
        <td>${m.canceled ? '<span class="status X">Canceled</span>' : '<span class="status C">Reconciled</span>'}</td>
        <td>${m.canceled ? "" : `<button class="btn small ghost br-cancel" data-n="${m.mth_num}">Cancel</button>`}</td></tr>`).join("")
        || `<tr><td colspan="7" class="empty">No reconciliations yet.</td></tr>`}</tbody></table></div>`;
  $("#br-acct").onchange = (e) => (location.hash = `#/bank-reconciliation?acct=${e.target.value}`);
  const sel = () => {
    const rows = $$(".br-row:checked").reduce((s, cb) => s + Number(cb.dataset.amt), 0);
    const lines = $$(".br-line:checked").reduce((s, cb) => s + Number(cb.dataset.amt), 0);
    $("#br-srows").textContent = fmt(rows); $("#br-slines").textContent = fmt(lines); $("#br-sdiff").textContent = fmt(rows - lines);
    const any = $$(".br-row:checked, .br-line:checked").length;
    const rowsOnly = !$$(".br-line:checked").length, linesOnly = !$$(".br-row:checked").length;
    $("#br-rec").disabled = !any || Math.abs((rowsOnly ? rows : linesOnly ? lines : rows - lines)) > 0.004;
  };
  $$(".br-row, .br-line").forEach((cb) => (cb.onchange = sel));
  const reload = () => { location.hash = `#/bank-reconciliation?acct=${acct}&r=${Date.now()}`; };
  $("#br-rec").onclick = async () => {
    const body = { acct_code: acct, rows: $$(".br-row:checked").map((cb) => Number(cb.dataset.seq)),
      lines: $$(".br-line:checked").map((cb) => cb.dataset.k.split(":").map(Number)) };
    if (await act(() => post("/bank-reconciliation", body), (m) => `Reconciliation ${m.mth_num} created`)) reload();
  };
  $("#br-auto").onclick = async () => {
    if (await act(() => post("/bank-reconciliation/auto", { acct_code: acct, days: Number($("#br-days").value || 3) }), (r) => `${r.length} rows reconciled automatically`)) reload();
  };
  $$(".br-cancel").forEach((b) => (b.onclick = async () => {
    if (!confirm(`Cancel reconciliation ${b.dataset.n}? The rows and journal lines become open again.`)) return;
    if (await act(() => post(`/bank-reconciliation/${b.dataset.n}/cancel`, {}), "Reconciliation canceled")) reload();
  }));
  $$(".br-proc").forEach((b) => (b.onclick = () => {
    const moneyIn = Number(b.dataset.amt) > 0;
    $("#br-process").innerHTML = `<div class="card"><div class="card-head">Process statement row (${moneyIn ? "money in" : "money out"} ${fmt(Math.abs(Number(b.dataset.amt)))})</div><div class="card-body">
      <div class="form-grid">${fieldsHtml([
        { k: "kind", label: "Post as", type: "select", blank: false, options: [[moneyIn ? "incoming" : "outgoing", moneyIn ? "Incoming payment" : "Outgoing payment"], ["journal", "Journal entry (charges, interest ...)"]] },
        { k: "card_code", label: "Business partner", type: "select", options: () => state.partners.filter((p) => !p.frozen).map((p) => [p.card_code, `${p.card_code} — ${p.card_name}`]) },
        { k: "acct_code", label: "Offset G/L account (journal entry)", type: "select", options: O.accounts((a) => !a.control) },
        { k: "memo", label: "Remarks", max: 50, span: 2 }], {}, "pr")}</div>
      <div id="pr-items"></div>
      <button class="btn" id="pr-save" style="margin-top:10px">Post and reconcile</button></div></div>`;
    $("#pr-card_code").onchange = async () => {
      const code = $("#pr-card_code").value;
      const items = code ? await api(`/payments/open-items?card_code=${encodeURIComponent(code)}`) : [];
      $("#pr-items").innerHTML = items.length ? `<h3 class="section">Pay open items (else: payment on account)</h3><table><tbody>${items.map((it, n) => `<tr>
        <td><input type="checkbox" class="pr-item" data-n="${n}"></td><td>${esc(DOC_NAMES[it.inv_type] || "Journal Entry")} ${esc(it.doc_num)}</td><td>${it.due_date}</td>
        <td class="num">${fmt(it.open)}</td></tr>`).join("")}</tbody></table>` : "";
      $("#pr-items").items = items;
    };
    $("#pr-save").onclick = async () => {
      const f = readFields([{ k: "kind", type: "select" }, { k: "card_code", type: "select" }, { k: "acct_code", type: "select" }, { k: "memo" }], "pr");
      const items = ($("#pr-items").items || []);
      const picked = $$(".pr-item:checked").map((cb) => items[Number(cb.dataset.n)]).map((it) => ({ trans_id: it.trans_id, line_id: it.line_id, sum_applied: Number(it.open) }));
      if (await act(() => post(`/bank-statements/rows/${b.dataset.seq}/process`, { ...f, items: picked }), (m) => `Posted and reconciled (${m.mth_num})`)) {
        state.partners = await api("/partners"); reload();
      }
    };
  }));
};
