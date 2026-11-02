"""End-to-end check for users and general authorizations, through the HTTP API.

No session -> 401; wrong password refused; the sales user (sales full, items read-only, no
journal entries) may add an A/R invoice and read items but not change them, and may not see
journal entries; the accountant posts a journal entry recorded under its user code; a new user
gets authorizations from the manager, is locked and cannot log in any more; passwords follow
the rules and can be changed; the last superuser cannot be removed; logout ends the session.

Run after app.seed (rerunnable):  python -m app.verify_users
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models.users import User


def _client(code: str, password: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"user_code": code, "password": password})
    assert r.status_code == 200, (code, r.text)
    return c


def main() -> None:
    anon = TestClient(app)
    assert anon.get("/api/journal-entries").status_code == 401
    assert anon.post("/api/auth/login", json={"user_code": "manager", "password": "wrong"}).status_code == 401
    assert anon.get("/health").status_code == 200 and anon.get("/").status_code == 200  # web client is public
    print("1 Without a session: API 401, wrong password refused, web client and /health public")

    sales = _client("sales", "sales2026")
    me = sales.get("/api/auth/me").json()
    assert me["permissions"]["SALES"] == "F" and me["permissions"]["JE"] == "N" and me["permissions"]["ITEMS"] == "R"
    r = sales.post("/api/documents/13", json={"doc_date": date.today().isoformat(), "card_code": "C10000", "doc_type": "S",
                                              "lines": [{"dscription": "Service", "acct_code": "412000", "price": 1000, "vat_group": "OCS18"}]})
    assert r.status_code == 200, r.text
    inv = r.json()
    assert sales.get("/api/items").status_code == 200 and sales.get("/api/items/A00001").status_code == 200
    assert sales.patch("/api/items/A00001", json={"frgn_name": "x"}).status_code == 403
    assert sales.get("/api/journal-entries").status_code == 403
    assert sales.post("/api/documents/18", json={"doc_date": "2026-01-01", "card_code": "V10000", "lines": []}).status_code == 403
    assert sales.get("/api/users").status_code == 403
    print(f"2 Sales user: added A/R invoice {inv['doc_num']}; items read-only (change 403); journal entries, A/P documents, users 403")

    acc = _client("accountant", "account2026")
    je = acc.post("/api/journal-entries", json={"ref_date": date.today().isoformat(), "memo": "Accrual by accountant", "lines": [
        {"account": "612000", "debit": 100}, {"account": "112000", "credit": 100}]})
    assert je.status_code == 200 and je.json()["user_sign"] == "accountant", je.text
    assert acc.post("/api/documents/13", json={"doc_date": "2026-01-01", "card_code": "C10000", "lines": []}).status_code == 403
    assert acc.get("/api/documents/13").status_code == 200  # sales read-only
    print(f"3 Accountant: JE {je.json()['number']} recorded as {je.json()['user_sign']}; sales documents read-only")

    mgr = _client("manager", "manager")
    s = SessionLocal()
    n = (s.scalar(select(func.count()).select_from(User).where(User.user_code.like("vuser%"))) or 0) + 1
    s.close()
    code = f"vuser{n}"
    assert mgr.post("/api/users", json={"user_code": code, "u_name": "Verify", "password": "short"}).status_code == 422
    u = mgr.post("/api/users", json={"user_code": code, "u_name": "Verify user", "password": "Start2026x",
                                     "permissions": {"FINRPT": "R"}})
    assert u.status_code == 200, u.text
    uid = u.json()["user_id"]
    new = _client(code, "Start2026x")
    assert new.get("/api/reports/trial-balance?date_from=2026-01-01&date_to=2026-12-31").status_code == 200
    assert new.post("/api/auth/password", json={"old_password": "Start2026x", "new_password": "Changed2026y"}).status_code == 200
    assert TestClient(app).post("/api/auth/login", json={"user_code": code, "password": "Changed2026y"}).status_code == 200
    assert mgr.patch(f"/api/users/{uid}", json={"locked": True}).status_code == 200
    assert new.get("/api/reports/trial-balance?date_from=2026-01-01&date_to=2026-12-31").status_code == 401  # session ended
    assert TestClient(app).post("/api/auth/login", json={"user_code": code, "password": "Changed2026y"}).status_code == 401
    print(f"4 New user {code}: password rules, read-only reports, own password changed, locked -> logged out and refused")

    me_mgr = mgr.get("/api/auth/me").json()
    assert mgr.patch(f"/api/users/{me_mgr['user_id']}", json={"locked": True}).status_code == 422  # not yourself / last superuser
    assert mgr.post("/api/auth/logout").status_code == 200 and mgr.get("/api/cockpit").status_code == 401
    print("5 Manager cannot lock itself (last superuser); logout ends the session")
    print("\nOK - authentication and general authorizations are enforced.")


if __name__ == "__main__":
    main()
