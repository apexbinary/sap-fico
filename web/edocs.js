/* India e-documents: e-invoice (IRN, QR) and e-way bill panel on A/R invoices, credit memos and
   deliveries; Administration -> E-Documents (settings, register, documents still needing one). */
"use strict";

const EDOC_OBJS = ["13", "14", "15"];
const dt = (v) => (v ? String(v).replace("T", " ").slice(0, 16) : "");

async function edocPanel(el, t, d) {
  if (!EDOC_OBJS.includes(t.obj) || d.canceled) return;
  const box = document.createElement("div");
  el.appendChild(box);
  const base = `/documents/${t.obj}/${d.doc_entry}`;
  const render = async () => {
    const s = await api(`${base}/edocs`);
    const canChange = may(areaOfObj(t.obj), "F");
    const reasons = Object.entries(s.cancel_reasons);
    const test = s.settings.mode === "T";
    const irn = s.irn, ewb = s.ewb;
    const trDefs = [
      { k: "trans_mode", label: "Transport mode", type: "select", blank: false, options: Object.entries(s.trans_modes), value: "1" },
      { k: "distance", label: "Distance (km)", type: "number", step: 1, min: 1, maxv: 4000, req: true },
      { k: "vehicle_no", label: "Vehicle no.", max: 20 },
      { k: "vehicle_type", label: "Vehicle type", type: "select", blank: false, options: Object.entries(s.vehicle_types), value: "R" },
      { k: "transporter_id", label: "Transporter ID (GSTIN)", max: 15 }, { k: "transporter_name", label: "Transporter name", max: 100 },
      { k: "trans_doc_no", label: "Transport doc. no. (RR / AWB / BL)", max: 15 }, { k: "trans_doc_date", label: "Transport doc. date", type: "date" },
    ];
    const cancelDefs = () => [{ k: "reason", label: "Cancel reason", type: "select", blank: false, options: reasons },
      { k: "remark", label: "Remark", max: 100, req: true }];
    const irnPart = !s.einvoice_applicable ? "" : `<h3 class="section">E-invoice (IRN)${test ? ' <span class="status X">TEST mode</span>' : ""}</h3>
      ${!s.settings.e_invoice ? '<div class="help">E-invoicing is not active (Administration → E-Documents).</div>' : irn ? `
        <div class="edoc-irn"><div>${s.qr_svg || ""}</div><div>
          <div>IRN <span class="mono">${esc(irn.irn)}</span></div><div>Ack. no. <b>${esc(irn.ack_no)}</b> · ${dt(irn.ack_date)} · ${irn.mode === "T" ? "test" : "IRP"}</div>
          ${irn.cancelable && canChange ? `<div class="form-grid" style="margin-top:8px">${fieldsHtml(cancelDefs(), {}, "ic")}</div>
            <button class="btn small secondary" id="ic-go">Cancel IRN</button> <span class="help">possible within 24 hours of the acknowledgement</span>`
            : '<div class="help">The IRN can no longer be canceled (24 hours passed); correct the invoice with a credit memo.</div>'}</div></div>`
      : `${s.einvoice_issues.length ? `<ul class="gr-issues">${s.einvoice_issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : '<div class="help">Ready to register.</div>'}
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
          <a class="btn small secondary" href="/api${base}/einvoice/json" download>Download e-invoice JSON</a>
          ${canChange && test && !s.einvoice_issues.length ? '<button class="btn small" id="irn-go">Generate IRN (test)</button>' : ""}
          ${canChange && !test ? '<button class="btn small" id="irn-imp">Import IRP response</button>' : ""}</div>
        ${canChange && !test ? '<textarea id="irn-resp" rows="3" style="width:100%;margin-top:6px" placeholder="Paste the IRP response JSON (Irn, AckNo, AckDt, SignedQRCode)"></textarea>' : ""}`}`;
    const ewbPart = !s.ewb_applicable ? "" : `<h3 class="section">E-way bill${test ? ' <span class="status X">TEST mode</span>' : ""}
        ${s.ewb_required && !ewb ? ' <span class="status O">required: goods above 50,000</span>' : ""}</h3>
      ${!s.settings.e_way_bill ? '<div class="help">E-way bills are not active (Administration → E-Documents).</div>' : ewb ? `
        <div>EWB no. <b class="mono">${esc(ewb.ewb_no)}</b> · ${dt(ewb.ewb_date)} · ${ewb.valid_until ? `valid until <b>${dt(ewb.valid_until)}</b>` : '<span class="status X">Part B missing: not valid for movement</span>'}
          ${ewb.expired ? ' <span class="status X">expired</span>' : ""}</div>
        <div class="help">${esc(s.trans_modes[ewb.trans_mode] || "")}, ${ewb.distance} km${ewb.vehicle_no ? `, vehicle ${esc(ewb.vehicle_no)}` : ""}${ewb.transporter_name ? `, ${esc(ewb.transporter_name)}` : ""}</div>
        ${canChange && !ewb.expired ? `<div class="form-grid" style="margin-top:8px">${fieldsHtml([trDefs[2], trDefs[0]], { vehicle_no: "", trans_mode: ewb.trans_mode }, "ev")}</div>
          <button class="btn small secondary" id="ev-go">Update vehicle (Part B)</button>` : ""}
        ${ewb.cancelable && canChange ? `<div class="form-grid" style="margin-top:8px">${fieldsHtml(cancelDefs(), {}, "ec")}</div>
          <button class="btn small secondary" id="ec-go">Cancel e-way bill</button>` : ""}`
      : canChange ? `<div class="form-grid">${fieldsHtml(trDefs, {}, "et")}</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
          <button class="btn small secondary" id="et-json">Download e-way bill JSON</button>
          ${test ? '<button class="btn small" id="et-go">Generate e-way bill (test)</button>' : '<button class="btn small" id="et-imp">Import portal response</button>'}</div>
        ${!test ? '<textarea id="et-resp" rows="2" style="width:100%;margin-top:6px" placeholder=\'Paste the response, e.g. {"ewayBillNo": 331000123456, "ewayBillDate": "03/11/2026 10:15:00 AM", "validUpto": "04/11/2026 11:59:00 PM"}\'></textarea>' : ""}`
      : '<div class="help">No e-way bill.</div>'}`;
    const hist = s.history.filter((h) => h.status === "C");
    box.innerHTML = irnPart || ewbPart ? `<div class="card"><div class="card-head">E-documents (GST)</div><div class="card-body">${irnPart}${ewbPart}
      ${hist.length ? `<h3 class="section">Canceled</h3><table><tbody>${hist.map((h) => `<tr><td>${h.kind_name}</td><td class="mono">${esc(h.irn || h.ewb_no)}</td>
        <td>${dt(h.cancel_date)}</td><td>${esc(s.cancel_reasons[h.cancel_reason] || "")}: ${esc(h.cancel_remark || "")}</td></tr>`).join("")}</tbody></table>` : ""}</div></div>` : "";
    const run = async (fn, msg) => { if (await act(fn, msg)) render(); };
    const json = (id) => { try { return JSON.parse($(id).value); } catch (e) { toast("The response is not valid JSON", "bad"); return null; } };
    const on = (id, f) => { const b = $(id); if (b) b.onclick = f; };
    on("#irn-go", () => run(() => post(`${base}/einvoice`, {}), "IRN generated"));
    on("#irn-imp", () => { const r = json("#irn-resp"); if (r) run(() => post(`${base}/einvoice/import`, r), "IRP response imported"); });
    on("#ic-go", () => run(() => post(`${base}/einvoice/cancel`, readFields(cancelDefs(), "ic")), "IRN canceled"));
    on("#et-go", () => run(() => post(`${base}/ewaybill`, readFields(trDefs, "et")), "E-way bill generated"));
    on("#et-imp", () => { const r = json("#et-resp"); if (r) run(() => post(`${base}/ewaybill/import`, { ...readFields(trDefs, "et"), response: r }), "E-way bill imported"); });
    on("#et-json", async () => {
      try {
        const res = await fetch(`/api${base}/ewaybill/json`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(readFields(trDefs, "et")) });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || res.statusText);
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([JSON.stringify(body, null, 2)], { type: "application/json" }));
        a.download = `EWB_${t.obj}_${d.doc_num}.json`; a.click(); URL.revokeObjectURL(a.href);
      } catch (e) { toast(e.message, "bad"); }
    });
    on("#ev-go", () => run(() => post(`${base}/ewaybill/vehicle`, readFields([trDefs[2], trDefs[0]], "ev")), "Vehicle updated"));
    on("#ec-go", () => run(() => post(`${base}/ewaybill/cancel`, readFields(cancelDefs(), "ec")), "E-way bill canceled"));
  };
  await render().catch((e) => (box.innerHTML = `<div class="empty">E-documents: ${esc(e.message)}</div>`));
}

views["e-documents"] = async (c) => {
  const since = query().get("since") || new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10);
  const data = await api(`/e-documents?since=${since}`);
  const st = data.settings;
  const defs = [
    { k: "e_invoice", label: "E-invoicing (IRN) active", type: "check" }, { k: "e_way_bill", label: "E-way bills active", type: "check" },
    { k: "mode", label: "Mode", type: "select", blank: false, options: [["T", "Test (IRN / EWB made here, marked TEST)"], ["L", "Live (JSON to the portal / GSP, import the response)"]] },
    { k: "street", label: "Company street (ADM1)", max: 100 }, { k: "city", label: "City", max: 100, req: true },
    { k: "zip_code", label: "PIN code", max: 6, req: true },
  ];
  const docName = (o) => ({ "13": "A/R Invoice", "14": "A/R Credit Memo", "15": "Delivery" }[o] || o);
  c.innerHTML = `<div class="page-head"><div><h1>E-Documents</h1><div class="sub">GST e-invoicing (IRN, signed QR code) and e-way bills — settings, register and documents still needing one</div></div></div>
    <div class="card"><div class="card-head">Settings</div><div class="card-body"><div class="form-grid">${fieldsHtml(defs, st, "es")}</div>
      <div class="help">E-invoicing applies to B2B, SEZ and export invoices / credit notes of companies above the turnover limit (5 crore); e-way bills to the movement of goods above 50,000.
        Live mode needs a GST Suvidha Provider (GSP) account: send the downloaded JSON and import the response here.</div>
      <button class="btn" id="es-save" style="margin-top:8px">Update</button></div></div>
    <div class="card"><div class="card-head">Documents without the needed IRN / e-way bill since <input type="date" id="es-since" value="${esc(since)}"></div>
      <table><thead><tr><th>Document</th><th>No.</th><th>Date</th><th>Customer</th><th class="num">Total</th><th>Needs</th></tr></thead><tbody>
      ${data.pending.map((p) => `<tr style="cursor:pointer" onclick="location.hash='#/docs?obj=${p.obj_type}&entry=${p.doc_entry}'"><td>${docName(p.obj_type)}</td><td>${p.doc_num}</td>
        <td>${p.doc_date}</td><td>${esc(p.card_name || p.card_code)}</td><td class="num">${fmt(p.doc_total)}</td><td>${p.needs.map((n) => `<span class="status O">${n}</span>`).join(" ")}</td></tr>`).join("")
        || '<tr><td colspan="6" class="empty">Nothing pending.</td></tr>'}</tbody></table></div>
    <div class="card"><div class="card-head">Register</div><div style="overflow-x:auto"><table><thead><tr><th>Type</th><th>Document</th><th>No.</th><th>Customer</th><th>IRN / EWB no.</th>
      <th>Ack. no.</th><th>Generated</th><th>Valid until</th><th>Mode</th><th>Status</th></tr></thead><tbody>
      ${data.register.map((e) => `<tr style="cursor:pointer" onclick="location.hash='#/docs?obj=${e.obj_type}&entry=${e.doc_entry}'"><td>${e.kind_name}</td><td>${docName(e.obj_type)}</td>
        <td>${e.doc_num ?? ""}</td><td>${esc(e.card_name || "")}</td><td class="mono">${esc(e.kind === "I" ? `${e.irn.slice(0, 16)}…` : e.ewb_no)}</td><td>${esc(e.ack_no || "")}</td>
        <td>${dt(e.ack_date || e.ewb_date)}</td><td>${dt(e.valid_until)}</td><td>${e.mode === "T" ? "Test" : "Live"}</td>
        <td>${e.status === "A" ? (e.expired ? '<span class="status X">Expired</span>' : '<span class="status O">Active</span>') : '<span class="status C">Canceled</span>'}</td></tr>`).join("")
        || '<tr><td colspan="10" class="empty">No e-documents yet.</td></tr>'}</tbody></table></div></div>`;
  $("#es-save").onclick = async () => { if (await act(() => api("/admin/e-documents", { method: "PUT", body: JSON.stringify(readFields(defs, "es")) }), "Settings saved")) views["e-documents"](c); };
  $("#es-since").onchange = (e) => { location.hash = `#/e-documents?since=${e.target.value}`; };
};
