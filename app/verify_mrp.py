"""End-to-end check for MRP.

Kit = 2 x part A + 3 x part B; a sales order of 10 kits due in 20 days; A has 5 in stock, a preferred
vendor and 7 days lead time; B has no stock, a minimum order quantity of 50 and no preferred vendor.
MRP recommends producing 10 kits, buying 15 A (ordered 7 days before it is needed) and 50 B; the
recommendations become a production order and purchase orders (B from the chosen default vendor);
a second run recommends nothing more for these items.

Run after app.seed (rerunnable: fresh items each run):  python -m app.verify_mrp
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.inventory import Item
from app.services import documents as docs
from app.services import masterdata, mrp, production
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
TODAY = date(2027, 10, 1)


def _item(s, code: str, name: str, **kw) -> str:
    masterdata.create_item(s, masterdata.ItemRequest(item_code=code, item_name=name, itms_grp_cod=101, invntry_uom="Each", dflt_wh="01",
                                                     prices={1: D(500), 3: D(10)}, **kw))
    return code


def main() -> None:
    s = SessionLocal()
    try:
        n = s.scalar(select(func.count()).select_from(Item).where(Item.item_code.like("MK%"))) + 1
        kit = _item(s, f"MK{n:04d}", "MRP kit")
        a = _item(s, f"MA{n:04d}", "MRP part A", card_code="V10000", lead_time=7)
        b = _item(s, f"MB{n:04d}", "MRP part B", min_ordr_qty=D(50))
        production.save_bom(s, kit, {"qauntity": 1, "lines": [{"code": a, "quantity": 2}, {"code": b, "quantity": 3}]})
        docs.create_document(s, DR(obj="20", doc_date=TODAY, card_code="V10000", lines=[DL(item_code=a, quantity=D(5), price=D(100))]))
        need = TODAY + timedelta(days=20)
        docs.create_document(s, DR(obj="17", doc_date=TODAY, card_code="C10000", lines=[DL(item_code=kit, quantity=D(10), price=D(1000), ship_date=need)]))
        r = mrp.run(s, TODAY + timedelta(days=60), TODAY)
        mine = {x["item_code"]: x for x in r["recommendations"] if x["item_code"] in (kit, a, b)}
        assert mine[kit]["type"] == "production" and mine[kit]["quantity"] == 10 and mine[kit]["due_date"] == need
        assert mine[a]["type"] == "purchase" and mine[a]["quantity"] == 15 and mine[a]["card_code"] == "V10000"
        assert mine[a]["order_date"] == need - timedelta(days=7)
        assert mine[b]["quantity"] == 50 and mine[b]["card_code"] is None
        print(f"1 MRP: produce 10 {kit} by {need}; buy 15 {a} from V10000 (order {mine[a]['order_date']}, 7 days lead time); buy 50 {b} "
              "(30 needed, minimum order 50)")

        made = mrp.create_documents(s, [mine[kit], mine[a], mine[b]], TODAY, default_vendor="V20000")
        assert len(made["production_orders"]) == 1 and len(made["purchase_orders"]) == 2
        s.expire_all()
        assert s.get(Item, a).on_order == 15 and s.get(Item, b).on_order == 50
        again = [x for x in mrp.run(s, TODAY + timedelta(days=60), TODAY)["recommendations"] if x["item_code"] in (kit, a, b)]
        assert not again, again
        print(f"2 Created production order {made['production_orders'][0]} and purchase orders {made['purchase_orders']} "
              f"({b} from the default vendor V20000); a second run recommends nothing for these items")
        print("\nOK - MRP plans production and purchasing through the bills of materials.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
