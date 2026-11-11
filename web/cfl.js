/* Choose from list (B1 "CFL"): every dropdown of business partners, items, G/L accounts and warehouses opens a
   window with search, filters and paging instead of the plain list; the golden arrow next to the field opens
   the master record of the selected value. The window offers exactly the options the field allows (the select's
   own options), enriched with the master data, so field restrictions (only customers, only active accounts ...)
   are kept. Fields are recognised by id / class (card_code, item_code, ..._acct, whs_code, l-item, je-acct ...)
   or by data-cfl="bp|item|account|whs"; selects opt out with data-cfl="none". */
"use strict";

const CFL_PAGE = 15;
const CFL_KINDS = {
  bp: {
    title: "Business Partners", noun: "business partner", master: (c) => `#/partners?code=${encodeURIComponent(c)}`, list: "#/partners",
    load: () => api("/partners"), key: "card_code",
    cols: [["card_code", "Code"], ["card_name", "Name"], ["card_type", "Type", (v) => ({ C: "Customer", S: "Vendor", L: "Lead" })[v] || v],
      ["city", "City"], ["currency", "Currency"], ["balance", "Balance", (v) => fmt(v), 1]],
    filters: (rows) => [["card_type", "Type", [["C", "Customer"], ["S", "Vendor"], ["L", "Lead"]]],
      ["group_code", "Group", [...new Set(rows.map((r) => r.group_code))].filter((v) => v != null).map((g) => [g, nameOf(state.partnerGroups || [], "group_code", g, "group_name") || g])],
      ["city", "City", [...new Set(rows.map((r) => r.city).filter(Boolean))].sort().map((v) => [v, v])]],
  },
  item: {
    title: "Items", noun: "item", master: (c) => `#/items?code=${encodeURIComponent(c)}`, list: "#/items",
    load: () => api("/items"), key: "item_code",
    cols: [["item_code", "Code"], ["item_name", "Description"], ["itms_grp_cod", "Group", (v) => nameOf(state.itemGroups || [], "itms_grp_cod", v, "itms_grp_nam") || v],
      ["on_hand", "In stock", (v, r) => (r.invnt_item ? qtyFmt(v) : "—"), 1], ["is_commited", "Committed", (v, r) => (r.invnt_item ? qtyFmt(v) : ""), 1],
      ["on_order", "Ordered", (v, r) => (r.invnt_item ? qtyFmt(v) : ""), 1], ["available", "Available", (v, r) => (r.invnt_item ? qtyFmt(v) : ""), 1],
      ["invntry_uom", "UoM"]],
    filters: (rows) => [["itms_grp_cod", "Group", [...new Set(rows.map((r) => r.itms_grp_cod))].filter((v) => v != null).map((g) => [g, nameOf(state.itemGroups || [], "itms_grp_cod", g, "itms_grp_nam") || g])],
      ["invnt_item", "Inventory item", [["true", "Yes"], ["false", "No"]]], ["_stock", "Stock", [["in", "In stock"], ["none", "No stock"]]]],
  },
  account: {
    title: "G/L Accounts", noun: "account", master: (c) => (c.startsWith("BP:") ? CFL_KINDS.bp.master(c.slice(3)) : `#/accounts?code=${encodeURIComponent(c)}`), list: "#/accounts",
    load: async () => [...state.accounts, ...state.partners.map((b) => ({ acct_code: `BP:${b.card_code}`, acct_name: b.card_name, _bp: b.card_type }))], key: "acct_code",
    cols: [["acct_code", "Code", (v) => esc(v.replace(/^BP:/, ""))], ["acct_name", "Name"],
      ["group_mask", "Drawer", (v, r) => (r._bp ? ({ C: "Customer", S: "Vendor", L: "Lead" })[r._bp] : ({ 1: "Assets", 2: "Liabilities", 3: "Capital", 4: "Turnover", 5: "Cost of sales", 6: "Operating costs", 7: "Non-operating", 8: "Taxation", 9: "Other" })[v] || "")],
      ["balance", "Balance", (v, r) => (r._bp ? "" : fmt(v)), 1]],
    filters: () => [["group_mask", "Drawer", [[1, "Assets"], [2, "Liabilities"], [3, "Capital"], [4, "Turnover"], [5, "Cost of sales"], [6, "Operating costs"], [7, "Non-operating"], [8, "Taxation"], [9, "Other"]]]],
  },
  whs: {
    title: "Warehouses", noun: "warehouse", master: () => "#/warehouses", list: "#/warehouses",
    load: () => api("/warehouses"), key: "whs_code",
    cols: [["whs_code", "Code"], ["whs_name", "Name"], ["city", "City"], ["state", "State"]],
    filters: () => [],
  },
};

function cflKind(sel) {
  if (sel.dataset.cfl) return sel.dataset.cfl === "none" ? null : sel.dataset.cfl;
  const s = ` ${sel.id || ""} ${sel.className || ""} `;
  if (/(^|[-_ ])(card_code|cstmr_code|customer|card|bp_code|vendor)( |$)/.test(s) || /\bl-bp\b/.test(s)) return "bp";
  if (/(^|[-_ ])(item_code|itemcode|item)( |$)|\bl-item\b|\bcl-item\b/.test(s)) return "item";
  if (/(^|[-_ ])(whs_code|dflt_wh|from_whs|to_whs|whs|warehouse)( |$)|\bl-whs\b|\bl-from\b/.test(s)) return "whs";
  if (/(^|[-_ ])(account|acct_code|[a-z_]*_acct|[a-z_]*_ac|acct)( |$)|\bl-acct\b|\bje-acct\b|\bfr-acct\b/.test(s)) return "account";
  return null;
}

const cflCache = {};
async function cflData(kind) {
  if (!cflCache[kind] || Date.now() - cflCache[kind].t > 30000) cflCache[kind] = { t: Date.now(), rows: await CFL_KINDS[kind].load() };
  return cflCache[kind].rows;
}

async function cflOpen(sel) {
  const kind = cflKind(sel), K = CFL_KINDS[kind];
  if (!K || sel.disabled) return;
  const master = await cflData(kind).catch(() => []);
  const byKey = Object.fromEntries(master.map((r) => [String(r[K.key]), r]));
  // the field's own options are the choices (keeps its restrictions); empty option = "no value" when allowed
  const opts = [...sel.options].filter((o) => o.value !== "");
  const allowEmpty = [...sel.options].some((o) => o.value === "");
  const rows = opts.map((o) => ({ ...(byKey[o.value] || {}), [K.key]: o.value, _label: o.textContent }));
  const filterDefs = K.filters(rows).filter(([, , choices]) => choices.length > 1);
  const st = { q: "", page: 0, f: {} };
  const box = document.createElement("div");
  box.className = "cfl-overlay";
  box.innerHTML = `<div class="cfl" role="dialog" aria-label="${esc(K.title)}"><div class="cfl-head"><b>List of ${esc(K.title)}</b>
      <a class="btn small ghost cfl-master-list" href="${K.list}">Open ${esc(K.title)} master</a><button class="btn small ghost cfl-x" title="Close (Esc)">✕</button></div>
    <div class="cfl-tools"><input class="cfl-q" placeholder="Find (code, name, any column)" autocomplete="off">
      ${filterDefs.map(([k, l, ch]) => `<select class="cfl-f" data-k="${k}">${opt("", `${l}: all`)}${ch.map(([v, t]) => opt(v, t)).join("")}</select>`).join("")}</div>
    <div class="cfl-body"><table><thead><tr>${K.cols.map(([, h, , n]) => `<th${n ? ' class="num"' : ""}>${esc(h)}</th>`).join("")}<th></th></tr></thead><tbody></tbody></table></div>
    <div class="cfl-foot"><span class="cfl-count"></span><span class="cfl-pager"><button class="btn small ghost cfl-prev">‹ Previous</button>
      <span class="cfl-pg"></span><button class="btn small ghost cfl-next">Next ›</button></span>
      ${allowEmpty ? '<button class="btn small ghost cfl-clear">No value</button>' : ""}<button class="btn small secondary cfl-cancel">Cancel</button></div></div>`;
  document.body.appendChild(box);
  const close = () => { box.remove(); sel.focus(); };
  const pick = (v) => {
    sel.value = v;
    sel.dispatchEvent(new Event("change", { bubbles: true }));
    sel.dispatchEvent(new Event("input", { bubbles: true }));
    box.remove();
    cflArrow(sel);
    sel.focus();
  };
  const matches = () => rows.filter((r) => {
    for (const [k, v] of Object.entries(st.f)) {
      if (v === "") continue;
      if (k === "_stock") { if ((v === "in") !== Number(r.on_hand || 0) > 0) return false; continue; }
      if (String(r[k]) !== v) return false;
    }
    if (!st.q) return true;
    const q = st.q.toLowerCase();
    return [r._label, ...K.cols.map(([k]) => r[k])].some((x) => x != null && String(x).toLowerCase().includes(q));
  });
  const draw = () => {
    const list = matches(), pages = Math.max(1, Math.ceil(list.length / CFL_PAGE));
    st.page = Math.min(st.page, pages - 1);
    const slice = list.slice(st.page * CFL_PAGE, (st.page + 1) * CFL_PAGE);
    $("tbody", box).innerHTML = slice.map((r) => `<tr class="cfl-row${String(r[K.key]) === sel.value ? " cfl-cur" : ""}" data-v="${esc(r[K.key])}" tabindex="0">
      ${K.cols.map(([k, , f, n]) => `<td${n ? ' class="num"' : ""}>${r[k] == null && k !== K.key ? (k === K.cols[1][0] ? esc(r._label) : "") : f ? f(r[k], r) : esc(r[k])}</td>`).join("")}
      <td><a class="cfl-go" href="${K.master(String(r[K.key]))}" title="Open the master record" data-stop="1">➜</a></td></tr>`).join("")
      || `<tr><td colspan="${K.cols.length + 1}" class="empty">No ${esc(K.noun)} matches.</td></tr>`;
    $(".cfl-count", box).textContent = `${list.length} of ${rows.length}`;
    $(".cfl-pg", box).textContent = `Page ${st.page + 1} of ${pages}`;
    $(".cfl-prev", box).disabled = st.page === 0;
    $(".cfl-next", box).disabled = st.page >= pages - 1;
    $$(".cfl-row", box).forEach((tr) => {
      tr.onclick = (e) => { if (!e.target.dataset.stop) pick(tr.dataset.v); };
      tr.onkeydown = (e) => { if (e.key === "Enter") pick(tr.dataset.v); };
    });
    $$(".cfl-go", box).forEach((a) => (a.onclick = () => box.remove()));
  };
  $(".cfl-q", box).oninput = (e) => { st.q = e.target.value.trim(); st.page = 0; draw(); };
  $(".cfl-q", box).onkeydown = (e) => { if (e.key === "Enter") { const first = $(".cfl-row", box); if (first) pick(first.dataset.v); } };
  $$(".cfl-f", box).forEach((s) => (s.onchange = () => { st.f[s.dataset.k] = s.value; st.page = 0; draw(); }));
  $(".cfl-prev", box).onclick = () => { st.page -= 1; draw(); };
  $(".cfl-next", box).onclick = () => { st.page += 1; draw(); };
  $(".cfl-x", box).onclick = close;
  $(".cfl-cancel", box).onclick = close;
  $(".cfl-master-list", box).onclick = () => box.remove();
  if ($(".cfl-clear", box)) $(".cfl-clear", box).onclick = () => pick("");
  box.onclick = (e) => { if (e.target === box) close(); };
  box.onkeydown = (e) => { if (e.key === "Escape") close(); };
  // start on the page of the current value
  const idx = matches().findIndex((r) => String(r[K.key]) === sel.value);
  st.page = idx > 0 ? Math.floor(idx / CFL_PAGE) : 0;
  draw();
  $(".cfl-q", box).focus();
}

function cflArrow(sel) {  // B1's golden arrow: opens the master record of the selected value
  const kind = cflKind(sel);
  let a = sel.nextElementSibling && sel.nextElementSibling.classList.contains("cfl-link") ? sel.nextElementSibling : null;
  if (!a) {
    a = document.createElement("a");
    a.className = "cfl-link";
    a.title = `Open the ${CFL_KINDS[kind].noun} master record`;
    a.textContent = "➜";
    sel.insertAdjacentElement("afterend", a);
  }
  a.href = sel.value ? CFL_KINDS[kind].master(sel.value) : CFL_KINDS[kind].list;
  a.classList.toggle("empty", !sel.value);
}

function cflDecorate(root = document) {
  $$("select", root).forEach((sel) => {
    if (sel.dataset.cflDone || !cflKind(sel)) return;
    sel.dataset.cflDone = "1";
    sel.classList.add("cfl-field");
    sel.title = sel.title || "Click or press F2 for the list (search, filters, pages)";
    sel.addEventListener("mousedown", (e) => { if (e.button === 0 && !sel.disabled) { e.preventDefault(); cflOpen(sel); } });
    sel.addEventListener("keydown", (e) => { if (e.key === "F2" || (e.altKey && e.key === "ArrowDown")) { e.preventDefault(); cflOpen(sel); } });
    sel.addEventListener("change", () => cflArrow(sel));
    cflArrow(sel);
  });
}

// decorate every screen as it is rendered (views, document lines added later, dialogs)
new MutationObserver(() => { clearTimeout(cflDecorate.t); cflDecorate.t = setTimeout(() => cflDecorate(), 30); })
  .observe(document.documentElement, { childList: true, subtree: true });
