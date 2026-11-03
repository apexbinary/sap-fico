"""End-to-end check for the service module.

A serial-number managed printer is received and delivered to a customer: the delivery creates an
equipment card per serial number (status active, delivery document linked). A serial number
contract (4 h response, 24 h resolution) covers one of them; a customer contract of another customer
covers everything. A service call on the covered unit takes the contract and its deadlines, the
uncovered unit gets none; the call shows in the technician's alert, an activity links to it, it moves
to pending, cannot close without a resolution, closes and reopens. Wrong customers, vendors,
contract periods and empty item contracts are refused. Canceling a delivery removes its unused
equipment cards.

Run after app.seed (rerunnable):  python -m app.verify_service
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.context import current_user_code, current_user_id
from app.database import SessionLocal
from app.models.inventory import Item
from app.models.service import CustomerEquipment
from app.services import alerts, crm, masterdata, service
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
    today = date.today()
    with SessionLocal() as s:
        n = s.scalar(select(func.count()).select_from(Item).where(Item.item_code.like("SV%"))) + 1
        prn = f"SV{n:04d}"
        masterdata.create_item(s, masterdata.ItemRequest(item_code=prn, item_name="Service printer (serial)", itms_grp_cod=100, invntry_uom="Each",
                                                         dflt_wh="01", chapter_id="84433210", man_ser_num=True, prices={1: D(20000), 3: D(12000)}))
        sns = [f"{prn}-{i}" for i in (1, 2, 3)]
        docs.create_document(s, DR(obj="20", doc_date=today, card_code="V10000", lines=[
            DL(item_code=prn, quantity=D(3), price=D(12000), serials=[{"number": x} for x in sns])]))
        dl = docs.create_document(s, DR(obj="15", doc_date=today, card_code="C10000", lines=[
            DL(item_code=prn, quantity=D(2), price=D(20000), serials=[{"number": sns[0]}, {"number": sns[1]}])]))
        cards = s.scalars(select(CustomerEquipment).where(CustomerEquipment.item_code == prn).order_by(CustomerEquipment.internal_sn)).all()
        assert [c.internal_sn for c in cards] == sns[:2] and all(c.customer == "C10000" and c.status == "A" and c.dlv_type == "15"
                                                                 and c.dlv_entry == dl.doc_entry for c in cards), cards
        print(f"1 Delivery {dl.doc_num} of {sns[0]} / {sns[1]} to C10000 created equipment cards {cards[0].ins_id} and {cards[1].ins_id}")

        _refused(lambda: service.save_contract(s, {"cstmr_code": "V10000", "start_date": today, "end_date": today}), "Choose a customer", s)
        _refused(lambda: service.save_contract(s, {"cstmr_code": "C10000", "start_date": today, "end_date": today - timedelta(days=1)}), "ends before", s)
        _refused(lambda: service.save_contract(s, {"cstmr_code": "C10000", "cntrc_type": "I", "start_date": today, "end_date": today}), "needs the covered", s)
        ct = service.save_contract(s, {"cstmr_code": "C10000", "cntrc_type": "S", "start_date": today - timedelta(days=10),
                                       "end_date": today + timedelta(days=355), "rspns_time": 4, "resol_time": 24, "incl_travel": True,
                                       "lines": [{"item_code": prn, "internal_sn": sns[0]}]})
        other = service.save_contract(s, {"cstmr_code": "C20000", "cntrc_type": "C", "start_date": today, "end_date": today + timedelta(days=30), "rspns_time": 8})
        assert service.covering_contract(s, "C10000", prn, sns[0], today).contract_id == ct.contract_id
        assert service.covering_contract(s, "C10000", prn, sns[0], today + timedelta(days=400)) is None
        assert service.covering_contract(s, "C20000", "A00001", None, today).cntrc_type == "C"
        print(f"2 Serial contract {ct.contract_id} covers {sns[0]} for a year (4 h / 24 h); customer contract {other.contract_id} covers all of C20000; "
              "vendor, reversed period and an item contract without items refused")

        _refused(lambda: service.create_call(s, {"customer": "C10000", "subject": " "}), "subject", s)
        _refused(lambda: service.create_call(s, {"customer": "C20000", "subject": "x", "ins_id": cards[0].ins_id}), "does not belong", s)
        call = service.create_call(s, {"customer": "C10000", "subject": "Paper jam", "ins_id": cards[0].ins_id, "priority": "H", "assignee": 1,
                                       "origin": "Phone", "call_type": "Repair"})
        assert call.contract == ct.contract_id and call.internal_sn == sns[0] and call.item_code == prn
        assert call.response_by - call.create_date == timedelta(hours=4) and call.resol_by - call.create_date == timedelta(hours=24)
        free = service.create_call(s, {"customer": "C10000", "subject": "Noise", "internal_sn": sns[1], "item_code": prn})
        assert free.contract is None and free.response_by is None and free.ins_id == cards[1].ins_id
        mine = alerts.for_user(s, 1)
        assert any(f"Service call {call.call_id} " in i["text"] for a in mine["alerts"] for i in a["items"]), mine
        print(f"3 Call {call.call_id} on {sns[0]} takes contract {ct.contract_id} (respond in 4 h, resolve in 24 h) and shows in manager's alert; "
              f"call {free.call_id} on {sns[1]} has no contract")

        act = crm.save_activity(s, {"action": "C", "details": "Called customer about jam", "card_code": "C10000", "recontact": today,
                                    "doc_type": "191", "doc_entry": call.call_id})
        service.update_call(s, call.call_id, {"status": -2, "responded": True})
        _refused(lambda: service.update_call(s, call.call_id, {"status": -1}), "resolution", s)
        service.update_call(s, call.call_id, {"resolution": "Replaced the pickup roller", "status": -1})
        out = service.call_out(s, s.get(type(call), call.call_id))
        assert out["status_name"] == "Closed" and out["responded"] and out["close_date"] and not out["resolution_late"]
        assert [a["clg_code"] for a in out["activities"]] == [act.clg_code]
        _refused(lambda: service.update_call(s, call.call_id, {"subject": "changed"}), "is closed", s)
        service.update_call(s, call.call_id, {"status": -3})
        assert s.get(type(call), call.call_id).close_date is None
        service.update_call(s, call.call_id, {"status": -1})
        rep = service.report(s)
        assert rep["closed"] >= 1 and rep["open"] >= 1
        print(f"4 Activity {act.clg_code} linked to call {call.call_id}; pending, close refused without a resolution, closed, reopened and closed again; "
              f"overview: {rep['open']} open, {rep['closed']} closed")

        dl2 = docs.create_document(s, DR(obj="15", doc_date=today, card_code="C20000", lines=[
            DL(item_code=prn, quantity=D(1), price=D(20000), serials=[{"number": sns[2]}])]))
        assert s.scalar(select(CustomerEquipment).where(CustomerEquipment.internal_sn == sns[2])).customer == "C20000"
        docs.cancel_document(s, "15", dl2.doc_entry)
        assert s.scalar(select(CustomerEquipment).where(CustomerEquipment.internal_sn == sns[2])) is None
        eq = service.save_equipment(s, {"customer": "C30000", "item_code": "A00001", "manuf_sn": "MFG-778"})
        _refused(lambda: service.save_equipment(s, {"customer": "C30000", "item_code": "A00001"}), "serial number", s)
        print(f"5 Delivery {dl2.doc_num} of {sns[2]} to C20000 created a card, its cancellation removed it; manual card {eq.ins_id} "
              "for MFG-778; a card without a serial number refused")
    print("\nOK - service calls, contracts and equipment cards work like B1.")


if __name__ == "__main__":
    main()
