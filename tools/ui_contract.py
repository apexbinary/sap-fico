"""UI contract check: every ✅ row of docs/dependency-matrix.md is opened in a browser (as manager) and its field
must exist on the screen. Also fails on JavaScript errors and failed API calls while checking.

    python tools/ui_contract.py http://127.0.0.1:8000 [path-to-chromium-or-edge]

Needs `pip install playwright` and a Chromium / Edge browser (default: the Edge of Windows). Run it after every
feature together with app.verify_all; a new concept / screen gets its matrix rows in the same commit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

MATRIX = Path(__file__).resolve().parents[1] / "docs" / "dependency-matrix.md"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def rows() -> list[dict]:
    out = []
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6 or not cells[5].startswith("✅"):
            continue
        out.append({"concept": cells[0], "screen": cells[1], "url": cells[2], "setup": cells[3], "field": cells[4]})
    return out


def setup(pg, actions: str) -> None:
    for act in filter(None, (a.strip() for a in actions.split(";"))):
        kind, _, arg = act.partition(":")
        if kind == "select":
            sel, _, value = arg.rpartition("=")
            pg.evaluate("""([s, v]) => { const e = document.querySelector(s); if (!e) throw new Error('setup: no ' + s);
                e.value = v; e.dispatchEvent(new Event('change', {bubbles: true})); }""", [sel, value])
        elif kind == "click":
            pg.evaluate("(s) => { const e = document.querySelector(s); if (!e) throw new Error('setup: no ' + s); e.click(); }", arg)
        else:
            raise ValueError(f"unknown setup action {act}")
        pg.wait_for_timeout(900)


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    browser = sys.argv[2] if len(sys.argv) > 2 else EDGE
    failures, checked = [], 0
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=browser, headless=True)
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        cur = {"row": None}
        pg.on("pageerror", lambda e: failures.append(f"JS error on {cur['row']}: {e}"))
        pg.on("response", lambda r: "/api/" in r.url and r.status >= 400 and r.status not in (401, 403, 404)
              and failures.append(f"HTTP {r.status} {r.url.split('/api/')[1]} on {cur['row']}"))
        pg.on("dialog", lambda d: d.dismiss())
        pg.goto(base + "/")
        pg.fill("#lg-user", "manager")
        pg.fill("input[type=password]", "manager")
        pg.click("button[type=submit]")
        pg.wait_for_timeout(2000)
        for r in rows():
            cur["row"] = f"{r['concept']} / {r['screen']}"
            try:
                pg.goto(base + "/" + r["url"])
                pg.wait_for_timeout(1500)
                setup(pg, r["setup"])
                missing = [s.strip() for s in r["field"].split("&") if not pg.query_selector(s.strip())]
                if missing:
                    failures.append(f"MISSING {cur['row']} ({r['url']}): {' & '.join(missing)}")
            except Exception as e:  # noqa: BLE001
                failures.append(f"ERROR {cur['row']} ({r['url']}): {e}")
            checked += 1
        b.close()
    print(f"{checked} matrix rows checked")
    for f in failures:
        print(" ", f)
    print("UI CONTRACT OK" if not failures else f"UI CONTRACT FAILED ({len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
