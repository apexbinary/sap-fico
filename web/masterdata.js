/* Master data screens: chart of accounts, business partners, items, warehouses & price lists, administration.
   Every field is declared with its B1 type (see fieldHtml in app.js). */
"use strict";

const reloadAll = async () => { await reloadMasterData(); route(); };
const yesNo = (b) => (b ? "&#10003;" : "");

// ---------- Chart of Accounts ----------
const ACCOUNT_FIELDS = (titles, edit) => [
  ...(edit ? [] : [{ k: "father_num", label: "Under title account", type: "select", req: true, blank: false,
    options: titles.map((t) => [t.acct_code, `${t.acct_code} — ${t.acct_name}`]) },
  { k: "acct_code", label: "G/L account", req: true, max: 15 },
  { k: "postable", label: "Active account (not a title)", type: "check", value: true }]),
  { k: "acct_name", label: "Name", req: true, max: 100 },
  { k: "frgn_name", label: "Foreign name", max: 100 },
  { k: "act_type", label: "Account type", type: "select", options: [["I", "Sales"], ["E", "Expenditure"], ["N", "Other"]], blank: "As title account" },
  { k: "act_curr", label: "Currency", type: "select", blank: false, options: () => [["##", "All currencies"], ...O.currencies()], value: "##" },
  { k: "project", label: "Project", type: "select", options: () => O.projects() },
  { k: "details", label: "Remarks", type: "textarea", max: 254, span: 2 },
  { k: "control", label: "Control account", type: "check" },
  { k: "cash", label: "Cash account", type: "check" },
  { k: "bloc_man_pos", label: "Block manual posting", type: "check" },
  ...(edit ? [{ k: "frozen", label: "Inactive", type: "check" }] : []),
];

views.accounts = async (c) => {
  state.accounts = await api("/accounts");
  const code = query().get("code");
  const byParent = {};
  state.accounts.forEach((a) => (byParent[a.father_num || "root"] ||= []).push(a));
  const rows = [];
  const walk = (parent, depth) => (byParent[parent] || []).forEach((a) => {
    rows.push(`<tr class="${a.postable === "N" ? "tree-title" : ""}" style="cursor:pointer" onclick="location.hash='#/accounts?code=${encodeURIComponent(a.acct_code)}'">
      <td style="padding-left:${14 + depth * 22}px" class="mono">${esc(a.acct_code)}</td>
      <td>${esc(a.acct_name)}${a.control ? ' <span class="chip dr">control</span>' : ""}${a.cash ? ' <span class="chip ok">cash</span>' : ""}${a.bloc_man_pos ? ' <span class="chip no">no manual posting</span>' : ""}${a.frozen ? ' <span class="chip no">inactive</span>' : ""}</td>
      <td>${a.postable === "Y" ? "Active" : "Title"}</td><td>${{ I: "Sales", E: "Expenditure", N: "Other" }[a.act_type] || ""}</td>
      <td>${a.act_curr === "##" ? "All" : esc(a.act_curr)}</td><td class="num">${a.postable === "Y" ? fmt(a.balance) : ""}</td></tr>`);
    walk(a.acct_code, depth + 1);
  });
  walk("root", 0);
  const titles = state.accounts.filter((a) => a.postable === "N");
  const edit = code && state.accounts.find((a) => a.acct_code === code);
  const defs = ACCOUNT_FIELDS(titles, !!edit);
  c.innerHTML = `
    <div class="page-head"><div><h1>Chart of Accounts</h1><div class="sub">Drawers, title accounts and active accounts (OACT) — click an account to change it</div></div></div>
    <div class="card"><div class="card-head">${edit ? `G/L account ${esc(edit.acct_code)} — ${esc(edit.acct_name)} <a class="btn small ghost" href="#/accounts">New account</a>` : "New G/L account"}</div>
      <div class="card-body"><div class="form-grid">${fieldsHtml(defs, edit || {}, "ac")}</div>
      ${edit ? `<div class="help" style="margin-top:8px">Level ${edit.levels} · drawer ${esc(edit.drawer)} · balance ${fmt(edit.balance)}</div>` : ""}
      <button class="btn" id="ac-save" style="margin-top:12px">${edit ? "Update" : "Add"}</button></div></div>
    <div class="card"><table><thead><tr><th>Account</th><th>Name</th><th>Level type</th><th>Account type</th><th>Currency</th><th class="num">Balance</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
  $("#ac-save").onclick = async () => {
    const data = readFields(defs, "ac");
    const r = edit ? await act(() => patch(`/accounts/${encodeURIComponent(edit.acct_code)}`, data), "Account updated")
      : await act(() => post("/accounts", data), "Account created");
    if (r) { await reloadMasterData(); location.hash = `#/accounts?code=${encodeURIComponent(r.acct_code)}`; }
  };
};

// ---------- Business Partner Master Data ----------
const CARD_TYPES = { C: "Customer", S: "Vendor", L: "Lead" };
const PARTNER_GENERAL = [
  { k: "card_f_name", label: "Foreign name", max: 100 },
  { k: "phone1", label: "Tel 1", max: 20 }, { k: "phone2", label: "Tel 2", max: 20 },
  { k: "cellular", label: "Mobile phone", max: 50 }, { k: "fax", label: "Fax", max: 20 },
  { k: "e_mail", label: "E-mail", max: 100 }, { k: "intrnt_site", label: "Web site", max: 100 },
  { k: "slp_code", label: "Sales employee / buyer", type: "select", int: true, blank: false, options: () => O.salesEmployees(), value: -1 },
  { k: "project_cod", label: "BP project", type: "select", options: () => O.projects() },
  { k: "lic_trad_num", label: "Federal tax ID", max: 32 },
  { k: "notes", label: "Remarks", max: 100, span: 2 },
];
const PARTNER_ADDRESS = [
  { k: "address", label: "Street", max: 100 }, { k: "zip_code", label: "Zip code", max: 20 },
  { k: "city", label: "City", max: 100 }, { k: "country", label: "Country", type: "select", options: () => O.countries() },
];
const PARTNER_PAYMENT = (vendor) => [
  { k: "group_num", label: "Payment terms", type: "select", int: true, options: () => O.terms(), value: 1 },
  { k: "list_num", label: "Price list", type: "select", int: true, options: () => O.priceLists(), value: vendor ? 3 : 1 },
  { k: "discount", label: "Total discount %", type: "number", step: "0.01", min: 0, maxv: 99.99, value: 0 },
  { k: "credit_line", label: "Credit limit", type: "number", step: "0.01", min: 0, value: 0 },
  { k: "debt_line", label: "Commitment limit", type: "number", step: "0.01", min: 0, value: 0 },
];
const PARTNER_ACCOUNTING = (vendor) => [
  { k: "vat_group", label: "Tax group", type: "select", options: O.taxes(vendor ? "I" : "O") },
];
const ADDRESS_FIELDS = [
  { k: "adres_type", label: "Type", type: "select", blank: false, options: [["B", "Bill to"], ["S", "Ship to"]] },
  { k: "address", label: "Address ID", req: true, max: 50 },
  { k: "street", label: "Street / PO box", max: 100 }, { k: "block", label: "Block", max: 100 },
  { k: "building", label: "Building / floor / room", max: 100 }, { k: "zip_code", label: "Zip code", max: 20 },
  { k: "city", label: "City", max: 100 }, { k: "county", label: "County", max: 100 },
  { k: "country", label: "Country", type: "select", options: () => O.countries() },
  { k: "state", label: "State", type: "select", options: [] },
  { k: "gst_regn_no", label: "GSTIN", max: 15 },
  { k: "gst_type", label: "GST type", type: "select", options: [["R", "Regular"], ["U", "Unregistered"], ["C", "Composition"], ["E", "SEZ"]] },
  { k: "make_default", label: "Set as default", type: "check" },
];
const CONTACT_FIELDS = [
  { k: "name", label: "Contact ID", req: true, max: 50 }, { k: "title", label: "Title", max: 10 },
  { k: "first_name", label: "First name", max: 50 }, { k: "middle_name", label: "Middle name", max: 50 },
  { k: "last_name", label: "Last name", max: 50 }, { k: "position", label: "Position", max: 90 },
  { k: "address", label: "Address", max: 100 }, { k: "tel1", label: "Tel 1", max: 20 }, { k: "tel2", label: "Tel 2", max: 20 },
  { k: "cellolar", label: "Mobile phone", max: 50 }, { k: "fax", label: "Fax", max: 20 }, { k: "e_mail", label: "E-mail", max: 100 },
  { k: "notes1", label: "Remarks", max: 100, span: 2 }, { k: "active", label: "Active", type: "check", value: true },
];

views.partners = async (c) => {
  const code = query().get("code"), type = query().get("type") || "";
  const [list, groups] = await Promise.all([api(`/partners${type ? `?card_type=${type}` : ""}`), api("/partner-groups")]);
  c.innerHTML = `<div class="page-head"><div><h1>Business Partner Master Data</h1><div class="sub">Customers, vendors and leads (OCRD)</div></div>
      <a class="btn" href="#/partners?new=1">+ New business partner</a></div>
    <div class="toolbar"><div class="field"><label>Type</label><select id="bp-filter">${opt("", "All", type)}${Object.entries(CARD_TYPES).map(([k, v]) => opt(k, v, type)).join("")}</select></div></div>
    <div class="card"><table><thead><tr><th>BP code</th><th>BP name</th><th>Type</th><th>Group</th><th>City</th><th>Sales employee</th><th>Control account</th><th class="num">Account balance</th><th>Status</th></tr></thead>
      <tbody>${list.map((b) => `<tr style="cursor:pointer" onclick="location.hash='#/partners?code=${encodeURIComponent(b.card_code)}'">
        <td class="mono">${esc(b.card_code)}</td><td>${esc(b.card_name)}</td><td>${CARD_TYPES[b.card_type]}</td>
        <td>${esc(nameOf(groups, "group_code", b.group_code, "group_name"))}</td><td>${esc(b.city || "")}</td>
        <td>${esc(nameOf(state.master.sales_employees, "slp_code", b.slp_code, "slp_name"))}</td>
        <td class="mono">${esc(b.deb_pay_acct)}</td><td class="num">${fmt(b.balance)}</td>
        <td>${b.frozen ? '<span class="status X">Inactive</span>' : '<span class="status O">Active</span>'}</td></tr>`).join("")
        || `<tr><td colspan="9" class="empty">No business partners.</td></tr>`}</tbody></table></div>
    <div id="bp-form"></div>`;
  $("#bp-filter").onchange = (e) => (location.hash = `#/partners${e.target.value ? `?type=${e.target.value}` : ""}`);
  if (code) await partnerForm($("#bp-form"), groups, await api(`/partners/${encodeURIComponent(code)}`));
  else if (query().get("new")) await partnerForm($("#bp-form"), groups, null);
};

async function partnerForm(el, groups, b) {
  const isNew = !b;
  let vendor = b ? b.card_type === "S" : false;
  const head = () => [
    { k: "card_code", label: "BP code", req: true, max: 15, ro: !isNew },
    { k: "card_name", label: "BP name", req: true, max: 100 },
    { k: "card_type", label: "Type", type: "select", blank: false, ro: !isNew, options: Object.entries(CARD_TYPES) },
    { k: "group_code", label: "Group", type: "select", int: true, blank: false, ro: !isNew,
      options: groups.filter((g) => g.group_type === (vendor ? "S" : "C")).map((g) => [g.group_code, g.group_name]) },
    { k: "currency", label: "Currency", type: "select", blank: false, ro: !isNew, options: () => [["##", "All currencies"], ...O.currencies()], value: "##" },
    { k: "deb_pay_acct", label: vendor ? "Accounts payable" : "Accounts receivable", type: "select", blank: false, ro: !isNew,
      options: O.accounts((a) => a.control), value: vendor ? "211000" : "114000" },
  ];
  const sections = () => [
    ["General", PARTNER_GENERAL.concat(isNew ? [] : [
      { k: "cntct_prsn", label: "Contact person", type: "select", options: b.contacts.map((x) => [x.name, x.name]) },
      { k: "frozen", label: "Inactive", type: "check" }])],
    ["Address (general)", PARTNER_ADDRESS],
    ["Payment terms", PARTNER_PAYMENT(vendor)],
    ["Accounting", PARTNER_ACCOUNTING(vendor).concat(isNew ? [] : [
      { k: "bill_to_def", label: "Default bill-to", type: "select", options: b.addresses.filter((a) => a.adres_type === "B").map((a) => [a.address, a.address]) },
      { k: "ship_to_def", label: "Default ship-to", type: "select", options: b.addresses.filter((a) => a.adres_type === "S").map((a) => [a.address, a.address]) }])],
    ["Remarks", [{ k: "free_text", label: "Remarks", type: "textarea", max: 254, span: 4 }]],
  ];
  const render = () => {
    const values = b || {};
    el.innerHTML = `<div class="card"><div class="card-head"><span>${isNew ? "New business partner" : `${CARD_TYPES[b.card_type]} ${esc(b.card_code)} — ${esc(b.card_name)}`}</span>
        ${isNew ? "" : `<span class="help">Account balance ${fmt(b.balance)} · Deliveries ${fmt(b.dnotes_bal)} · Orders ${fmt(b.orders_bal)}</span>`}</div>
      <div class="card-body"><div class="form-grid">${fieldsHtml(head(), values, "bp")}</div>
      ${sections().map(([title, defs]) => `<h3 class="section">${title}</h3><div class="form-grid">${fieldsHtml(defs, values, "bp")}</div>`).join("")}
      <button class="btn" id="bp-save" style="margin-top:12px">${isNew ? "Add" : "Update"}</button></div></div>
      ${isNew ? "" : `<div class="grid-2">
        <div class="card"><div class="card-head">Addresses (CRD1)</div><table><thead><tr><th>Type</th><th>Address ID</th><th>Address</th><th>Default</th></tr></thead><tbody>
          ${b.addresses.map((a) => `<tr><td>${a.adres_type === "B" ? "Bill to" : "Ship to"}</td><td>${esc(a.address)}</td>
            <td>${esc([a.street, a.block, a.building, [a.zip_code, a.city].filter(Boolean).join(" "), a.county, a.state, a.country].filter(Boolean).join(", "))}
              ${a.gst_regn_no ? `<div class="help">GSTIN ${esc(a.gst_regn_no)}${a.gst_type ? ` · ${esc({ R: "Regular", U: "Unregistered", C: "Composition", E: "SEZ" }[a.gst_type])}` : ""}</div>` : ""}</td>
            <td>${(a.adres_type === "B" ? b.bill_to_def : b.ship_to_def) === a.address ? "&#10003;" : ""}</td></tr>`).join("") || `<tr><td colspan="4" class="empty">No addresses.</td></tr>`}</tbody></table>
          <div class="card-body"><div class="form-grid">${fieldsHtml(ADDRESS_FIELDS, {}, "ad")}</div><button class="btn secondary small" id="ad-save" style="margin-top:8px">Add / update address</button></div></div>
        <div class="card"><div class="card-head">Contact persons (OCPR)</div><table><thead><tr><th>Contact ID</th><th>Name</th><th>Position</th><th>Tel 1</th><th>Mobile</th><th>E-mail</th><th>Active</th></tr></thead><tbody>
          ${b.contacts.map((p) => `<tr><td>${esc(p.name)}${b.cntct_prsn === p.name ? ' <span class="chip ok">default</span>' : ""}</td><td>${esc([p.title, p.first_name, p.middle_name, p.last_name].filter(Boolean).join(" "))}</td>
            <td>${esc(p.position || "")}</td><td>${esc(p.tel1 || "")}</td><td>${esc(p.cellolar || "")}</td><td>${esc(p.e_mail || "")}</td><td>${yesNo(p.active)}</td></tr>`).join("")
            || `<tr><td colspan="7" class="empty">No contact persons.</td></tr>`}</tbody></table>
          <div class="card-body"><div class="form-grid">${fieldsHtml(CONTACT_FIELDS, {}, "cp")}</div><button class="btn secondary small" id="cp-save" style="margin-top:8px">Add contact person</button></div></div>
      </div>
      <div class="card"><div class="card-head">Open items</div><table><thead><tr><th>Origin</th><th>Posting date</th><th>Due date</th><th>Remarks</th><th class="num">Open</th></tr></thead><tbody>
        ${b.open_items.map((o) => `<tr><td>${docLink(o.trans_type, o.created_by, `${transTypeName(o.trans_type)} ${o.base_ref || o.trans_id}`)}</td>
          <td>${o.ref_date}</td><td>${o.due_date}</td><td>${esc(o.line_memo || "")}</td><td class="num">${fmt(o.open)}</td></tr>`).join("")
          || `<tr><td colspan="5" class="empty">No open items.</td></tr>`}</tbody></table></div>`}`;
    if (isNew) $("#bp-card_type").onchange = () => {  // type decides group, control account, tax group and price list
      const keep = readFields(head(), "bp");
      vendor = $("#bp-card_type").value === "S";
      b = null;
      render();
      $("#bp-card_code").value = keep.card_code || ""; $("#bp-card_name").value = keep.card_name || "";
      $("#bp-card_type").value = vendor ? "S" : keep.card_type;
    };
    $("#bp-save").onclick = async () => {
      const data = Object.assign({}, ...[head(), ...sections().map(([, d]) => d)].map((d) => readFields(d, "bp")));
      const r = isNew ? await act(() => post("/partners", data), (x) => `Business partner ${x.card_code} added`)
        : await act(() => patch(`/partners/${encodeURIComponent(b.card_code)}`, data), "Business partner updated");
      if (r) { state.partners = await api("/partners"); location.hash = `#/partners?code=${encodeURIComponent(r.card_code)}&r=${Date.now()}`; }
    };
    if (!isNew) {
      bindCountryState("ad");
      $("#ad-save").onclick = async () => {
        if (await act(() => post(`/partners/${encodeURIComponent(b.card_code)}/addresses`, readFields(ADDRESS_FIELDS, "ad")), "Address saved")) reloadAll();
      };
      $("#cp-save").onclick = async () => {
        if (await act(() => post(`/partners/${encodeURIComponent(b.card_code)}/contacts`, readFields(CONTACT_FIELDS, "cp")), "Contact person added")) reloadAll();
      };
    }
  };
  render();
}

// ---------- Item Master Data ----------
const ITEM_SECTIONS = (groups, isNew) => [
  ["General", [
    { k: "frgn_name", label: "Foreign name", max: 100 },
    { k: "item_type", label: "Item type", type: "select", blank: false, options: () => O.itemTypes(), value: "I" },
    { k: "itms_grp_cod", label: "Item group", type: "select", int: true, blank: false, ro: !isNew, options: groups.map((g) => [g.itms_grp_cod, g.itms_grp_nam]) },
    { k: "code_bars", label: "Bar code", max: 254 },
    { k: "chapter_id", label: "HSN / SAC code", type: "select", options: () => O.hsn() },
    { k: "firm_code", label: "Manufacturer", type: "select", int: true, blank: false, options: () => O.manufacturers(), value: -1 },
    ...(isNew ? [{ k: "invnt_item", label: "Inventory item", type: "check", value: true }] : []),
    { k: "sell_item", label: "Sales item", type: "check", value: true },
    { k: "prchse_item", label: "Purchase item", type: "check", value: true },
    { k: "man_ser_num", label: "Manage serial numbers", type: "check", ro: true },
    { k: "man_btch_num", label: "Manage batch numbers", type: "check", ro: true },
    ...(isNew ? [] : [{ k: "frozen", label: "Inactive", type: "check" }]),
  ]],
  ["Purchasing data", [
    { k: "card_code", label: "Preferred vendor", type: "select", options: () => O.vendors() },
    { k: "supp_cat_num", label: "Mfr catalog no.", max: 50 },
    { k: "buy_unit_msr", label: "Purchasing UoM name", max: 100 },
    { k: "num_in_buy", label: "Items per purchase unit", type: "number", min: 0, value: 1 },
    { k: "vat_group_pu", label: "Tax code", type: "select", options: O.taxes("I"), value: "ICS18" },
  ]],
  ["Sales data", [
    { k: "sal_unit_msr", label: "Sales UoM name", max: 100 },
    { k: "num_in_sale", label: "Items per sales unit", type: "number", min: 0, value: 1 },
    { k: "vat_gourp_sa", label: "Tax code", type: "select", options: O.taxes("O"), value: "OCS18" },
  ]],
  ["Inventory data", [
    { k: "gl_method", label: "Set G/L accounts by", type: "select", blank: false, options: [["C", "Item group"]], ro: true, value: "C" },
    { k: "invntry_uom", label: "Inventory UoM", max: 20, value: "Each" },
    { k: "dflt_wh", label: "Default warehouse", type: "select", options: () => O.warehouses(), value: "01" },
    { k: "by_wh", label: "Manage inventory by warehouse", type: "check", ro: isNew },
    { k: "min_level", label: "Minimum", type: "number", min: 0, value: 0 },
    { k: "max_level", label: "Maximum", type: "number", min: 0, value: 0 },
    { k: "reorder_qty", label: "Required (reorder)", type: "number", min: 0, value: 0 },
    { k: "eval_system", label: "Valuation method", type: "select", blank: false, options: [["A", "Moving Average"]], ro: true, value: "A" },
    ...(isNew ? [] : [{ k: "avg_price", label: "Item cost", type: "number", ro: true }, { k: "stock_value", label: "Inventory value", type: "number", ro: true },
      { k: "last_pur_prc", label: "Last purchase price", type: "number", ro: true }]),
  ]],
  ["Planning data", [
    { k: "lead_time", label: "Lead time (days)", type: "number", step: 1, min: 0 },
    { k: "min_ordr_qty", label: "Minimum order qty", type: "number", min: 0, value: 0 },
  ]],
  ["Remarks", [{ k: "user_text", label: "Remarks", type: "textarea", max: 254, span: 4 }]],
];

views.items = async (c) => {
  const code = query().get("code");
  const [list, groups] = await Promise.all([api("/items"), api("/item-groups")]);
  const qty = (i, n) => (i.invnt_item ? qtyFmt(n) : "");
  c.innerHTML = `<div class="page-head"><div><h1>Item Master Data</h1><div class="sub">Items (OITM) valued at moving average; G/L accounts by item group</div></div>
      <a class="btn" href="#/items?new=1">+ New item</a></div>
    <div class="card"><table><thead><tr><th>Item No.</th><th>Description</th><th>Type</th><th>Group</th><th>Inv.</th><th>Sales</th><th>Purch.</th><th class="num">In stock</th>
      <th class="num">Committed</th><th class="num">Ordered</th><th class="num">Available</th><th class="num">Item cost</th></tr></thead>
      <tbody>${list.map((i) => `<tr style="cursor:pointer" onclick="location.hash='#/items?code=${encodeURIComponent(i.item_code)}'">
        <td class="mono">${esc(i.item_code)}</td><td>${esc(i.item_name)}</td><td>${esc(nameOf(state.master.item_types, "code", i.item_type, "name"))}</td>
        <td>${esc(nameOf(groups, "itms_grp_cod", i.itms_grp_cod, "itms_grp_nam"))}</td>
        <td>${yesNo(i.invnt_item)}</td><td>${yesNo(i.sell_item)}</td><td>${yesNo(i.prchse_item)}</td>
        <td class="num">${qty(i, i.on_hand)}</td><td class="num">${qty(i, i.is_commited)}</td><td class="num">${qty(i, i.on_order)}</td>
        <td class="num">${qty(i, i.available)}</td><td class="num">${i.invnt_item ? fmt(i.avg_price) : ""}</td></tr>`).join("")
        || `<tr><td colspan="12" class="empty">No items.</td></tr>`}</tbody></table></div>
    <div id="it-form"></div>`;
  if (code) await itemForm($("#it-form"), groups, await api(`/items/${encodeURIComponent(code)}`));
  else if (query().get("new")) await itemForm($("#it-form"), groups, null);
};

async function itemForm(el, groups, i) {
  const isNew = !i;
  const head = [{ k: "item_code", label: "Item No.", req: true, max: 50, ro: !isNew }, { k: "item_name", label: "Description", req: true, max: 100, span: 2 }];
  const sections = ITEM_SECTIONS(groups, isNew);
  const g = i ? groups.find((x) => x.itms_grp_cod === i.itms_grp_cod) || {} : {};
  const basePrices = state.priceLists.filter((p) => p.base_num === p.list_num);
  el.innerHTML = `<div class="card"><div class="card-head">${isNew ? "New item" : `${esc(i.item_code)} — ${esc(i.item_name)}`}</div>
    <div class="card-body"><div class="form-grid">${fieldsHtml(head, i || {}, "it")}</div>
      ${sections.map(([title, defs]) => `<h3 class="section">${title}</h3><div class="form-grid">${fieldsHtml(defs, i || {}, "it")}</div>`).join("")}
      ${isNew ? `<h3 class="section">Prices</h3><div class="form-grid">${basePrices.map((p) => fieldHtml({ k: `price_${p.list_num}`, label: p.list_name, type: "number", step: "0.01", min: 0 }, "", "it")).join("")}</div>` : ""}
      <button class="btn" id="it-save" style="margin-top:12px">${isNew ? "Add" : "Update"}</button></div></div>
    ${isNew ? "" : `<div class="grid-2">
      <div class="card"><div class="card-head">Stock per warehouse (OITW)</div><div style="overflow-x:auto"><table><thead><tr><th>Whs</th><th class="num">In stock</th><th class="num">Committed</th><th class="num">Ordered</th><th class="num">Available</th>
        <th class="num">Min.</th><th class="num">Max.</th><th>Locked</th><th></th></tr></thead><tbody>
        ${i.warehouses.map((w) => `<tr><td>${esc(w.whs_code)} — ${esc(nameOf(state.warehouses, "whs_code", w.whs_code, "whs_name"))}</td>
          <td class="num">${qtyFmt(w.on_hand)}</td><td class="num">${qtyFmt(w.is_commited)}</td><td class="num">${qtyFmt(w.on_order)}</td><td class="num">${qtyFmt(w.available)}</td>
          <td class="num"><input class="ow-min" data-w="${esc(w.whs_code)}" type="number" min="0" step="any" value="${Number(w.min_stock)}" style="width:70px"></td>
          <td class="num"><input class="ow-max" data-w="${esc(w.whs_code)}" type="number" min="0" step="any" value="${Number(w.max_stock)}" style="width:70px"></td>
          <td><input class="ow-lock" data-w="${esc(w.whs_code)}" type="checkbox"${w.locked ? " checked" : ""}></td>
          <td><button class="btn small ghost ow-save" data-w="${esc(w.whs_code)}">Save</button></td></tr>`).join("")
          || `<tr><td colspan="9" class="empty">Not an inventory item.</td></tr>`}</tbody></table></div></div>
      <div class="card"><div class="card-head">Prices (ITM1)</div><table><thead><tr><th>Price list</th><th class="num">Unit price</th><th></th></tr></thead><tbody>
        ${i.prices.map((p) => `<tr><td>${esc(p.list_name)}${p.own ? "" : ' <span class="help">(from base list)</span>'}</td>
          <td class="num"><input class="pr-val" data-list="${p.list_num}" type="number" step="0.01" min="0" value="${Number(p.price).toFixed(2)}" style="width:110px"></td>
          <td><button class="btn small ghost pr-save" data-list="${p.list_num}">Save</button></td></tr>`).join("")}</tbody></table>
        <div class="card-body help">G/L accounts by item group ${esc(g.itms_grp_nam || "")}: inventory ${esc(g.bal_invnt_ac || "")} · COGS ${esc(g.sale_cost_ac || "")} ·
          revenue ${esc(g.revenues_ac || "")} · expense ${esc(g.expenses_ac || "")} · price difference ${esc(g.price_dif_ac || "")}</div></div>
    </div>
    <div class="card"><div class="card-body"><a class="btn small ghost" href="#/inventory-audit?item=${encodeURIComponent(i.item_code)}">Inventory audit report for this item &#8599;</a></div></div>`}`;
  $("#it-save").onclick = async () => {
    const data = Object.assign({}, readFields(head, "it"), ...sections.map(([, d]) => readFields(d, "it")));
    if (isNew) {
      data.prices = {};
      basePrices.forEach((p) => { const v = $(`#it-price_${p.list_num}`).value; if (v !== "") data.prices[p.list_num] = Number(v); });
    }
    const r = isNew ? await act(() => post("/items", data), (x) => `Item ${x.item_code} added`)
      : await act(() => patch(`/items/${encodeURIComponent(i.item_code)}`, data), "Item updated");
    if (r) location.hash = `#/items?code=${encodeURIComponent(r.item_code)}&r=${Date.now()}`;
  };
  if (isNew) return;
  $$(".pr-save").forEach((btn) => (btn.onclick = async () => {
    const val = Number($(`.pr-val[data-list="${btn.dataset.list}"]`).value);
    if (await act(() => api(`/items/${encodeURIComponent(i.item_code)}/prices/${btn.dataset.list}`, { method: "PUT", body: JSON.stringify({ price: val }) }), "Price saved")) route();
  }));
  $$(".ow-save").forEach((btn) => (btn.onclick = async () => {
    const w = btn.dataset.w, sel = (cls) => $(`.${cls}[data-w="${w}"]`);
    await act(() => patch(`/items/${encodeURIComponent(i.item_code)}/warehouses/${encodeURIComponent(w)}`, {
      min_stock: Number(sel("ow-min").value || 0), max_stock: Number(sel("ow-max").value || 0), locked: sel("ow-lock").checked }), "Warehouse data saved");
  }));
}

// ---------- Warehouses & Price Lists ----------
const WAREHOUSE_FIELDS = [
  { k: "whs_code", label: "Warehouse code", req: true, max: 8 }, { k: "whs_name", label: "Warehouse name", req: true, max: 100 },
  { k: "street", label: "Street / PO box", max: 100 }, { k: "block", label: "Block", max: 100 },
  { k: "building", label: "Building / floor / room", max: 100 }, { k: "zip_code", label: "Zip code", max: 20 },
  { k: "city", label: "City", max: 100 }, { k: "county", label: "County", max: 100 },
  { k: "country", label: "Country", type: "select", options: () => O.countries(), value: "IN" },
  { k: "state", label: "State", type: "select", options: [] },
  { k: "drop_ship", label: "Drop-ship", type: "check" }, { k: "nettable", label: "Nettable", type: "check", value: true },
];
const PRICE_LIST_FIELDS = [
  { k: "list_name", label: "Price list name", req: true, max: 32 },
  { k: "base_num", label: "Base price list", type: "select", int: true, blank: "(own prices)", options: () => state.priceLists.map((p) => [p.list_num, p.list_name]) },
  { k: "factor", label: "Factor", type: "number", min: 0, value: 1 },
  { k: "prim_curr", label: "Primary currency", type: "select", options: () => O.currencies(), value: "EUR" },
  { k: "active", label: "Active", type: "check", value: true },
];

views.warehouses = async (c) => {
  await reloadMasterData();
  const whs = state.warehouses, plists = state.priceLists;
  c.innerHTML = `<div class="page-head"><div><h1>Warehouses &amp; Price Lists</h1><div class="sub">Warehouses (OWHS) and price lists (OPLN)</div></div></div>
    <div class="card"><div class="card-head">Warehouses</div><div style="overflow-x:auto"><table><thead><tr><th>Code</th><th>Name</th><th>Address</th><th>Country</th><th>Drop-ship</th><th>Nettable</th></tr></thead><tbody>
      ${whs.map((w) => `<tr><td class="mono">${esc(w.whs_code)}</td><td>${esc(w.whs_name)}</td>
        <td>${esc([w.street, w.block, w.building, [w.zip_code, w.city].filter(Boolean).join(" "), w.county, w.state].filter(Boolean).join(", "))}</td>
        <td>${esc(nameOf(state.master.countries, "code", w.country, "name"))}</td><td>${yesNo(w.drop_ship)}</td><td>${yesNo(w.nettable)}</td></tr>`).join("")}</tbody></table></div>
      <div class="card-body"><h3 class="section">New warehouse</h3><div class="form-grid">${fieldsHtml(WAREHOUSE_FIELDS, {}, "wh")}</div>
        <button class="btn secondary" id="wh-add" style="margin-top:8px">Add warehouse</button></div></div>
    <div class="card"><div class="card-head">Price lists</div><table><thead><tr><th>No.</th><th>Name</th><th>Base price list</th><th class="num">Factor</th><th>Currency</th><th>Active</th></tr></thead><tbody>
      ${plists.map((p) => `<tr><td>${p.list_num}</td><td>${esc(p.list_name)}</td>
        <td>${p.base_num === p.list_num ? '<span class="help">own prices</span>' : esc(nameOf(plists, "list_num", p.base_num, "list_name"))}</td>
        <td class="num">${Number(p.factor)}</td><td>${esc(p.prim_curr || "")}</td>
        <td><input type="checkbox" class="pl-active" data-n="${p.list_num}"${p.active ? " checked" : ""}></td></tr>`).join("")}</tbody></table>
      <div class="card-body"><h3 class="section">New price list</h3><div class="form-grid">${fieldsHtml(PRICE_LIST_FIELDS, {}, "pl")}</div>
        <button class="btn secondary" id="pl-add" style="margin-top:8px">Add price list</button></div></div>`;
  bindCountryState("wh");
  $("#wh-add").onclick = async () => { if (await act(() => post("/warehouses", readFields(WAREHOUSE_FIELDS, "wh")), "Warehouse added")) reloadAll(); };
  $("#pl-add").onclick = async () => { if (await act(() => post("/price-lists", readFields(PRICE_LIST_FIELDS, "pl")), "Price list added")) reloadAll(); };
  $$(".pl-active").forEach((cb) => (cb.onchange = async () => {
    if (await act(() => patch(`/price-lists/${cb.dataset.n}`, { active: cb.checked }), "Price list updated")) reloadAll();
  }));
};

// ---------- Administration ----------
const COMPANY_FIELDS = [
  { k: "company_name", label: "Company name", req: true, max: 100, span: 2 },
  { k: "address", label: "Address", max: 254, span: 2 },
  { k: "country", label: "Country", type: "select", options: () => O.countries() },
  { k: "state", label: "State", type: "select", options: [] },
  { k: "tax_id", label: "Federal tax ID / GSTIN", max: 32 },
  { k: "phone", label: "Telephone 1", max: 20 }, { k: "phone2", label: "Telephone 2", max: 20 },
  { k: "fax", label: "Fax", max: 20 }, { k: "e_mail", label: "E-mail", max: 100 },
  { k: "manager", label: "Manager", max: 100 },
  { k: "main_curncy", label: "Local currency", type: "select", options: () => O.currencies(), ro: true },
  { k: "sys_curncy", label: "System currency", type: "select", options: () => O.currencies(), ro: true },
];
const TERMS_FIELDS = [
  { k: "name", label: "Payment terms code", req: true, max: 100 },
  { k: "bsline_date", label: "Due date based on", type: "select", blank: false, options: [["P", "Posting date"], ["T", "Document date"], ["S", "System date"]] },
  { k: "pay_du_month", label: "Start from", type: "select", blank: false, options: [["N", "—"], ["S", "Month start"], ["H", "Half month"], ["E", "Month end"]] },
  { k: "extra_month", label: "+ Months", type: "number", step: 1, min: 0, value: 0 },
  { k: "extra_days", label: "+ Days", type: "number", step: 1, min: 0, value: 0 },
  { k: "tol_days", label: "Tolerance days", type: "number", step: 1, min: 0, value: 0 },
  { k: "discount_pct", label: "Total discount %", type: "number", step: "0.01", min: 0, maxv: 99.99, value: 0 },
  { k: "list_num", label: "Price list", type: "select", int: true, options: () => O.priceLists() },
  { k: "cred_limit", label: "Max. credit", type: "number", step: "0.01", min: 0, value: 0 },
  { k: "oblig_limit", label: "Commitment limit", type: "number", step: "0.01", min: 0, value: 0 },
];
const SLP_FIELDS = [
  { k: "slp_name", label: "Sales employee name", req: true, max: 155 }, { k: "commission", label: "Commission %", type: "number", step: "0.01", min: 0, maxv: 100, value: 0 },
  { k: "telephone", label: "Telephone", max: 20 }, { k: "email", label: "E-mail", max: 100 },
  { k: "memo", label: "Remarks", max: 50 }, { k: "active", label: "Active", type: "check", value: true },
];
const PROJECT_FIELDS = [
  { k: "prj_code", label: "Project code", req: true, max: 20 }, { k: "prj_name", label: "Project name", req: true, max: 100 },
  { k: "valid_from", label: "Valid from", type: "date" }, { k: "valid_to", label: "Valid to", type: "date" },
  { k: "active", label: "Active", type: "check", value: true },
];

views.setup = async (c) => {
  await reloadMasterData();
  state.company = await api("/admin/company");
  const [periods, rates] = await Promise.all([api("/admin/periods"), api(`/admin/exchange-rates?rate_date=${today()}`)]);
  const L = state.lookups, M = state.master;
  const termsId = query().get("terms");
  const termsEdit = termsId && L.payment_terms.find((t) => String(t.group_num) === termsId);
  const year = query().get("year") || String(new Date().getFullYear());
  c.innerHTML = `<div class="page-head"><div><h1>Administration</h1><div class="sub">Company details, currencies, tax groups, payment terms, posting periods, sales employees, projects, manufacturers, transaction codes</div></div></div>
    <div class="card"><div class="card-head">Company details (OADM)</div><div class="card-body"><div class="form-grid">${fieldsHtml(COMPANY_FIELDS, state.company, "co")}</div>
      <button class="btn secondary" id="co-save" style="margin-top:8px">Update</button></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Exchange rates today (ORTT)</div><table><tbody>
        ${rates.map((r) => `<tr><td>${esc(r.currency)}</td><td class="num">${Number(r.rate).toFixed(4)} ${esc(state.company.main_curncy)}</td></tr>`).join("") || `<tr><td class="empty">No rates for today.</td></tr>`}</tbody></table>
        <div class="card-body"><div class="form-grid">${fieldsHtml([
          { k: "currency", label: "Currency", type: "select", blank: false, options: () => O.currencies().filter(([v]) => v !== state.company.main_curncy) },
          { k: "rate_date", label: "Date", type: "date", value: today() }, { k: "rate", label: "Rate", type: "number", step: "0.0001", min: 0 }], {}, "rt")}</div>
          <button class="btn secondary" id="rt-save" style="margin-top:8px">Save rate</button></div></div>
      <div class="card"><div class="card-head">Tax codes (OVTG + components STC1) <a class="btn small ghost" href="#/tax-setup">Tax setup &#8599;</a></div>
        <div style="max-height:320px;overflow:auto"><table><thead><tr><th>Code</th><th>Name</th><th>Category</th><th class="num">Rate</th><th>Components</th></tr></thead><tbody>
        ${L.tax_groups.map((t) => `<tr><td class="mono">${esc(t.code)}</td><td>${esc(t.name)}</td><td>${t.category === "O" ? "Output" : "Input"}</td><td class="num">${Number(t.rate)}%</td>
          <td>${t.components.length ? t.components.map((x) => `${esc(x.sta_code)} ${Number(x.rate)}%`).join(" + ") : `<span class="mono">${esc(t.account)}</span>`}</td></tr>`).join("")}</tbody></table></div></div>
    </div>
    <div class="card"><div class="card-head">Payment terms (OCTG)</div><div style="overflow-x:auto"><table><thead><tr><th>Code</th><th>Due date based on</th><th>Start from</th><th class="num">Months</th><th class="num">Days</th>
      <th class="num">Tolerance</th><th class="num">Discount %</th><th>Price list</th><th class="num">Max. credit</th><th class="num">Commitment</th></tr></thead><tbody>
      ${L.payment_terms.map((p) => `<tr style="cursor:pointer" onclick="location.hash='#/setup?terms=${p.group_num}'"><td>${esc(p.name)}</td>
        <td>${{ P: "Posting date", T: "Document date", S: "System date" }[p.bsline_date]}</td><td>${{ N: "—", S: "Month start", H: "Half month", E: "Month end" }[p.pay_du_month]}</td>
        <td class="num">${p.extra_month}</td><td class="num">${p.extra_days}</td><td class="num">${p.tol_days}</td><td class="num">${Number(p.discount_pct)}</td>
        <td>${esc(nameOf(state.priceLists, "list_num", p.list_num, "list_name"))}</td><td class="num">${fmt(p.cred_limit)}</td><td class="num">${fmt(p.oblig_limit)}</td></tr>`).join("")}</tbody></table></div>
      <div class="card-body"><h3 class="section">${termsEdit ? `Change ${esc(termsEdit.name)} <a class="btn small ghost" href="#/setup">New</a>` : "New payment terms"}</h3>
        <div class="form-grid">${fieldsHtml(TERMS_FIELDS, termsEdit || {}, "pt")}</div><button class="btn secondary" id="pt-save" style="margin-top:8px">${termsEdit ? "Update" : "Add"}</button></div></div>
    <div class="card"><div class="card-head">Posting periods (OFPR)
      <select id="pe-year">${[...new Set(periods.map((p) => p.category))].map((y) => opt(y, y, year)).join("")}</select></div>
      <div style="overflow-x:auto"><table><thead><tr><th>Period code</th><th>Name</th><th>Posting date from</th><th>to</th><th>Due date from</th><th>to</th><th>Document date from</th><th>to</th><th>Status</th><th></th></tr></thead><tbody>
      ${periods.filter((p) => p.category === year).map((p) => `<tr><td class="mono">${esc(p.code)}</td><td>${esc(p.name)}</td><td>${p.from}</td><td>${p.to}</td>
        <td>${p.due_from || ""}</td><td>${p.due_to || ""}</td><td>${p.doc_from || ""}</td><td>${p.doc_to || ""}</td>
        <td><span class="status ${p.status === "N" ? "O" : "C"}">${{ N: "Unlocked", Y: "Locked", C: "Closing period" }[p.status]}</span></td>
        <td><select class="pe-status" data-id="${p.abs_entry}">${[["N", "Unlocked"], ["C", "Closing period"], ["Y", "Locked"]].map(([v, l]) => opt(v, l, p.status)).join("")}</select></td></tr>`).join("")}</tbody></table></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Sales employees / buyers (OSLP)</div><table><thead><tr><th>Name</th><th class="num">Commission %</th><th>Telephone</th><th>E-mail</th><th>Active</th></tr></thead><tbody>
        ${M.sales_employees.map((e) => `<tr><td>${esc(e.slp_name)}</td><td class="num">${Number(e.commission)}</td><td>${esc(e.telephone || "")}</td><td>${esc(e.email || "")}</td><td>${yesNo(e.active)}</td></tr>`).join("")}</tbody></table>
        <div class="card-body"><div class="form-grid">${fieldsHtml(SLP_FIELDS, {}, "sl")}</div><button class="btn secondary small" id="sl-add" style="margin-top:8px">Add</button></div></div>
      <div class="card"><div class="card-head">Projects (OPRJ)</div><table><thead><tr><th>Code</th><th>Name</th><th>Valid from</th><th>Valid to</th><th>Active</th></tr></thead><tbody>
        ${M.projects.map((p) => `<tr><td class="mono">${esc(p.prj_code)}</td><td>${esc(p.prj_name)}</td><td>${p.valid_from || ""}</td><td>${p.valid_to || ""}</td><td>${yesNo(p.active)}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">No projects.</td></tr>`}</tbody></table>
        <div class="card-body"><div class="form-grid">${fieldsHtml(PROJECT_FIELDS, {}, "pj")}</div><button class="btn secondary small" id="pj-add" style="margin-top:8px">Add</button></div></div>
      <div class="card"><div class="card-head">Manufacturers (OMRC)</div><table><tbody>
        ${M.manufacturers.map((m) => `<tr><td>${esc(m.firm_name)}</td></tr>`).join("")}</tbody></table>
        <div class="card-body"><div class="form-grid">${fieldsHtml([{ k: "firm_name", label: "Manufacturer name", req: true, max: 30 }], {}, "mf")}</div><button class="btn secondary small" id="mf-add" style="margin-top:8px">Add</button></div></div>
      <div class="card"><div class="card-head">Transaction codes (OTRC)</div><table><tbody>
        ${M.transaction_codes.map((t) => `<tr><td class="mono">${esc(t.trns_code)}</td><td>${esc(t.trns_cod_dsc)}</td></tr>`).join("")}</tbody></table>
        <div class="card-body"><div class="form-grid">${fieldsHtml([{ k: "trns_code", label: "Code", req: true, max: 4 }, { k: "trns_cod_dsc", label: "Description", req: true, max: 30 }], {}, "tc")}</div>
          <button class="btn secondary small" id="tc-add" style="margin-top:8px">Add</button></div></div>
    </div>`;
  const save = (sel, fn, msg) => ($(sel).onclick = async () => { if (await act(fn, msg)) reloadAll(); });
  bindCountryState("co");
  $("#co-state").value = state.company.state || "";
  save("#co-save", () => patch("/admin/company", readFields(COMPANY_FIELDS, "co")), "Company details updated");
  save("#rt-save", () => post("/admin/exchange-rates", readFields([{ k: "currency", type: "select" }, { k: "rate_date", type: "date" }, { k: "rate", type: "number" }], "rt")), "Rate saved");
  save("#pt-save", () => (termsEdit ? api(`/admin/payment-terms/${termsEdit.group_num}`, { method: "PUT", body: JSON.stringify(readFields(TERMS_FIELDS, "pt")) })
    : post("/admin/payment-terms", readFields(TERMS_FIELDS, "pt"))), "Payment terms saved");
  save("#sl-add", () => post("/sales-employees", readFields(SLP_FIELDS, "sl")), "Sales employee added");
  save("#pj-add", () => post("/projects", readFields(PROJECT_FIELDS, "pj")), "Project added");
  save("#mf-add", () => post("/manufacturers", readFields([{ k: "firm_name" }], "mf")), "Manufacturer added");
  save("#tc-add", () => post("/transaction-codes", readFields([{ k: "trns_code" }, { k: "trns_cod_dsc" }], "tc")), "Transaction code added");
  $("#pe-year").onchange = (e) => (location.hash = `#/setup?year=${e.target.value}`);
  $$(".pe-status").forEach((s) => (s.onchange = async () => {
    if (await act(() => api(`/admin/periods/${s.dataset.id}`, { method: "PUT", body: JSON.stringify({ status: s.value }) }), "Period updated")) route();
  }));
};
