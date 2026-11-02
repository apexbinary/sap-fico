/* Dunning: dunning terms, dunning wizard and printable dunning letters. */
"use strict";

views.dunning = async (c) => {
  const [terms, runs] = await Promise.all([api("/dunning/terms"), api("/dunning/runs")]);
  const defs = [
    { k: "dun_date", label: "Dunning date", type: "date", req: true, value: today() },
    { k: "card_code", label: "Customer", type: "select", blank: "All customers with a dunning term",
      options: () => state.partners.filter((b) => b.card_type === "C" && b.dun_term && !b.frozen).map((b) => [b.card_code, `${b.card_code} — ${b.card_name}`]) },
    { k: "highest", label: "Straight to the highest level due", type: "check" },
    { k: "post_fees", label: "Post interest and fees as an open item", type: "check" },
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Dunning Wizard</h1><div class="sub">Raise the dunning level of overdue customer items and print dunning letters</div></div></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(defs, {}, "dw")}</div>
      <div style="display:flex;gap:8px;margin-top:10px"><button class="btn secondary" id="dw-preview">Preview</button><button class="btn" id="dw-run" disabled>Execute</button></div></div></div>
    <div id="dw-letters"></div>
    <div class="card"><div class="card-head">Runs (ODWZ)</div><table><thead><tr><th>No.</th><th>Name</th><th>Date</th><th>Letters</th><th class="num">Interest</th><th class="num">Fees</th><th>Posted</th></tr></thead><tbody>
      ${runs.map((r) => `<tr style="cursor:pointer" onclick="location.hash='#/dunning-letter?run=${r.abs_entry}'"><td class="mono">${r.abs_entry}</td><td>${esc(r.wizard_name)}</td><td>${r.dun_date}</td>
        <td>${r.letters_count}</td><td class="num">${fmt(r.total_interest)}</td><td class="num">${fmt(r.total_fee)}</td><td>${yesNo(r.post_fees)}</td></tr>`).join("")
        || `<tr><td colspan="7" class="empty">No dunning runs yet.</td></tr>`}</tbody></table></div>
    <div class="card"><div class="card-head">Dunning terms (ODUT / DUT1)</div><table><thead><tr><th>Code</th><th>Name</th><th class="num">Interest % p.a.</th><th class="num">Days between letters</th><th>Levels</th></tr></thead><tbody>
      ${terms.map((t) => `<tr><td class="mono">${esc(t.code)}</td><td>${esc(t.name)}</td><td class="num">${Number(t.interest)}</td><td class="num">${t.days_between}</td>
        <td>${t.levels.map((l) => `L${l.level}: ${l.days} days, fee ${fmt(l.fee)}, min. ${fmt(l.min_balance)}`).join(" · ")}</td></tr>`).join("")
        || `<tr><td colspan="5" class="empty">No dunning terms.</td></tr>`}</tbody></table>
      <div class="card-body"><div class="form-grid">${fieldsHtml([
        { k: "code", label: "Code", req: true, max: 8 }, { k: "name", label: "Name", req: true, max: 50 },
        { k: "interest", label: "Interest % p.a.", type: "number", step: "0.01", min: 0, value: 18 },
        { k: "days_between", label: "Minimum days between letters", type: "number", step: 1, min: 0, value: 7 },
        { k: "highest", label: "Straight to the highest level", type: "check" }], {}, "dt")}</div>
        <table class="lines" style="margin-top:6px"><thead><tr><th class="num">After days</th><th class="num">Fee</th><th class="num">Min. balance</th><th>Letter text</th><th></th></tr></thead><tbody id="dt-levels"></tbody></table>
        <button class="btn secondary small" id="dt-add" style="margin-top:6px">+ Level</button>
        <div><button class="btn secondary" id="dt-save" style="margin-top:8px">Add / update term</button></div></div></div>`;
  const params = () => { const p = readFields(defs, "dw"); return { ...p, card_codes: p.card_code ? [p.card_code] : null }; };
  $("#dw-preview").onclick = async () => {
    const p = params();
    const letters = await act(() => api(`/dunning/preview?on=${p.dun_date}${p.card_code ? `&card_codes=${encodeURIComponent(p.card_code)}` : ""}${p.highest ? "&highest=true" : ""}`));
    if (!letters) return;
    $("#dw-letters").innerHTML = `<div class="card"><div class="card-head">Preview: ${letters.length} letters</div>
      ${letters.map((l) => `<div class="card-body"><b>${esc(l.card_code)} — ${esc(l.card_name)}</b> · level ${l.level} · overdue ${fmt(l.total_open)} · interest ${fmt(l.interest)} (${Number(l.interest_rate)} % p.a.) · fee ${fmt(l.fee)}
        <table style="margin-top:6px"><thead><tr><th>Document</th><th>Due date</th><th class="num">Days</th><th class="num">Open</th><th>Level</th><th class="num">Interest</th></tr></thead><tbody>
        ${l.items.map((i) => `<tr><td>${esc(transTypeName(i.trans_type))} ${esc(i.doc_num || i.trans_id)}</td><td>${i.due_date}</td><td class="num">${i.days_overdue}</td>
          <td class="num">${fmt(i.open_amount)}</td><td>${i.old_level} → ${i.new_level}</td><td class="num">${fmt(i.interest)}</td></tr>`).join("")}</tbody></table></div>`).join("")
        || '<div class="empty">Nothing to dun on this date.</div>'}</div>`;
    $("#dw-run").disabled = !letters.length;
  };
  $("#dw-run").onclick = async () => {
    const p = params();
    if (!confirm(`Execute the dunning run of ${p.dun_date}?`)) return;
    const r = await act(() => post("/dunning/runs", { dun_date: p.dun_date, card_codes: p.card_codes, highest: p.highest || null, post_fees: p.post_fees }),
      (x) => `Dunning run ${x.abs_entry}: ${x.letters_count} letters`);
    if (r) { state.partners = await api("/partners"); location.hash = `#/dunning-letter?run=${r.abs_entry}`; }
  };
  const levelRow = (v = {}) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="num"><input class="dl-d" type="number" step="1" min="0" value="${v.days ?? ""}" style="width:80px"></td>
      <td class="num"><input class="dl-f" type="number" step="0.01" min="0" value="${v.fee ?? 0}" style="width:90px"></td>
      <td class="num"><input class="dl-m" type="number" step="0.01" min="0" value="${v.min_balance ?? 0}" style="width:90px"></td>
      <td><input class="dl-t" maxlength="1000" value="${esc(v.letter_text || "")}"></td><td><button class="btn ghost small dl-del">✕</button></td>`;
    $("#dt-levels").appendChild(tr);
    $(".dl-del", tr).onclick = () => tr.remove();
  };
  levelRow();
  $("#dt-add").onclick = () => levelRow();
  $("#dt-save").onclick = async () => {
    const body = { ...readFields([{ k: "code" }, { k: "name" }, { k: "interest", type: "number" }, { k: "days_between", type: "number" }, { k: "highest", type: "check" }], "dt"),
      levels: $$("#dt-levels tr").filter((tr) => $(".dl-d", tr).value !== "").map((tr) => ({ days: Number($(".dl-d", tr).value), fee: Number($(".dl-f", tr).value || 0),
        min_balance: Number($(".dl-m", tr).value || 0), letter_text: $(".dl-t", tr).value || null })) };
    if (await act(() => post("/dunning/terms", body), "Dunning term saved")) route();
  };
};

// printable dunning letters of a run
views["dunning-letter"] = async (c) => {
  const r = await api(`/dunning/runs/${query().get("run")}`);
  const co = state.company;
  c.innerHTML = `<div class="page-head no-print"><div><h1>Dunning letters — run ${r.abs_entry}</h1><div class="sub">${esc(r.wizard_name)} · ${r.letters_count} letters</div></div>
      <span style="display:flex;gap:8px"><a class="btn secondary" href="#/dunning">Back</a><button class="btn" onclick="window.print()">Print</button></span></div>
    ${r.letters.map((l) => {
      const bp = state.partners.find((b) => b.card_code === l.card_code) || {};
      return `<div class="card letter"><div class="card-body">
        <div style="display:flex;justify-content:space-between;gap:20px"><div><b>${esc(co.company_name)}</b><div class="help">${esc(co.address || "")}<br>GSTIN ${esc(co.tax_id || "")}</div></div>
          <div style="text-align:right">Date: ${r.dun_date}<br>Dunning level ${l.level}</div></div>
        <div style="margin:18px 0"><b>${esc(l.card_name || l.card_code)}</b><br>${esc([bp.address, [bp.zip_code, bp.city].filter(Boolean).join(" ")].filter(Boolean).join(", "))}</div>
        <h3>${l.level >= 3 ? "Final notice" : l.level === 2 ? "Second reminder" : "Payment reminder"}</h3>
        <p>${esc(l.letter_text || "The items below are overdue.")}</p>
        <table><thead><tr><th>Document</th><th>Due date</th><th class="num">Days overdue</th><th class="num">Open amount</th><th class="num">Interest</th></tr></thead><tbody>
          ${l.items.map((i) => `<tr><td>${esc(transTypeName(i.trans_type))} ${esc(i.doc_num || i.trans_id)}</td><td>${i.due_date}</td><td class="num">${i.days_overdue}</td>
            <td class="num">${fmt(i.open_amount)}</td><td class="num">${fmt(i.interest)}</td></tr>`).join("")}</tbody>
          <tfoot><tr><td colspan="3">Overdue items</td><td class="num">${fmt(l.items.reduce((s, i) => s + Number(i.open_amount), 0))}</td><td class="num">${fmt(l.interest)}</td></tr>
            ${Number(l.fee) ? `<tr><td colspan="4">Dunning fee</td><td class="num">${fmt(l.fee)}</td></tr>` : ""}
            <tr><td colspan="4"><b>Amount due</b></td><td class="num"><b>${fmt(l.items.reduce((s, i) => s + Number(i.open_amount), 0) + Number(l.interest) + Number(l.fee))} ${esc(co.main_curncy)}</b></td></tr></tfoot></table>
        ${l.trans_id ? `<p class="help no-print">Interest and fee posted: <a href="#/journal?id=${l.trans_id}">journal entry ${l.trans_id}</a></p>` : ""}
      </div></div>`;
    }).join("")}`;
};
