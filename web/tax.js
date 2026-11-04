/* Tax setup: tax types (OSTT), tax authorities (OSTA), tax codes with components (OVTG + STC1),
   HSN / SAC codes (OCHP), tax code determination rules (OTCD). */
"use strict";

const TYPE_FIELDS = [{ k: "code", label: "Tax type code", req: true, max: 8 }, { k: "name", label: "Name", req: true, max: 50 }];
const AUTHORITY_FIELDS = () => [
  { k: "code", label: "Tax authority code", req: true, max: 8 }, { k: "name", label: "Name", req: true, max: 50 },
  { k: "type", label: "Tax type", type: "select", options: () => state.taxSetup.types.map((t) => [t.code, `${t.code} — ${t.name}`]) },
  { k: "sales_tax", label: "Output tax account", type: "select", blank: false, options: O.accounts((a) => !a.control) },
  { k: "purch_tax", label: "Input tax account", type: "select", blank: false, options: O.accounts((a) => !a.control) },
  { k: "rvs_chrg_act", label: "Reverse charge liability account", type: "select", options: O.accounts((a) => !a.control) },
];
const RC_NAMES = { N: "", Y: "reverse charge", I: "import of goods" };
const HSN_FIELDS = [
  { k: "chapter_id", label: "HSN / SAC code", req: true, max: 20 }, { k: "dscription", label: "Description", req: true, max: 254, span: 2 },
  { k: "item_type", label: "Type", type: "select", blank: false, options: [["I", "Goods (HSN)"], ["S", "Services (SAC)"]] },
];
const RULE_FIELDS = () => [
  { k: "priority", label: "Priority (lower first)", type: "number", step: 1, min: 0, value: 10 },
  { k: "doc_area", label: "Document area", type: "select", blank: false, options: [["S", "Sales"], ["P", "Purchasing"]] },
  { k: "card_code", label: "Business partner", type: "select", options: () => state.partners.map((b) => [b.card_code, `${b.card_code} — ${b.card_name}`]) },
  { k: "group_code", label: "BP group", type: "select", int: true, options: () => (state.partnerGroups || []).map((g) => [g.group_code, g.group_name]) },
  { k: "item_code", label: "Item", type: "select", options: () => (state.items || []).map((i) => [i.item_code, `${i.item_code} — ${i.item_name}`]) },
  { k: "itms_grp_cod", label: "Item group", type: "select", int: true, options: () => (state.itemGroups || []).map((g) => [g.itms_grp_cod, g.itms_grp_nam]) },
  { k: "chapter_id", label: "HSN / SAC", type: "select", options: () => O.hsn() },
  { k: "state", label: "Place-of-supply state", type: "select", options: () => O.states("IN") },
  { k: "supply", label: "Supply", type: "select", options: [["I", "Intra-state"], ["O", "Inter-state"]] },
  { k: "tax_code", label: "Tax code", type: "select", blank: false, req: true, options: () => state.taxSetup.codes.filter((t) => !t.inactive).map((t) => [t.code, `${t.code} — ${t.name}`]) },
  { k: "descr", label: "Description", max: 100, span: 2 },
  { k: "active", label: "Active", type: "check", value: true },
];

views["tax-setup"] = async (c) => {
  [state.taxSetup, state.partnerGroups, state.items, state.itemGroups] = await Promise.all([
    api("/tax/setup"), api("/partner-groups"), api("/items"), api("/item-groups")]);
  const T = state.taxSetup, codeId = query().get("code"), ruleId = query().get("rule");
  const edit = codeId && T.codes.find((t) => t.code === codeId);
  const rule = ruleId && T.determination.find((r) => String(r.abs_id) === ruleId);
  const auth = (code) => T.authorities.find((a) => a.code === code) || {};
  const cond = (r) => [r.card_code && `BP ${r.card_code}`, r.group_code != null && `BP group ${nameOf(state.partnerGroups, "group_code", r.group_code, "group_name")}`,
    r.item_code && `item ${r.item_code}`, r.itms_grp_cod != null && `item group ${nameOf(state.itemGroups, "itms_grp_cod", r.itms_grp_cod, "itms_grp_nam")}`,
    r.chapter_id && `HSN/SAC ${r.chapter_id}`, r.state && `state ${r.state}`, r.supply && (r.supply === "I" ? "intra-state" : "inter-state")].filter(Boolean).join(", ") || "all";
  c.innerHTML = `<div class="page-head"><div><h1>Tax Setup</h1><div class="sub">Tax types, tax authorities, tax codes with components, HSN / SAC codes and tax code determination</div></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Tax types (OSTT)</div><table><tbody>
        ${T.types.map((t) => `<tr><td class="mono">${esc(t.code)}</td><td>${esc(t.name)}</td></tr>`).join("") || `<tr><td class="empty">No tax types.</td></tr>`}</tbody></table>
        <div class="card-body"><div class="form-grid">${fieldsHtml(TYPE_FIELDS, {}, "tt")}</div><button class="btn secondary small" id="tt-save" style="margin-top:8px">Add / update</button></div></div>
      <div class="card"><div class="card-head">Tax authorities (OSTA)</div><table><thead><tr><th>Code</th><th>Name</th><th>Type</th><th>Output account</th><th>Input account</th><th>Reverse charge</th></tr></thead><tbody>
        ${T.authorities.map((a) => `<tr><td class="mono">${esc(a.code)}</td><td>${esc(a.name)}</td><td>${esc(a.type || "")}</td><td class="mono">${esc(a.sales_tax)}</td><td class="mono">${esc(a.purch_tax)}</td><td class="mono">${esc(a.rvs_chrg_act || "")}</td></tr>`).join("")}</tbody></table>
        <div class="card-body"><div class="form-grid">${fieldsHtml(AUTHORITY_FIELDS(), {}, "ta")}</div><button class="btn secondary small" id="ta-save" style="margin-top:8px">Add / update</button></div></div>
    </div>
    <div class="card"><div class="card-head">Tax codes (OVTG + components STC1) — click a code to change it</div><div style="max-height:360px;overflow:auto"><table><thead><tr><th>Code</th><th>Name</th><th>Category</th><th class="num">Rate</th><th>Components</th><th>GST</th><th>Used</th><th>Active</th></tr></thead><tbody>
      ${T.codes.map((t) => `<tr style="cursor:pointer" onclick="location.hash='#/tax-setup?code=${encodeURIComponent(t.code)}'"><td class="mono">${esc(t.code)}</td><td>${esc(t.name)}</td>
        <td>${t.category === "O" ? "Output" : "Input"}</td><td class="num">${Number(t.rate)}%</td>
        <td>${t.components.length ? t.components.map((x) => `${esc(x.sta_code)} ${Number(x.rate)}% <span class="help">(${esc(t.category === "O" ? auth(x.sta_code).sales_tax : auth(x.sta_code).purch_tax)})</span>`).join(" + ") : `account <span class="mono">${esc(t.account)}</span>`}</td>
        <td>${t.gst ? (t.gst === "intra" ? "intra-state" : "inter-state") : ""}${t.rev_charge !== "N" ? ` <span class="status P">${RC_NAMES[t.rev_charge]}</span>` : ""}${Number(t.non_dedct) ? ` <span class="status X">${Number(t.non_dedct)} % blocked</span>` : ""}</td><td>${yesNo(t.used)}</td><td>${yesNo(!t.inactive)}</td></tr>`).join("")}</tbody></table></div>
      <div class="card-body"><h3 class="section">${edit ? `Change tax code ${esc(edit.code)} <a class="btn small ghost" href="#/tax-setup">New</a>${edit.used ? ' <span class="help">used in postings: only name and active can change</span>' : ""}` : "New tax code"}</h3>
        <div class="form-grid">${fieldsHtml([
          { k: "code", label: "Tax code", req: true, max: 8, ro: !!edit }, { k: "name", label: "Name", req: true, max: 30, span: 2 },
          { k: "category", label: "Category", type: "select", blank: false, options: [["O", "Output (sales)"], ["I", "Input (purchasing)"]], ro: !!(edit && edit.used) },
          { k: "rate", label: "Rate % (without components)", type: "number", step: "0.01", min: 0, maxv: 99.99, ro: !!(edit && edit.used) },
          { k: "account", label: "Tax account (without components)", type: "select", options: O.accounts((a) => !a.control), ro: !!(edit && edit.used) },
          { k: "rev_charge", label: "Reverse charge (purchasing)", type: "select", blank: false, ro: !!(edit && edit.used),
            options: [["N", "No — vendor charges the tax"], ["Y", "Reverse charge — company pays (RCM)"], ["I", "Import of goods — IGST paid at customs"]] },
          { k: "non_dedct", label: "Non-deductible % (blocked credit)", type: "number", step: "0.01", min: 0, maxv: 100, ro: !!(edit && edit.used) },
          { k: "non_ded_acc", label: "Non-deductible tax account", type: "select", options: O.accounts((a) => !a.control) },
          { k: "inactive", label: "Inactive", type: "check" }], edit ? { ...edit, rate: edit.components.length ? "" : edit.rate, account: edit.components.length ? "" : edit.account } : {}, "tc")}</div>
        <table class="lines" style="margin-top:8px"><thead><tr><th>Component (tax authority)</th><th class="num">Rate %</th><th></th></tr></thead><tbody id="tc-comps"></tbody></table>
        <button class="btn secondary small" id="tc-add" style="margin-top:6px">+ Component</button> <b style="margin-left:12px">Total rate: <span id="tc-total">0</span>%</b>
        <div><button class="btn" id="tc-save" style="margin-top:10px">${edit ? "Update" : "Add"}</button></div></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">HSN / SAC codes (OCHP)</div><div style="max-height:300px;overflow:auto"><table><thead><tr><th>Code</th><th>Description</th><th>Type</th></tr></thead><tbody>
        ${T.hsn.map((h) => `<tr><td class="mono">${esc(h.chapter_id)}</td><td>${esc(h.dscription)}</td><td>${h.item_type === "S" ? "SAC" : "HSN"}</td></tr>`).join("") || `<tr><td colspan="3" class="empty">No codes.</td></tr>`}</tbody></table></div>
        <div class="card-body"><div class="form-grid">${fieldsHtml(HSN_FIELDS, {}, "hs")}</div><button class="btn secondary small" id="hs-save" style="margin-top:8px">Add</button></div></div>
      <div class="card"><div class="card-head">Tax code determination (OTCD) — first matching active rule, lowest priority first</div><div style="max-height:300px;overflow:auto"><table><thead><tr><th class="num">Prio</th><th>Area</th><th>Conditions</th><th>Tax code</th><th>Active</th><th></th></tr></thead><tbody>
        ${T.determination.map((r) => `<tr><td class="num">${r.priority}</td><td>${r.doc_area === "S" ? "Sales" : "Purchasing"}</td><td>${esc(cond(r))}${r.descr ? `<div class="help">${esc(r.descr)}</div>` : ""}</td>
          <td class="mono">${esc(r.tax_code)}</td><td>${yesNo(r.active === "Y")}</td>
          <td><a class="btn small ghost" href="#/tax-setup?rule=${r.abs_id}">Edit</a> <button class="btn small ghost rule-del" data-id="${r.abs_id}">✕</button></td></tr>`).join("")
          || `<tr><td colspan="6" class="empty">No rules: tax codes come from the item and the business partner.</td></tr>`}</tbody></table></div>
        <div class="card-body"><h3 class="section">${rule ? `Change rule ${rule.abs_id} <a class="btn small ghost" href="#/tax-setup">New</a>` : "New rule"}</h3>
          <div class="form-grid">${fieldsHtml(RULE_FIELDS(), rule ? { ...rule, active: rule.active === "Y" } : {}, "rl")}</div>
          <button class="btn secondary small" id="rl-save" style="margin-top:8px">${rule ? "Update" : "Add"}</button></div></div>
    </div>`;

  const compRow = (v = {}) => {
    const tr = document.createElement("tr");
    const locked = edit && edit.used ? " disabled" : "";
    tr.innerHTML = `<td><select class="tc-sta"${locked}>${T.authorities.map((a) => opt(a.code, `${a.code} — ${a.name}`, v.sta_code)).join("")}</select></td>
      <td class="num"><input class="tc-rate" type="number" step="0.01" min="0" max="99.99" value="${v.rate != null ? Number(v.rate) : ""}"${locked}></td>
      <td>${locked ? "" : '<button class="btn ghost small tc-del">✕</button>'}</td>`;
    $("#tc-comps").appendChild(tr);
    $(".tc-rate", tr).oninput = total;
    if ($(".tc-del", tr)) $(".tc-del", tr).onclick = () => { tr.remove(); total(); };
  };
  const total = () => {
    const rows = $$("#tc-comps tr");
    $("#tc-total").textContent = rows.length ? rows.reduce((s, tr) => s + Number($(".tc-rate", tr).value || 0), 0) : Number($("#tc-rate").value || 0);
  };
  (edit ? edit.components : []).forEach(compRow);
  total();
  $("#tc-rate").oninput = total;
  if (edit && edit.used) $("#tc-add").style.display = "none";
  $("#tc-add").onclick = () => compRow();

  const done = async (r) => { if (r) { await reloadMasterData(); location.hash = `#/tax-setup?r=${Date.now()}`; } };
  $("#tt-save").onclick = async () => done(await act(() => post("/tax/types", readFields(TYPE_FIELDS, "tt")), "Tax type saved"));
  $("#ta-save").onclick = async () => done(await act(() => post("/tax/authorities", readFields(AUTHORITY_FIELDS(), "ta")), "Tax authority saved"));
  $("#hs-save").onclick = async () => done(await act(() => post("/tax/hsn", readFields(HSN_FIELDS, "hs")), "HSN / SAC code added"));
  $("#tc-save").onclick = async () => {
    const h = readFields([{ k: "code" }, { k: "name" }, { k: "category", type: "select" }, { k: "rate", type: "number" },
      { k: "account", type: "select" }, { k: "rev_charge", type: "select" }, { k: "non_dedct", type: "number" }, { k: "non_ded_acc", type: "select" },
      { k: "inactive", type: "check" }], "tc");
    if (edit && edit.used) Object.assign(h, { rev_charge: edit.rev_charge, non_dedct: edit.non_dedct });  // read-only fields
    if (edit) h.code = edit.code;
    const body = { ...h, components: $$("#tc-comps tr").map((tr) => ({ sta_code: $(".tc-sta", tr).value, rate: Number($(".tc-rate", tr).value || 0) })) };
    done(await act(() => post("/tax/codes", body), (x) => `Tax code ${x.code} saved (${Number(x.rate)} %)`));
  };
  $("#rl-save").onclick = async () => {
    const body = readFields(RULE_FIELDS(), "rl");
    done(await act(() => (rule ? api(`/tax/determination/${rule.abs_id}`, { method: "PUT", body: JSON.stringify(body) })
      : post("/tax/determination", body)), "Rule saved"));
  };
  $$(".rule-del").forEach((b) => (b.onclick = async () => {
    if (!confirm("Remove this determination rule?")) return;
    done(await act(() => api(`/tax/determination/${b.dataset.id}`, { method: "DELETE" }), "Rule removed"));
  }));
};
