/* GST returns (India): GSTR-1 (outward supplies) and GSTR-3B (summary with ITC set-off) of a month,
   with the JSON for the GST portal's offline tool. */
"use strict";

const GST_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

views["gst-returns"] = async (c) => {
  const q = query(), now = new Date();
  const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);  // returns are filed for the month just ended
  const year = Number(q.get("year") || prev.getFullYear()), month = Number(q.get("month") || prev.getMonth() + 1);
  const tab = q.get("tab") || "gstr1";
  const defs = [
    { k: "year", label: "Year", type: "number", step: 1, min: 2000, maxv: 2100, req: true },
    { k: "month", label: "Month", type: "select", blank: false, int: true, options: GST_MONTHS.map((m, i) => [i + 1, m]) },
  ];
  const args = `year=${year}&month=${month}`;
  const r = await api(`/gst-returns/${tab}?${args}`);
  const n = (x) => fmt(x);
  const cells = (x, keys = ["taxable", "igst", "cgst", "sgst", "cess"]) => keys.map((k) => `<td class="num">${n(x[k])}</td>`).join("");
  const heads = (keys = ["Taxable value", "IGST", "CGST", "SGST", "Cess"]) => keys.map((k) => `<th class="num">${k}</th>`).join("");
  const docLink = (obj, x) => `<a href="#/docs?obj=${obj}&entry=${x.doc_entry}">${x.doc_num}</a>`;
  const itemsSum = (x) => x.items.reduce((a, i) => { ["taxable", "igst", "cgst", "sgst", "cess"].forEach((k) => (a[k] += Number(i[k]))); return a; },
    { taxable: 0, igst: 0, cgst: 0, sgst: 0, cess: 0 });
  const empty = (cols) => `<tr><td colspan="${cols}" class="empty">None in this period.</td></tr>`;
  const section = (title, sub, body) => `<div class="card"><div class="card-head">${title}${sub ? ` <span class="help">${sub}</span>` : ""}</div><div style="overflow-x:auto">${body}</div></div>`;
  const docTable = (rows, obj, extraHead = "", extra = () => "") => `<table><thead><tr><th>No.</th><th>Date</th><th>Customer</th><th>GSTIN</th><th>POS</th>${extraHead}<th class="num">Value</th>${heads()}</tr></thead><tbody>
    ${rows.map((x) => `<tr><td>${docLink(obj, x)}</td><td>${x.doc_date}</td><td>${esc(x.card_name || x.card_code || "")}</td><td class="mono">${esc(x.gstin || "")}</td>
      <td>${esc(x.pos ? `${x.pos} ${x.pos_name || ""}` : "")}</td>${extra(x)}<td class="num">${n(x.value)}</td>${cells(itemsSum(x))}</tr>`).join("") || empty(10 + (extraHead ? 1 : 0))}</tbody></table>`;

  let body;
  if (tab === "gstr1") {
    const t = r.totals;
    body = `
      ${section("Summary", `${r.documents} documents`, `<table><thead><tr><th>Table</th>${heads()}</tr></thead><tbody>
        ${[["4A B2B invoices", t.b2b], ["5 B2C large (B2CL)", t.b2cl], ["7 B2C others (B2CS)", t.b2cs], ["6A Exports", t.exp],
           ["9B Credit notes, registered (CDNR)", t.cdnr], ["9B Credit notes, unregistered (CDNUR)", t.cdnur]]
          .map(([l, x]) => `<tr><td>${l}</td>${cells(x)}</tr>`).join("")}
        <tr class="total"><td>Net outward supplies (invoices - credit notes, incl. nil-rated / exempt of Table 8)</td>${cells(r.total)}</tr></tbody></table>`)}
      ${section("4A B2B invoices", "registered customers", docTable(r.b2b, "13", "<th>Type</th>", (x) => `<td>${esc(x.invoice_type)}</td>`))}
      ${section("5 B2C large invoices (B2CL)", "unregistered, inter-state, invoice value above 1,00,000", docTable(r.b2cl, "13"))}
      ${section("7 B2C others (B2CS)", "by place of supply and rate", `<table><thead><tr><th>Place of supply</th><th>Supply</th><th class="num">Rate %</th>${heads()}</tr></thead><tbody>
        ${r.b2cs.map((x) => `<tr><td>${esc(`${x.pos || ""} ${x.pos_name || ""}`)}</td><td>${x.supply}</td><td class="num">${Number(x.rate)}</td>${cells(x)}</tr>`).join("") || empty(8)}</tbody></table>`)}
      ${section("6A Exports", "", docTable(r.exp, "13", "<th>Type</th>", (x) => `<td>${esc(x.type)}</td>`))}
      ${section("9B Credit / debit notes, registered (CDNR)", "", docTable(r.cdnr, "14"))}
      ${section("9B Credit / debit notes, unregistered (CDNUR)", "", docTable(r.cdnur, "14", "<th>Type</th>", (x) => `<td>${esc(x.type)}</td>`))}
      ${section("8 Nil-rated, exempt and non-GST supplies", "", `<table><thead><tr><th>Supply</th><th class="num">Nil rated</th><th class="num">Exempt</th><th class="num">Non-GST</th></tr></thead><tbody>
        ${r.nil.map((x) => `<tr><td>${x.supply}</td><td class="num">${n(x.nil)}</td><td class="num">${n(x.exempt)}</td><td class="num">${n(x.non_gst)}</td></tr>`).join("")}</tbody></table>`)}
      ${["b2b", "b2c"].map((k) => section(`12 HSN-wise summary — ${k.toUpperCase()}`, "", `<table><thead><tr><th>HSN / SAC</th><th>Description</th><th>UQC</th><th class="num">Qty</th><th class="num">Rate %</th><th class="num">Total value</th>${heads()}</tr></thead><tbody>
        ${r.hsn[k].map((h) => `<tr><td class="mono">${esc(h.hsn || "")}</td><td>${esc(h.description || "")}</td><td>${esc(h.uqc)}</td><td class="num">${qtyFmt(h.qty)}</td>
          <td class="num">${Number(h.rate)}</td><td class="num">${n(h.value)}</td>${cells(h)}</tr>`).join("") || empty(11)}</tbody></table>`)).join("")}
      ${section("13 Documents issued", "", `<table><thead><tr><th>Nature of document</th><th>Series</th><th>From</th><th>To</th><th class="num">Total</th><th class="num">Canceled</th><th class="num">Net issued</th></tr></thead><tbody>
        ${r.doc_issue.map((x) => `<tr><td>${esc(x.nature)}</td><td>${esc(x.series)}</td><td>${x.from}</td><td>${x.to}</td><td class="num">${x.total}</td><td class="num">${x.canceled}</td><td class="num">${x.net_issued}</td></tr>`).join("") || empty(7)}</tbody></table>`)}`;
  } else {
    const o = r.outward, p = r.payment;
    const usedBy = (credit, against) => (p.used.find((u) => u.credit === credit && u.against === against) || { amount: 0 }).amount;
    body = `
      ${section("3.1 Outward supplies and inward supplies liable to reverse charge", "", `<table><thead><tr><th>Nature of supplies</th>${heads(["Taxable value", "IGST", "CGST", "SGST", "Cess"])}</tr></thead><tbody>
        ${[["(a) Outward taxable supplies (other than zero rated, nil rated and exempted)", o.a_taxable], ["(b) Outward taxable supplies (zero rated)", o.b_zero_rated],
           ["(c) Other outward supplies (nil rated, exempted)", o.c_nil_exempt], ["(d) Inward supplies (liable to reverse charge)", o.d_reverse_charge],
           ["(e) Non-GST outward supplies", o.e_non_gst]].map(([l, x]) => `<tr><td>${l}</td>${cells(x)}</tr>`).join("")}</tbody></table>`)}
      ${section("3.2 Inter-state supplies to unregistered persons and composition dealers", "", `<table><thead><tr><th>Place of supply</th><th>To</th><th class="num">Taxable value</th><th class="num">IGST</th></tr></thead><tbody>
        ${[...r.inter_state_unregistered.map((x) => ({ ...x, to: "Unregistered persons" })), ...r.inter_state_composition.map((x) => ({ ...x, to: "Composition dealers" }))]
          .map((x) => `<tr><td>${esc(`${x.pos || ""} ${x.pos_name || ""}`)}</td><td>${x.to}</td><td class="num">${n(x.taxable)}</td><td class="num">${n(x.igst)}</td></tr>`).join("") || empty(4)}</tbody></table>`)}
      ${section("4 Eligible ITC", "from A/P invoices less A/P credit memos", `<table><thead><tr><th>Details</th>${heads(["IGST", "CGST", "SGST", "Cess"])}</tr></thead><tbody>
        <tr><td>(A)(5) All other ITC</td>${cells(r.itc.available_other, ["igst", "cgst", "sgst", "cess"])}</tr>
        <tr><td>(B) ITC reversed</td>${cells(r.itc.reversed, ["igst", "cgst", "sgst", "cess"])}</tr>
        <tr class="total"><td>(C) Net ITC available</td>${cells(r.itc.net, ["igst", "cgst", "sgst", "cess"])}</tr>
        <tr><td>(D) Ineligible ITC</td>${cells(r.itc.ineligible, ["igst", "cgst", "sgst", "cess"])}</tr></tbody></table>`)}
      ${section("5 Exempt, nil-rated and non-GST inward supplies", "", `<table><thead><tr><th>Nature of supplies</th><th class="num">Inter-state</th><th class="num">Intra-state</th></tr></thead><tbody>
        <tr><td>Composition, exempt and nil-rated supplies</td><td class="num">${n(r.exempt_inward.inter)}</td><td class="num">${n(r.exempt_inward.intra)}</td></tr>
        <tr><td>Non-GST supplies</td><td class="num">${n(0)}</td><td class="num">${n(0)}</td></tr></tbody></table>`)}
      ${section("6.1 Payment of tax", "ITC set-off: IGST credit first against IGST, then CGST / SGST; CGST and SGST credit against themselves, then IGST", `<table><thead><tr><th>Tax</th><th class="num">Tax payable</th><th class="num">Paid by IGST credit</th>
        <th class="num">Paid by CGST credit</th><th class="num">Paid by SGST credit</th><th class="num">Paid by cess credit</th><th class="num">Paid in cash</th></tr></thead><tbody>
        ${["igst", "cgst", "sgst", "cess"].map((h) => `<tr><td>${h.toUpperCase()}</td><td class="num">${n(r.liability[h])}</td>
          ${["igst", "cgst", "sgst", "cess"].map((cr) => `<td class="num">${n(usedBy(cr, h))}</td>`).join("")}<td class="num"><b>${n(p.cash[h])}</b></td></tr>`).join("")}
        <tr class="total"><td>Credit carried forward</td><td></td>${["igst", "cgst", "sgst", "cess"].map((h) => `<td class="num">${n(p.credit_left[h])}</td>`).join("")}<td></td></tr></tbody></table>`)}`;
  }
  c.innerHTML = `<div class="page-head"><div><h1>GST Returns</h1><div class="sub">GSTR-1 and GSTR-3B of ${GST_MONTHS[month - 1]} ${year} — GSTIN ${esc(r.gstin || "")}, from the posted A/R and A/P documents</div></div>
      <a class="btn" href="/api/gst-returns/${tab}/json?${args}" download>Download ${tab === "gstr1" ? "GSTR-1" : "GSTR-3B"} JSON</a></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(defs, { year, month }, "gr")}
      <div class="field"><label>&nbsp;</label><button class="btn" id="gr-go">Show</button></div></div>
      <div class="tabs" style="margin-top:8px">${[["gstr1", "GSTR-1 outward supplies"], ["gstr3b", "GSTR-3B summary"]].map(([k, l]) =>
        `<a class="tab${k === tab ? " active" : ""}" href="#/gst-returns?${args}&tab=${k}">${l}</a>`).join("")}</div></div></div>
    ${r.issues.length ? `<div class="card"><div class="card-head">Check before filing (${r.issues.length})</div><div class="card-body"><ul class="gr-issues">${r.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div></div>` : ""}
    ${body}
    <div class="help" style="margin:8px 0 24px">The JSON follows the layout of the GST portal's offline tool; check it in the offline tool before uploading.
      Not covered yet: reverse charge, imports, ITC reversals, amendments, e-invoice (IRN).</div>`;
  $("#gr-go").onclick = () => {
    const f = readFields(defs, "gr");
    if (!f.year || f.year < 2000 || f.year > 2100) return toast("Enter a year between 2000 and 2100", "bad");
    location.hash = `#/gst-returns?year=${f.year}&month=${f.month}&tab=${tab}`;
  };
};
