"""End-to-end check for approval procedures and alerts.

Template: sales orders of user 'sales' above 1,00,000 or with a discount of 10 % or more need the
accountant (stage 1) and then the manager (stage 2). A small order is added at once; a large one is
validated and held (no document, no number used); only the stage's authorizer decides, once; after
both stages the originator adds the document; a rejected request cannot be added; the discount
condition holds an order too. Alerts: the approval alert lists the request for its authorizer until
decided; the minimum stock alert reaches its recipients only.

Run after app.seed (rerunnable):  python -m app.verify_approvals
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select

from app.api_documents import DocumentIn, build_request, create_document
from app.context import current_user_id
from app.database import SessionLocal
from app.models.approvals import ApprovalTemplate
from app.models.documents import DOCUMENT_CLASSES
from app.models.inventory import ItemWarehouse
from app.services import alerts, approvals
from app.services.admin import B1Error

D = Decimal
DAY = date(2027, 8, 16)
SALES, ACCOUNTANT, MANAGER = 2, 3, 1


def _order(s, price: int, disc: int = 0) -> dict:
    current_user_id.set(SALES)
    return create_document("17", DocumentIn(doc_date=DAY, card_code="C10000", disc_prcnt=D(disc),
                                            lines=[{"item_code": "S00001", "quantity": 1, "price": price}]), s)


def _refused(fn, text: str, s) -> None:
    try:
        fn()
    except (B1Error, HTTPException) as exc:
        assert text in str(getattr(exc, "detail", exc)), exc
        s.rollback()
        return
    raise AssertionError(f"expected refusal: {text}")


def main() -> None:
    s = SessionLocal()
    try:
        st1 = approvals.save_stage(s, {"name": "Accounts", "authorizers": [ACCOUNTANT], "max_reqr": 1})
        st2 = approvals.save_stage(s, {"name": "Management", "authorizers": [MANAGER], "max_reqr": 1})
        t = approvals.save_template(s, {"name": "Large sales orders", "originators": [SALES], "documents": ["17"], "stages": [st1.wst_code, st2.wst_code],
                                        "conditions": [{"cond_id": "TOTAL", "op_code": "GT", "value": 100000}, {"cond_id": "DISC", "op_code": "GE", "value": 10}]})
        orders = lambda: s.scalar(select(func.count()).select_from(DOCUMENT_CLASSES["17"][0]))  # noqa: E731
        small = _order(s, 5000)
        assert "doc_entry" in small and "pending_approval" not in small
        n = orders()
        big = _order(s, 200000)["pending_approval"]
        assert orders() == n and big["status"] == "W" and big["stage"] == "Accounts" and big["doc_total"] == 236000 and "236000.00 > 100000" in big["reason"]
        print(f"1 Order of 5,000 added at once; order of 2,36,000 held as request {big['wdd_code']} ({big['reason']}), no document added")

        assert any(x["wdd_code"] == big["wdd_code"] for x in alerts.for_user(s, ACCOUNTANT)["alerts"][0]["items"] and
                   approvals.requests_for(s, ACCOUNTANT, False)["to_decide"])
        _refused(lambda: approvals.decide(s, big["wdd_code"], SALES, True), "not an authorizer", s)
        approvals.decide(s, big["wdd_code"], ACCOUNTANT, True, "ok, known customer")
        _refused(lambda: approvals.decide(s, big["wdd_code"], ACCOUNTANT, True), "not an authorizer of stage Management", s)
        assert not approvals.requests_for(s, ACCOUNTANT, False)["to_decide"] or all(
            x["wdd_code"] != big["wdd_code"] for x in approvals.requests_for(s, ACCOUNTANT, False)["to_decide"])
        _refused(lambda: approvals.generate(s, big["wdd_code"], SALES, False, lambda p: build_request("17", p)), "not approved", s)
        approvals.decide(s, big["wdd_code"], MANAGER, True)
        _refused(lambda: approvals.generate(s, big["wdd_code"], ACCOUNTANT, False, lambda p: build_request("17", p)), "Only the originator", s)
        entry = approvals.generate(s, big["wdd_code"], SALES, False, lambda p: build_request("17", p))
        doc = s.get(DOCUMENT_CLASSES["17"][0], entry)
        assert doc.doc_total == 236000 and orders() == n + 1
        print(f"2 Accounts then Management approve (others refused, once each); the originator adds order {doc.doc_num}")

        rej = _order(s, 150000)["pending_approval"]
        approvals.decide(s, rej["wdd_code"], ACCOUNTANT, False, "price too low")
        _refused(lambda: approvals.generate(s, rej["wdd_code"], SALES, False, lambda p: build_request("17", p)), "rejected", s)
        disc = _order(s, 1000, disc=15)["pending_approval"]
        assert "Discount %" in disc["reason"]
        approvals.decide(s, disc["wdd_code"], ACCOUNTANT, False)
        print(f"3 Request {rej['wdd_code']} rejected by Accounts cannot be added; a 15 % discount order is held as well")

        row = s.get(ItemWarehouse, ("A00002", "01"))
        before_min = row.min_stock
        row.min_stock = row.on_hand + 5
        s.commit()
        mgr = {a["type"]: a for a in alerts.for_user(s, MANAGER)["alerts"]}
        assert any("A00002" in i["text"] for i in mgr["MINSTOCK"]["items"])
        assert "MINSTOCK" not in {a["type"] for a in alerts.for_user(s, SALES)["alerts"]}
        row.min_stock = before_min
        s.commit()
        print("4 Minimum stock alert lists A00002 for its recipient (manager), not for the sales user; approval alert for the authorizer")
        print("\nOK - approval procedures and alerts work like B1.")
    finally:
        s.rollback()
        for tt in s.scalars(select(ApprovalTemplate)):
            tt.active = "N"  # leave no active template behind for the other checks
        s.commit()
        current_user_id.set(None)
        s.close()


if __name__ == "__main__":
    main()
