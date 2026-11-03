/* Approval procedures (stages, templates), approval requests / decisions, alerts (bell, list, setup). */
"use strict";

async function refreshAlertBell() {
  const bell = $("#alert-bell");
  if (!bell) return;
  const r = await api("/alerts").catch(() => ({ total: 0 }));
  bell.innerHTML = `&#128276;${r.total ? `<span class="bell-count">${r.total}</span>` : ""}`;
  bell.title = r.total ? `${r.total} alerts` : "No alerts";
}

views.alerts = async (c) => {
  const r = await api("/alerts");
  c.innerHTML = `<div class="page-head"><div><h1>Alerts</h1><div class="sub">Your alerts, evaluated now</div></div>
      ${may("ADMIN", "F") ? '<a class="btn secondary" href="#/alert-setup">Alert settings</a>' : ""}</div>
    ${r.alerts.map((a) => `<div class="card"><div class="card-head">${esc(a.name)} <span class="status X">${a.count}</span></div><table><tbody>
      ${a.items.map((i) => `<tr style="cursor:pointer" onclick="location.hash='${i.link}'"><td>${esc(i.text)}</td></tr>`).join("")}</tbody></table></div>`).join("")
      || '<div class="card"><div class="card-body empty">No alerts.</div></div>'}`;
  refreshAlertBell();
};

views["alert-setup"] = async (c) => {
  const r = await api("/alerts/setup");
  c.innerHTML = `<div class="page-head"><div><h1>Alert Settings</h1><div class="sub">System alerts (OALT): active, days, recipients (ALT1)</div></div></div>
    <div class="card"><table><thead><tr><th>Alert</th><th>Type</th><th>Days</th><th>Recipients</th><th>Active</th><th></th></tr></thead><tbody>
      ${r.alerts.map((a) => `<tr data-code="${a.code}"><td>${esc(a.name)}</td><td>${esc(a.type_name)}</td>
        <td>${["OVERDUE", "EXPIRY"].includes(a.type) ? `<input class="al-param" type="number" min="0" step="1" value="${a.param ?? ""}" style="width:80px">` : ""}</td>
        <td><div class="multi">${r.users.map((u) => `<label><input type="checkbox" class="al-user" value="${u.user_id}"${a.recipients.includes(u.user_id) ? " checked" : ""}> ${esc(u.user_code)}</label>`).join("")}</div>
          ${a.type === "APPROVAL" ? '<div class="help">also always shown to the authorizers and originators concerned</div>' : ""}</td>
        <td><input type="checkbox" class="al-act"${a.active ? " checked" : ""}></td><td><button class="btn small secondary al-save">Save</button></td></tr>`).join("")}</tbody></table></div>`;
  $$("tr[data-code]").forEach((tr) => {
    $(".al-save", tr).onclick = async () => {
      const body = { active: $(".al-act", tr).checked, recipients: $$(".al-user", tr).filter((x) => x.checked).map((x) => Number(x.value)) };
      if ($(".al-param", tr)) body.param = $(".al-param", tr).value === "" ? null : Number($(".al-param", tr).value);
      if (await act(() => patch(`/alerts/setup/${tr.dataset.code}`, body), "Alert saved")) refreshAlertBell();
    };
  });
};

views.approvals = async (c) => {
  const r = await api("/approval-requests");
  const row = (x, decide) => `<tr data-wdd="${x.wdd_code}"><td>${x.wdd_code}</td><td>${esc(x.doc_name)}</td><td class="mono">${esc(x.card_code || "")}</td>
    <td class="num">${fmt(x.doc_total)}</td><td>${esc(x.owner)}</td><td>${esc(x.reason || "")}</td><td>${esc(x.stage || "")}</td>
    <td><span class="status ${x.status === "W" ? "O" : x.status === "N" ? "X" : "C"}">${x.status_name}</span>
      ${x.decisions.map((d) => `<div class="help">${esc(d.stage)}: ${esc(d.user)} ${d.status === "Y" ? "approved" : "rejected"}${d.remarks ? ` — ${esc(d.remarks)}` : ""}</div>`).join("")}</td>
    <td>${decide ? '<input class="ap-rem" maxlength="254" placeholder="Remarks"><button class="btn small ap-yes">Approve</button> <button class="btn small secondary ap-no">Reject</button>'
      : x.status === "Y" && x.owner_id === state.user.user_id ? '<button class="btn small ap-add">Add document</button>'
      : x.doc_entry ? `<a href="#/docs?obj=${x.obj_type}&entry=${x.doc_entry}">Document</a>` : ""}</td></tr>`;
  const head = '<thead><tr><th>No.</th><th>Document</th><th>BP</th><th class="num">Total</th><th>Originator</th><th>Reason</th><th>Stage</th><th>Status</th><th></th></tr></thead>';
  c.innerHTML = `<div class="page-head"><div><h1>Approvals</h1><div class="sub">Requests waiting for your decision and your own requests</div></div>
      ${may("ADMIN", "F") ? '<a class="btn secondary" href="#/approval-setup">Approval procedures</a>' : ""}</div>
    <div class="card"><div class="card-head">Waiting for my decision</div><table>${head}<tbody>${r.to_decide.map((x) => row(x, true)).join("")
      || '<tr><td colspan="9" class="empty">Nothing to decide.</td></tr>'}</tbody></table></div>
    <div class="card"><div class="card-head">My requests</div><table>${head}<tbody>${r.mine.map((x) => row(x, false)).join("")
      || '<tr><td colspan="9" class="empty">No requests.</td></tr>'}</tbody></table></div>`;
  $$("tr[data-wdd]").forEach((tr) => {
    const code = tr.dataset.wdd;
    const decide = (approve) => async () => {
      if (await act(() => post(`/approval-requests/${code}/decide`, { approve, remarks: ($(".ap-rem", tr) || {}).value || null }), approve ? "Approved" : "Rejected")) views.approvals(c);
    };
    if ($(".ap-yes", tr)) { $(".ap-yes", tr).onclick = decide(true); $(".ap-no", tr).onclick = decide(false); }
    if ($(".ap-add", tr)) $(".ap-add", tr).onclick = async () => {
      const d = await act(() => post(`/approval-requests/${code}/add`, {}), "Document added");
      if (d) location.hash = `#/docs?obj=${d.obj}&entry=${d.doc_entry}`;
    };
  });
  refreshAlertBell();
};

views["approval-setup"] = async (c) => {
  const r = await api("/approvals/setup");
  const types = await docTypes();
  const docOpts = Object.values(types).filter((t) => t.side !== "I").map((t) => [t.obj, t.name]);
  const userOpts = r.users.map((u) => [u.user_id, u.user_code]);
  const stageOpts = r.stages.map((s) => [s.wst_code, s.name]);
  const sDefs = [{ k: "name", label: "Stage name", req: true, max: 30 }, { k: "authorizers", label: "Authorizers", type: "multi", options: userOpts, span: 2 },
    { k: "max_reqr", label: "Approvals required", type: "number", step: 1, min: 1, value: 1 }, { k: "max_rej_reqr", label: "Rejections required", type: "number", step: 1, min: 1, value: 1 }];
  const tDefs = [{ k: "name", label: "Template name", req: true, max: 50 }, { k: "active", label: "Active", type: "check", value: true },
    { k: "originators", label: "Originators", type: "multi", options: userOpts, span: 2 }, { k: "documents", label: "Documents", type: "multi", options: docOpts, span: 4 },
    { k: "stages", label: "Stages (in this order)", type: "multi", options: stageOpts, span: 2 }];
  const condRow = (x = {}) => `<tr><td><select class="cd-id">${opt("", "")}${Object.entries(r.conditions).map(([k, v]) => opt(k, v, x.cond_id)).join("")}</select></td>
    <td><select class="cd-op">${Object.entries(r.ops).map(([k, v]) => opt(k, v, x.op_code)).join("")}</select></td>
    <td><input class="cd-val" type="number" step="0.01" value="${x.value != null ? Number(x.value) : ""}"></td></tr>`;
  c.innerHTML = `<div class="page-head"><div><h1>Approval Procedures</h1><div class="sub">Approval stages and templates: which documents of which users need whose approval</div></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">Stages</div><table><thead><tr><th>Stage</th><th>Authorizers</th><th class="num">Approvals</th><th class="num">Rejections</th></tr></thead><tbody>
        ${r.stages.map((s) => `<tr><td>${esc(s.name)}</td><td>${s.authorizer_codes.map(esc).join(", ")}</td><td class="num">${s.max_reqr}</td><td class="num">${s.max_rej_reqr}</td></tr>`).join("")
          || '<tr><td colspan="4" class="empty">No stages.</td></tr>'}</tbody></table>
        <div class="card-body"><h3 class="section">New stage</h3><div class="form-grid">${fieldsHtml(sDefs, {}, "as")}</div><button class="btn secondary" id="as-save" style="margin-top:6px">Add stage</button></div></div>
      <div class="card"><div class="card-head">Templates</div><table><thead><tr><th>Template</th><th>Documents</th><th>Stages</th><th>Conditions</th><th>Active</th></tr></thead><tbody>
        ${r.templates.map((t) => `<tr><td>${esc(t.name)}</td><td>${t.documents.map((d) => esc((types[d] || {}).name || d)).join(", ")}</td>
          <td>${t.stages.map((s) => esc((r.stages.find((x) => x.wst_code === s) || {}).name || s)).join(" → ")}</td>
          <td>${t.conditions.map((x) => `${esc(r.conditions[x.cond_id])} ${r.ops[x.op_code]} ${Number(x.value)}`).join(" or ") || "always"}</td><td>${yesNo(t.active)}</td></tr>`).join("")
          || '<tr><td colspan="5" class="empty">No templates.</td></tr>'}</tbody></table></div></div>
    <div class="card"><div class="card-head">New template</div><div class="card-body"><div class="form-grid">${fieldsHtml(tDefs, {}, "at")}</div>
      <h3 class="section">Conditions (any met → approval; none → always)</h3><table class="lines"><thead><tr><th>Term</th><th>Operator</th><th>Value</th></tr></thead><tbody id="at-cond">${condRow()}${condRow()}</tbody></table>
      <button class="btn" id="at-save" style="margin-top:8px">Add template</button></div></div>`;
  $("#as-save").onclick = async () => { if (await act(() => post("/approvals/stages", readFields(sDefs, "as")), "Stage added")) views["approval-setup"](c); };
  $("#at-save").onclick = async () => {
    const body = readFields(tDefs, "at");
    body.stages = body.stages.map(Number); body.originators = body.originators.map(Number);
    body.conditions = $$("#at-cond tr").map((tr) => ({ cond_id: $(".cd-id", tr).value, op_code: $(".cd-op", tr).value, value: Number($(".cd-val", tr).value || 0) })).filter((x) => x.cond_id);
    if (await act(() => post("/approvals/templates", body), "Template added")) views["approval-setup"](c);
  };
};
