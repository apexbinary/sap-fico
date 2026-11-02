/* Cockpit: KPI tiles, analyses (SVG charts), open documents, alerts and common functions;
   widgets can be shown / hidden and reordered per user. */
"use strict";

const short = (n) => {  // compact amounts for chart labels (lakh / crore for INR)
  const v = Number(n || 0), a = Math.abs(v), inr = state.company.main_curncy === "INR";
  if (inr && a >= 1e7) return `${(v / 1e7).toFixed(1)} Cr`;
  if (inr && a >= 1e5) return `${(v / 1e5).toFixed(1)} L`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(1)}k`;
  return v.toFixed(0);
};

function barChart(months) {  // grouped bars: sales and purchases per month
  const w = 640, h = 220, pad = 30, max = Math.max(1, ...months.flatMap((m) => [Number(m.sales), Number(m.purchases)]));
  const slot = (w - pad * 2) / months.length, bw = Math.max(4, slot / 2 - 4);
  const y = (v) => h - pad - (Number(v) / max) * (h - pad * 2);
  return `<svg viewBox="0 0 ${w} ${h}" class="chart" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Sales and purchases per month">
    <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" class="axis"/>
    <text x="${pad}" y="14" class="lbl">max ${short(max)}</text>
    ${months.map((m, i) => {
      const x = pad + i * slot + 2;
      return `<rect x="${x}" y="${y(m.sales)}" width="${bw}" height="${h - pad - y(m.sales)}" class="bar-a" fill="#4a90d9"><title>${m.month} sales ${fmt(m.sales)}</title></rect>
        <rect x="${x + bw + 2}" y="${y(m.purchases)}" width="${bw}" height="${h - pad - y(m.purchases)}" class="bar-b" fill="#e8a33d"><title>${m.month} purchases ${fmt(m.purchases)}</title></rect>
        <text x="${x + bw}" y="${h - pad + 14}" class="lbl" text-anchor="middle">${m.month.slice(5)}</text>`;
    }).join("")}
  </svg><div class="legend"><span class="sw bar-a"></span> Sales <span class="sw bar-b"></span> Purchases (net, ${esc(state.company.main_curncy)})</div>`;
}

function hbars(rows, label, value) {  // horizontal bars
  const max = Math.max(1, ...rows.map((r) => Math.abs(Number(r[value]))));
  return rows.length ? `<div class="hbars">${rows.map((r) => `<div class="hbar"><span class="hl">${esc(r[label])}</span>
    <span class="ht"><span class="hf" style="width:${(Math.abs(Number(r[value])) / max) * 100}%"></span></span><span class="hv">${fmt(r[value])}</span></div>`).join("")}</div>`
    : '<div class="empty">No data yet.</div>';
}

const aging = (b) => hbars(Object.entries(b).map(([k, v]) => ({ k: k === "current" ? "Not yet due" : `${k} days`, v })), "k", "v");

function widget(id, d) {
  const k = d.kpis, docsLink = (obj, label, x) => `<tr style="cursor:pointer" onclick="location.hash='#/docs?obj=${obj}'"><td>${label}</td><td class="num">${x.count}</td><td class="num">${fmt(x.value)}</td></tr>`;
  switch (id) {
    case "kpis": return `<div class="tiles">${[
      ["Sales this month", k.sales_mtd, `year ${fmt(k.sales_ytd)}`, "#/docs?obj=13"], ["Purchases this month", k.purchases_mtd, `year ${fmt(k.purchases_ytd)}`, "#/docs?obj=18"],
      ["Receivables", k.receivable, `${fmt(k.overdue)} overdue`, "#/partners?type=C", Number(k.overdue) > 0 ? "bad" : ""],
      ["Payables", k.payable, `${fmt(k.payable_due_7d)} due in 7 days`, "#/partners?type=S"],
      ["Cash and bank", k.cash, "all cash accounts", "#/bank-reconciliation"], ["Inventory value", k.inventory_value, "moving average", "#/items"],
      ["Gross profit (year)", k.gross_profit_ytd, `net ${fmt(k.net_profit_ytd)}`, "#/profit-loss", Number(k.net_profit_ytd) >= 0 ? "good" : "bad"],
      ["Open sales orders", k.open_orders, "gross, not yet delivered", "#/docs?obj=17"], ["Tax payable this month", k.tax_payable_mtd, "output - input", "#/tax-report"],
    ].map(([label, v, foot, href, cls]) => `<a class="tile" href="${href}"><div class="label">${label}</div><div class="value ${cls || ""}">${fmt(v)}</div><div class="foot">${foot}</div></a>`).join("")}</div>`;
    case "sales_chart": return barChart(d.sales_chart);
    case "aging_ar": return aging(d.aging_ar);
    case "aging_ap": return aging(d.aging_ap);
    case "top_customers": return hbars(d.top_customers.map((c) => ({ ...c, label: `${c.card_code} ${c.card_name || ""}` })), "label", "sales");
    case "top_items": return hbars(d.top_items.map((i) => ({ ...i, label: `${i.item_code} ${i.item_name || ""}` })), "label", "sales");
    case "open_docs": return `<table><thead><tr><th>Document</th><th class="num">Open</th><th class="num">Value</th></tr></thead><tbody>
      ${docsLink("17", "Sales orders to deliver", d.open_docs.sales_orders)}${docsLink("15", "Deliveries to invoice", d.open_docs.deliveries)}
      ${docsLink("22", "Purchase orders to receive", d.open_docs.purchase_orders)}${docsLink("20", "Goods receipts to invoice", d.open_docs.goods_receipts)}</tbody></table>`;
    case "alerts": {
      const a = d.alerts;
      const rows = [
        ...a.overdue.map((o) => `<li class="bad">Overdue ${o.days} days: ${docLink(o.trans_type, o.created_by, `${transTypeName(o.trans_type)} ${o.doc_num || o.trans_id}`)} ${esc(o.card_code)} ${fmt(o.open)}</li>`),
        ...a.credit_limit.map((c) => `<li class="bad">Credit limit exceeded: <a href="#/partners?code=${encodeURIComponent(c.card_code)}">${esc(c.card_code)}</a> ${fmt(c.exposure)} / ${fmt(c.credit_line)}</li>`),
        ...a.low_stock.map((i) => `<li>Below minimum stock: <a href="#/items?code=${encodeURIComponent(i.item_code)}">${esc(i.item_code)}</a> ${esc(i.item_name)} — ${qtyFmt(i.on_hand)} of ${qtyFmt(i.min_level)}</li>`),
        a.unreconciled_bank_rows ? `<li><a href="#/bank-reconciliation">${a.unreconciled_bank_rows} bank statement rows to reconcile</a></li>` : "",
        a.saved_payment_runs ? `<li><a href="#/payment-wizard">${a.saved_payment_runs} payment runs not executed</a></li>` : "",
      ].filter(Boolean);
      return rows.length ? `<div class="help">${a.overdue_count} overdue items · ${a.low_stock_count} items below minimum</div><ul class="alerts">${rows.join("")}</ul>`
        : '<div class="empty">No alerts.</div>';
    }
    case "cash": return hbars(d.cash.map((c) => ({ ...c, label: `${c.acct_code} ${c.acct_name}` })), "label", "balance");
    case "links": return `<div class="links">${[
      ["#/doc?obj=13", "A/R Invoice"], ["#/doc?obj=17", "Sales Order"], ["#/doc?obj=22", "Purchase Order"], ["#/doc?obj=18", "A/P Invoice"],
      ["#/payment?kind=incoming", "Incoming Payment"], ["#/payment?kind=outgoing", "Outgoing Payment"], ["#/journal-entry", "Journal Entry"],
      ["#/partners?new=1", "New Business Partner"], ["#/items?new=1", "New Item"], ["#/payment-wizard", "Payment Wizard"], ["#/dunning", "Dunning Wizard"],
      ["#/trial-balance", "Trial Balance"]].map(([h, l]) => `<a class="btn secondary small" href="${h}">${l}</a>`).join("")}</div>`;
    default: return "";
  }
}

views.cockpit = async (c) => {
  const [d, layout] = await Promise.all([api("/cockpit"), api("/cockpit/layout")]);
  const wide = new Set(["kpis", "sales_chart", "links"]);
  c.innerHTML = `<div class="page-head"><div><h1>Cockpit</h1><div class="sub">${esc(state.company.company_name)} · ${d.on}</div></div>
      <button class="btn secondary" id="ck-custom">Customize</button></div>
    <div id="ck-panel"></div>
    <div class="cockpit">${layout.filter((w) => w.visible).map((w) => `<div class="card ${wide.has(w.id) ? "wide" : ""}"><div class="card-head">${esc(w.title)}</div>
      <div class="card-body">${widget(w.id, d)}</div></div>`).join("")}</div>`;
  $("#ck-custom").onclick = () => {
    const rows = layout.map((w) => ({ ...w }));
    const draw = () => {
      $("#ck-panel").innerHTML = `<div class="card"><div class="card-head">Widgets — show / hide and order</div><div class="card-body"><table><tbody>
        ${rows.map((w, n) => `<tr><td><input type="checkbox" class="ck-vis" data-n="${n}"${w.visible ? " checked" : ""}></td><td>${esc(w.title)}</td>
          <td><button class="btn ghost small ck-up" data-n="${n}"${n ? "" : " disabled"}>↑</button><button class="btn ghost small ck-down" data-n="${n}"${n < rows.length - 1 ? "" : " disabled"}>↓</button></td></tr>`).join("")}</tbody></table>
        <button class="btn" id="ck-save" style="margin-top:8px">Save layout</button></div></div>`;
      $$(".ck-vis").forEach((cb) => (cb.onchange = () => (rows[cb.dataset.n].visible = cb.checked)));
      const swap = (a, b) => { [rows[a], rows[b]] = [rows[b], rows[a]]; draw(); };
      $$(".ck-up").forEach((b) => (b.onclick = () => swap(Number(b.dataset.n), Number(b.dataset.n) - 1)));
      $$(".ck-down").forEach((b) => (b.onclick = () => swap(Number(b.dataset.n), Number(b.dataset.n) + 1)));
      $("#ck-save").onclick = async () => {
        if (await act(() => api("/cockpit/layout", { method: "PUT", body: JSON.stringify(rows.map((w) => ({ id: w.id, visible: w.visible }))) }), "Layout saved")) route();
      };
    };
    draw();
  };
};
