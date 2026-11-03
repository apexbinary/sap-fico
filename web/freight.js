/* Freight / additional expenses (OEXD): accounts, tax codes and SAC code per charge. */
"use strict";

views.freight = async (c) => {
  const rows = await api("/freight");
  state.freight = rows;
  const code = query().get("code");
  const edit = code && rows.find((e) => String(e.expns_code) === code);
  const taxes = (cat) => state.lookups.tax_groups.filter((x) => x.category === cat).map((x) => [x.code, `${x.code} — ${x.name}`]);
  const defs = [
    { k: "expns_name", label: "Name", req: true, max: 20 },
    { k: "rev_acct", label: "Revenue account (sales)", type: "select", blank: false, options: O.accounts((a) => !a.control), value: "413000" },
    { k: "expns_acct", label: "Expense account (purchasing)", type: "select", blank: false, options: O.accounts((a) => !a.control), value: "616000" },
    { k: "vat_group_o", label: "Output tax code", type: "select", options: taxes("O"), value: "OCS18" },
    { k: "vat_group_i", label: "Input tax code", type: "select", options: taxes("I"), value: "ICS18" },
    { k: "sac_code", label: "SAC code (GST)", max: 8 },
    { k: "fix_amnt", label: "Default amount", type: "number", step: "0.01", min: 0, value: 0 },
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Freight</h1><div class="sub">Freight / additional expenses (OEXD) added to sales and purchasing documents</div></div>
      <a class="btn" href="#/freight?new=1">+ New charge</a></div>
    <div class="card"><table><thead><tr><th>Code</th><th>Name</th><th>Revenue account</th><th>Expense account</th><th>Output tax</th><th>Input tax</th><th>SAC</th><th class="num">Default amount</th></tr></thead><tbody>
      ${rows.map((e) => `<tr style="cursor:pointer" onclick="location.hash='#/freight?code=${e.expns_code}'"><td>${e.expns_code}</td><td>${esc(e.expns_name)}</td>
        <td class="mono">${esc(e.rev_acct)}</td><td class="mono">${esc(e.expns_acct)}</td><td>${esc(e.vat_group_o || "")}</td><td>${esc(e.vat_group_i || "")}</td>
        <td class="mono">${esc(e.sac_code || "")}</td><td class="num">${Number(e.fix_amnt) ? fmt(e.fix_amnt) : ""}</td></tr>`).join("") || '<tr><td colspan="8" class="empty">No charges.</td></tr>'}</tbody></table></div>
    <div class="card"><div class="card-head">${edit ? `Charge ${edit.expns_code}` : "New charge"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(defs, edit || {}, "fr")}</div>
      <div class="help">On a document the charge has no header discount; its tax code switches between CGST + SGST and IGST like the lines.</div>
      <button class="btn" id="fr-save" style="margin-top:8px">${edit ? "Update" : "Add"}</button></div></div>`;
  $("#fr-save").onclick = async () => {
    const body = readFields(defs, "fr");
    const r = edit ? await act(() => patch(`/freight/${edit.expns_code}`, body), "Charge updated") : await act(() => post("/freight", body), (e) => `Charge ${e.expns_code} added`);
    if (r) { state.freight = await api("/freight"); location.hash = `#/freight?code=${r.expns_code}&r=${Date.now()}`; }
  };
};
