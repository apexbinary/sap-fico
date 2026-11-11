/* CRM: sales opportunities (stages, won / lost), activities, calendar, pipeline. */
"use strict";

const custOpts = (sel) => state.partners.filter((p) => p.card_type !== "S").map((p) => opt(p.card_code, `${p.card_code} — ${p.card_name}`, sel)).join("");

views.opportunities = async (c) => {
  const id = query().get("id");
  const [list, stages] = await Promise.all([api("/crm/opportunities"), api("/crm/stages")]);
  const o = id ? await api(`/crm/opportunities/${id}`) : null;
  const ST = { O: "O", W: "C", L: "X" };
  c.innerHTML = `<div class="page-head"><div><h1>Sales Opportunities</h1><div class="sub">Potential deals through the sales stages</div></div>
      <a class="btn" href="#/opportunities?id=">+ New opportunity</a></div>
    <div class="card"><table><thead><tr><th>No.</th><th>Name</th><th>Customer</th><th>Stage</th><th class="num">Potential</th><th class="num">%</th><th class="num">Weighted</th><th>Closing</th><th>Status</th></tr></thead><tbody>
      ${list.map((x) => `<tr style="cursor:pointer" onclick="location.hash='#/opportunities?id=${x.oppr_id}'"><td>${x.oppr_id}</td><td>${esc(x.name)}</td><td>${esc(x.card_name || x.card_code)}</td>
        <td>${esc(x.stage_name || "")}</td><td class="num">${fmt(x.max_sum_loc)}</td><td class="num">${Number(x.clo_prcnt)}</td><td class="num">${fmt(x.wt_sum_loc)}</td>
        <td>${x.close_date || x.pred_date || ""}</td><td><span class="status ${ST[x.status]}">${x.status_name}</span></td></tr>`).join("") || '<tr><td colspan="9" class="empty">No opportunities.</td></tr>'}</tbody></table></div>
    ${id === "" ? `<div class="card"><div class="card-head">New opportunity</div><div class="card-body"><div class="form-grid">
        <div class="field"><label class="req">Name</label><input id="op-name" maxlength="100"></div>
        <div class="field"><label class="req">Customer / lead</label><select id="op-card">${opt("", "")}${custOpts()}</select></div>
        <div class="field"><label>Stage</label><select id="op-stage">${stages.map((s) => opt(s.num, `${s.descript} (${Number(s.clo_prcnt)} %)`)).join("")}</select></div>
        <div class="field"><label>Potential amount</label><input id="op-amt" type="number" step="0.01" min="0"></div>
        <div class="field"><label>Predicted closing</label><input id="op-pred" type="date"></div>
        <div class="field"><label>Contact person</label><select id="op-cpr"></select></div>
        <div class="field"><label>Sales employee</label><select id="op-slp">${O.salesEmployees().map(([v, l]) => opt(v, l)).join("")}</select></div>
        <div class="field" style="grid-column:span 2"><label>Remarks</label><input id="op-memo" maxlength="254"></div></div>
        <button class="btn" id="op-add" style="margin-top:8px">Add</button></div></div>` : ""}
    ${o ? `<div class="card"><div class="card-head"><span>Opportunity ${o.oppr_id}: ${esc(o.name)} — ${esc(o.card_name || o.card_code)} <span class="status ${ST[o.status]}">${o.status_name}</span></span>
        <span class="help">potential ${fmt(o.max_sum_loc)} · ${Number(o.clo_prcnt)} % · weighted ${fmt(o.wt_sum_loc)}${o.reason ? ` · ${esc(o.reason)}` : ""}</span></div>
      <table><thead><tr><th>Stage</th><th>From</th><th>To</th><th class="num">Amount</th><th class="num">%</th><th>Document</th><th>Remarks</th></tr></thead><tbody>
        ${o.lines.map((l) => `<tr><td>${esc(l.stage)}</td><td>${l.open_date}</td><td>${l.close_date || ""}</td><td class="num">${fmt(l.max_sum_loc)}</td><td class="num">${Number(l.close_prcnt)}</td>
          <td>${l.obj_type ? docLink(l.obj_type, l.doc_number, `${transTypeName(l.obj_type)} ${l.doc_number}`) : ""}</td><td>${esc(l.memo || "")}</td></tr>`).join("")}</tbody></table>
      ${o.status === "O" ? `<div class="card-body"><div class="form-grid">
          <div class="field"><label>Next stage</label><select id="os-stage">${stages.map((s) => opt(s.num, `${s.descript} (${Number(s.clo_prcnt)} %)`)).join("")}</select></div>
          <div class="field"><label>Amount</label><input id="os-amt" type="number" step="0.01" min="0" value="${Number(o.max_sum_loc)}"></div>
          <div class="field"><label>Linked document</label><select id="os-obj">${opt("", "")}${opt("23", "Sales quotation")}${opt("17", "Sales order")}</select></div>
          <div class="field"><label>Document no. (entry)</label><input id="os-doc" type="number" step="1" min="1"></div>
          <div class="field"><label>Reason (lost)</label><input id="os-reason" maxlength="100"></div></div>
        <div style="display:flex;gap:8px;margin-top:8px"><button class="btn secondary" id="os-go">Move to stage</button><button class="btn" id="os-won">Won</button>
          <button class="btn ghost" id="os-lost">Lost</button><a class="btn ghost" href="#/activities?id=&opr=${o.oppr_id}&card=${encodeURIComponent(o.card_code)}">+ Activity</a></div></div>` : ""}
      <div class="card-body"><h3 class="section">Activities</h3><table><tbody>${o.activities.map((a) => `<tr style="cursor:pointer" onclick="location.hash='#/activities?id=${a.clg_code}'">
        <td>${a.recontact} ${esc(a.begin_time || "")}</td><td>${esc(a.action_name)}</td><td>${esc(a.details)}</td><td>${a.closed ? "done" : ""}</td></tr>`).join("") || '<tr><td class="empty">No activities.</td></tr>'}</tbody></table></div></div>` : ""}`;
  if ($("#op-card")) {
    linkContacts($("#op-card"), $("#op-cpr"));
    $("#op-card").addEventListener("change", () => {  // the partner's sales employee by default
      const b = state.partners.find((x) => x.card_code === $("#op-card").value);
      if (b && b.slp_code != null) $("#op-slp").value = String(b.slp_code);
    });
  }
  if ($("#op-add")) $("#op-add").onclick = async () => {
    const body = { name: $("#op-name").value, card_code: $("#op-card").value, stage: Number($("#op-stage").value), max_sum_loc: Number($("#op-amt").value || 0),
      pred_date: $("#op-pred").value || null, memo: $("#op-memo").value || null,
      cpr_code: $("#op-cpr").value ? Number($("#op-cpr").value) : null, slp_code: $("#op-slp").value !== "" ? Number($("#op-slp").value) : null };
    const r = await act(() => post("/crm/opportunities", body), (x) => `Opportunity ${x.oppr_id} added`);
    if (r) location.hash = `#/opportunities?id=${r.oppr_id}`;
  };
  if (!o || o.status !== "O") return;
  const reload = () => { location.hash = `#/opportunities?id=${o.oppr_id}&r=${Date.now()}`; };
  const doc = () => ($("#os-obj").value ? { obj_type: $("#os-obj").value, doc_entry: Number($("#os-doc").value || 0) } : {});
  $("#os-go").onclick = async () => { if (await act(() => post(`/crm/opportunities/${o.oppr_id}/stage`, { stage: Number($("#os-stage").value), amount: Number($("#os-amt").value || 0), ...doc() }), "Stage changed")) reload(); };
  $("#os-won").onclick = async () => { if (await act(() => post(`/crm/opportunities/${o.oppr_id}/close`, { won: true, ...doc() }), "Opportunity won")) reload(); };
  $("#os-lost").onclick = async () => { if (await act(() => post(`/crm/opportunities/${o.oppr_id}/close`, { won: false, reason: $("#os-reason").value || null }), "Opportunity lost")) reload(); };
};

views.activities = async (c) => {
  const q = query(), id = q.get("id");
  const mine = q.get("all") !== "1";
  const data = await api(`/crm/activities?${mine && state.user ? `user_id=${state.user.user_id}&` : ""}open_only=${q.get("done") === "1" ? "false" : "true"}`);
  const edit = id && id !== "" && (await api("/crm/activities")).activities.find((a) => String(a.clg_code) === id);
  const [users, opps] = await Promise.all([api("/crm/users").catch(() => []), api("/crm/opportunities?status=O").catch(() => [])]);
  const defs = [
    { k: "action", label: "Activity", type: "select", blank: false, options: Object.entries(data.actions), value: "C" },
    { k: "details", label: "Subject", req: true, max: 100, span: 2 },
    { k: "card_code", label: "Business partner", type: "select", options: state.partners.map((p) => [p.card_code, `${p.card_code} — ${p.card_name}`]), value: q.get("card") || "" },
    { k: "cntct_code", label: "Contact person", type: "select", int: true, options: [] },
    { k: "attend_user", label: "Handled by", type: "select", int: true, blank: false, options: users.map((u) => [u.user_id, `${u.user_code} — ${u.u_name}`]),
      value: state.user ? state.user.user_id : "" },
    { k: "opr_id", label: "Opportunity", type: "select", int: true, options: opps.map((o) => [o.oppr_id, `${o.oppr_id} — ${o.name}`]), value: q.get("opr") || "" },
    { k: "doc_type", label: "Linked document type", type: "select", options: [["23", "Sales quotation"], ["17", "Sales order"], ["15", "Delivery"], ["13", "A/R invoice"],
      ["22", "Purchase order"], ["18", "A/P invoice"], ["191", "Service call"]], value: q.get("call") ? "191" : "" },
    { k: "doc_entry", label: "Linked document no. (entry)", type: "number", step: 1, min: 1, value: q.get("call") || "" },
    { k: "recontact", label: "Date", type: "date", value: today(), req: true }, { k: "begin_time", label: "Start (HH:MM)", max: 5 }, { k: "end_time", label: "End (HH:MM)", max: 5 },
    { k: "priority", label: "Priority", type: "select", blank: false, options: Object.entries(data.priorities), value: "1" },
    { k: "location", label: "Location", max: 100 }, { k: "notes", label: "Notes", type: "textarea", max: 1000, span: 3 },
    ...(edit ? [{ k: "closed", label: "Closed (done)", type: "check" }] : []),
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Activities</h1><div class="sub">${mine ? "My" : "All"} ${q.get("done") === "1" ? "" : "open "}activities — calls, meetings, tasks, notes</div></div>
      <span style="display:flex;gap:8px"><a class="btn ghost" href="#/activities?all=${mine ? 1 : 0}">${mine ? "All users" : "Only mine"}</a>
      <a class="btn ghost" href="#/activities?done=${q.get("done") === "1" ? 0 : 1}">${q.get("done") === "1" ? "Open only" : "Include done"}</a><a class="btn" href="#/activities?id=">+ New activity</a></span></div>
    <div class="card"><table><thead><tr><th>Date</th><th>Time</th><th>Activity</th><th>Subject</th><th>Partner</th><th>Handled by</th><th>Priority</th><th>Status</th></tr></thead><tbody>
      ${data.activities.map((a) => `<tr style="cursor:pointer" onclick="location.hash='#/activities?id=${a.clg_code}'"><td>${a.recontact}</td><td>${esc(a.begin_time || "")}${a.end_time ? `–${esc(a.end_time)}` : ""}</td>
        <td>${esc(a.action_name)}</td><td>${esc(a.details)}</td><td>${esc(a.card_name || "")}</td><td>${esc(a.attend_code || "")}</td><td>${data.priorities[a.priority]}</td>
        <td>${a.closed ? '<span class="status C">done</span>' : a.overdue ? '<span class="status X">overdue</span>' : '<span class="status O">open</span>'}</td></tr>`).join("")
        || '<tr><td colspan="8" class="empty">No activities.</td></tr>'}</tbody></table></div>
    ${id !== null ? `<div class="card"><div class="card-head">${edit ? `Activity ${edit.clg_code}` : "New activity"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(defs, edit || {}, "ac")}</div><button class="btn" id="ac-save" style="margin-top:8px">${edit ? "Update" : "Add"}</button></div></div>` : ""}`;
  if ($("#ac-card_code")) linkContacts($("#ac-card_code"), $("#ac-cntct_code"), edit ? edit.cntct_code : null);
  if ($("#ac-save")) $("#ac-save").onclick = async () => {
    const body = readFields(defs, "ac");
    if (!body.doc_type) body.doc_entry = null;
    const r = edit ? await act(() => patch(`/crm/activities/${edit.clg_code}`, body), "Activity updated") : await act(() => post("/crm/activities", body), "Activity added");
    if (r) { location.hash = `#/activities?r=${Date.now()}`; if (typeof refreshAlertBell === "function") refreshAlertBell(); }
  };
};

views.calendar = async (c) => {
  const q = query(), base = q.get("month") ? new Date(`${q.get("month")}-01T00:00:00`) : new Date();
  const y = base.getFullYear(), m = base.getMonth();
  const first = new Date(y, m, 1), last = new Date(y, m + 1, 0);
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const data = await api(`/crm/activities?date_from=${iso(first)}&date_to=${iso(last)}${q.get("all") === "1" || !state.user ? "" : `&user_id=${state.user.user_id}`}`);
  const byDay = {};
  data.activities.forEach((a) => { (byDay[a.recontact] = byDay[a.recontact] || []).push(a); });
  const start = (first.getDay() + 6) % 7;  // Monday first
  const cells = [];
  for (let i = 0; i < start; i++) cells.push("<td class='cal-empty'></td>");
  for (let d = 1; d <= last.getDate(); d++) {
    const key = iso(new Date(y, m, d));
    cells.push(`<td class="cal-day${key === today() ? " cal-today" : ""}"><div class="cal-n">${d}</div>${(byDay[key] || []).map((a) =>
      `<a class="cal-item${a.closed ? " done" : ""}" href="#/activities?id=${a.clg_code}">${esc(a.begin_time || "")} ${esc(a.details)}</a>`).join("")}</td>`);
  }
  while (cells.length % 7) cells.push("<td class='cal-empty'></td>");
  const rows = [];
  for (let i = 0; i < cells.length; i += 7) rows.push(`<tr>${cells.slice(i, i + 7).join("")}</tr>`);
  const prev = new Date(y, m - 1, 1), next = new Date(y, m + 1, 1), ym = (d) => iso(d).slice(0, 7);
  c.innerHTML = `<div class="page-head"><div><h1>Calendar</h1><div class="sub">${first.toLocaleString("en", { month: "long", year: "numeric" })} — ${q.get("all") === "1" ? "all users" : "my activities"}</div></div>
      <span style="display:flex;gap:8px"><a class="btn ghost" href="#/calendar?month=${ym(prev)}">‹</a><a class="btn ghost" href="#/calendar">Today</a>
      <a class="btn ghost" href="#/calendar?month=${ym(next)}">›</a><a class="btn ghost" href="#/calendar?month=${ym(first)}&all=${q.get("all") === "1" ? 0 : 1}">${q.get("all") === "1" ? "Only mine" : "All users"}</a></span></div>
    <div class="card no-export"><table class="calendar"><thead><tr>${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => `<th>${d}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
};

views.pipeline = async (c) => {
  const p = await api("/crm/pipeline");
  const emp = (code) => ((state.master.sales_employees || []).find((e) => e.slp_code === code) || {}).slp_name || "—";
  const max = Math.max(1, ...p.stages.map((s) => Number(s.potential)));
  c.innerHTML = `<div class="page-head"><div><h1>Opportunity Pipeline</h1><div class="sub">Open opportunities by stage and sales employee; won / lost</div></div></div>
    <div class="tiles"><div class="tile"><div class="label">Open</div><div class="value">${fmt(p.open.potential)}</div><div class="foot">${p.open.count} opportunities, weighted ${fmt(p.open.weighted)}</div></div>
      <div class="tile"><div class="label">Won</div><div class="value good">${fmt(p.won.amount)}</div><div class="foot">${p.won.count}</div></div>
      <div class="tile"><div class="label">Lost</div><div class="value bad">${fmt(p.lost.amount)}</div><div class="foot">${p.lost.count}</div></div>
      <div class="tile"><div class="label">Win rate</div><div class="value">${p.win_rate == null ? "—" : `${Number(p.win_rate)} %`}</div></div></div>
    <div class="grid-2"><div class="card"><div class="card-head">By stage</div><table><thead><tr><th>Stage</th><th class="num">%</th><th class="num">Count</th><th class="num">Potential</th><th class="num">Weighted</th><th></th></tr></thead><tbody>
      ${p.stages.map((s) => `<tr><td>${esc(s.stage)}</td><td class="num">${Number(s.clo_prcnt)}</td><td class="num">${s.count}</td><td class="num">${fmt(s.potential)}</td><td class="num">${fmt(s.weighted)}</td>
        <td style="width:30%"><span class="ht" style="display:block"><span class="hf" style="width:${(Number(s.potential) / max) * 100}%"></span></span></td></tr>`).join("")
        || '<tr><td colspan="6" class="empty">No open opportunities.</td></tr>'}</tbody></table></div>
      <div class="card"><div class="card-head">By sales employee</div><table><thead><tr><th>Sales employee</th><th class="num">Count</th><th class="num">Potential</th><th class="num">Weighted</th></tr></thead><tbody>
      ${p.by_employee.map((e) => `<tr><td>${esc(emp(e.slp_code))}</td><td class="num">${e.count}</td><td class="num">${fmt(e.potential)}</td><td class="num">${fmt(e.weighted)}</td></tr>`).join("")
        || '<tr><td colspan="4" class="empty">—</td></tr>'}</tbody></table></div></div>`;
};
