/* Inventory counting (OINC / INC1) and inventory posting (OIQR / IQR1). */
"use strict";

views.counting = async (c) => {
  const id = query().get("id");
  const list = await api("/inventory/counting");
  const cnt = id ? await api(`/inventory/counting/${id}`) : null;
  const groups = await api("/item-groups");
  const newDefs = [
    { k: "count_date", label: "Count date", type: "date", value: today(), req: true },
    { k: "whs_code", label: "Warehouse", type: "select", blank: false, options: () => state.warehouses.map((w) => [w.whs_code, `${w.whs_code} — ${w.whs_name}`]) },
    { k: "item_group", label: "Item group", type: "select", int: true, blank: "All item groups", options: groups.map((g) => [g.itms_grp_cod, g.itms_grp_nam]) },
    { k: "remarks", label: "Remarks", max: 254, span: 2 },
  ];
  const STATUS_TXT = (s) => (s === "O" ? '<span class="status O">Open</span>' : '<span class="status C">Closed</span>');
  c.innerHTML = `<div class="page-head"><div><h1>Inventory Counting</h1><div class="sub">Count stock per warehouse and post the differences (inventory posting)</div></div>
      <a class="btn" href="#/counting?new=1">+ New counting</a></div>
    <div class="card"><table><thead><tr><th>No.</th><th>Count date</th><th>Remarks</th><th class="num">Lines</th><th class="num">Counted</th><th class="num">Differences</th><th>Status</th></tr></thead><tbody>
      ${list.map((x) => `<tr style="cursor:pointer" onclick="location.hash='#/counting?id=${x.doc_entry}'"><td>${x.doc_num}</td><td>${x.count_date}</td><td>${esc(x.remarks || "")}</td>
        <td class="num">${x.lines}</td><td class="num">${x.counted}</td><td class="num">${x.differences}</td><td>${STATUS_TXT(x.status)}</td></tr>`).join("")
        || '<tr><td colspan="7" class="empty">No countings yet.</td></tr>'}</tbody></table></div>
    ${cnt ? `<div class="card"><div class="card-head"><span>Counting ${cnt.doc_num} · ${cnt.count_date} ${STATUS_TXT(cnt.status)}</span>
        ${cnt.posting ? `<span class="help">Posted ${cnt.posting.doc_date}: ${cnt.posting.gr_entry ? `<a href="#/docs?obj=59&entry=${cnt.posting.gr_entry}">goods receipt</a> ${fmt(cnt.posting.value_in)}` : ""}
          ${cnt.posting.gi_entry ? `<a href="#/docs?obj=60&entry=${cnt.posting.gi_entry}">goods issue</a> ${fmt(cnt.posting.value_out)}` : ""}</span>` : ""}</div>
      <div style="overflow-x:auto"><table class="lines"><thead><tr><th>#</th><th>Item</th><th>Description</th><th>Whs</th><th class="num">In warehouse</th><th>Counted</th>
        <th class="num w-amt">Counted qty</th><th class="num">Difference</th><th>Batches / serial no. (surplus)</th></tr></thead><tbody>
        ${cnt.lines.map((l) => `<tr data-line="${l.line_num}"><td>${l.line_num + 1}</td><td class="mono">${esc(l.item_code)}</td><td>${esc(l.item_name || "")}</td><td>${esc(l.whs_code)}</td>
          <td class="num">${qtyFmt(l.in_whs_qty)}</td><td><input type="checkbox" class="ct-on"${l.counted ? " checked" : ""}${cnt.status !== "O" ? " disabled" : ""}></td>
          <td class="num"><input class="ct-qty" type="number" step="any" min="0" value="${l.counted ? Number(l.count_qty) : ""}"${cnt.status !== "O" ? " disabled" : ""}></td>
          <td class="num ct-diff">${l.counted ? qtyFmt(l.difference) : ""}</td>
          <td>${l.managed ? `<input class="ct-bat" maxlength="500" placeholder="${l.managed === "10000044" ? "LOT:qty@expiry; ..." : "SN-1, SN-2"}" value="${esc((l.batches || []).map((b) => (l.managed === "10000044" ? `${b.number}:${b.quantity}${b.exp_date ? `@${b.exp_date}` : ""}` : b.number)).join(l.managed === "10000044" ? "; " : ", "))}"${cnt.status !== "O" ? " disabled" : ""}>` : ""}</td></tr>`).join("")}</tbody></table></div>
      ${cnt.status === "O" ? `<div class="card-body" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button class="btn secondary" id="ct-save">Save counts</button>
        <span>Posting date <input type="date" id="ct-date" value="${today()}"></span><button class="btn" id="ct-post">Post differences</button>
        <button class="btn ghost" id="ct-close">Close without posting</button></div>` : ""}</div>` : `<div class="card"><div class="card-head">New counting</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(newDefs, {}, "nc")}</div><div class="help">All inventory items of the warehouse (and group) are listed with their current quantity.</div>
      <button class="btn" id="nc-add" style="margin-top:8px">Create counting</button></div></div>`}`;
  if (!cnt) {
    $("#nc-add").onclick = async () => {
      const r = await act(() => post("/inventory/counting", readFields(newDefs, "nc")), (x) => `Counting ${x.doc_num} created`);
      if (r) location.hash = `#/counting?id=${r.doc_entry}`;
    };
    return;
  }
  if (cnt.status !== "O") return;
  $$("tr[data-line]").forEach((tr) => {
    const upd = () => {
      const l = cnt.lines.find((x) => x.line_num === Number(tr.dataset.line));
      const on = $(".ct-on", tr).checked, v = $(".ct-qty", tr).value;
      $(".ct-diff", tr).textContent = on && v !== "" ? qtyFmt(Number(v) - Number(l.in_whs_qty)) : "";
    };
    $(".ct-qty", tr).oninput = () => { if ($(".ct-qty", tr).value !== "") $(".ct-on", tr).checked = true; upd(); };
    $(".ct-on", tr).onchange = upd;
  });
  const counts = () => $$("tr[data-line]").map((tr) => {
    const l = cnt.lines.find((x) => x.line_num === Number(tr.dataset.line));
    const on = $(".ct-on", tr).checked, v = $(".ct-qty", tr).value;
    const bat = $(".ct-bat", tr) ? $(".ct-bat", tr).value.trim() : "";
    const nums = !bat ? null : l.managed === "10000044"
      ? bat.split(/[;\n]/).map((x) => x.trim()).filter(Boolean).map((x) => { const [n, rest = "1"] = x.split(":"); const [q, e] = rest.split("@"); return { number: n.trim(), quantity: Number(q), exp_date: e ? e.trim() : null }; })
      : bat.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean).map((x) => ({ number: x }));
    return { line_num: l.line_num, count_qty: on ? Number(v || 0) : null, batches: nums };
  });
  $("#ct-save").onclick = async () => { if (await act(() => api(`/inventory/counting/${cnt.doc_entry}/counts`, { method: "PUT", body: JSON.stringify(counts()) }), "Counts saved")) views.counting(c); };
  $("#ct-post").onclick = async () => {
    if (!(await act(() => api(`/inventory/counting/${cnt.doc_entry}/counts`, { method: "PUT", body: JSON.stringify(counts()) })))) return;
    if (await act(() => post(`/inventory/counting/${cnt.doc_entry}/post`, { doc_date: $("#ct-date").value }), "Differences posted")) views.counting(c);
  };
  $("#ct-close").onclick = async () => { if (await act(() => post(`/inventory/counting/${cnt.doc_entry}/close`, {}), "Counting closed")) views.counting(c); };
};
