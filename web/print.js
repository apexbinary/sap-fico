/* Printable document (GST layout): opened from a document's "Print / PDF" button; the browser
   prints it or saves it as PDF. The layout (RDOC) of the document type sets the template style,
   accent colour, logo and optional sections; Administration -> Print Layouts maintains them. */
"use strict";

views.print = async (c) => {
  const obj = query().get("obj"), entry = query().get("entry"), chosen = query().get("layout");
  const p = await api(`/documents/${obj}/${entry}/print${chosen ? `?layout=${encodeURIComponent(chosen)}` : ""}`);
  const L = p.layout;
  const money = (n) => fmt(n);
  const pct = (t) => (t ? `${Number(t[0])}%` : "");
  const amt = (t) => (t ? money(t[1]) : "");
  const gstIntra = p.supply !== "inter-state";
  const party = (title, x) => `<div class="pp-box"><div class="pp-label">${title}</div><b>${esc(x.name || "")}</b>
    <div>${esc(x.address || "")}</div>${x.gstin ? `<div>GSTIN: <b>${esc(x.gstin)}</b></div>` : ""}
    ${x.state ? `<div>State: ${esc(x.state)}${x.state_code ? ` (${esc(x.state_code)})` : ""}</div>` : ""}</div>`;
  const taxHead = p.no_prices ? "" : gstIntra ? '<th class="num">CGST</th><th class="num">SGST</th>' : '<th class="num">IGST</th>';
  const layoutPick = p.layouts.length > 1 ? `<label class="pp-pick">Layout <select id="pp-layout">${p.layouts.map((l) =>
    opt(l.doc_code, `${l.doc_name}${l.default ? " (default)" : ""}`, L.doc_code)).join("")}</select></label>` : "";
  c.innerHTML = `<div class="page-head no-print"><div><h1>${esc(p.title)} ${p.doc_num}</h1><div class="sub">Print preview — layout ${esc(L.doc_name)} · use Print and choose "Save as PDF" for a PDF</div></div>
      <span style="display:flex;gap:8px;align-items:center">${layoutPick}<a class="btn secondary" href="#/docs?obj=${obj}&entry=${entry}">Back</a><button class="btn" onclick="window.print()">Print / PDF</button></span></div>
    <div class="print-page pp-${esc(L.style)}" style="--pp-accent:${esc(L.color)}">
      <div class="pp-head"><div class="pp-brand">${p.company.logo ? `<img class="pp-logo" src="${esc(p.company.logo)}" alt="">` : ""}
        <div><div class="pp-company">${esc(p.company.name)}</div><div>${esc(p.company.address || "")}</div>
        <div>GSTIN: <b>${esc(p.company.gstin || "")}</b>${p.company.state ? ` · State: ${esc(p.company.state)} (${esc(p.company.state_code || "")})` : ""}</div>
        <div>${esc([p.company.phone, p.company.e_mail].filter(Boolean).join(" · "))}</div></div></div>
        <div class="pp-title">${esc(p.title)}${p.canceled ? '<div class="pp-cancel">CANCELED</div>' : ""}
          ${p.edoc && p.edoc.qr_svg ? `<div class="pp-qr">${p.edoc.qr_svg}${p.edoc.test ? '<div class="pp-test">TEST</div>' : ""}</div>` : ""}</div></div>
      ${p.edoc ? `<div class="pp-edoc">${p.edoc.irn ? `<div>IRN: <span class="mono">${esc(p.edoc.irn)}</span></div>
        <div>Ack. no.: <b>${esc(p.edoc.ack_no)}</b> · Ack. date: ${esc(String(p.edoc.ack_date).replace("T", " ").slice(0, 16))}${p.edoc.test ? " · <b>TEST — not registered with the IRP</b>" : ""}</div>` : ""}
        ${p.edoc.ewb_no ? `<div>E-way bill: <b>${esc(p.edoc.ewb_no)}</b> · ${esc(String(p.edoc.ewb_date).replace("T", " ").slice(0, 16))}${p.edoc.valid_until ? ` · valid until ${esc(String(p.edoc.valid_until).replace("T", " ").slice(0, 16))}` : ""}${p.edoc.vehicle_no ? ` · vehicle ${esc(p.edoc.vehicle_no)}` : ""}${p.edoc.ewb_test ? " · TEST" : ""}</div>` : ""}</div>` : ""}
      <div class="pp-grid">
        <div class="pp-box"><table class="pp-kv"><tbody>
          <tr><td>No.</td><td><b>${p.doc_num}</b></td></tr><tr><td>Date</td><td>${p.doc_date}</td></tr>
          ${p.no_prices ? "" : `<tr><td>${p.obj === "13" || p.obj === "18" ? "Due date" : "Valid / delivery"}</td><td>${p.doc_due_date}</td></tr>`}
          ${p.num_at_card ? `<tr><td>Your reference</td><td>${esc(p.num_at_card)}</td></tr>` : ""}
          ${p.place_of_supply ? `<tr><td>Place of supply</td><td>${esc(p.place_of_supply)} (${esc(p.supply || "")})</td></tr>` : ""}
          ${p.currency !== state.company.main_curncy ? `<tr><td>Currency</td><td>${esc(p.currency)} @ ${Number(p.rate)}</td></tr>` : ""}</tbody></table></div>
        ${party("Bill to", p.bill_to)}${party("Ship to", p.ship_to)}</div>
      <table class="pp-lines"><thead><tr><th>#</th><th>Description</th><th>HSN/SAC</th><th class="num">Qty</th><th>UoM</th>
        ${p.no_prices ? "" : '<th class="num">Rate</th><th class="num">Disc. %</th><th class="num">Taxable value</th>'}${taxHead}${p.no_prices ? "" : '<th class="num">Total</th>'}</tr></thead>
        <tbody>${p.lines.map((l) => `<tr><td>${l.line}</td><td>${esc(l.description || "")}${l.item_code ? `<div class="help">${esc(l.item_code)}</div>` : ""}</td>
          <td>${esc(l.hsn || "")}</td><td class="num">${qtyFmt(l.quantity)}</td><td>${esc(l.uom || "")}</td>
          ${p.no_prices ? "" : `<td class="num">${money(l.rate)}</td><td class="num">${Number(l.disc_prcnt) ? Number(l.disc_prcnt) : ""}</td><td class="num">${money(l.taxable)}</td>`}
          ${p.no_prices ? "" : gstIntra ? `<td class="num">${pct(l.cgst)}<div>${amt(l.cgst)}</div></td><td class="num">${pct(l.sgst)}<div>${amt(l.sgst)}</div></td>`
            : `<td class="num">${pct(l.igst)}<div>${amt(l.igst)}</div></td>`}
          ${p.no_prices ? "" : `<td class="num">${money(l.total)}</td>`}</tr>`).join("")}</tbody></table>
      ${p.no_prices ? "" : `<div class="pp-grid2">
        <div>${L.show_hsn ? `<div class="pp-label">HSN / SAC summary</div><table class="pp-lines"><thead><tr><th>HSN/SAC</th><th class="num">Taxable value</th>
          ${gstIntra ? '<th class="num">CGST</th><th class="num">SGST</th>' : '<th class="num">IGST</th>'}<th class="num">Total tax</th></tr></thead><tbody>
          ${p.hsn_summary.map((h) => { const t = Number(h.CGST || 0) + Number(h.SGST || 0) + Number(h.IGST || 0);
            return `<tr><td>${esc(h.hsn)}</td><td class="num">${money(h.taxable)}</td>${gstIntra ? `<td class="num">${money(h.CGST || 0)}</td><td class="num">${money(h.SGST || 0)}</td>`
              : `<td class="num">${money(h.IGST || 0)}</td>`}<td class="num">${money(t)}</td></tr>`; }).join("")}</tbody></table>` : ""}</div>
        <div><table class="pp-kv pp-totals"><tbody>
          <tr><td>Total before discount</td><td class="num">${money(p.totals.before_discount)}</td></tr>
          ${Number(p.totals.discount) ? `<tr><td>Discount ${Number(p.totals.disc_prcnt)}%</td><td class="num">-${money(p.totals.discount)}</td></tr>` : ""}
          <tr><td>Tax</td><td class="num">${money(p.totals.tax)}</td></tr>
          ${Number(p.totals.wt) ? `<tr><td>Total before TDS</td><td class="num">${money(Number(p.totals.total) + Number(p.totals.wt))}</td></tr>
            <tr><td>Less TDS deducted</td><td class="num">-${money(p.totals.wt)}</td></tr>` : ""}
          <tr class="pp-grand"><td>${Number(p.totals.wt) ? "Amount payable" : "Total"} (${esc(p.currency)})</td><td class="num">${money(p.totals.total)}</td></tr>
          ${Number(p.totals.paid) ? `<tr><td>Paid</td><td class="num">${money(p.totals.paid)}</td></tr><tr><td>Balance due</td><td class="num">${money(p.totals.total - p.totals.paid)}</td></tr>` : ""}</tbody></table></div></div>
      <div class="pp-words">Amount in words: <b>${esc(p.amount_in_words)}</b></div>`}
      <div class="pp-grid2 pp-foot">
        <div>${p.payment_terms && !p.no_prices ? `<div>Payment terms: ${esc(p.payment_terms)}</div>` : ""}
          ${L.show_bank && p.bank && ["13", "23", "17"].includes(p.obj) ? `<div>Bank: ${esc(p.bank.name)} · A/c ${esc(p.bank.account)} · IFSC ${esc(p.bank.branch || "")}</div>` : ""}
          ${p.comments ? `<div>Remarks: ${esc(p.comments)}</div>` : ""}
          ${p.obj === "13" ? "<div class=\"help\">This is a computer generated invoice.</div>" : ""}</div>
        ${L.show_sign ? `<div class="pp-sign">For ${esc(p.company.name)}<br><br><br>Authorised Signatory</div>` : "<div></div>"}</div>
      ${L.footer ? `<div class="pp-footer">${esc(L.footer)}</div>` : ""}
    </div>`;
  if ($("#pp-layout")) $("#pp-layout").onchange = (e) => { location.hash = `#/print?obj=${obj}&entry=${entry}&layout=${encodeURIComponent(e.target.value)}`; };
};

/* Administration -> Print Layouts: layouts per document type (RDOC) and the company logo. */
views["print-layouts"] = async (c) => {
  const [data, logo] = await Promise.all([api("/print-layouts"), api("/admin/company/logo")]);
  const code = query().get("code");
  const edit = code && data.layouts.find((l) => l.doc_code === code);
  const types = Object.entries(data.types), styles = Object.entries(data.styles);
  const defs = [
    { k: "doc_code", label: "Layout code", req: true, max: 20, ro: !!edit },
    { k: "doc_name", label: "Layout name", req: true, max: 100 },
    { k: "type_code", label: "Document type", type: "select", blank: false, options: types, ro: !!edit },
    { k: "style", label: "Template style", type: "select", blank: false, options: styles },
    { k: "footer", label: "Footer text", type: "textarea", max: 254, span: 2 },
    { k: "show_logo", label: "Print company logo", type: "check" }, { k: "show_hsn", label: "HSN / SAC summary", type: "check" },
    { k: "show_bank", label: "Bank details (quotations, orders, invoices)", type: "check" }, { k: "show_sign", label: "Authorised signatory", type: "check" },
    { k: "default", label: "Default layout of the document type", type: "check", ro: !!(edit && edit.default) },
  ];
  const blank = { type_code: query().get("type") || "13", style: "classic", show_logo: true, show_hsn: true, show_bank: true, show_sign: true };
  const byType = types.map(([obj, name]) => [obj, name, data.layouts.filter((l) => l.type_code === obj)]).filter((t) => t[2].length);
  c.innerHTML = `<div class="page-head"><div><h1>Print Layouts</h1><div class="sub">Layouts per document type (RDOC), default layout and company logo — the print preview of a document lets you choose the layout</div></div>
      <a class="btn" href="#/print-layouts?new=1">+ New layout</a></div>
    <div class="card"><div class="card-head">Company logo</div><div class="card-body pl-logo">
      <div class="pl-logo-box">${logo.image ? `<img src="${esc(logo.image)}" alt="Company logo">` : '<span class="help">No logo</span>'}</div>
      <div><input type="file" id="pl-file" accept="image/png,image/jpeg,image/gif">
        <div class="help">PNG, JPEG or GIF, at most 512 KB; printed at the top left of every layout that has "Print company logo".</div>
        <div style="display:flex;gap:8px;margin-top:8px"><button class="btn" id="pl-upload">Upload logo</button>${logo.image ? '<button class="btn secondary" id="pl-remove">Remove logo</button>' : ""}</div></div></div></div>
    <div class="card"><table><thead><tr><th>Document type</th><th>Code</th><th>Layout</th><th>Style</th><th>Colour</th><th>Default</th></tr></thead><tbody>
      ${byType.map(([, name, rows]) => rows.map((l, i) => `<tr style="cursor:pointer" onclick="location.hash='#/print-layouts?code=${encodeURIComponent(l.doc_code)}'">
        <td>${i === 0 ? esc(name) : ""}</td><td class="mono">${esc(l.doc_code)}</td><td>${esc(l.doc_name)}</td><td>${esc(data.styles[l.style] || l.style)}</td>
        <td><span class="pl-swatch" style="background:${esc(l.color)}"></span> <span class="mono">${esc(l.color)}</span></td><td>${l.default ? "&#10003;" : ""}</td></tr>`).join("")).join("")}</tbody></table></div>
    <div class="card"><div class="card-head">${edit ? `Layout ${esc(edit.doc_code)}` : "New layout"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(defs, edit || blank, "pl")}
        <div class="field"><label for="pl-color">Accent colour</label><input id="pl-color" type="color" value="${esc((edit && edit.color) || "#1f3b63")}"></div></div>
      ${edit && edit.default ? '<div class="help">This is the default layout; to change that, make another layout of this document type the default.</div>' : ""}
      <div style="display:flex;gap:8px;margin-top:10px"><button class="btn" id="pl-save">${edit ? "Update" : "Add"}</button>
        ${edit && !edit.default ? '<button class="btn secondary" id="pl-delete">Remove</button>' : ""}</div></div></div>`;
  $("#pl-save").onclick = async () => {
    const body = { ...readFields(defs, "pl"), color: $("#pl-color").value };
    if (edit && edit.default) delete body.default;
    const r = edit ? await act(() => patch(`/print-layouts/${encodeURIComponent(edit.doc_code)}`, body), "Layout updated")
      : await act(() => post("/print-layouts", body), (l) => `Layout ${l.doc_code} added`);
    if (r) location.hash = `#/print-layouts?code=${encodeURIComponent(r.doc_code)}&r=${Date.now()}`;
  };
  if ($("#pl-delete")) $("#pl-delete").onclick = async () => {
    if (await act(() => api(`/print-layouts/${encodeURIComponent(edit.doc_code)}`, { method: "DELETE" }), "Layout removed")) location.hash = `#/print-layouts?r=${Date.now()}`;
  };
  const putLogo = (image, msg) => act(() => api("/admin/company/logo", { method: "PUT", body: JSON.stringify({ image }) }), msg);
  $("#pl-upload").onclick = () => {
    const f = $("#pl-file").files[0];
    if (!f) return toast("Choose an image file first", "bad");
    if (f.size > 512 * 1024) return toast(`The logo is ${Math.round(f.size / 1024)} KB; at most 512 KB is allowed`, "bad");
    const rd = new FileReader();
    rd.onload = async () => { if (await putLogo(rd.result, "Logo uploaded")) { state.company.has_logo = true; views["print-layouts"](c); } };
    rd.readAsDataURL(f);
  };
  if ($("#pl-remove")) $("#pl-remove").onclick = async () => { if (await putLogo(null, "Logo removed")) views["print-layouts"](c); };
};
