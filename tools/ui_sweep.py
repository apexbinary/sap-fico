"""Browser sweep: every menu screen as manager, sales and accountant, plus document lists, a document,
new-document forms and detail screens. Reports JS errors, failed API calls (status >= 400 other than
expected 401 before login / 403 for unauthorized areas) and screens that stay on "Loading"."""
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
EDGE = sys.argv[2] if len(sys.argv) > 2 else r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
USERS = [("manager", "manager"), ("sales", "sales2026"), ("accountant", "account2026")]
problems = []


def sweep(pw, user, pwd):
    b = pw.chromium.launch(executable_path=EDGE, headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    cur = {"url": ""}
    pg.on("pageerror", lambda e: problems.append(f"[{user}] JS error {cur['url']}: {e}"))
    pg.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and problems.append(f"[{user}] console {cur['url']}: {m.text}"))
    pg.on("response", lambda r: "/api/" in r.url and r.status >= 400 and r.status not in (401, 403)
          and problems.append(f"[{user}] HTTP {r.status} {r.request.method} {r.url.split('8000')[1]} on {cur['url']}"))
    pg.on("dialog", lambda d: d.dismiss())
    pg.goto(BASE + "/")
    pg.fill("#lg-user", user)
    pg.fill("input[type=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_timeout(2500)
    links = pg.evaluate("[...new Set([...document.querySelectorAll('.nav-item')].filter(a => a.style.display !== 'none').map(a => a.getAttribute('href')))]")
    extra = ["#/payments?kind=incoming", "#/payments?kind=outgoing", "#/payment?kind=incoming", "#/payment?kind=outgoing", "#/journal-entry",
             "#/gst-returns?year=2027&month=5&tab=gstr1", "#/gst-returns?year=2027&month=5&tab=gstr3b", "#/gst-returns?tab=gstr2b",
             "#/tds-returns?fy=2027&quarter=3&kind=D", "#/tds-returns?fy=2027&quarter=3&kind=C", "#/opening-balances?kind=partners",
             "#/opening-balances?kind=items"] if user == "manager" else []
    seen = 0
    for href in links + extra:
        cur["url"] = href
        try:
            pg.goto(BASE + "/" + href)
            pg.wait_for_timeout(1400)
            txt = pg.evaluate("document.querySelector('#view, main, .content') ? (document.querySelector('#view, main, .content').innerText || '') : document.body.innerText")
            if "Loading…" in txt[:200]:
                pg.wait_for_timeout(2500)
                txt = pg.evaluate("document.body.innerText")
                if "Loading…" in txt[:400]:
                    problems.append(f"[{user}] still loading: {href}")
            seen += 1
        except Exception as e:  # noqa: BLE001
            problems.append(f"[{user}] {href}: {e}")
    # documents: list -> first document -> new form, for every type in the nav
    if user == "manager":
        for obj in ["23", "17", "15", "16", "13", "14", "203", "540000006", "22", "20", "21", "18", "19", "204", "59", "60", "67"]:
            cur["url"] = f"#/docs?obj={obj}"
            pg.goto(BASE + f"/#/docs?obj={obj}")
            pg.wait_for_timeout(1300)
            row = pg.query_selector("table tbody tr[onclick]")
            if row:
                row.click()
                pg.wait_for_timeout(1500)
                cur["url"] = pg.url.split("#")[1]
            cur["url"] = f"#/doc?obj={obj}"
            pg.goto(BASE + f"/#/doc?obj={obj}")
            pg.wait_for_timeout(1500)
            seen += 1
        for href in ["#/print?obj=13&entry=1", "#/tds-certificate?fy=2027&quarter=3&kind=D&card=V95020", "#/journal?id=1"]:
            cur["url"] = href
            pg.goto(BASE + "/" + href)
            pg.wait_for_timeout(1600)
            seen += 1
    b.close()
    return seen


with sync_playwright() as pw:
    for u, p in USERS:
        n = sweep(pw, u, p)
        print(f"{u}: {n} screens")
print("PROBLEMS:" if problems else "no problems: no JS errors, no failed API calls, no stuck screens")
for x in problems:
    print(" ", x)
