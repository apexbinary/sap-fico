/* Recurring postings (ORCR / RCR1): journal entry templates posted at a frequency. */
"use strict";

views.recurring = async (c) => {
  const q = query(), on = q.get("on") || today(), code = q.get("code");
  const data = await api(`/recurring-postings?on=${on}`);
  const edit = code && data.templates.find((x) => x.rcur_code === code);
  const defs = [
    { k: "rcur_code", label: "Code", req: true, max: 8, ro: !!edit }, { k: "rcur_desc", label: "Description", req: true, max: 50, span: 2 },
    { k: "frequency", label: "Frequency", type: "select", blank: false, options: Object.entries(data.frequencies), value: "M" },
    { k: "next_deu", label: "Next due date", type: "date", req: true, value: on },
    { k: "valid_until", label: "Valid until", type: "date" }, { k: "limit_rtrns", label: "Number of postings (empty: no limit)", type: "number", step: 1, min: 1 },
    { k: "memo", label: "Journal memo", max: 50 }, ...(edit ? [{ k: "active", label: "Active", type: "check" }] : []),
  ];
  const targets = () => `${opt("", "— account / partner —")}${accountOptions((a) => !a.control)}${state.partners.map((p) => opt(`BP:${p.card_code}`, `BP ${p.card_code} — ${p.card_name}`)).join("")}`;
  c.innerHTML = `<div class="page-head"><div><h1>Recurring Postings</h1><div class="sub">Journal entry templates posted at a frequency — execute the due postings</div></div>
      <a class="btn" href="#/recurring?new=1">+ New template</a></div>
    <div class="card"><div class="card-head">Due up to <input type="date" id="rc-on" value="${esc(on)}"></div><table><thead><tr><th></th><th>Code</th><th>Description</th><th>Due dates</th><th class="num">Amount</th></tr></thead><tbody>
      ${data.due.map((x) => `<tr><td><input type="checkbox" class="rc-pick" value="${esc(x.rcur_code)}" checked></td><td class="mono">${esc(x.rcur_code)}</td><td>${esc(x.rcur_desc)}</td>
        <td>${x.dates.join(", ")}</td><td class="num">${fmt(x.amount)}</td></tr>`).join("") || '<tr><td colspan="5" class="empty">Nothing due.</td></tr>'}</tbody></table>
      ${data.due.length ? '<div class="card-body"><button class="btn" id="rc-exec">Post the selected</button></div>' : ""}</div>
    <div class="card"><table><thead><tr><th>Code</th><th>Description</th><th>Frequency</th><th>Next due</th><th>Last posted</th><th class="num">Posted</th><th>Ends</th><th>Active</th></tr></thead><tbody>
      ${data.templates.map((x) => `<tr style="cursor:pointer" onclick="location.hash='#/recurring?code=${encodeURIComponent(x.rcur_code)}'"><td class="mono">${esc(x.rcur_code)}</td>
        <td>${esc(x.rcur_desc)}</td><td>${esc(x.frequency_name)}</td><td>${x.next_deu}</td><td>${x.last_date || ""}</td><td class="num">${x.instance}</td>
        <td>${[x.valid_until, x.limit_rtrns ? `${x.limit_rtrns} postings` : ""].filter(Boolean).join(" / ")}</td><td>${yesNo(x.active)}</td></tr>`).join("")
        || '<tr><td colspan="8" class="empty">No templates.</td></tr>'}</tbody></table></div>
    <div class="card"><div class="card-head">${edit ? `Template ${esc(edit.rcur_code)}` : "New template"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(defs, edit || {}, "rc")}</div>
      <table class="lines" style="margin-top:8px"><thead><tr><th>G/L account / business partner</th><th class="num w-amt">Debit</th><th class="num w-amt">Credit</th><th>Line memo</th>${dimHead()}<th></th></tr></thead><tbody id="rc-lines"></tbody></table>
      <div style="display:flex;gap:8px;margin-top:6px"><button class="btn small secondary" id="rc-add">+ Line</button><span class="help" id="rc-bal"></span></div>
      <button class="btn" id="rc-save" style="margin-top:10px">${edit ? "Update" : "Add"}</button></div></div>`;
  const addLine = (l = {}) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><select class="rl-t">${targets()}</select></td><td class="num"><input class="rl-d" type="number" step="0.01" min="0" value="${Number(l.debit) || ""}"></td>
      <td class="num"><input class="rl-c" type="number" step="0.01" min="0" value="${Number(l.credit) || ""}"></td><td><input class="rl-m" maxlength="50" value="${esc(l.line_memo || "")}"></td>
      ${dimCells(l.ocr_codes)}<td><button class="btn ghost small rl-del">✕</button></td>`;
    $(".rl-t", tr).value = l.card_code ? `BP:${l.card_code}` : (l.account || "");
    $(".rl-del", tr).onclick = () => { tr.remove(); bal(); };
    $(".rl-d", tr).oninput = bal; $(".rl-c", tr).oninput = bal;
    $("#rc-lines").appendChild(tr);
  };
  const bal = () => {
    let d = 0, cr = 0;
    $$("#rc-lines tr").forEach((tr) => { d += Number($(".rl-d", tr).value || 0); cr += Number($(".rl-c", tr).value || 0); });
    $("#rc-bal").textContent = `Debit ${fmt(d)} · Credit ${fmt(cr)}${d.toFixed(2) === cr.toFixed(2) && d > 0 ? " · balanced" : " · not balanced"}`;
  };
  ((edit && edit.lines) || [{}, {}]).forEach(addLine);
  bal();
  $("#rc-add").onclick = () => addLine();
  $("#rc-on").onchange = (e) => { location.hash = `#/recurring?on=${e.target.value}`; };
  if ($("#rc-exec")) $("#rc-exec").onclick = async () => {
    const codes = $$(".rc-pick").filter((x) => x.checked).map((x) => x.value);
    const r = await act(() => post("/recurring-postings/execute", { on, codes }), (x) => `Posted journal entries ${Object.values(x).flat().join(", ") || "-"}`);
    if (r) views.recurring(c);
  };
  $("#rc-save").onclick = async () => {
    const body = readFields(defs, "rc");
    body.lines = $$("#rc-lines tr").map((tr) => {
      const t = $(".rl-t", tr).value;
      return { account: t.startsWith("BP:") ? null : t || null, card_code: t.startsWith("BP:") ? t.slice(3) : null, debit: Number($(".rl-d", tr).value || 0),
        credit: Number($(".rl-c", tr).value || 0), line_memo: $(".rl-m", tr).value || null, ocr_codes: readDims(tr) };
    }).filter((l) => l.account || l.card_code);
    const r = edit ? await act(() => patch(`/recurring-postings/${encodeURIComponent(edit.rcur_code)}`, body), "Template updated")
      : await act(() => post("/recurring-postings", body), (x) => `Template ${x.rcur_code} added`);
    if (r) location.hash = `#/recurring?code=${encodeURIComponent(r.rcur_code)}&r=${Date.now()}`;
  };
};
