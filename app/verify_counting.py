"""End-to-end check for inventory counting / inventory posting and item groups.

A counting snapshots the warehouse quantities; counted 12 of 10 and 7 of 10 (batch item): the
posting receives the surplus at the item cost and issues the shortage (batches selected
automatically) — stock, value and batches follow, the counting closes; an item cannot be in two
open countings; a counting whose items moved since must be recounted; a batch surplus needs
its batch numbers; a whole warehouse can be counted. Item groups: added with their accounts;
the inventory account cannot change while items of the group have stock.

Run after app.seed (rerunnable: fresh items each run):  python -m app.verify_counting
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.finance import Account
from app.models.inventory import Item, ItemWarehouse
from app.services import batches as bt
from app.services import counting
from app.services import documents as docs
from app.services import masterdata
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 12, 6)


def _item(s, batch: bool, group: int = 101) -> str:
    n = s.scalar(select(func.count()).select_from(Item).where(Item.item_code.like("K9%"))) + 1
    code = f"K9{n:04d}"
    masterdata.create_item(s, masterdata.ItemRequest(item_code=code, item_name="Counted item", itms_grp_cod=group, invntry_uom="Each",
                                                     dflt_wh="01", man_btch_num=batch, prices={1: D(20), 3: D(12)}))
    return code


def _refused(fn, text: str) -> None:
    try:
        fn()
    except (B1Error, HTTPException) as exc:
        assert text in str(getattr(exc, "detail", exc)), exc
        return
    raise AssertionError(f"expected refusal: {text}")


def _whs(s, code: str, whs: str = "01") -> D:
    row = s.get(ItemWarehouse, (code, whs))
    s.refresh(row)
    return row.on_hand


def main() -> None:
    s = SessionLocal()
    try:
        a, b = _item(s, False), _item(s, True)
        docs.create_document(s, DR(obj="20", doc_date=DAY, card_code="V10000", lines=[
            DL(item_code=a, quantity=D(10), price=D(12)),
            DL(item_code=b, quantity=D(10), price=D(12), batches=[{"number": "LOT-K", "quantity": 10, "exp_date": "2029-01-31"}])]))
        cnt = counting.create(s, DAY, [{"item_code": a, "whs_code": "01"}, {"item_code": b, "whs_code": "01"}], remarks="Year-end count")
        assert [l.in_whs_qty for l in cnt.lines] == [10, 10]
        _refused(lambda: counting.create(s, DAY, [{"item_code": a, "whs_code": "01"}]), "already in open counting")
        counting.record(s, cnt.doc_entry, [{"line_num": 0, "count_qty": 12}, {"line_num": 1, "count_qty": 7}])
        assert [l.difference for l in cnt.lines] == [2, -3]
        p = counting.post(s, cnt.doc_entry, DAY)
        assert _whs(s, a) == 12 and _whs(s, b) == 7 and cnt.status == "C"
        lot = [r for r in bt.numbers(s, b) if r["number"] == "LOT-K"][0]
        assert lot["quantity"] == 7 and p.value_in == 24 and p.value_out == 36 and p.gr_entry and p.gi_entry
        _refused(lambda: counting.record(s, cnt.doc_entry, [{"line_num": 0, "count_qty": 1}]), "is closed")
        print(f"1 Counting {cnt.doc_num}: {a} 10 -> 12, {b} 10 -> 7; posting {p.doc_num}: goods receipt +2 (24.00), goods issue -3 "
              f"(36.00, LOT-K 10 -> 7); closed; an item in two open countings is refused")

        c2 = counting.create(s, DAY, [{"item_code": a, "whs_code": "01"}])
        counting.record(s, c2.doc_entry, [{"line_num": 0, "count_qty": 11}])
        docs.create_document(s, DR(obj="60", doc_date=DAY, lines=[DL(item_code=a, quantity=D(1))]))
        _refused(lambda: counting.post(s, c2.doc_entry, DAY), "changed since the counting was created")
        counting.close(s, c2.doc_entry)
        c3 = counting.create(s, DAY, [{"item_code": b, "whs_code": "01"}])
        counting.record(s, c3.doc_entry, [{"line_num": 0, "count_qty": 9}])
        _refused(lambda: counting.post(s, c3.doc_entry, DAY), "enter the batches")
        counting.record(s, c3.doc_entry, [{"line_num": 0, "count_qty": 9, "batches": [{"number": "LOT-FOUND", "quantity": 2}]}])
        counting.post(s, c3.doc_entry, DAY)
        assert _whs(s, b) == 9 and [r["quantity"] for r in bt.numbers(s, b) if r["number"] == "LOT-FOUND"] == [2]
        z = _item(s, False)
        from app.models.inventory import ItemPrice

        for ip in s.scalars(select(ItemPrice).where(ItemPrice.item_code == z)):
            ip.price = D(0)
        s.commit()
        cz = counting.create(s, DAY, [{"item_code": z, "whs_code": "01"}])
        counting.record(s, cz.doc_entry, [{"line_num": 0, "count_qty": 3}])
        _refused(lambda: counting.post(s, cz.doc_entry, DAY), "no item cost")
        for ip in s.scalars(select(ItemPrice).where(ItemPrice.item_code == z)):
            ip.price = D(15)
        s.commit()
        pz = counting.post(s, cz.doc_entry, DAY)
        assert pz.value_in == 45
        print("2 A counting whose item moved must be recounted (closed without posting); a batch surplus needs its batch: "
              "LOT-FOUND 2 created; a surplus without any cost is refused, with a list price valued 3 x 15")

        from app.api_masterdata import ItemGroupIn, add_item_group, change_item_group

        g = add_item_group(ItemGroupIn(itms_grp_nam="Counted", bal_invnt_ac="115000", sale_cost_ac="511000", revenues_ac="411000",
                                       expenses_ac="611000", price_dif_ac="512000"), s)
        _refused(lambda: add_item_group(ItemGroupIn(itms_grp_nam="Bad", bal_invnt_ac="1", sale_cost_ac="511000", revenues_ac="411000",
                                                    expenses_ac="611000", price_dif_ac="512000"), s), "title account")
        c = _item(s, False, g["itms_grp_cod"])
        whole = counting.create(s, DAY, whs_code="02", item_group=g["itms_grp_cod"])
        assert [l.item_code for l in whole.lines] == [c]
        counting.close(s, whole.doc_entry)
        _refused(lambda: change_item_group(101, ItemGroupIn(bal_invnt_ac="116000"), s), "cannot change")
        assert change_item_group(g["itms_grp_cod"], ItemGroupIn(itms_grp_nam="Counted 2"), s)["itms_grp_nam"] == "Counted 2"
        assert s.scalar(select(func.sum(Account.curr_total)).where(Account.postable == "Y")) == 0
        print(f"3 Item group {g['itms_grp_cod']} added (title account refused); counting of a whole warehouse / group lists its items; "
              "the inventory account of a group with stock cannot change; trial balance 0")
        print("\nOK - inventory counting, inventory posting and item groups work like B1.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
