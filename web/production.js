/* Production: bills of materials, production orders (issue / receipt / close), MRP recommendations. */
"use strict";

const itemOpts = (items, sel) => items.map((i) => opt(i.item_code, `${i.item_code} — ${i.item_name}`, sel)).join("");

views.boms = async (c) => {
  const [boms, items] = await Promise.all([api("/production/boms"), api("/items")]);
  const code = query().get("code");
  const edit = code && boms.find((b) => b.code === code);
  const inv = items.filter((i) => i.invnt_item);
  c.innerHTML = `<div class="page-head"><div><h1>Bills of Materials</h1><div class="sub">Production BOMs: components per quantity of the parent item</div></div>
      <a class="btn" href="#/boms?code=">+ New BOM</a></div>
    <div class="card"><table><thead><tr><th>Parent item</th><th>Description</th><th>Type</th><th class="num">Quantity</th><th>Warehouse</th><th class="num">Components</th><th class="num">Cost</th></tr></thead><tbody>
      ${boms.map((b) => `<tr style="cursor:pointer" onclick="location.hash='#/boms?code=${encodeURIComponent(b.code)}'"><td class="mono">${esc(b.code)}</td><td>${esc(b.item_name || "")}</td>
        <td>${{ P: "Production", S: "Sales", A: "Assembly", T: "Template" }[b.tree_type]}</td><td class="num">${qtyFmt(b.qauntity)}</td><td>${esc(b.to_wh || "")}</td>
        <td class="num">${b.lines.length}</td><td class="num">${fmt(b.cost)}</td></tr>`).join("") || '<tr><td colspan="7" class="empty">No bills of materials.</td></tr>'}</tbody></table></div>
    ${code !== null ? `<div class="card"><div class="card-head">${edit ? `BOM of ${esc(edit.code)}` : "New bill of materials"}</div><div class="card-body">
      <div class="form-grid">
        <div class="field"><label class="req">Parent item</label><select id="bm-code"${edit ? " disabled" : ""}>${opt("", "")}${itemOpts(inv, edit && edit.code)}</select></div>
        <div class="field"><label>Type</label><select id="bm-type">${[["P", "Production"], ["S", "Sales"], ["A", "Assembly"], ["T", "Template"]].map(([v, l]) => opt(v, l, edit ? edit.tree_type : "P")).join("")}</select></div>
        <div class="field"><label>Quantity</label><input id="bm-qty" type="number" step="any" min="0" value="${edit ? Number(edit.qauntity) : 1}"></div>
        <div class="field"><label>Warehouse</label><select id="bm-wh">${state.warehouses.map((w) => opt(w.whs_code, w.whs_code, edit ? edit.to_wh : "01")).join("")}</select></div></div>
      <table class="lines" style="margin-top:8px"><thead><tr><th>Component</th><th class="num">Quantity</th><th>Warehouse</th><th>Issue method</th><th></th></tr></thead><tbody id="bm-lines"></tbody></table>
      <div style="display:flex;gap:8px;margin-top:6px"><button class="btn small secondary" id="bm-add">+ Component</button></div>
      <button class="btn" id="bm-save" style="margin-top:10px">Save</button></div></div>` : ""}`;
  if (code === null) return;
  const addLine = (l = {}) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><select class="bl-code">${opt("", "— item —")}${itemOpts(items, l.code)}</select></td>
      <td class="num"><input class="bl-qty" type="number" step="any" min="0" value="${l.quantity != null ? Number(l.quantity) : ""}"></td>
      <td><select class="bl-wh">${state.warehouses.map((w) => opt(w.whs_code, w.whs_code, l.warehouse || "01")).join("")}</select></td>
      <td><select class="bl-m">${opt("M", "Manual", l.issue_mthd)}${opt("B", "Backflush", l.issue_mthd)}</select></td><td><button class="btn ghost small bl-del">✕</button></td>`;
    $(".bl-del", tr).onclick = () => tr.remove();
    $("#bm-lines").appendChild(tr);
  };
  ((edit && edit.lines) || [{}, {}]).forEach(addLine);
  $("#bm-add").onclick = () => addLine();
  $("#bm-save").onclick = async () => {
    const parent = edit ? edit.code : $("#bm-code").value;
    if (!parent) return toast("Choose the parent item", "bad");
    const body = { tree_type: $("#bm-type").value, qauntity: Number($("#bm-qty").value || 1), to_wh: $("#bm-wh").value,
      lines: $$("#bm-lines tr").map((tr) => ({ code: $(".bl-code", tr).value, quantity: Number($(".bl-qty", tr).value || 0), warehouse: $(".bl-wh", tr).value, issue_mthd: $(".bl-m", tr).value })).filter((l) => l.code) };
    if (await act(() => api(`/production/boms/${encodeURIComponent(parent)}`, { method: "PUT", body: JSON.stringify(body) }), "Bill of materials saved"))
      location.hash = `#/boms?code=${encodeURIComponent(parent)}&r=${Date.now()}`;
  };
};

views["production-orders"] = async (c) => {
  const id = query().get("id");
  const [list, boms] = await Promise.all([api("/production/orders"), api("/production/boms")]);
  const po = id ? await api(`/production/orders/${id}`) : null;
  const prodBoms = boms.filter((b) => b.tree_type === "P");
  const st = (s) => `<span class="status ${s === "R" ? "O" : s === "C" ? "X" : "C"}">${{ P: "Planned", R: "Released", L: "Closed", C: "Canceled" }[s]}</span>`;
  c.innerHTML = `<div class="page-head"><div><h1>Production Orders</h1><div class="sub">Issue components, receive products, close with the variance</div></div>
      <a class="btn" href="#/production-orders?id=">+ New production order</a></div>
    <div class="card"><table><thead><tr><th>No.</th><th>Product</th><th class="num">Planned</th><th class="num">Completed</th><th>Due</th><th class="num">WIP</th><th>Status</th></tr></thead><tbody>
      ${list.map((o) => `<tr style="cursor:pointer" onclick="location.hash='#/production-orders?id=${o.doc_entry}'"><td>${o.doc_num}</td><td>${esc(o.item_code)} ${esc(o.item_name || "")}</td>
        <td class="num">${qtyFmt(o.planned_qty)}</td><td class="num">${qtyFmt(o.cmplt_qty)}</td><td>${o.due_date}</td><td class="num">${fmt(o.wip)}</td><td>${st(o.status)}</td></tr>`).join("")
        || '<tr><td colspan="7" class="empty">No production orders.</td></tr>'}</tbody></table></div>
    ${id === "" ? `<div class="card"><div class="card-head">New production order</div><div class="card-body"><div class="form-grid">
        <div class="field"><label class="req">Product</label><select id="no-item">${prodBoms.map((b) => opt(b.code, `${b.code} — ${b.item_name || ""}`)).join("")}</select></div>
        <div class="field"><label class="req">Planned quantity</label><input id="no-qty" type="number" step="any" min="0" value="1"></div>
        <div class="field"><label>Order date</label><input id="no-date" type="date" value="${today()}"></div>
        <div class="field"><label>Due date</label><input id="no-due" type="date" value="${today()}"></div>
        <div class="field check"><label><input type="checkbox" id="no-rel" checked> Release</label></div></div>
        ${prodBoms.length ? "" : '<div class="help">Create a production bill of materials first.</div>'}
        <button class="btn" id="no-add" style="margin-top:8px"${prodBoms.length ? "" : " disabled"}>Add</button></div></div>` : ""}
    ${po ? `<div class="card"><div class="card-head"><span>Production order ${po.doc_num}: ${esc(po.item_code)} ${esc(po.item_name || "")} ${st(po.status)}</span>
        <span class="help">planned ${qtyFmt(po.planned_qty)} · completed ${qtyFmt(po.cmplt_qty)} · issued ${fmt(po.issued_val)} · received ${fmt(po.rcpt_val)} · cost / unit ${fmt(po.unit_cost)}</span></div>
      <table class="lines"><thead><tr><th>#</th><th>Component</th><th class="num">Per unit</th><th class="num">Planned</th><th class="num">Issued</th><th class="num">Issued value</th><th>Whs</th><th>Method</th><th class="num w-amt">Issue now</th></tr></thead><tbody>
        ${po.lines.map((l) => `<tr data-line="${l.line_num}"><td>${l.line_num + 1}</td><td>${esc(l.item_code)} ${esc(l.item_name || "")}</td><td class="num">${qtyFmt(l.base_qty)}</td>
          <td class="num">${qtyFmt(l.planned_qty)}</td><td class="num">${qtyFmt(l.issued_qty)}</td><td class="num">${fmt(l.issued_val)}</td><td>${esc(l.warehouse)}</td>
          <td>${l.issue_type === "B" ? "Backflush" : "Manual"}</td><td class="num">${po.status === "R" ? `<input class="pl-qty" type="number" step="any" min="0" value="${l.issue_type === "M" ? Math.max(0, Number(l.planned_qty) - Number(l.issued_qty)) : ""}">` : ""}</td></tr>`).join("")}</tbody></table>
      <div class="card-body" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <span>Date <input type="date" id="po-date" value="${today()}"></span>
        ${po.status === "P" ? '<button class="btn" id="po-rel">Release</button>' : ""}
        ${po.status === "R" ? `<button class="btn secondary" id="po-issue">Issue components</button>
          <span>Receive <input type="number" id="po-rqty" step="any" min="0" value="${Math.max(0, Number(po.planned_qty) - Number(po.cmplt_qty))}" style="width:90px"></span>
          <button class="btn" id="po-recv">Receipt from production</button><button class="btn secondary" id="po-close">Close</button>` : ""}
        ${["P", "R"].includes(po.status) ? '<button class="btn ghost" id="po-cancel">Cancel</button>' : ""}
        ${po.var_trans ? `<a href="#/journal?id=${po.var_trans}">Variance journal entry</a>` : ""}</div></div>` : ""}`;
  if (id === "" && $("#no-add")) $("#no-add").onclick = async () => {
    const body = { item_code: $("#no-item").value, planned_qty: Number($("#no-qty").value || 0), post_date: $("#no-date").value, due_date: $("#no-due").value, release: $("#no-rel").checked };
    const r = await act(() => post("/production/orders", body), (x) => `Production order ${x.doc_num} added`);
    if (r) location.hash = `#/production-orders?id=${r.doc_entry}`;
  };
  if (!po) return;
  const reload = () => { location.hash = `#/production-orders?id=${po.doc_entry}&r=${Date.now()}`; };
  const on = (sel, f) => { const b = $(sel); if (b) b.onclick = f; };
  on("#po-rel", async () => { if (await act(() => post(`/production/orders/${po.doc_entry}/release`, {}), "Released")) reload(); });
  on("#po-issue", async () => {
    const lines = $$("tr[data-line]").map((tr) => ({ line_num: Number(tr.dataset.line), quantity: Number(($(".pl-qty", tr) || {}).value || 0) })).filter((l) => l.quantity > 0);
    if (!lines.length) return toast("Enter the quantities to issue", "bad");
    if (await act(() => post(`/production/orders/${po.doc_entry}/issue`, { doc_date: $("#po-date").value, lines }), "Components issued")) reload();
  });
  on("#po-recv", async () => { if (await act(() => post(`/production/orders/${po.doc_entry}/receive`, { doc_date: $("#po-date").value, quantity: Number($("#po-rqty").value || 0) }), "Products received")) reload(); });
  on("#po-close", async () => { if (await act(() => post(`/production/orders/${po.doc_entry}/close`, { doc_date: $("#po-date").value }), "Production order closed")) reload(); });
  on("#po-cancel", async () => { if (await act(() => post(`/production/orders/${po.doc_entry}/cancel`, {}), "Production order canceled")) reload(); });
};

views.mrp = async (c) => {
  const horizon = query().get("horizon") || new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
  const r = await api(`/production/mrp?horizon=${horizon}`);
  const vendors = state.partners.filter((p) => p.card_type === "S");
  c.innerHTML = `<div class="page-head"><div><h1>MRP</h1><div class="sub">Net requirements up to ${horizon} from sales orders, production orders and minimum levels; order recommendations</div></div>
      <span>Horizon <input type="date" id="mr-h" value="${esc(horizon)}"></span></div>
    <div class="card"><div class="card-head">Recommendations</div><table><thead><tr><th></th><th>Type</th><th>Item</th><th class="num w-amt">Quantity</th><th>Order date</th><th>Due date</th><th>Vendor</th></tr></thead><tbody>
      ${r.recommendations.map((x, n) => `<tr data-n="${n}"><td><input type="checkbox" class="mr-pick" checked></td><td>${x.type === "production" ? "Production order" : "Purchase order"}</td>
        <td>${esc(x.item_code)} ${esc(x.item_name || "")}</td><td class="num"><input class="mr-qty" type="number" step="any" min="0" value="${Number(x.quantity)}" style="width:100px"></td>
        <td>${x.order_date}</td><td>${x.due_date}</td><td>${x.type === "purchase" ? esc(x.card_code || "default vendor") : ""}</td></tr>`).join("")
        || '<tr><td colspan="7" class="empty">Nothing to order.</td></tr>'}</tbody></table>
      ${r.recommendations.length ? `<div class="card-body" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">Default vendor
        <select id="mr-vendor">${opt("", "")}${vendors.map((v) => opt(v.card_code, `${v.card_code} — ${v.card_name}`)).join("")}</select>
        <button class="btn" id="mr-create">Create the selected documents</button></div>` : ""}</div>
    <div class="card"><div class="card-head">Requirements</div><table><thead><tr><th>Item</th><th class="num">Level</th><th class="num">Gross</th><th class="num">On hand</th><th class="num">On order</th><th class="num">In production</th><th class="num">Net</th><th>Demand from</th></tr></thead><tbody>
      ${r.items.map((x) => `<tr><td>${esc(x.item_code)} ${esc(x.item_name || "")}</td><td class="num">${x.level}</td><td class="num">${qtyFmt(x.gross)}</td><td class="num">${qtyFmt(x.on_hand)}</td>
        <td class="num">${qtyFmt(x.on_order)}</td><td class="num">${qtyFmt(x.in_production)}</td><td class="num"><b>${qtyFmt(x.net)}</b></td><td class="help">${x.sources.map(esc).join(", ")}</td></tr>`).join("")
        || '<tr><td colspan="8" class="empty">No demand.</td></tr>'}</tbody></table></div>`;
  $("#mr-h").onchange = (e) => { location.hash = `#/mrp?horizon=${e.target.value}`; };
  if ($("#mr-create")) $("#mr-create").onclick = async () => {
    const recs = $$("tr[data-n]").filter((tr) => $(".mr-pick", tr).checked).map((tr) => ({ ...r.recommendations[Number(tr.dataset.n)], quantity: Number($(".mr-qty", tr).value || 0) }));
    if (!recs.length) return toast("Select recommendations", "bad");
    const made = await act(() => post("/production/mrp/create", { doc_date: today(), recommendations: recs, default_vendor: $("#mr-vendor").value || null }),
      (x) => `Created purchase orders ${x.purchase_orders.join(", ") || "-"}, production orders ${x.production_orders.join(", ") || "-"}`);
    if (made) views.mrp(c);
  };
};
