/* Service: service calls (deadlines from the contract, activities, resolution), service contracts, customer equipment cards. */
"use strict";

const svcCustomers = () => state.partners.filter((p) => p.card_type === "C").map((p) => [p.card_code, `${p.card_code} — ${p.card_name}`]);
const svcItems = (items) => items.map((i) => [i.item_code, `${i.item_code} — ${i.item_name}`]);
const svcDt = (v) => (v ? String(v).replace("T", " ").slice(0, 16) : "");
const SVC_ST = { "-3": "O", "-2": "P", "-1": "C" };

views["service-calls"] = async (c) => {
  const q = query(), id = q.get("id");
  const filter = q.get("status") ?? "open";
  const [all, rep, techs, items, eqs] = await Promise.all([api("/service/calls"), api("/service/report"), api("/service/technicians"), api("/items"), api("/service/equipment")]);
  const list = all.filter((x) => filter === "all" || (filter === "open" ? x.status !== -1 : x.status === -1));
  const call = id ? all.find((x) => String(x.call_id) === id) : null;
  const techOpts = techs.map((u) => [u.user_id, `${u.user_code} — ${u.u_name}`]);
  const defs = [
    { k: "customer", label: "Customer", type: "select", options: svcCustomers, req: true, value: q.get("card") || "" },
    { k: "subject", label: "Subject", req: true, max: 254, span: 2 },
    { k: "ins_id", label: "Equipment card", type: "select", int: true, options: eqs.map((e) => [e.ins_id, `${e.internal_sn || e.manuf_sn} — ${e.item_code} (${e.customer})`]), value: q.get("ins") || "" },
    { k: "item_code", label: "Item", type: "select", options: svcItems(items) },
    { k: "internal_sn", label: "Serial number", max: 36 },
    { k: "origin", label: "Origin", type: "select", options: [["Phone", "Phone"], ["E-mail", "E-mail"], ["Web", "Web"], ["Visit", "Visit"]] },
    { k: "call_type", label: "Call type", type: "select", options: [["Repair", "Repair"], ["Installation", "Installation"], ["Maintenance", "Maintenance"], ["Inquiry", "Inquiry"]] },
    { k: "problem_typ", label: "Problem type", max: 50 },
    { k: "priority", label: "Priority", type: "select", blank: false, options: [["L", "Low"], ["M", "Medium"], ["H", "High"]], value: "M" },
    { k: "assignee", label: "Technician", type: "select", int: true, options: techOpts },
    { k: "descrption", label: "Description", type: "textarea", max: 1000, span: 3 },
  ];
  const editDefs = [
    { k: "subject", label: "Subject", req: true, max: 254, span: 2 },
    { k: "priority", label: "Priority", type: "select", blank: false, options: [["L", "Low"], ["M", "Medium"], ["H", "High"]] },
    { k: "assignee", label: "Technician", type: "select", int: true, options: techOpts },
    { k: "problem_typ", label: "Problem type", max: 50 },
    { k: "status", label: "Status", type: "select", int: true, blank: false, options: [[-3, "Open"], [-2, "Pending"], [-1, "Closed"]] },
    { k: "descrption", label: "Description", type: "textarea", max: 1000, span: 3 },
    { k: "resolution", label: "Resolution", type: "textarea", max: 1000, span: 3 },
  ];
  const late = (x) => (x.resolution_late ? ' <span class="status X">late</span>' : "");
  c.innerHTML = `<div class="page-head"><div><h1>Service Calls</h1><div class="sub">Customer problems with deadlines from the service contract</div></div>
      <span style="display:flex;gap:8px">${["open", "closed", "all"].map((f) => `<a class="btn ${f === filter ? "secondary" : "ghost"}" href="#/service-calls?status=${f}">${f[0].toUpperCase() + f.slice(1)}</a>`).join("")}
      <a class="btn" href="#/service-calls?id=">+ New service call</a></span></div>
    <div class="tiles"><div class="tile"><div class="label">Open</div><div class="value">${rep.open}</div></div>
      <div class="tile"><div class="label">Pending</div><div class="value">${rep.pending}</div></div>
      <div class="tile"><div class="label">Resolution overdue</div><div class="value">${rep.late}</div></div>
      <div class="tile"><div class="label">Closed · avg. hours</div><div class="value">${rep.closed} · ${rep.avg_hours ?? "-"}</div></div></div>
    <div class="card"><table><thead><tr><th>No.</th><th>Created</th><th>Customer</th><th>Subject</th><th>Item / serial no.</th><th>Priority</th><th>Technician</th><th>Contract</th><th>Resolve by</th><th>Status</th></tr></thead><tbody>
      ${list.map((x) => `<tr style="cursor:pointer" onclick="location.hash='#/service-calls?id=${x.call_id}'"><td>${x.call_id}</td><td>${svcDt(x.create_date)}</td><td>${esc(x.card_name || x.customer)}</td>
        <td>${esc(x.subject)}</td><td>${esc(x.item_code || "")} ${esc(x.internal_sn || "")}</td><td>${x.priority_name}</td><td>${esc(x.assignee_code || "")}</td><td>${x.contract || ""}</td>
        <td>${svcDt(x.resol_by)}</td><td><span class="status ${SVC_ST[x.status]}">${x.status_name}</span>${late(x)}</td></tr>`).join("") || '<tr><td colspan="10" class="empty">No service calls.</td></tr>'}</tbody></table></div>
    ${rep.by_technician.length ? `<div class="card"><div class="card-head">Open calls by technician</div><table><thead><tr><th>Technician</th><th class="num">Open</th><th class="num">Overdue</th></tr></thead><tbody>
      ${rep.by_technician.map((t) => `<tr><td>${esc(t.technician)}</td><td class="num">${t.open}</td><td class="num">${t.late}</td></tr>`).join("")}</tbody></table></div>` : ""}
    ${id === "" ? `<div class="card"><div class="card-head">New service call</div><div class="card-body"><div class="form-grid">${fieldsHtml(defs, {}, "sc")}</div>
      <p class="help">An equipment card fills in the item and serial number. The customer's approved contract that covers the call sets the response and resolution deadlines.</p>
      <button class="btn" id="sc-add" style="margin-top:8px">Add</button></div></div>` : ""}
    ${call ? `<div class="card"><div class="card-head"><span>Service call ${call.call_id}: ${esc(call.subject)} — ${esc(call.card_name || call.customer)} <span class="status ${SVC_ST[call.status]}">${call.status_name}</span></span>
        <span class="help">${call.contract ? `contract ${call.contract} · respond by ${svcDt(call.response_by)}${call.response_late ? " (late)" : ""} · resolve by ${svcDt(call.resol_by)}${call.resolution_late ? " (late)" : ""}` : "no service contract"}
        ${call.responded ? ` · responded ${svcDt(call.responded)}` : ""}${call.close_date ? ` · closed ${svcDt(call.close_date)}` : ""}</span></div>
      <div class="card-body"><p class="help">${esc(call.item_code || "")} ${call.internal_sn ? `serial ${esc(call.internal_sn)}` : ""}${call.ins_id ? ` · <a href="#/equipment?id=${call.ins_id}">equipment card ${call.ins_id}</a>` : ""}
        ${call.origin ? ` · ${esc(call.origin)}` : ""}${call.call_type ? ` · ${esc(call.call_type)}` : ""}</p>
        <div class="form-grid">${fieldsHtml(editDefs, call, "se")}</div>
        <div style="display:flex;gap:8px;margin-top:8px"><button class="btn" id="se-save">Update</button>
          ${call.status !== -1 && !call.responded ? '<button class="btn secondary" id="se-resp">Mark responded</button>' : ""}
          <a class="btn ghost" href="#/activities?id=&call=${call.call_id}&card=${encodeURIComponent(call.customer)}">+ Activity</a></div>
        <h3 class="section">Activities</h3><table><tbody>${call.activities.map((a) => `<tr style="cursor:pointer" onclick="location.hash='#/activities?id=${a.clg_code}'">
          <td>${a.recontact} ${esc(a.begin_time || "")}</td><td>${esc(a.action_name)}</td><td>${esc(a.details)}</td><td>${esc(a.attend_code || "")}</td><td>${a.closed ? "done" : ""}</td></tr>`).join("")
          || '<tr><td class="empty">No activities.</td></tr>'}</tbody></table></div></div>` : ""}`;
  if ($("#sc-add")) {
    $("#sc-ins_id").onchange = () => {
      const e = eqs.find((x) => String(x.ins_id) === $("#sc-ins_id").value);
      if (e) { $("#sc-customer").value = e.customer; $("#sc-item_code").value = e.item_code; $("#sc-internal_sn").value = e.internal_sn || ""; }
    };
    $("#sc-add").onclick = async () => {
      const r = await act(() => post("/service/calls", readFields(defs, "sc")), (x) => `Service call ${x.call_id} added${x.contract ? ` (contract ${x.contract})` : ""}`);
      if (r) { location.hash = `#/service-calls?id=${r.call_id}`; if (typeof refreshAlertBell === "function") refreshAlertBell(); }
    };
  }
  if (!call) return;
  const reload = () => { location.hash = `#/service-calls?id=${call.call_id}&r=${Date.now()}`; if (typeof refreshAlertBell === "function") refreshAlertBell(); };
  $("#se-save").onclick = async () => { if (await act(() => patch(`/service/calls/${call.call_id}`, readFields(editDefs, "se")), "Service call updated")) reload(); };
  if ($("#se-resp")) $("#se-resp").onclick = async () => { if (await act(() => patch(`/service/calls/${call.call_id}`, { responded: true }), "Response recorded")) reload(); };
};

views["service-contracts"] = async (c) => {
  const q = query(), id = q.get("id");
  const [list, items] = await Promise.all([api("/service/contracts"), api("/items")]);
  const ct = id ? list.find((x) => String(x.contract_id) === id) : null;
  const CS = { A: "O", F: "P", D: "P", T: "X" };
  const defs = [
    { k: "cstmr_code", label: "Customer", type: "select", options: svcCustomers, req: true },
    { k: "cntrc_type", label: "Contract type", type: "select", blank: false, options: [["C", "Customer (all items)"], ["I", "Items"], ["S", "Serial numbers"]], value: "C" },
    { k: "status", label: "Status", type: "select", blank: false, options: [["A", "Approved"], ["F", "On hold"], ["D", "Draft"], ["T", "Terminated"]], value: "A" },
    { k: "start_date", label: "Start date", type: "date", req: true, value: today() }, { k: "end_date", label: "End date", type: "date", req: true },
    { k: "rspns_time", label: "Response time (hours)", type: "number", step: 1, min: 0 }, { k: "resol_time", label: "Resolution time (hours)", type: "number", step: 1, min: 0 },
    { k: "incl_parts", label: "Parts included", type: "check", value: true }, { k: "incl_labor", label: "Labor included", type: "check", value: true },
    { k: "incl_travel", label: "Travel included", type: "check" }, { k: "descriptio", label: "Description", max: 254, span: 3 },
  ];
  const lines = ct ? ct.lines : [];
  const lineRow = (l = {}) => `<tr><td><select class="cl-item">${opt("", "")}${svcItems(items).map(([v, t]) => opt(v, t, l.item_code)).join("")}</select></td>
    <td><input class="cl-sn" maxlength="36" value="${esc(l.internal_sn || "")}"></td><td><button class="btn ghost cl-del" type="button">×</button></td></tr>`;
  c.innerHTML = `<div class="page-head"><div><h1>Service Contracts</h1><div class="sub">Coverage and response / resolution times per customer, item or serial number</div></div>
      <a class="btn" href="#/service-contracts?id=">+ New contract</a></div>
    <div class="card"><table><thead><tr><th>No.</th><th>Customer</th><th>Type</th><th>From</th><th>To</th><th class="num">Response h</th><th class="num">Resolution h</th><th>Covers</th><th>Status</th></tr></thead><tbody>
      ${list.map((x) => `<tr style="cursor:pointer" onclick="location.hash='#/service-contracts?id=${x.contract_id}'"><td>${x.contract_id}</td><td>${esc(x.card_name || x.cstmr_code)}</td><td>${x.type_name}</td>
        <td>${x.start_date}</td><td>${x.end_date}</td><td class="num">${x.rspns_time ?? ""}</td><td class="num">${x.resol_time ?? ""}</td>
        <td>${x.lines.map((l) => esc([l.item_code, l.internal_sn].filter(Boolean).join(" "))).join(", ")}</td><td><span class="status ${CS[x.status]}">${x.status_name}</span></td></tr>`).join("")
        || '<tr><td colspan="9" class="empty">No service contracts.</td></tr>'}</tbody></table></div>
    ${id !== null ? `<div class="card"><div class="card-head">${ct ? `Service contract ${ct.contract_id}` : "New service contract"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(defs, ct || {}, "ct")}</div>
      <h3 class="section">Covered items / serial numbers (item and serial number contracts)</h3>
      <table><thead><tr><th>Item</th><th>Serial number</th><th></th></tr></thead><tbody id="cl-rows">${(lines.length ? lines : [{}]).map(lineRow).join("")}</tbody></table>
      <div style="display:flex;gap:8px;margin-top:8px"><button class="btn ghost" id="cl-add" type="button">+ Line</button><button class="btn" id="ct-save">${ct ? "Update" : "Add"}</button></div></div></div>` : ""}`;
  if (!$("#ct-save")) return;
  const bindDel = () => $$(".cl-del").forEach((b) => (b.onclick = () => b.closest("tr").remove()));
  bindDel();
  $("#cl-add").onclick = () => { $("#cl-rows").insertAdjacentHTML("beforeend", lineRow()); bindDel(); };
  $("#ct-save").onclick = async () => {
    const body = readFields(defs, "ct");
    body.lines = $$("#cl-rows tr").map((r) => ({ item_code: $(".cl-item", r).value || null, internal_sn: $(".cl-sn", r).value.trim() || null }));
    const r = ct ? await act(() => patch(`/service/contracts/${ct.contract_id}`, body), "Contract updated")
      : await act(() => post("/service/contracts", body), (x) => `Service contract ${x.contract_id} added`);
    if (r) location.hash = `#/service-contracts?id=${r.contract_id}&r=${Date.now()}`;
  };
};

views.equipment = async (c) => {
  const q = query(), id = q.get("id");
  const [list, items] = await Promise.all([api("/service/equipment"), api("/items")]);
  const eq = id ? list.find((x) => String(x.ins_id) === id) : null;
  const defs = [
    { k: "customer", label: "Customer", type: "select", options: svcCustomers, req: true },
    { k: "item_code", label: "Item", type: "select", options: svcItems(items), req: true },
    { k: "manuf_sn", label: "Mfr serial no.", max: 36 }, { k: "internal_sn", label: "Serial number", max: 36 },
    { k: "status", label: "Status", type: "select", blank: false, options: [["A", "Active"], ["R", "Returned"], ["T", "Terminated"], ["L", "Loaned"], ["I", "In repair lab"]], value: "A" },
    { k: "street", label: "Street (installed at)", max: 100 }, { k: "city", label: "City", max: 100 },
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Customer Equipment Cards</h1><div class="sub">Serial numbers delivered to customers — created by deliveries, or entered by hand</div></div>
      <a class="btn" href="#/equipment?id=">+ New equipment card</a></div>
    <div class="card"><table><thead><tr><th>No.</th><th>Serial no.</th><th>Item</th><th>Customer</th><th>Delivered</th><th>Contract</th><th>Status</th></tr></thead><tbody>
      ${list.map((x) => `<tr style="cursor:pointer" onclick="location.hash='#/equipment?id=${x.ins_id}'"><td>${x.ins_id}</td><td>${esc(x.internal_sn || x.manuf_sn)}</td><td>${esc(x.item_code)} ${esc(x.item_name || "")}</td>
        <td>${esc(x.card_name || x.customer)}</td><td>${x.dlv_date ? `${x.dlv_date} ${docLink(x.dlv_type, x.dlv_entry, transTypeName(x.dlv_type))}` : ""}</td>
        <td>${x.contract ? `${x.contract} (until ${x.contract_end})` : ""}</td><td>${x.status_name}</td></tr>`).join("") || '<tr><td colspan="7" class="empty">No equipment cards.</td></tr>'}</tbody></table></div>
    ${id !== null ? `<div class="card"><div class="card-head">${eq ? `Equipment card ${eq.ins_id}` : "New equipment card"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(defs, eq || {}, "eq")}</div>
      <div style="display:flex;gap:8px;margin-top:8px"><button class="btn" id="eq-save">${eq ? "Update" : "Add"}</button>
        ${eq ? `<a class="btn ghost" href="#/service-calls?id=&ins=${eq.ins_id}&card=${encodeURIComponent(eq.customer)}">+ Service call</a>` : ""}</div>
      ${eq ? `<h3 class="section">Service calls</h3><table><tbody>${eq.calls.map((x) => `<tr style="cursor:pointer" onclick="location.hash='#/service-calls?id=${x.call_id}'">
        <td>${x.call_id}</td><td>${svcDt(x.create_date)}</td><td>${esc(x.subject)}</td><td>${x.status_name}</td></tr>`).join("") || '<tr><td class="empty">No service calls.</td></tr>'}</tbody></table>` : ""}</div></div>` : ""}`;
  if (!$("#eq-save")) return;
  $("#eq-save").onclick = async () => {
    const body = readFields(defs, "eq");
    const r = eq ? await act(() => patch(`/service/equipment/${eq.ins_id}`, body), "Equipment card updated")
      : await act(() => post("/service/equipment", body), (x) => `Equipment card ${x.ins_id} added`);
    if (r) location.hash = `#/equipment?id=${r.ins_id}&r=${Date.now()}`;
  };
};
