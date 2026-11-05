/* Opening balances (Administration -> Opening Balances): G/L accounts, business partners (open items) and
   items (opening stock), each against the opening balance account. */
"use strict";

const OB_KINDS = { accounts: "G/L accounts", partners: "Business partners", items: "Items (opening stock)" };

views["opening-balances"] = async (c) => {
  const kind = query().get("kind") || "accounts";
  const [data, items] = await Promise.all([api("/opening-balances"), kind === "items" ? api("/items") : Promise.resolve([])]);
  const acctOpts = O.accounts((a) => !a.control);
  const bpOpts = state.partners.filter((b) => b.card_type !== "L").map((b) => [b.card_code, `${b.card_code} — ${b.card_name}`]);
  const itemOpts = items.filter((i) => i.invnt_item).map((i) => [i.item_code, `${i.item_code} — ${i.item_name}`]);
  const rowDefs = {
    accounts: [{ k: "account", label: "Account", type: "select", options: acctOpts },
      { k: "debit", label: "Debit", type: "number", step: "0.01", min: 0 }, { k: "credit", label: "Credit", type: "number", step: "0.01", min: 0 }],
    partners: [{ k: "card_code", label: "Business partner", type: "select", options: bpOpts },
      { k: "debit", label: "Debit (customer owes)", type: "number", step: "0.01", min: 0 }, { k: "credit", label: "Credit (we owe)", type: "number", step: "0.01", min: 0 },
      { k: "due_date", label: "Due date", type: "date" }, { k: "ref", label: "Reference (invoice no.)", max: 50 }],
    items: [{ k: "item_code", label: "Item", type: "select", options: itemOpts },
      { k: "whs_code", label: "Warehouse", type: "select", options: () => O.warehouses() },
      { k: "quantity", label: "Quantity", type: "number", step: "0.001", min: 0 }, { k: "price", label: "Cost per unit", type: "number", step: "0.01", min: 0 }],
  }[kind];
  const head = [{ k: "ref_date", label: "Posting date", type: "date", req: true, value: today() }, { k: "memo", label: "Remarks", max: 50, span: 2 }];
  const diff = Number(data.difference);
  c.innerHTML = `<div class="page-head"><div><h1>Opening Balances</h1><div class="sub">Balances when starting with the system, against the opening balance account
      ${esc(data.opening_account || "")} ${esc(data.opening_account_name || "")}</div></div></div>
    <div class="tiles"><div class="tile"><div class="label">Left on the opening balance account</div><div class="value">${fmt(diff)}</div>
      <div class="foot">${diff ? "not balanced yet: assets, liabilities and capital differ" : "balanced"}</div></div></div>
    <div class="card"><div class="card-body"><div class="tabs">${Object.entries(OB_KINDS).map(([k, l]) =>
      `<a class="tab${k === kind ? " active" : ""}" href="#/opening-balances?kind=${k}">${l}</a>`).join("")}</div>
      <div class="form-grid" style="margin-top:10px">${fieldsHtml(head, {}, "ob")}</div>
      <table class="lines" style="margin-top:8px"><thead><tr>${rowDefs.map((d) => `<th>${esc(d.label)}</th>`).join("")}<th></th></tr></thead><tbody id="ob-rows"></tbody></table>
      <div style="display:flex;gap:8px;margin-top:8px"><button class="btn ghost small" id="ob-add">+ Row</button>
        <b style="margin-left:auto" id="ob-sum"></b><button class="btn" id="ob-post">Post</button></div>
      <p class="help">${kind === "accounts" ? "Balance sheet accounts (assets, liabilities, capital); control accounts are filled by the business partner opening balances."
        : kind === "partners" ? "One open item per row (paid later like an invoice); enter each unpaid invoice with its due date, or one balance per partner."
        : "Stock at cost per warehouse (moving average); batch / serial items need their numbers (enter them with a goods receipt instead)."}</p></div></div>
    <div class="card"><div class="card-head">Posted opening balances</div><table><thead><tr><th>Kind</th><th>No.</th><th>Date</th><th>Remarks</th><th class="num">Rows</th><th class="num">Total</th><th>Status</th><th></th></tr></thead><tbody>
      ${data.entries.map((e) => `<tr><td>${OB_KINDS[e.kind]}</td><td>${e.kind === "items" ? `<a href="#/docs?obj=59&entry=${e.doc_entry}">${e.number}</a>` : `<a href="#/journal?id=${e.trans_id}">${e.number}</a>`}</td>
        <td>${e.ref_date}</td><td>${esc(e.memo || "")}</td><td class="num">${e.rows}</td><td class="num">${fmt(e.total)}</td>
        <td>${e.canceled ? '<span class="status C">canceled</span>' : '<span class="status O">posted</span>'}</td>
        <td>${e.canceled ? "" : `<button class="btn small ghost ob-cancel" data-kind="${e.kind}" data-key="${e.kind === "items" ? e.doc_entry : e.trans_id}">Cancel</button>`}</td></tr>`).join("")
        || '<tr><td colspan="8" class="empty">No opening balances yet.</td></tr>'}</tbody></table></div>`;
  let n = 0;
  const sum = () => {
    if (kind === "items") {
      $("#ob-sum").textContent = `Stock value ${fmt($$("#ob-rows tr").reduce((s, tr) => s + Number($(".obr-quantity", tr).value || 0) * Number($(".obr-price", tr).value || 0), 0))}`;
    } else {
      const d = $$("#ob-rows tr").reduce((s, tr) => s + Number($(".obr-debit", tr).value || 0) - Number($(".obr-credit", tr).value || 0), 0);
      $("#ob-sum").textContent = `Debit - credit ${fmt(d)} (offset on ${data.opening_account || "the opening balance account"})`;
    }
  };
  const addRow = () => {
    const p = `obr${n++}`;
    const tr = document.createElement("tr");
    tr.innerHTML = rowDefs.map((d) => `<td>${fieldHtml({ ...d, label: "" }, d.value, p).replace(`id="${p}-${d.k}"`, `id="${p}-${d.k}" class="obr-${d.k}"`)}</td>`).join("")
      + '<td><button class="btn ghost small ob-del">✕</button></td>';
    tr.dataset.p = p;
    $("#ob-rows").appendChild(tr);
    $(".ob-del", tr).onclick = () => { tr.remove(); sum(); };
    $$("input", tr).forEach((i) => (i.oninput = sum));
  };
  addRow();
  $("#ob-add").onclick = addRow;
  $("#ob-post").onclick = async () => {
    const rows = $$("#ob-rows tr").map((tr) => readFields(rowDefs, tr.dataset.p)).filter((r) => Object.values(r).some((v) => v !== null && v !== ""));
    const body = { ...readFields(head, "ob"), rows };
    const r = await act(() => post(`/opening-balances/${kind}`, body), (x) => `${OB_KINDS[kind]}: ${kind === "items" ? "goods receipt" : "journal entry"} ${x.number} posted`);
    if (r) { state.partners = await api("/partners"); location.hash = `#/opening-balances?kind=${kind}&r=${Date.now()}`; }
  };
  $$(".ob-cancel").forEach((b) => (b.onclick = async () => {
    if (!confirm("Cancel these opening balances? The journal entry is reversed (goods receipt: canceled).")) return;
    if (await act(() => post(`/opening-balances/${b.dataset.kind}/${b.dataset.key}/cancel`, {}), "Opening balances canceled")) location.hash = `#/opening-balances?kind=${kind}&r=${Date.now()}`;
  }));
};
