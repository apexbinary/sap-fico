"""End-to-end check for CRM.

An opportunity of 5,00,000 starts in Lead (10 % -> weighted 50,000), moves to Proposal with 4,00,000
(50 % -> 2,00,000) linked to a quotation of the customer, and is won (100 %); a second one is lost and
needs a reason; vendors and foreign documents are refused; the pipeline counts open ones by stage;
activities: a meeting with times (duration), an overdue call that shows in the handling user's alert
until it is closed, bad times refused.

Run after app.seed (rerunnable):  python -m app.verify_crm
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.context import current_user_code, current_user_id
from app.database import SessionLocal
from app.services import alerts, crm
from app.services import documents as docs
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal


def _refused(fn, text: str, s) -> None:
    try:
        fn()
    except B1Error as exc:
        assert text in str(exc), exc
        s.rollback()
        return
    raise AssertionError(f"expected refusal: {text}")


def main() -> None:
    current_user_id.set(1)
    current_user_code.set("manager")
    s = SessionLocal()
    try:
        before = crm.pipeline(s)["open"]
        o = crm.create_opportunity(s, {"name": "Printers for new branch", "card_code": "C10000", "max_sum_loc": 500000, "pred_date": "2027-12-31"})
        assert o.status == "O" and o.wt_sum_loc == 50000 and o.clo_prcnt == 10
        _refused(lambda: crm.create_opportunity(s, {"name": "x", "card_code": "V10000"}), "customers or leads", s)
        q = docs.create_document(s, DR(obj="23", doc_date=date(2027, 11, 2), card_code="C10000", lines=[DL(item_code="S00001", quantity=D(1), price=D(400000))]))
        other = docs.create_document(s, DR(obj="23", doc_date=date(2027, 11, 2), card_code="C20000", lines=[DL(item_code="S00001", quantity=D(1), price=D(100))]))
        _refused(lambda: crm.advance(s, o.oppr_id, 3, D(400000), obj_type="23", doc_entry=other.doc_entry), "does not belong", s)
        crm.advance(s, o.oppr_id, 3, D(400000), obj_type="23", doc_entry=q.doc_entry)
        o = crm.get(s, o.oppr_id)
        assert o.wt_sum_loc == 200000 and len(o.lines) == 2 and o.lines[0].close_date is not None and o.lines[1].doc_number == q.doc_entry
        mid = crm.pipeline(s)["open"]
        assert mid["count"] - before["count"] == 1 and mid["weighted"] - before["weighted"] == 200000
        crm.close(s, o.oppr_id, won=True)
        assert crm.get(s, o.oppr_id).status == "W" and crm.get(s, o.oppr_id).wt_sum_loc == 400000
        o2 = crm.create_opportunity(s, {"name": "Toner contract", "card_code": "C20000", "max_sum_loc": 80000, "stage": 2})
        _refused(lambda: crm.close(s, o2.oppr_id, won=False), "reason", s)
        crm.close(s, o2.oppr_id, won=False, reason="Price")
        p = crm.pipeline(s)
        assert p["open"]["count"] == before["count"] and p["won"]["count"] >= 1 and p["lost"]["count"] >= 1
        print(f"1 Opportunity {o.oppr_id}: Lead 5,00,000 (weighted 50,000) -> Proposal 4,00,000 with quotation {q.doc_num} (2,00,000) -> won; "
              f"opportunity {o2.oppr_id} lost (reason needed); vendors and other partners' documents refused; pipeline win rate {p['win_rate']} %")

        meet = crm.save_activity(s, {"action": "M", "details": "Demo at customer", "card_code": "C10000", "recontact": "2027-11-10",
                                     "begin_time": "10:00", "end_time": "11:30", "opr_id": o.oppr_id, "priority": "2"})
        assert meet.duration == 90 and meet.attend_user == 1
        _refused(lambda: crm.save_activity(s, {"action": "C", "details": "x", "recontact": "2027-11-10", "begin_time": "25:00"}), "HH:MM", s)
        _refused(lambda: crm.save_activity(s, {"action": "C", "details": "x", "recontact": "2027-11-10", "begin_time": "11:00", "end_time": "10:00"}), "before the start", s)
        call = crm.save_activity(s, {"action": "C", "details": "Follow up payment", "card_code": "C20000", "recontact": (date.today() - timedelta(days=2)).isoformat()})
        mine = {a["type"]: a for a in alerts.for_user(s, 1)["alerts"]}
        assert any("Follow up payment" in i["text"] and "overdue" in i["text"] for i in mine["ACTIVITY"]["items"])
        crm.save_activity(s, {"closed": True}, call.clg_code)
        after = {a["type"]: a for a in alerts.for_user(s, 1)["alerts"]}
        assert not any("Follow up payment" in i["text"] and i["link"].endswith(f"id={call.clg_code}") for i in after.get("ACTIVITY", {"items": []})["items"])
        assert crm.opportunity_out(s, crm.get(s, o.oppr_id))["activities"][0]["clg_code"] == meet.clg_code
        print(f"2 Meeting 10:00-11:30 (90 min) linked to the opportunity; bad / reversed times refused; overdue call in the user's alert "
              "until closed")
        print("\nOK - CRM opportunities and activities work like B1.")
    finally:
        s.close()
        current_user_id.set(None)
        current_user_code.set(None)


if __name__ == "__main__":
    main()
