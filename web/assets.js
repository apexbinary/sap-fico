/* Fixed assets: register, asset master with capitalization / retirement, monthly depreciation run, asset classes. */
"use strict";

views.assets = async (c) => {
  const q = query(), code = q.get("code"), cls = q.get("class");
  const data = await api("/fixed-assets");
  // the run that is due next (months are posted in order), else the current month
  const due = data.next_due && data.next_due <= `${today().slice(0, 7)}-01` ? data.next_due : `${today().slice(0, 7)}-01`;
  const month = q.get("month") || due;
  const preview = await api(`/fixed-assets/depreciation?month=${month}`).catch((e) => ({ error: e.message }));
  const edit = code && data.assets.find((a) => a.asset_code === code);
  const cEdit = cls && data.classes.find((x) => x.code === cls);
  const STAT = { N: "New", A: "Active", R: "Retired" };
  const aDefs = [
    { k: "asset_code", label: "Asset no.", req: true, max: 20, ro: !!edit }, { k: "name", label: "Description", req: true, max: 100, span: 2 },
    { k: "class_code", label: "Asset class", type: "select", blank: false, options: data.classes.map((x) => [x.code, `${x.code} — ${x.name}`]), ro: !!(edit && edit.status !== "N") },
    { k: "serial", label: "Serial no.", max: 36 }, { k: "location", label: "Location", max: 50 },
    { k: "salvage", label: "Salvage value", type: "number", step: "0.01", min: 0, ro: !!(edit && edit.status !== "N") },
  ];
  const acct = (k, label, value, filter) => ({ k, label, type: "select", blank: false, options: O.accounts(filter || ((a) => !a.control)), value });
  const cDefs = [
    { k: "code", label: "Class", req: true, max: 8, ro: !!cEdit }, { k: "name", label: "Name", req: true, max: 50 },
    acct("asset_acct", "Asset account", "121000"), acct("acc_dep_acct", "Accumulated depreciation", "129000"),
    acct("dep_acct", "Depreciation expense", "617000"), acct("retire_acct", "Gain / loss on retirement", "724000"),
    { k: "method", label: "Depreciation method", type: "select", blank: false, options: [["SL", "Straight line"], ["WD", "Written-down value"]], value: "SL" },
    { k: "useful_life", label: "Useful life (months, SL)", type: "number", step: 1, min: 1 }, { k: "wdv_rate", label: "Rate % p.a. (WDV)", type: "number", step: "0.01", min: 0, maxv: 99.99 },
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Fixed Assets</h1><div class="sub">Asset register, capitalization, monthly depreciation and retirement</div></div>
      <span style="display:flex;gap:8px"><a class="btn" href="#/assets?code=">+ Asset</a><a class="btn secondary" href="#/assets?class=">+ Asset class</a></span></div>
    <div class="tiles"><div class="tile"><div class="label">Acquisition value</div><div class="value">${fmt(data.totals.cost)}</div></div>
      <div class="tile"><div class="label">Accumulated depreciation</div><div class="value">${fmt(data.totals.acc_dep)}</div></div>
      <div class="tile"><div class="label">Net book value</div><div class="value">${fmt(data.totals.book_value)}</div></div></div>
    <div class="card"><div class="card-head">Asset register</div><div style="overflow-x:auto"><table><thead><tr><th>Asset</th><th>Description</th><th>Class</th><th>Capitalized</th>
      <th class="num">Cost</th><th class="num">Acc. depreciation</th><th class="num">Book value</th><th>Depreciated to</th><th>Status</th></tr></thead><tbody>
      ${data.assets.map((a) => `<tr style="cursor:pointer" onclick="location.hash='#/assets?code=${encodeURIComponent(a.asset_code)}'"><td class="mono">${esc(a.asset_code)}</td>
        <td>${esc(a.name)}</td><td>${esc(a.class_code)}</td><td>${a.cap_date || ""}</td><td class="num">${fmt(a.cost)}</td><td class="num">${fmt(a.acc_dep)}</td>
        <td class="num">${fmt(a.book_value)}</td><td>${a.dep_until || ""}</td><td>${STAT[a.status]}${a.retire_date ? ` ${a.retire_date}` : ""}</td></tr>`).join("")
        || '<tr><td colspan="9" class="empty">No assets.</td></tr>'}</tbody></table></div></div>
    <div class="card"><div class="card-head">Depreciation run · <input type="month" id="dp-month" value="${month.slice(0, 7)}"></div>
      ${preview.error ? `<div class="card-body"><div class="gr-issues">${esc(preview.error)}</div></div>` : `<table><thead><tr><th>Asset</th><th>Description</th><th>Method</th>
        <th class="num">Book value before</th><th class="num">Depreciation</th><th class="num">Book value after</th></tr></thead><tbody>
        ${preview.map((r) => `<tr><td class="mono">${esc(r.asset_code)}</td><td>${esc(r.name)}</td><td>${r.method === "SL" ? "Straight line" : "WDV"}</td>
          <td class="num">${fmt(r.book_before)}</td><td class="num">${fmt(r.amount)}</td><td class="num">${fmt(r.book_after)}</td></tr>`).join("")
          || '<tr><td colspan="6" class="empty">Nothing to depreciate in this month.</td></tr>'}</tbody></table>`}
      <div class="card-body" style="display:flex;gap:8px">${!preview.error && preview.length ? '<button class="btn" id="dp-run">Post depreciation</button>' : ""}
        <button class="btn ghost" id="dp-rev">Reverse this month</button></div></div>
    ${code !== null ? `<div class="card"><div class="card-head">${edit ? `Asset ${esc(edit.asset_code)} · ${STAT[edit.status]}` : "New asset"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(aDefs, edit || {}, "fa")}</div><button class="btn" id="fa-save" style="margin-top:8px">${edit ? "Update" : "Add"}</button>
      ${edit && edit.status !== "R" ? `<div class="grid-2" style="margin-top:12px">
        ${!edit.dep_until ? `<div><h3 class="section">Capitalization</h3><div class="form-grid">
          <div class="field"><label>Date</label><input type="date" id="fc-date" value="${today()}"></div>
          <div class="field"><label>Amount</label><input type="number" id="fc-amt" step="0.01" min="0"></div>
          <div class="field"><label>Offset account</label><select id="fc-acct">${accountOptions((a) => !a.control)}</select></div></div>
          <button class="btn secondary" id="fc-go" style="margin-top:6px">Capitalize</button></div>` : "<div></div>"}
        ${edit.status === "A" ? `<div><h3 class="section">Retirement</h3><div class="form-grid">
          <div class="field"><label>Date</label><input type="date" id="fr-date" value="${today()}"></div>
          <div class="field"><label>Proceeds (0 = scrapped)</label><input type="number" id="fr-amt" step="0.01" min="0" value="0"></div>
          <div class="field"><label>Proceeds account</label><select id="fr-acct">${accountOptions((a) => !a.control)}</select></div></div>
          <button class="btn secondary" id="fr-go" style="margin-top:6px">Retire</button></div>` : ""}</div>` : ""}
      ${edit ? `<h3 class="section">Transactions</h3><table><thead><tr><th>Date</th><th>Type</th><th class="num">Amount</th><th>Journal entry</th><th></th></tr></thead><tbody>
        ${edit.transactions.map((t) => `<tr><td>${t.doc_date}</td><td>${{ C: "Capitalization", D: `Depreciation ${t.period}`, R: "Retirement" }[t.tran_type]}</td>
          <td class="num">${fmt(t.amount)}</td><td>${t.trans_id ? `<a href="#/journal?id=${t.trans_id}">${t.trans_id}</a>` : ""}</td>
          <td>${t.reversed ? '<span class="status C">reversed</span>' : esc(t.memo || "")}</td></tr>`).join("")}</tbody></table>` : ""}</div></div>` : ""}
    ${cls !== null ? `<div class="card"><div class="card-head">${cEdit ? `Asset class ${esc(cEdit.code)}` : "New asset class"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(cDefs, cEdit || {}, "ac")}</div><button class="btn" id="ac-save" style="margin-top:8px">${cEdit ? "Update" : "Add"}</button></div></div>` : ""}
    <div class="card"><div class="card-head">Asset classes</div><table><thead><tr><th>Class</th><th>Name</th><th>Method</th><th>Life / rate</th><th>Asset</th><th>Acc. dep.</th><th>Expense</th></tr></thead><tbody>
      ${data.classes.map((x) => `<tr style="cursor:pointer" onclick="location.hash='#/assets?class=${encodeURIComponent(x.code)}'"><td class="mono">${esc(x.code)}</td><td>${esc(x.name)}</td>
        <td>${x.method === "SL" ? "Straight line" : "WDV"}</td><td>${x.method === "SL" ? `${x.useful_life} months` : `${Number(x.wdv_rate)} %`}</td>
        <td class="mono">${esc(x.asset_acct)}</td><td class="mono">${esc(x.acc_dep_acct)}</td><td class="mono">${esc(x.dep_acct)}</td></tr>`).join("")}</tbody></table></div>`;
  const reload = (extra = "") => { location.hash = `#/assets?month=${month}${extra}&r=${Date.now()}`; };
  $("#dp-month").onchange = (e) => { location.hash = `#/assets?month=${e.target.value}-01`; };
  if ($("#dp-run")) $("#dp-run").onclick = async () => { if (await act(() => post("/fixed-assets/depreciation", { month }), "Depreciation posted")) reload(); };
  $("#dp-rev").onclick = async () => { if (await act(() => post("/fixed-assets/depreciation/reverse", { month }), "Depreciation reversed")) reload(); };
  if ($("#fa-save")) $("#fa-save").onclick = async () => {
    const body = readFields(aDefs, "fa");
    const r = edit ? await act(() => patch(`/fixed-assets/${encodeURIComponent(edit.asset_code)}`, body), "Asset updated") : await act(() => post("/fixed-assets", body), (x) => `Asset ${x.asset_code} added`);
    if (r) reload(`&code=${encodeURIComponent(r.asset_code)}`);
  };
  if ($("#fc-go")) $("#fc-go").onclick = async () => {
    const body = { doc_date: $("#fc-date").value, amount: Number($("#fc-amt").value || 0), offset_acct: $("#fc-acct").value };
    if (await act(() => post(`/fixed-assets/${encodeURIComponent(edit.asset_code)}/capitalize`, body), "Capitalized")) reload(`&code=${encodeURIComponent(edit.asset_code)}`);
  };
  if ($("#fr-go")) $("#fr-go").onclick = async () => {
    const body = { doc_date: $("#fr-date").value, proceeds: Number($("#fr-amt").value || 0), offset_acct: $("#fr-acct").value };
    if (await act(() => post(`/fixed-assets/${encodeURIComponent(edit.asset_code)}/retire`, body), "Asset retired")) reload(`&code=${encodeURIComponent(edit.asset_code)}`);
  };
  if ($("#ac-save")) $("#ac-save").onclick = async () => {
    const body = readFields(cDefs, "ac");
    const r = cEdit ? await act(() => patch(`/fixed-assets/classes/${encodeURIComponent(cEdit.code)}`, body), "Class updated") : await act(() => post("/fixed-assets/classes", body), "Class added");
    if (r) reload(`&class=${encodeURIComponent(r.code)}`);
  };
};
