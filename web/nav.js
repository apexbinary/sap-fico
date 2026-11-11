/* Two-level navigation: a module rail (main sidebar) and the menu of the selected module (secondary sidebar).
   Built from the menu in index.html: every "nav-sep" title starts a module, the entries after it are its menu,
   so new screens only need their entry in index.html. Modules without an authorized entry are hidden; the
   module of the current screen is selected automatically. */
"use strict";

const MOD_ICONS = { Home: "&#8962;", Financials: "&#8721;", "Business Partners": "&#9787;", "Sales — A/R": "&#8599;", "Purchasing — A/P": "&#8601;",
  Inventory: "&#9638;", CRM: "&#9733;", Service: "&#9874;", Production: "&#9881;", Banking: "&#8377;", "Financial Reports": "&#9636;",
  Administration: "&#9965;" };
const navState = { mod: null, groups: [] };

function navBuild() {
  const nav = $("#sidenav");
  if (!nav || nav.dataset.grouped) return;
  nav.dataset.grouped = "1";
  const groups = [];
  let cur = { name: "Home", els: [] };
  [...nav.children].forEach((el) => {
    if (el.classList.contains("nav-sep")) { groups.push(cur); cur = { name: el.textContent.trim(), els: [] }; } else cur.els.push(el);
  });
  groups.push(cur);
  nav.innerHTML = "";
  groups.filter((g) => g.els.length).forEach((g, i) => {
    const div = document.createElement("div");
    div.className = "nav-group";
    div.dataset.mod = String(i);
    div.innerHTML = `<div class="nav-mod-title">${esc(g.name)}</div>`;
    g.els.forEach((e) => div.appendChild(e));
    nav.appendChild(div);
    navState.groups.push({ name: g.name, div });
  });
  const rail = document.createElement("nav");
  rail.id = "modrail";
  rail.className = "modrail";
  rail.setAttribute("aria-label", "Modules");
  rail.innerHTML = navState.groups.map((g, i) => `<button class="mod-btn" data-mod="${i}" title="${esc(g.name)}"><span class="mod-ic">${MOD_ICONS[g.name] || "&#9679;"}</span>
    <span class="mod-name">${esc(g.name.replace(/ — .*/, ""))}</span></button>`).join("");
  nav.parentElement.insertBefore(rail, nav);
  $$(".mod-btn", rail).forEach((b) => (b.onclick = () => {
    navShow(Number(b.dataset.mod));
    const first = [...navState.groups[Number(b.dataset.mod)].div.querySelectorAll(".nav-item")].find((a) => a.style.display !== "none");
    if (first && navState.groups[Number(b.dataset.mod)].div.querySelectorAll(".nav-item").length === 1) location.hash = first.getAttribute("href");
    $("#sidenav").classList.remove("collapsed");
  }));
}

function navShow(i) {
  navState.mod = i;
  navState.groups.forEach((g, n) => { g.div.style.display = n === i ? "" : "none"; });
  $$(".mod-btn").forEach((b) => b.classList.toggle("active", Number(b.dataset.mod) === i));
}

// after login / authorization changes and on every route: hide modules without entries, select the current one
function navSync() {
  navBuild();
  navState.groups.forEach((g, i) => {
    const visible = [...g.div.querySelectorAll(".nav-item")].some((a) => a.style.display !== "none");
    const btn = $(`.mod-btn[data-mod="${i}"]`);
    if (btn) btn.style.display = visible ? "" : "none";
  });
  const active = $(".nav-item.active");
  const g = active ? active.closest(".nav-group") : null;
  navShow(g ? Number(g.dataset.mod) : navState.mod ?? 0);
}
