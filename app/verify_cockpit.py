"""End-to-end check for the cockpit: its figures move exactly with new postings; widget layout.

Taken on a fixed date: an A/R invoice raises sales (month / year), receivables and the current
aging bucket; an overdue one moves to its aging bucket and the overdue alerts; a sales order
counts in open documents and open orders; an item below its minimum stock is alerted; the
user's widget order and visibility are saved and read back.

Run after app.seed (rerunnable):  python -m app.verify_cockpit
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.inventory import Item
from app.services import cockpit, masterdata
from app.services import documents as docs
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
ON = date(2027, 11, 15)


def _invoice(s, card: str, day: date, amount: str):
    return docs.create_document(s, DR(obj="13", doc_date=day, card_code=card, doc_type="S", disc_prcnt=D(0), lines=[
        DL(dscription="Service", acct_code="412000", price=D(amount), vat_group="OCS18")]))


def main() -> None:
    s = SessionLocal()
    try:
        before = cockpit.cockpit(s, ON)

        inv = _invoice(s, "C10000", ON, "10000")                         # current
        old = _invoice(s, "C10000", ON - timedelta(days=75), "5000")     # net 30: due ON - 45, 31-60 days overdue
        so = docs.create_document(s, DR(obj="17", doc_date=ON, card_code="C30000", doc_type="S", disc_prcnt=D(0), lines=[
            DL(dscription="Project", acct_code="412000", price=D(2000), vat_group="OCS18")]))
        n = (s.scalar(select(func.count()).select_from(Item).where(Item.item_code.like("VCKP%"))) or 0) + 1
        masterdata.create_item(s, masterdata.ItemRequest(item_code=f"VCKP{n:03d}", item_name="Low stock item", itms_grp_cod=101,
                                                         vat_gourp_sa="OCS18", vat_group_pu="ICS18", dflt_wh="01", min_level=D(5)))
        after = cockpit.cockpit(s, ON)
        k0, k1 = before["kpis"], after["kpis"]
        print(f"1 Sales MTD {k0['sales_mtd']} -> {k1['sales_mtd']}, YTD +{k1['sales_ytd'] - k0['sales_ytd']}; receivables "
              f"+{k1['receivable'] - k0['receivable']}; overdue +{k1['overdue'] - k0['overdue']}")
        assert k1["sales_mtd"] - k0["sales_mtd"] == D(10000)               # the old invoice belongs to an earlier month
        assert k1["sales_ytd"] - k0["sales_ytd"] == D(15000)
        assert k1["receivable"] - k0["receivable"] == inv.doc_total + old.doc_total
        assert k1["overdue"] - k0["overdue"] == old.doc_total
        a0, a1 = before["aging_ar"], after["aging_ar"]
        print(f"2 Aging: current +{a1['current'] - a0['current']}, 31-60 +{a1['31-60'] - a0['31-60']}")
        assert a1["current"] - a0["current"] == inv.doc_total and a1["31-60"] - a0["31-60"] == old.doc_total
        o0, o1 = before["open_docs"]["sales_orders"], after["open_docs"]["sales_orders"]
        assert o1["count"] - o0["count"] == 1 and o1["value"] - o0["value"] == so.doc_total
        assert k1["open_orders"] - k0["open_orders"] == so.doc_total
        assert after["alerts"]["low_stock_count"] - before["alerts"]["low_stock_count"] == 1
        assert after["alerts"]["overdue_count"] - before["alerts"]["overdue_count"] == 1
        assert len(after["sales_chart"]) == 12 and after["sales_chart"][-1]["month"] == "2027-11"
        print(f"3 Open sales orders {o0['count']} -> {o1['count']}; low-stock alerts {after['alerts']['low_stock_count']}; "
              f"top customer {after['top_customers'][0]['card_code'] if after['top_customers'] else '-'}")

        # 4) widget layout per user
        from app.api_cockpit import WidgetIn, _layout, save_layout

        order = [w["id"] for w in _layout(s)][::-1]
        save_layout([WidgetIn(id=w, visible=w != "links") for w in order], s)
        lay = _layout(s)
        assert [w["id"] for w in lay] == order and next(w for w in lay if w["id"] == "links")["visible"] is False
        save_layout([WidgetIn(id=w, visible=True) for w, _ in cockpit.WIDGETS], s)  # back to the default
        print("4 Widget order and visibility saved and restored")
        print("\nOK - cockpit figures follow the postings; the layout is kept per user.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
