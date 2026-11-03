/* Item groups (OITB) with the G/L accounts the item postings use. */
"use strict";

views["item-groups"] = async (c) => {
  const rows = await api("/item-groups");
  const code = query().get("code");
  const edit = code && rows.find((g) => String(g.itms_grp_cod) === code);
  const acct = (k, label, value) => ({ k, label, type: "select", blank: false, options: O.accounts((a) => !a.control), value });
  const defs = [
    { k: "itms_grp_nam", label: "Group name", req: true, max: 20 },
    acct("bal_invnt_ac", "Inventory account", "115000"), acct("sale_cost_ac", "Cost of goods sold account", "511000"),
    acct("revenues_ac", "Revenue account", "411000"), acct("expenses_ac", "Expense account", "611000"),
    acct("price_dif_ac", "Price difference account", "512000"),
  ];
  const name = (a) => { const x = state.accounts.find((y) => y.acct_code === a); return x ? `${a} ${x.acct_name}` : a; };
  c.innerHTML = `<div class="page-head"><div><h1>Item Groups</h1><div class="sub">Item groups (OITB) and the G/L accounts of their items' postings</div></div>
      <a class="btn" href="#/item-groups?new=1">+ New group</a></div>
    <div class="card"><div style="overflow-x:auto"><table><thead><tr><th>Code</th><th>Name</th><th>Inventory</th><th>COGS</th><th>Revenue</th><th>Expense</th><th>Price difference</th></tr></thead><tbody>
      ${rows.map((g) => `<tr style="cursor:pointer" onclick="location.hash='#/item-groups?code=${g.itms_grp_cod}'"><td>${g.itms_grp_cod}</td><td>${esc(g.itms_grp_nam)}</td>
        <td>${esc(name(g.bal_invnt_ac))}</td><td>${esc(name(g.sale_cost_ac))}</td><td>${esc(name(g.revenues_ac))}</td><td>${esc(name(g.expenses_ac))}</td>
        <td>${esc(name(g.price_dif_ac))}</td></tr>`).join("")}</tbody></table></div></div>
    <div class="card"><div class="card-head">${edit ? `Group ${edit.itms_grp_cod}` : "New group"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(defs, edit || {}, "ig")}</div>
      <div class="help">The inventory account cannot change while items of the group have stock.</div>
      <button class="btn" id="ig-save" style="margin-top:8px">${edit ? "Update" : "Add"}</button></div></div>`;
  $("#ig-save").onclick = async () => {
    const body = readFields(defs, "ig");
    const r = edit ? await act(() => patch(`/item-groups/${edit.itms_grp_cod}`, body), "Group updated") : await act(() => post("/item-groups", body), (g) => `Group ${g.itms_grp_cod} added`);
    if (r) location.hash = `#/item-groups?code=${r.itms_grp_cod}&r=${Date.now()}`;
  };
};
