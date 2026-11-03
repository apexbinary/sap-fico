/* Login, user menu, navigation by authorization, and user maintenance (OUSR / USR3). */
"use strict";

const AREA_OF_VIEW = {
  cockpit: "COCKPIT", accounts: "COA", "journal-entry": "JE", journal: "JE", "exchange-rate-differences": "FXREVAL",
  partners: "BP", dunning: "DUNNING", items: "ITEMS", warehouses: "ITEMS", "inventory-audit": "INV",
  payments: "BANK", "payment-wizard": "BANK", deposits: "BANK", "bank-statements": "BANK", "bank-reconciliation": "BANK",
  "trial-balance": "FINRPT", "balance-sheet": "FINRPT", "profit-loss": "FINRPT", "tax-report": "FINRPT", "gst-returns": "FINRPT",
  setup: "ADMIN", "tax-setup": "ADMIN", users: "ADMIN", "print-layouts": "ADMIN", "e-documents": "SALES", "withholding-tax": "ADMIN", freight: "ADMIN", batches: "INV", counting: "INV", "item-groups": "ITEMS", "cost-accounting": "ADMIN", "profit-centers": "FINRPT", budgets: "FINRPT", recurring: "JE", closing: "ADMIN", assets: "COA", "tds-report": "FINRPT",
};
const SALES_OBJS = ["23", "17", "15", "16", "13", "14", "203"], PURCH_OBJS = ["540000006", "22", "20", "21", "18", "19", "204"];
const areaOfObj = (obj) => (SALES_OBJS.includes(obj) ? "SALES" : PURCH_OBJS.includes(obj) ? "PURCH" : "INV");
const may = (area, level = "R") => !state.user || state.user.superuser || (level === "F" ? state.user.permissions[area] === "F"
  : ["R", "F"].includes(state.user.permissions[area]));

function showLogin(message) {
  if ($("#login")) return;
  const el = document.createElement("div");
  el.id = "login";
  el.innerHTML = `<form class="login-box" id="login-form"><div class="shell-logo" style="font-size:28px">B<span>1</span></div><h2>Business One</h2>
    <div class="field"><label>User code</label><input id="lg-user" autocomplete="username" required></div>
    <div class="field"><label>Password</label><input id="lg-pwd" type="password" autocomplete="current-password" required></div>
    <div class="login-msg" id="lg-msg">${esc(message || "")}</div><button class="btn" type="submit">Log in</button></form>`;
  document.body.appendChild(el);
  $("#lg-user").focus();
  $("#login-form").onsubmit = async (e) => {
    e.preventDefault();
    const res = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_code: $("#lg-user").value, password: $("#lg-pwd").value }) });
    if (res.ok) location.reload();
    else $("#lg-msg").textContent = (await res.json().catch(() => ({}))).detail || "Login failed";
  };
}

// header: user menu; sidebar: only the areas the user may open
function applyUser() {
  const u = state.user;
  const av = $(".avatar");
  av.textContent = u.u_name.split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
  av.title = `${u.u_name} (${u.user_code})`;
  av.style.cursor = "pointer";
  av.onclick = () => {
    const m = $("#user-menu");
    if (m) return m.remove();
    const menu = document.createElement("div");
    menu.id = "user-menu";
    menu.className = "user-menu";
    menu.innerHTML = `<div><b>${esc(u.u_name)}</b><div class="help">${esc(u.user_code)}${u.superuser ? " · superuser" : ""}</div></div>
      <a href="#/password">Change password</a><a href="#" id="um-logout">Log out</a>`;
    document.body.appendChild(menu);
    $("#um-logout").onclick = async (e) => { e.preventDefault(); await fetch("/api/auth/logout", { method: "POST" }); location.hash = ""; location.reload(); };
    menu.onclick = (e) => { if (e.target.tagName === "A") setTimeout(() => menu.remove(), 0); };
  };
  $$(".nav-item").forEach((a) => {
    const href = a.getAttribute("href") || "";
    const obj = (href.match(/obj=([0-9]+)/) || [])[1];
    const view = href.replace("#/", "").split("?")[0];
    const area = obj ? areaOfObj(obj) : AREA_OF_VIEW[view];
    a.style.display = !area || may(area) ? "" : "none";
  });
  $$(".nav-sep").forEach((sep) => {  // hide section titles without visible entries
    let n = sep.nextElementSibling, any = false;
    while (n && !n.classList.contains("nav-sep")) { if (n.style.display !== "none") any = true; n = n.nextElementSibling; }
    sep.style.display = any ? "" : "none";
  });
}

views.password = async (c) => {
  c.innerHTML = `<div class="page-head"><div><h1>Change password</h1><div class="sub">${esc(state.user.u_name)} (${esc(state.user.user_code)})</div></div></div>
    <div class="card"><div class="card-body"><div class="form-grid">
      <div class="field"><label class="req">Current password</label><input id="pw-old" type="password" autocomplete="current-password"></div>
      <div class="field"><label class="req">New password (8+ characters, letters and digits)</label><input id="pw-new" type="password" autocomplete="new-password"></div>
      <div class="field"><label class="req">Repeat new password</label><input id="pw-rep" type="password" autocomplete="new-password"></div></div>
      <button class="btn" id="pw-save" style="margin-top:10px">Change password</button></div></div>`;
  $("#pw-save").onclick = async () => {
    if ($("#pw-new").value !== $("#pw-rep").value) return toast("The new passwords differ", "bad");
    if (await act(() => post("/auth/password", { old_password: $("#pw-old").value, new_password: $("#pw-new").value }), "Password changed")) location.hash = "#/cockpit";
  };
};

views.users = async (c) => {
  const data = await api("/users");
  const id = query().get("id");
  const edit = id && data.users.find((u) => String(u.user_id) === id);
  const levels = [["F", "Full authorization"], ["R", "Read only"], ["N", "No authorization"]];
  const defs = [
    { k: "user_code", label: "User code", req: true, max: 25, ro: !!edit }, { k: "u_name", label: "User name", req: true, max: 155 },
    { k: "e_mail", label: "E-mail", max: 100 }, { k: "department", label: "Department", max: 50 },
    { k: "password", label: edit ? "New password (leave empty to keep)" : "Initial password", max: 100 },
    { k: "superuser", label: "Superuser", type: "check" }, ...(edit ? [{ k: "locked", label: "Locked", type: "check" }] : []),
  ];
  c.innerHTML = `<div class="page-head"><div><h1>Users</h1><div class="sub">Users (OUSR) and general authorizations (USR3)</div></div>
      <a class="btn" href="#/users?new=1">+ New user</a></div>
    <div class="card"><table><thead><tr><th>User code</th><th>Name</th><th>Department</th><th>Superuser</th><th>Locked</th><th>Last login</th></tr></thead><tbody>
      ${data.users.map((u) => `<tr style="cursor:pointer" onclick="location.hash='#/users?id=${u.user_id}'"><td class="mono">${esc(u.user_code)}</td><td>${esc(u.u_name)}</td>
        <td>${esc(u.department || "")}</td><td>${yesNo(u.superuser)}</td><td>${u.locked ? '<span class="status X">Locked</span>' : ""}</td>
        <td>${u.last_login ? esc(String(u.last_login).replace("T", " ").slice(0, 16)) : ""}</td></tr>`).join("")}</tbody></table></div>
    <div class="card"><div class="card-head">${edit ? `User ${esc(edit.user_code)}` : "New user"}</div><div class="card-body">
      <div class="form-grid">${fieldsHtml(defs, edit ? { ...edit, password: "" } : {}, "us")}</div>
      <h3 class="section">General authorizations</h3>
      <table><thead><tr><th>Area</th><th>Authorization</th></tr></thead><tbody>
        ${Object.entries(data.areas).map(([k, label]) => `<tr><td>${esc(label)}</td><td><select class="us-perm" data-k="${k}">${levels.map(([v, l]) => opt(v, l, edit ? edit.permissions[k] : "N")).join("")}</select></td></tr>`).join("")}</tbody></table>
      <div class="help" style="margin-top:6px">Superusers have full authorization everywhere.</div>
      <button class="btn" id="us-save" style="margin-top:10px">${edit ? "Update" : "Add"}</button></div></div>`;
  $("#us-save").onclick = async () => {
    const body = readFields(defs, "us");
    if (!body.password) delete body.password;
    body.permissions = Object.fromEntries($$(".us-perm").map((s) => [s.dataset.k, s.value]));
    const r = edit ? await act(() => patch(`/users/${edit.user_id}`, body), "User updated") : await act(() => post("/users", body), (u) => `User ${u.user_code} added`);
    if (r) location.hash = `#/users?id=${r.user_id}&r=${Date.now()}`;
  };
};
