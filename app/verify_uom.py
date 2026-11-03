"""End-to-end check for units of measure on documents (NumInBuy / NumInSale -> NumPerMsr).

Paper in sheets (inventory unit), bought in reams of 500, sold in packs of 100: a purchase order of
2 reams puts 1,000 sheets on order; the goods receipt adds 1,000 sheets (cost per sheet, last
purchase price per sheet); a sales order of 3 packs commits 300 sheets; the delivery issues 300
sheets at the average cost; default prices are the price list price per sheet x units; a return
brings 100 sheets back; canceling restores stock; OINM, item and warehouse quantities agree.

Run after app.seed (rerunnable: a fresh item each run):  python -m app.verify_uom
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.documents import WarehouseJournal
from app.models.inventory import Item, ItemWarehouse
from app.services import documents as docs
from app.services import masterdata
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 11, 3)


def _item(s) -> Item:
    n = s.scalar(select(func.count()).select_from(Item).where(Item.item_code.like("U9%"))) + 1
    code = f"U9{n:04d}"
    masterdata.create_item(s, masterdata.ItemRequest(
        item_code=code, item_name="A4 paper sheet", itms_grp_cod=101, invntry_uom="Sheet", buy_unit_msr="Ream", num_in_buy=D(500),
        sal_unit_msr="Pack", num_in_sale=D(100), chapter_id="48025690", vat_gourp_sa="OCS12", vat_group_pu="ICS12", dflt_wh="01",
        prices={1: D("0.80"), 3: D("0.45")}))
    return s.get(Item, code)


def _consistent(s, it: Item) -> None:
    s.refresh(it)
    oinm = s.scalar(select(func.coalesce(func.sum(WarehouseJournal.in_qty - WarehouseJournal.out_qty), 0)).where(WarehouseJournal.item_code == it.item_code))
    whs = s.scalar(select(func.coalesce(func.sum(ItemWarehouse.on_hand), 0)).where(ItemWarehouse.item_code == it.item_code))
    assert it.on_hand == oinm == whs, (it.on_hand, oinm, whs)


def main() -> None:
    s = SessionLocal()
    try:
        it = _item(s)
        po = docs.create_document(s, DR(obj="22", doc_date=DAY, card_code="V10000", lines=[DL(item_code=it.item_code, quantity=D(2))]))
        l = po.lines[0]
        s.refresh(it)
        assert l.unit_msr == "Ream" and l.num_per_msr == 500 and l.price_bef_di == D("225") and it.on_order == 1000
        print(f"1 Purchase order {po.doc_num}: 2 Ream x 225 (0.45 per sheet x 500); 1,000 sheets on order")

        grpo = docs.create_document(s, DR(obj="20", doc_date=DAY, card_code="V10000", lines=[DL(base_type="22", base_entry=po.doc_entry, base_line=0, quantity=D(2))]))
        s.refresh(it)
        assert grpo.lines[0].num_per_msr == 500 and it.on_hand == 1000 and it.on_order == 0 and it.avg_price == D("0.45")
        assert it.last_pur_prc == D("0.45") and grpo.lines[0].stock_price == D("0.45")
        _consistent(s, it)
        print(f"2 Goods receipt {grpo.doc_num}: +1,000 sheets at 0.45, nothing on order, last purchase price 0.45 per sheet")

        so = docs.create_document(s, DR(obj="17", doc_date=DAY, card_code="C10000", lines=[DL(item_code=it.item_code, quantity=D(3))]))
        s.refresh(it)
        sl = so.lines[0]
        assert sl.unit_msr == "Pack" and sl.num_per_msr == 100 and sl.price_bef_di == 80 and it.is_commited == 300
        dn = docs.create_document(s, DR(obj="15", doc_date=DAY, card_code="C10000", lines=[DL(base_type="17", base_entry=so.doc_entry, base_line=0, quantity=D(3))]))
        s.refresh(it)
        dl = dn.lines[0]
        assert it.on_hand == 700 and it.is_commited == 0 and dl.stock_price == D("0.45") and dl.grss_profit == 240 - 135
        _consistent(s, it)
        print(f"3 Sales order {so.doc_num}: 3 Pack x 80 (0.80 x 100), 300 sheets committed; delivery {dn.doc_num} issues 300 sheets, "
              "cost 135, gross profit 105")

        ret = docs.create_document(s, DR(obj="16", doc_date=DAY, card_code="C10000", lines=[DL(base_type="15", base_entry=dn.doc_entry, base_line=0, quantity=D(1))]))
        s.refresh(it)
        assert it.on_hand == 800
        docs.cancel_document(s, "16", ret.doc_entry, DAY)
        s.refresh(it)
        assert it.on_hand == 700
        inv = docs.create_document(s, DR(obj="18", doc_date=DAY, card_code="V10000", lines=[DL(item_code=it.item_code, quantity=D(1), price=D(250))]))
        s.refresh(it)
        assert it.on_hand == 1200 and it.last_pur_prc == D("0.5") and inv.lines[0].stock_price == D("0.5")
        _consistent(s, it)
        print(f"4 Return of 1 Pack: +100 sheets, canceled again; A/P invoice of 1 Ream at 250: +500 sheets at 0.50")
        print("\nOK - document quantities are converted to inventory units like B1.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
