"""End-to-end check for batch and serial numbers.

Batch item: a goods receipt PO needs the batches (sum = quantity), creates them with expiry
dates; a delivery without batches selects the earliest expiry first and skips expired batches; a
return copied from the delivery takes its batches back; a transfer moves the same batch between
warehouses; issuing more than a batch holds is refused; canceling reverses the logs; the batch
history shows every move. Serial item: serial numbers are new on receipt, unique, in stock on
issue, whole units, selected automatically when not named. Batch / serial quantities per
warehouse always equal the item's warehouse stock; management cannot change with stock.

Run after app.seed (rerunnable: fresh items each run):  python -m app.verify_batches
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.batches import BatchQuantity, SerialQuantity
from app.models.inventory import Item, ItemWarehouse
from app.services import batches as bt
from app.services import documents as docs
from app.services import masterdata
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 11, 22)


def _item(s, prefix: str, name: str, batch: bool) -> str:
    n = s.scalar(select(func.count()).select_from(Item).where(Item.item_code.like(f"{prefix}%"))) + 1
    code = f"{prefix}{n:04d}"
    masterdata.create_item(s, masterdata.ItemRequest(item_code=code, item_name=name, itms_grp_cod=101, invntry_uom="Each", dflt_wh="01",
                                                     chapter_id="84433210", man_btch_num=batch, man_ser_num=not batch,
                                                     prices={1: D(100), 3: D(60)}))
    return code


def _refused(fn, text: str) -> None:
    try:
        fn()
    except B1Error as exc:
        assert text in str(exc), exc
        return
    raise AssertionError(f"expected refusal: {text}")


def _qty(s, code: str, number: str, whs: str = "01") -> D:
    rows = [r for r in bt.numbers(s, code, with_stock=False) if r["number"] == number and r["whs_code"] == whs]
    return rows[0]["quantity"] if rows else D(0)


def _consistent(s, code: str) -> None:
    for w in s.scalars(select(ItemWarehouse).where(ItemWarehouse.item_code == code)):
        b = s.scalar(select(func.coalesce(func.sum(BatchQuantity.quantity), 0)).where(BatchQuantity.item_code == code, BatchQuantity.whs_code == w.whs_code))
        sr = s.scalar(select(func.coalesce(func.sum(SerialQuantity.quantity), 0)).where(SerialQuantity.item_code == code, SerialQuantity.whs_code == w.whs_code))
        assert b + sr == w.on_hand, (code, w.whs_code, b, sr, w.on_hand)


def main() -> None:
    s = SessionLocal()
    try:
        med = _item(s, "B9", "Paracetamol 500 mg (box)", True)
        grpo = lambda lines: docs.create_document(s, DR(obj="20", doc_date=DAY, card_code="V10000", lines=lines))  # noqa: E731
        _refused(lambda: grpo([DL(item_code=med, quantity=D(30))]), "enter the batches")
        _refused(lambda: grpo([DL(item_code=med, quantity=D(30), batches=[{"number": "LOT-A", "quantity": 10}])]), "must equal")
        grpo([DL(item_code=med, quantity=D(30), batches=[{"number": "LOT-A", "quantity": 10, "exp_date": "2028-06-30"},
                                                          {"number": "LOT-B", "quantity": 20, "exp_date": "2028-01-31", "mnf_date": "2027-01-31"}])])
        grpo([DL(item_code=med, quantity=D(5), batches=[{"number": "LOT-OLD", "quantity": 5, "exp_date": "2027-10-31"}])])
        assert _qty(s, med, "LOT-A") == 10 and _qty(s, med, "LOT-B") == 20 and _qty(s, med, "LOT-OLD") == 5
        _consistent(s, med)
        print("1 Goods receipts need their batches (sum = quantity): LOT-A 10 (exp 30-06-2028), LOT-B 20 (exp 31-01-2028), "
              "LOT-OLD 5 (expired 31-10-2027)")

        dn = docs.create_document(s, DR(obj="15", doc_date=DAY, card_code="C10000", lines=[DL(item_code=med, quantity=D(25))]))
        assert _qty(s, med, "LOT-B") == 0 and _qty(s, med, "LOT-A") == 5 and _qty(s, med, "LOT-OLD") == 5
        _refused(lambda: docs.create_document(s, DR(obj="15", doc_date=DAY, card_code="C10000", lines=[DL(item_code=med, quantity=D(10))])),
                 "not expired")
        _refused(lambda: docs.create_document(s, DR(obj="15", doc_date=DAY, card_code="C10000", lines=[
            DL(item_code=med, quantity=D(6), batches=[{"number": "LOT-A", "quantity": 6}])])), "5 in warehouse 01, 6 needed")
        print(f"2 Delivery {dn.doc_num} of 25 without batches: LOT-B 20 (earliest expiry) + LOT-A 5; expired LOT-OLD is not "
              "selected; more than a batch holds is refused")

        ret = docs.create_document(s, DR(obj="16", doc_date=DAY, card_code="C10000", lines=[
            DL(base_type="15", base_entry=dn.doc_entry, base_line=0, quantity=D(4))]))
        assert _qty(s, med, "LOT-B") == 4 and _qty(s, med, "LOT-A") == 5
        tr = docs.create_document(s, DR(obj="67", doc_date=DAY, from_whs="01", to_whs="02", lines=[
            DL(item_code=med, quantity=D(3), from_whs_cod="01", whs_code="02", batches=[{"number": "LOT-A", "quantity": 3}])]))
        assert _qty(s, med, "LOT-A") == 2 and _qty(s, med, "LOT-A", "02") == 3
        old = docs.create_document(s, DR(obj="60", doc_date=DAY, lines=[
            DL(item_code=med, quantity=D(5), batches=[{"number": "LOT-OLD", "quantity": 5}])]))
        assert _qty(s, med, "LOT-OLD") == 0
        _consistent(s, med)
        print(f"3 Return {ret.doc_num} copied from the delivery takes back 4 of LOT-B; transfer {tr.doc_num} moves 3 of LOT-A to "
              f"warehouse 02; goods issue {old.doc_num} writes off the expired LOT-OLD (named explicitly)")

        docs.cancel_document(s, "67", tr.doc_entry, DAY)
        docs.cancel_document(s, "16", ret.doc_entry, DAY)
        assert _qty(s, med, "LOT-A") == 5 and _qty(s, med, "LOT-A", "02") == 0 and _qty(s, med, "LOT-B") == 0
        _consistent(s, med)
        hist = bt.history(s, med, "LOT-B")
        assert [h["quantity"] for h in hist] == [20, -20, 4] and hist[-1]["reversed"]
        _refused(lambda: bt.check_item_change(s.get(Item, med), {"man_btch_num": False}), "has stock")
        print("4 Canceling the transfer and the return reverses their batches; history of LOT-B: +20 receipt, -20 delivery, "
              "+4 return (reversed); management cannot change while in stock")

        prn = _item(s, "S9", "Laser printer (serial)", False)
        docs.create_document(s, DR(obj="20", doc_date=DAY, card_code="V10000", lines=[
            DL(item_code=prn, quantity=D(3), serials=[{"number": "SN-001"}, {"number": "SN-002"}, {"number": "SN-003", "exp_date": "2030-12-31"}])]))
        _refused(lambda: docs.create_document(s, DR(obj="20", doc_date=DAY, card_code="V10000", lines=[
            DL(item_code=prn, quantity=D(1), serials=[{"number": "SN-002"}])])), "already in stock")
        _refused(lambda: docs.create_document(s, DR(obj="20", doc_date=DAY, card_code="V10000", lines=[
            DL(item_code=prn, quantity=D(2), serials=[{"number": "SN-009"}, {"number": "SN-009"}])])), "entered twice")
        _refused(lambda: docs.create_document(s, DR(obj="59", doc_date=DAY, lines=[
            DL(item_code=prn, quantity=D("1.5"), price=D(1000), serials=[{"number": "SN-010"}])])), "whole units")
        d2 = docs.create_document(s, DR(obj="15", doc_date=DAY, card_code="C10000", lines=[
            DL(item_code=prn, quantity=D(2), serials=[{"number": "SN-001"}, {"number": "SN-003"}])]))
        _refused(lambda: docs.create_document(s, DR(obj="15", doc_date=DAY, card_code="C10000", lines=[
            DL(item_code=prn, quantity=D(1), serials=[{"number": "SN-001"}])])), "0 in warehouse 01")
        gi = docs.create_document(s, DR(obj="60", doc_date=DAY, lines=[DL(item_code=prn, quantity=D(1))]))
        left = [r["number"] for r in bt.numbers(s, prn)]
        assert left == [] and _qty(s, prn, "SN-002") == 0
        _consistent(s, prn)
        print(f"5 Serial numbers SN-001..003 received; duplicates, repeated numbers and 1.5 units refused; delivery {d2.doc_num} "
              f"ships SN-001 / SN-003, SN-001 cannot ship again; goods issue {gi.doc_num} takes SN-002 automatically")
        print("\nOK - batches and serial numbers follow every stock move like B1.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
