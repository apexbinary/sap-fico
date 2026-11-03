"""End-to-end check for bills of materials and production orders.

Kit = 2 x part A (manual, cost 100) + 3 x part B (backflush, cost 20) per unit. An order for 10:
the BOM cost is 260; a cycle in BOMs is refused; issue all manual components (20 A = 2,000 to WIP);
receive 6 kits: 18 B are backflushed (360), the kits come in at 2 x 100 + 3 x 20 = 260 each (1,560);
receive 4 more (backflush 12 B = 240, 4 x 260 = 1,040); WIP is 2,000 + 600 - 2,600 = 0 ... then an
extra issue of 1 A (100) leaves WIP 100, which closing posts to the production variance account; the
WIP account of the order nets to zero; stock quantities follow; canceling needs an order without
postings.

Run after app.seed (rerunnable: fresh items each run):  python -m app.verify_production
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.finance import Account, JournalLine
from app.models.inventory import Item
from app.services import documents as docs
from app.services import masterdata, production
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 9, 6)


def _item(s, code: str, name: str, group: int = 101) -> str:
    masterdata.create_item(s, masterdata.ItemRequest(item_code=code, item_name=name, itms_grp_cod=group, invntry_uom="Each", dflt_wh="01",
                                                     chapter_id="84433210", prices={1: D(500), 3: D(10)}))
    return code


def _refused(fn, text: str, s) -> None:
    try:
        fn()
    except B1Error as exc:
        assert text in str(exc), exc
        s.rollback()
        return
    raise AssertionError(f"expected refusal: {text}")


def main() -> None:
    s = SessionLocal()
    try:
        n = s.scalar(select(func.count()).select_from(Item).where(Item.item_code.like("KIT%"))) + 1
        kit, a, b = _item(s, f"KIT{n:04d}", "Starter kit", 100), _item(s, f"PA{n:04d}", "Part A"), _item(s, f"PB{n:04d}", "Part B")
        docs.create_document(s, DR(obj="20", doc_date=DAY, card_code="V10000", lines=[DL(item_code=a, quantity=D(30), price=D(100)),
                                                                                     DL(item_code=b, quantity=D(40), price=D(20))]))
        production.save_bom(s, kit, {"qauntity": 1, "lines": [{"code": a, "quantity": 2, "issue_mthd": "M"}, {"code": b, "quantity": 3, "issue_mthd": "B"}]})
        assert production.bom_cost(s, kit) == 260
        production.save_bom(s, a, {"qauntity": 1, "lines": [{"code": b, "quantity": 1}]})
        _refused(lambda: production.save_bom(s, b, {"qauntity": 1, "lines": [{"code": kit, "quantity": 1}]}), "component of itself", s)
        s.delete(s.get(production.BillOfMaterials, a))
        s.commit()
        wip_before = s.scalar(select(Account.curr_total).where(Account.acct_code == "118000")) or D(0)
        var_before = s.scalar(select(Account.curr_total).where(Account.acct_code == "514000")) or D(0)

        po = production.create_order(s, kit, D(10), DAY)
        assert [l.planned_qty for l in po.lines] == [20, 30] and po.status == "P"
        _refused(lambda: production.issue(s, po.doc_entry, DAY), "must be released", s)
        production.release(s, po.doc_entry)
        production.issue(s, po.doc_entry, DAY)
        assert po.issued_val == 2000 and po.lines[0].issued_qty == 20 and po.lines[1].issued_qty == 0
        production.receive(s, po.doc_entry, DAY, D(6))
        assert po.lines[1].issued_qty == 18 and po.cmplt_qty == 6 and po.rcpt_val == 6 * 260
        production.receive(s, po.doc_entry, DAY, D(4))
        assert po.issued_val == 2000 + 600 and po.rcpt_val == 2600
        print(f"1 BOM of {kit}: 2 x {a} (manual) + 3 x {b} (backflush), cost 260; cycle refused; order {po.doc_num} for 10: "
              "20 A issued (2,000), receipts 6 + 4 backflush 30 B (600), kits at 260 (2,600); WIP 0")

        production.issue(s, po.doc_entry, DAY, [{"line_num": 0, "quantity": 1}])
        production.close(s, po.doc_entry, DAY)
        assert po.status == "L" and po.var_trans
        wip = s.scalar(select(Account.curr_total).where(Account.acct_code == "118000")) - wip_before
        var = s.scalar(select(Account.curr_total).where(Account.acct_code == "514000")) - var_before
        assert wip == 0 and var == 100, (wip, var)
        for code, qty in ((kit, 10), (a, 30 - 21), (b, 40 - 30)):
            assert s.get(Item, code).on_hand == qty, (code, s.get(Item, code).on_hand)
        kit_val = s.get(Item, kit).stock_value
        assert kit_val == 2600
        po2 = production.create_order(s, kit, D(1), DAY, release=True)
        production.cancel(s, po2.doc_entry)
        _refused(lambda: production.cancel(s, po.doc_entry), "closed", s)
        assert s.scalar(select(func.sum(Account.curr_total)).where(Account.postable == "Y")) == 0
        lines = s.scalars(select(JournalLine).where(JournalLine.trans_id == po.var_trans)).all()
        assert {l.account for l in lines} == {"118000", "514000"}
        print("2 Extra issue of 1 A (100) closed to production variance 514000; WIP of the order nets to 0; stock kit 10 (2,600), "
              f"A {30 - 21}, B 10; an order without postings cancels, a closed one does not; trial balance 0")
        print("\nOK - bills of materials and production orders post like B1.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
