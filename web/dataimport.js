/* Data import (Data Transfer Workbench): template, simulation, import with a result per row.
   Excel export: every page with tables gets an "Export to Excel" button (one sheet per table). */
"use strict";

views["data-import"] = async (c) => {
  const kinds = await api("/import/kinds");
  const kind = query().get("kind") || "partners";
  const defs = [
    { k: "kind", label: "Import", type: "select", blank: false, options: Object.entries(kinds).map(([k, v]) => [k, v.title]) },
    { k: "on", label: "Posting date (balances, stock)", type: "date", value: today() },
    { k: "all_or_nothing", label: "All or nothing (any error: nothing is imported)", type: "check" },
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Data Import</h1><div class="sub">CSV or Excel files; every row is checked like a manual entry — simulate first, then import</div></div></div>
    <div class="card"><div class="card-body"><div class="form-grid">${fieldsHtml(defs, { kind }, "di")}
      <div class="field"><label>File (CSV / XLSX)</label><input type="file" id="di-file" accept=".csv,.xlsx,.xlsm,text/csv"></div></div>
      <div class="help" style="margin-top:6px">Columns: <span class="mono" id="di-cols">${esc(kinds[kind].columns.join(", "))}</span> ·
        <a href="/api/import/${kind}/template" id="di-tpl" download>download the template</a></div>
      <div style="display:flex;gap:8px;margin-top:10px"><button class="btn secondary" id="di-sim">Simulate</button><button class="btn" id="di-run">Import</button></div></div></div>
    <div id="di-result"></div>`;
  $("#di-kind").onchange = (e) => { location.hash = `#/data-import?kind=${e.target.value}`; };
  const send = async (dry) => {
    const f = $("#di-file").files[0];
    if (!f) return toast("Choose a file", "bad");
    const content = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result.split(",")[1]); r.onerror = rej; r.readAsDataURL(f); });
    const opts = readFields(defs, "di");
    const r = await act(() => post(`/import/${opts.kind}`, { filename: f.name, content, dry_run: dry, all_or_nothing: opts.all_or_nothing, on: opts.on }),
      (x) => (dry ? `Simulation: ${x.ok} of ${x.rows} rows would be imported` : `${x.imported} of ${x.rows} rows imported`));
    if (!r) return;
    $("#di-result").innerHTML = `<div class="card"><div class="card-head">${dry ? "Simulation" : "Import"} — ${esc(r.title)}: ${r.ok} ok, ${r.failed} with errors${dry ? " (nothing saved)" : `, ${r.imported} imported`}</div>
      <table><thead><tr><th>Row</th><th>Result</th><th>Message</th></tr></thead><tbody>
      ${r.results.map((x) => `<tr><td>${x.row}</td><td>${x.ok ? '<span class="status O">ok</span>' : '<span class="status X">error</span>'}</td><td>${esc(x.message)}</td></tr>`).join("")}</tbody></table></div>`;
    if (!dry) reloadMasterData();
  };
  $("#di-sim").onclick = () => send(true);
  $("#di-run").onclick = () => send(false);
};

// ---------- Excel export of the tables of the current page ----------
function addExportButton(c, view) {
  if (view === "print" || !$(".page-head", c)) return;
  const tables = $$("table", c).filter((t) => !t.closest("td") && !t.closest(".no-export") && t.offsetParent !== null);
  if (!tables.length || $("#xl-export", c)) return;
  const btn = Object.assign(document.createElement("button"), { id: "xl-export", className: "btn small ghost no-print", textContent: "Export to Excel" });
  btn.style.marginLeft = "8px";
  const head = $(".page-head", c);
  (head.lastElementChild && head.children.length > 1 ? head.lastElementChild : head).appendChild(btn);
  btn.onclick = async () => {
    const title = ($(".page-head h1", c) || {}).textContent || view;
    const cellText = (el) => {
      const inp = $("input, select, textarea", el);
      if (inp) return inp.tagName === "SELECT" ? (inp.selectedOptions[0] || {}).text || "" : inp.type === "checkbox" ? (inp.checked ? "Y" : "N") : inp.value;
      return el.innerText.replace(/\s+/g, " ").trim();
    };
    const sheets = tables.map((t, n) => {
      const card = t.closest(".card");
      const name = (card && $(".card-head", card) ? $(".card-head", card).innerText.split("\n")[0] : "") || `${title} ${n + 1}`;
      const headers = $$("thead th", t).map(cellText);
      const rows = $$("tbody > tr, tfoot > tr", t).filter((tr) => !tr.classList.contains("hidden") && !tr.querySelector("td.empty"))
        .map((tr) => [...tr.children].map(cellText));
      return { name: name.slice(0, 60), headers, rows };
    }).filter((s) => s.rows.length);
    if (!sheets.length) return toast("Nothing to export", "bad");
    try {
      const res = await fetch("/api/export/xlsx", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, sheets }) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await res.blob());
      a.download = `${title.replace(/[^A-Za-z0-9_-]+/g, "_")}.xlsx`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { toast(e.message, "bad"); }
  };
}
