/* Cost accounting: dimensions (ODIM), profit centers (OPRC), distribution rules (OOCR / OCR1) and the
   profit center report. */
"use strict";

views["cost-accounting"] = async (c) => {
  const data = await api("/cost-accounting");
  state.costacct = data;
  const q = query(), prc = q.get("prc"), ocr = q.get("ocr");
  const cEdit = prc && data.centers.find((x) => x.prc_code === prc);
  const rEdit = ocr && data.rules.find((x) => x.ocr_code === ocr);
  const dimOpts = data.dimensions.map((d) => [d.dim_code, `${d.dim_code} — ${d.dim_name}`]);
  const cDefs = [
    { k: "prc_code", label: "Profit center", req: true, max: 8, ro: !!cEdit }, { k: "prc_name", label: "Name", req: true, max: 30 },
    { k: "dim_code", label: "Dimension", type: "select", int: true, blank: false, options: dimOpts, ro: !!cEdit, value: 1 },
    { k: "valid_from", label: "Valid from", type: "date" }, { k: "valid_to", label: "Valid to", type: "date" },
    ...(cEdit ? [{ k: "active", label: "Active", type: "check" }] : []),
  ];
  const rDefs = [
    { k: "ocr_code", label: "Distribution rule", req: true, max: 8, ro: !!rEdit }, { k: "ocr_name", label: "Name", req: true, max: 30 },
    { k: "dim_code", label: "Dimension", type: "select", int: true, blank: false, options: dimOpts, ro: !!rEdit, value: 1 },
    ...(rEdit ? [{ k: "active", label: "Active", type: "check" }] : []),
  ];
  const dimName = (n) => (data.dimensions.find((d) => d.dim_code === n) || {}).dim_name || n;
  c.innerHTML = `<div class="page-head"><div><h1>Cost Accounting</h1><div class="sub">Dimensions, profit centers and distribution rules — revenue and expense lines of postings carry the rules</div></div>
      <span style="display:flex;gap:8px"><a class="btn" href="#/cost-accounting?prc=">+ Profit center</a><a class="btn" href="#/cost-accounting?ocr=">+ Distribution rule</a></span></div>
    <div class="card"><div class="card-head">Dimensions</div><table><thead><tr><th>Dimension</th><th>Name</th><th>Description</th><th>Active</th></tr></thead><tbody>
      ${data.dimensions.map((d) => `<tr data-dim="${d.dim_code}"><td>${d.dim_code}</td><td><input class="dm-name" maxlength="30" value="${esc(d.dim_name)}"></td>
        <td><input class="dm-desc" maxlength="100" value="${esc(d.dim_desc || "")}"></td><td><input type="checkbox" class="dm-act"${d.active ? " checked" : ""}></td></tr>`).join("")}</tbody></table>
      <div class="card-body"><button class="btn secondary" id="dm-save">Update dimensions</button></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Profit centers</div><table><thead><tr><th>Code</th><th>Name</th><th>Dimension</th><th>Valid</th><th>Active</th></tr></thead><tbody>
        ${data.centers.map((p) => `<tr style="cursor:pointer" onclick="location.hash='#/cost-accounting?prc=${encodeURIComponent(p.prc_code)}'"><td class="mono">${esc(p.prc_code)}</td>
          <td>${esc(p.prc_name)}</td><td>${esc(dimName(p.dim_code))}</td><td>${p.valid_from || ""}${p.valid_to ? ` – ${p.valid_to}` : ""}</td><td>${yesNo(p.active)}</td></tr>`).join("")
          || '<tr><td colspan="5" class="empty">No profit centers.</td></tr>'}</tbody></table></div>
      <div class="card"><div class="card-head">Distribution rules</div><table><thead><tr><th>Code</th><th>Name</th><th>Dimension</th><th>Shares</th><th>Active</th></tr></thead><tbody>
        ${data.rules.map((r) => `<tr style="cursor:pointer" onclick="location.hash='#/cost-accounting?ocr=${encodeURIComponent(r.ocr_code)}'"><td class="mono">${esc(r.ocr_code)}</td>
          <td>${esc(r.ocr_name)}${r.direct ? ' <span class="help">direct</span>' : ""}</td><td>${esc(dimName(r.dim_code))}</td>
          <td>${r.shares.map((s) => `${esc(s.prc_code)} ${Number(s.prc_amount)}`).join(" / ")}</td><td>${yesNo(r.active)}</td></tr>`).join("")
          || '<tr><td colspan="5" class="empty">No distribution rules.</td></tr>'}</tbody></table></div></div>
    ${prc !== null ? `<div class="card"><div class="card-head">${cEdit ? `Profit center ${esc(cEdit.prc_code)}` : "New profit center"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(cDefs, cEdit || {}, "pc")}</div><div class="help">A new profit center gets a direct distribution rule with the same code.</div>
      <button class="btn" id="pc-save" style="margin-top:8px">${cEdit ? "Update" : "Add"}</button></div></div>` : ""}
    ${ocr !== null ? `<div class="card"><div class="card-head">${rEdit ? `Distribution rule ${esc(rEdit.ocr_code)}` : "New distribution rule"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(rDefs, rEdit || {}, "dr")}</div>
      ${rEdit && rEdit.direct ? '<div class="help">Direct rule of its profit center (100 %).</div>' : `<h3 class="section">Shares</h3>
      <table class="lines"><thead><tr><th>Profit center</th><th class="num w-amt">Share</th></tr></thead><tbody id="dr-shares"></tbody></table>
      <button class="btn small secondary" id="dr-add" style="margin-top:6px">+ Share</button>`}
      <div><button class="btn" id="dr-save" style="margin-top:8px">${rEdit ? "Update" : "Add"}</button></div></div></div>` : ""}`;
  $("#dm-save").onclick = async () => {
    for (const tr of $$("tr[data-dim]")) {
      const body = { dim_name: $(".dm-name", tr).value, dim_desc: $(".dm-desc", tr).value || null, active: $(".dm-act", tr).checked };
      if (!(await act(() => patch(`/cost-accounting/dimensions/${tr.dataset.dim}`, body)))) return;
    }
    toast("Dimensions updated", "good");
    await reloadMasterData();
    views["cost-accounting"](c);
  };
  if ($("#pc-save")) $("#pc-save").onclick = async () => {
    const body = readFields(cDefs, "pc");
    const r = cEdit ? await act(() => patch(`/cost-accounting/centers/${encodeURIComponent(cEdit.prc_code)}`, body), "Profit center updated")
      : await act(() => post("/cost-accounting/centers", body), "Profit center added");
    if (r) { state.costacct = r; location.hash = `#/cost-accounting?r=${Date.now()}`; }
  };
  if ($("#dr-save")) {
    const dimSel = () => Number(($("#dr-dim_code") || {}).value || (rEdit ? rEdit.dim_code : 1));
    const addShare = (s = {}) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><select class="sh-prc">${opt("", "")}${data.centers.filter((p) => p.dim_code === dimSel() && p.active)
        .map((p) => opt(p.prc_code, `${p.prc_code} — ${p.prc_name}`, s.prc_code)).join("")}</select></td>
        <td class="num"><input class="sh-amt" type="number" step="0.01" min="0" value="${s.prc_amount != null ? Number(s.prc_amount) : ""}"></td>`;
      $("#dr-shares").appendChild(tr);
    };
    if ($("#dr-shares")) {
      ((rEdit && rEdit.shares) || [{}, {}]).forEach(addShare);
      $("#dr-add").onclick = () => addShare();
      if ($("#dr-dim_code")) $("#dr-dim_code").onchange = () => { $("#dr-shares").innerHTML = ""; addShare(); addShare(); };
    }
    $("#dr-save").onclick = async () => {
      const body = readFields(rDefs, "dr");
      if ($("#dr-shares")) body.shares = $$("#dr-shares tr").map((tr) => ({ prc_code: $(".sh-prc", tr).value, prc_amount: Number($(".sh-amt", tr).value || 0) })).filter((s) => s.prc_code);
      const r = rEdit ? await act(() => patch(`/cost-accounting/rules/${encodeURIComponent(rEdit.ocr_code)}`, body), "Rule updated")
        : await act(() => post("/cost-accounting/rules", body), "Rule added");
      if (r) { state.costacct = r; location.hash = `#/cost-accounting?r=${Date.now()}`; }
    };
  }
};

views["profit-centers"] = async (c) => {
  const q = query(), from = q.get("from") || yearStart(), to = q.get("to") || yearEnd(), dim = Number(q.get("dim") || 1);
  const r = await api(`/reports/profit-centers?date_from=${from}&date_to=${to}&dim=${dim}`);
  const dims = (state.costacct || { dimensions: [] }).dimensions;
  c.innerHTML = `<div class="page-head"><div><h1>Profit Center Report</h1><div class="sub">${from} – ${to} · revenue and expenses split by the distribution rules</div></div>
      <label class="pp-pick">Dimension <select id="pc-dim">${dims.map((d) => opt(d.dim_code, `${d.dim_code} — ${d.dim_name}`, dim)).join("")}</select></label></div>
    ${periodToolbar(from, to)}
    <div class="card"><table><thead><tr><th>Profit center</th><th>Name</th><th class="num">Revenue</th><th class="num">Expenses</th><th class="num">Result</th></tr></thead><tbody>
      ${r.centers.map((x, n) => `<tr style="cursor:pointer" onclick="document.getElementById('pc-acc-${n}').classList.toggle('hidden')"><td class="mono">${esc(x.prc_code || "—")}</td>
        <td>${esc(x.prc_name)}</td><td class="num">${fmt(x.revenue)}</td><td class="num">${fmt(x.expenses)}</td>
        <td class="num ${Number(x.result) >= 0 ? "good" : "bad"}">${fmt(x.result)}</td></tr>
        <tr id="pc-acc-${n}" class="hidden"><td></td><td colspan="4"><table><tbody>${x.accounts.map((a) => `<tr><td class="mono">${esc(a.account)}</td><td>${esc(a.acct_name)}</td>
          <td class="num">${fmt(a.amount)}</td></tr>`).join("")}</tbody></table></td></tr>`).join("")
        || '<tr><td colspan="5" class="empty">No revenue or expenses in this period.</td></tr>'}</tbody>
      <tfoot><tr><td colspan="2">Total</td><td class="num">${fmt(r.total.revenue)}</td><td class="num">${fmt(r.total.expenses)}</td><td class="num">${fmt(r.total.result)}</td></tr></tfoot></table></div>`;
  $("#rp-go").onclick = () => { location.hash = `#/profit-centers?from=${$("#rp-from").value}&to=${$("#rp-to").value}&dim=${$("#pc-dim").value}`; };
  $("#pc-dim").onchange = (e) => { location.hash = `#/profit-centers?from=${from}&to=${to}&dim=${e.target.value}`; };
};
