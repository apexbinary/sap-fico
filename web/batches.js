/* Batches and serial numbers: quantities per warehouse (OBTQ / OSRQ) and the history of one number (OITL / ITL1). */
"use strict";

views.batches = async (c) => {
  const q = query(), item = q.get("item") || "", all = q.get("all") === "1", number = q.get("number");
  const managed = (await api("/items")).filter((i) => i.man_btch_num || i.man_ser_num);
  const rows = await api(`/batches?${item ? `item_code=${encodeURIComponent(item)}&` : ""}all=${all}`);
  const hist = item && number ? await api(`/batches/history?item_code=${encodeURIComponent(item)}&number=${encodeURIComponent(number)}`).catch(() => []) : null;
  const defs = [
    { k: "item", label: "Item", type: "select", blank: "All managed items", options: managed.map((i) => [i.item_code, `${i.item_code} — ${i.item_name} (${i.man_btch_num ? "batches" : "serial numbers"})`]) },
    { k: "all", label: "Include numbers without stock", type: "check" },
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Batches and Serial Numbers</h1><div class="sub">Quantity per warehouse, expiry dates and the transactions of each number</div></div></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(defs, { item, all }, "bn")}</div></div></div>
    <div class="card"><table><thead><tr><th>Item</th><th>Type</th><th>Number</th><th>Warehouse</th><th class="num">Quantity</th><th>Expiry date</th><th>Mfg. date</th><th>Admission</th></tr></thead><tbody>
      ${rows.map((r) => `<tr style="cursor:pointer" onclick="location.hash='#/batches?item=${encodeURIComponent(r.item_code)}&number=${encodeURIComponent(r.number)}${all ? "&all=1" : ""}'">
        <td class="mono">${esc(r.item_code)}</td><td>${r.type === "batch" ? "Batch" : "Serial no."}</td><td class="mono">${esc(r.number)}</td><td>${esc(r.whs_code)}</td>
        <td class="num">${qtyFmt(r.quantity)}</td><td>${r.exp_date ? `${r.exp_date}${r.expired ? ' <span class="status X">expired</span>' : ""}` : ""}</td>
        <td>${r.mnf_date || ""}</td><td>${r.in_date || ""}</td></tr>`).join("") || '<tr><td colspan="8" class="empty">No batches or serial numbers.</td></tr>'}</tbody></table></div>
    ${hist ? `<div class="card"><div class="card-head">History of ${esc(number)} (${esc(item)})</div><table><thead><tr><th>Document</th><th>No.</th><th>Date</th><th>Warehouse</th><th class="num">Quantity</th><th></th></tr></thead><tbody>
      ${hist.map((h) => `<tr><td>${esc(DOC_NAMES[h.doc_type] || h.doc_type)}</td><td>${docLink(h.doc_type, h.doc_entry, h.doc_num)}</td><td>${h.doc_date}</td><td>${esc(h.whs_code)}</td>
        <td class="num">${qtyFmt(h.quantity)}</td><td>${h.reversed ? '<span class="status C">canceled</span>' : ""}</td></tr>`).join("") || '<tr><td colspan="6" class="empty">No transactions.</td></tr>'}</tbody></table></div>` : ""}`;
  const go = () => { const f = readFields(defs, "bn"); location.hash = `#/batches?item=${encodeURIComponent(f.item || "")}${f.all ? "&all=1" : ""}`; };
  $("#bn-item").onchange = go; $("#bn-all").onchange = go;
};
