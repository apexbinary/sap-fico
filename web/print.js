/* Printable document (GST layout): opened from a document's "Print / PDF" button; the browser
   prints it or saves it as PDF. */
"use strict";

views.print = async (c) => {
  const obj = query().get("obj"), entry = query().get("entry");
  const p = await api(`/documents/${obj}/${entry}/print`);
  const money = (n) => fmt(n);
  const pct = (t) => (t ? `${Number(t[0])}%` : "");
  const amt = (t) => (t ? money(t[1]) : "");
  const gstIntra = p.supply !== "inter-state";
  const party = (title, x) => `<div class="pp-box"><div class="pp-label">${title}</div><b>${esc(x.name || "")}</b>
    <div>${esc(x.address || "")}</div>${x.gstin ? `<div>GSTIN: <b>${esc(x.gstin)}</b></div>` : ""}
    ${x.state ? `<div>State: ${esc(x.state)}${x.state_code ? ` (${esc(x.state_code)})` : ""}</div>` : ""}</div>`;
  const taxHead = p.no_prices ? "" : gstIntra ? '<th class="num">CGST</th><th class="num">SGST</th>' : '<th class="num">IGST</th>';
  c.innerHTML = `<div class="page-head no-print"><div><h1>${esc(p.title)} ${p.doc_num}</h1><div class="sub">Print preview — use Print and choose "Save as PDF" for a PDF</div></div>
      <span style="display:flex;gap:8px"><a class="btn secondary" href="#/docs?obj=${obj}&entry=${entry}">Back</a><button class="btn" onclick="window.print()">Print / PDF</button></span></div>
    <div class="print-page">
      <div class="pp-head"><div><div class="pp-company">${esc(p.company.name)}</div><div>${esc(p.company.address || "")}</div>
        <div>GSTIN: <b>${esc(p.company.gstin || "")}</b>${p.company.state ? ` · State: ${esc(p.company.state)} (${esc(p.company.state_code || "")})` : ""}</div>
        <div>${esc([p.company.phone, p.company.e_mail].filter(Boolean).join(" · "))}</div></div>
        <div class="pp-title">${esc(p.title)}${p.canceled ? '<div class="pp-cancel">CANCELED</div>' : ""}</div></div>
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
        <div><div class="pp-label">HSN / SAC summary</div><table class="pp-lines"><thead><tr><th>HSN/SAC</th><th class="num">Taxable value</th>
          ${gstIntra ? '<th class="num">CGST</th><th class="num">SGST</th>' : '<th class="num">IGST</th>'}<th class="num">Total tax</th></tr></thead><tbody>
          ${p.hsn_summary.map((h) => { const t = Number(h.CGST || 0) + Number(h.SGST || 0) + Number(h.IGST || 0);
            return `<tr><td>${esc(h.hsn)}</td><td class="num">${money(h.taxable)}</td>${gstIntra ? `<td class="num">${money(h.CGST || 0)}</td><td class="num">${money(h.SGST || 0)}</td>`
              : `<td class="num">${money(h.IGST || 0)}</td>`}<td class="num">${money(t)}</td></tr>`; }).join("")}</tbody></table></div>
        <div><table class="pp-kv pp-totals"><tbody>
          <tr><td>Total before discount</td><td class="num">${money(p.totals.before_discount)}</td></tr>
          ${Number(p.totals.discount) ? `<tr><td>Discount ${Number(p.totals.disc_prcnt)}%</td><td class="num">-${money(p.totals.discount)}</td></tr>` : ""}
          <tr><td>Tax</td><td class="num">${money(p.totals.tax)}</td></tr>
          <tr class="pp-grand"><td>Total (${esc(p.currency)})</td><td class="num">${money(p.totals.total)}</td></tr>
          ${Number(p.totals.paid) ? `<tr><td>Paid</td><td class="num">${money(p.totals.paid)}</td></tr><tr><td>Balance due</td><td class="num">${money(p.totals.total - p.totals.paid)}</td></tr>` : ""}</tbody></table></div></div>
      <div class="pp-words">Amount in words: <b>${esc(p.amount_in_words)}</b></div>`}
      <div class="pp-grid2 pp-foot">
        <div>${p.payment_terms && !p.no_prices ? `<div>Payment terms: ${esc(p.payment_terms)}</div>` : ""}
          ${p.bank && ["13", "23", "17"].includes(p.obj) ? `<div>Bank: ${esc(p.bank.name)} · A/c ${esc(p.bank.account)} · IFSC ${esc(p.bank.branch || "")}</div>` : ""}
          ${p.comments ? `<div>Remarks: ${esc(p.comments)}</div>` : ""}
          ${p.obj === "13" ? "<div class=\"help\">This is a computer generated invoice.</div>" : ""}</div>
        <div class="pp-sign">For ${esc(p.company.name)}<br><br><br>Authorised Signatory</div></div>
    </div>`;
};
