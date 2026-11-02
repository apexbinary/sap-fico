"""End-to-end check for marketing and inventory documents.

Purchase chain (PO -> GRPO -> A/P invoice with price difference), sales chain
(quotation -> order -> delivery -> A/R invoice -> credit memo), returns, goods
receipt / issue / transfer, cancellation; invariants: inventory account = sum of
item stock values, OITW = OITM quantities, OINM quantities = stock, trial balance.

Run after app.seed (rerunnable, uses a new item each run):  python -m app.verify_documents
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.finance import Account
from app.models.inventory import Item, ItemWarehouse
from app.models.documents import WarehouseJournal
from app.models.partners import BusinessPartner
from app.services import documents as docs
from app.services import masterdata, reports
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as L
from app.services.documents import DocumentRequest as R

D = Decimal
DAY = date(2026, 5, 4)


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def _copy(doc, qty=None, **kw) -> list[L]:
    return [L(base_type=doc.obj_type, base_entry=doc.doc_entry, base_line=l.line_num,
              quantity=qty if qty is not None else l.open_qty, **kw) for l in doc.lines if l.open_qty > 0]


def main() -> None:
    s = SessionLocal()
    try:
        n = (s.scalar(select(func.count()).select_from(Item)) or 0) + 1
        code = f"VDOC{n:04d}"
        masterdata.create_item(s, masterdata.ItemRequest(item_code=code, item_name="Verify printer", itms_grp_cod=100,
                                                         vat_gourp_sa="O1", vat_group_pu="I1", dflt_wh="01",
                                                         prices={1: D("400"), 3: D("250")}))
        item = lambda: s.get(Item, code)  # noqa: E731
        inv_acct = lambda: s.get(Account, "115000").curr_total  # noqa: E731
        grni = lambda: s.get(Account, "212000").curr_total  # noqa: E731
        vendor, customer = s.get(BusinessPartner, "V10000"), s.get(BusinessPartner, "C10000")
        inv0, grni0, vbal0, cbal0 = inv_acct(), grni(), vendor.balance, customer.balance
        dnotes0 = customer.dnotes_bal

        # 1) purchasing: PO 10 -> GRPO 10 @ 250 -> A/P invoice @ 260 (difference revalues the stock)
        po = docs.create_document(s, R(obj="22", doc_date=DAY, card_code="V10000", lines=[L(item_code=code, quantity=D(10))]))
        assert item().on_order == 10 and po.lines[0].price == D("250"), "PO price from the vendor's price list"
        grpo = docs.create_document(s, R(obj="20", doc_date=DAY, card_code="V10000", lines=_copy(po)))
        assert po.doc_status == "C" and item().on_order == 0 and item().on_hand == 10
        assert inv_acct() == inv0 + 2500 and grni() == grni0 - 2500
        ap = docs.create_document(s, R(obj="18", doc_date=DAY, card_code="V10000", lines=_copy(grpo, price=D("260"))))
        print(f"1 PO {po.doc_num} -> GRPO {grpo.doc_num} -> A/P invoice {ap.doc_num} total {ap.doc_total}; "
              f"item cost {item().avg_price}")
        assert ap.doc_total == D("3094.00") and grni() == grni0 and item().avg_price == D("260")
        assert vendor.balance == vbal0 - D("3094") and grpo.doc_status == "C"

        # 2) a GRPO without a base: moving average (10 x 260 + 5 x 280) / 15
        docs.create_document(s, R(obj="20", doc_date=DAY, card_code="V10000", lines=[L(item_code=code, quantity=D(5), price=D(280))]))
        print(f"2 GRPO 5 @ 280: on hand {item().on_hand.normalize()}, item cost {item().avg_price}, value {item().stock_value}")
        assert item().stock_value == D("4000") and item().avg_price == D("266.666667")

        # 3) sales: quotation -> order 4 (commits) -> delivery 3 -> invoice (3 from delivery + 1 from order)
        qt = docs.create_document(s, R(obj="23", doc_date=DAY, card_code="C10000", lines=[L(item_code=code, quantity=D(4))]))
        so = docs.create_document(s, R(obj="17", doc_date=DAY, card_code="C10000", lines=_copy(qt)))
        assert qt.doc_status == "C" and item().is_commited == 4 and so.lines[0].price == D("400")
        dn = docs.create_document(s, R(obj="15", doc_date=DAY, card_code="C10000", lines=_copy(so, qty=D(3))))
        assert item().is_commited == 1 and so.lines[0].open_qty == 1 and item().on_hand == 12
        assert dn.lines[0].stock_price == D("266.666667") and customer.dnotes_bal == dnotes0 + D("1428.00")
        inv = docs.create_document(s, R(obj="13", doc_date=DAY, card_code="C10000", lines=_copy(dn) + _copy(so)))
        print(f"3 Quotation {qt.doc_num} -> order {so.doc_num} -> delivery {dn.doc_num} -> A/R invoice {inv.doc_num} "
              f"total {inv.doc_total}; on hand {item().on_hand.normalize()}, committed {item().is_commited.normalize()}")
        assert inv.doc_total == D("1904.00") and so.doc_status == "C" and dn.doc_status == "C"
        assert item().on_hand == 11 and item().is_commited == 0 and customer.dnotes_bal == dnotes0
        assert customer.balance == cbal0 + D("1904")

        # 4) credit memo from the invoice (1 unit): stock back at invoice cost, invoice reconciled
        cm = docs.create_document(s, R(obj="14", doc_date=DAY, card_code="C10000", lines=_copy(inv, qty=D(1))[:1]))
        print(f"4 Credit memo {cm.doc_num} {cm.doc_total}: invoice paid to date {inv.paid_to_date}, BP balance {customer.balance}")
        assert cm.doc_total == D("476.00") and inv.paid_to_date == D("476.00") and item().on_hand == 12
        assert customer.balance == cbal0 + D("1428")
        _rejects(lambda: docs.cancel_document(s, "13", inv.doc_entry), "invoice has a credit memo")

        # 5) delivery 2 -> return 1 at the delivery cost
        dn2 = docs.create_document(s, R(obj="15", doc_date=DAY, card_code="C10000", lines=[L(item_code=code, quantity=D(2))]))
        rt = docs.create_document(s, R(obj="16", doc_date=DAY, card_code="C10000", lines=_copy(dn2, qty=D(1))))
        assert rt.lines[0].stock_price == dn2.lines[0].stock_price and dn2.lines[0].open_qty == 1
        print(f"5 Delivery {dn2.doc_num} (2) -> return {rt.doc_num} (1): on hand {item().on_hand.normalize()}")

        # 6) goods return of 2 to the vendor, A/P credit memo from it
        grpo3 = docs.create_document(s, R(obj="20", doc_date=DAY, card_code="V10000", lines=[L(item_code=code, quantity=D(2), price=D(270))]))
        gr = docs.create_document(s, R(obj="21", doc_date=DAY, card_code="V10000", lines=_copy(grpo3)))
        apc = docs.create_document(s, R(obj="19", doc_date=DAY, card_code="V10000", lines=_copy(gr)))
        print(f"6 GRPO {grpo3.doc_num} -> goods return {gr.doc_num} -> A/P credit memo {apc.doc_num} {apc.doc_total}")
        assert apc.doc_total == D("642.60") and gr.doc_status == "C"

        # 7) inventory documents: goods receipt, goods issue, transfer 01 -> 02
        before = item().on_hand
        docs.create_document(s, R(obj="59", doc_date=DAY, lines=[L(item_code=code, quantity=D(3), price=D(300))]))
        docs.create_document(s, R(obj="60", doc_date=DAY, lines=[L(item_code=code, quantity=D(2))]))
        tr = docs.create_document(s, R(obj="67", doc_date=DAY, from_whs="01", to_whs="02", lines=[L(item_code=code, quantity=D(4))]))
        w1, w2 = s.get(ItemWarehouse, (code, "01")), s.get(ItemWarehouse, (code, "02"))
        print(f"7 Goods receipt 3, goods issue 2, transfer {tr.doc_num} of 4: warehouse 01 {w1.on_hand.normalize()}, "
              f"02 {w2.on_hand.normalize()}")
        assert item().on_hand == before + 1 and w2.on_hand == 4 and tr.trans_id is None

        # 8) cancellation of a standalone invoice: stock back, journal entry reversed, BP balance restored
        bal = customer.balance
        stock = item().on_hand
        inv2 = docs.create_document(s, R(obj="13", doc_date=DAY, card_code="C10000", lines=[L(item_code=code, quantity=D(1), whs_code="02")]))
        docs.cancel_document(s, "13", inv2.doc_entry)
        print(f"8 A/R invoice {inv2.doc_num} canceled: BP balance {customer.balance}, on hand {item().on_hand.normalize()}")
        assert customer.balance == bal and item().on_hand == stock and inv2.canceled == "Y"

        # 9) rules
        _rejects(lambda: docs.create_document(s, R(obj="15", doc_date=DAY, card_code="C10000", lines=[L(item_code=code, quantity=D(999))])), "not enough stock")
        so2 = docs.create_document(s, R(obj="17", doc_date=DAY, card_code="C10000", lines=[L(item_code=code, quantity=D(2))]))
        _rejects(lambda: docs.create_document(s, R(obj="15", doc_date=DAY, card_code="C10000", lines=_copy(so2, qty=D(3)))), "more than open")
        _rejects(lambda: docs.create_document(s, R(obj="13", doc_date=DAY, card_code="V10000", lines=[L(item_code=code)])), "vendor on a sales document")
        _rejects(lambda: docs.create_document(s, R(obj="16", doc_date=DAY, card_code="C10000", lines=_copy(so2))), "return copied from an order")
        docs.close_document(s, "17", so2.doc_entry)
        assert item().is_commited == 0 and so2.doc_status == "C"

        # 10) service document: A/R invoice on a G/L account
        sv = docs.create_document(s, R(obj="13", doc_date=DAY, card_code="C20000", doc_type="S", lines=[
            L(dscription="Consulting", acct_code="412000", price=D(1000), vat_group="O1")]))
        assert sv.doc_total == D("1190.00")

        # invariants
        s.flush()
        values = s.scalar(select(func.sum(Item.stock_value))) or 0
        qty_ok = all(i.on_hand == (s.scalar(select(func.sum(ItemWarehouse.on_hand)).where(ItemWarehouse.item_code == i.item_code)) or 0)
                     for i in s.scalars(select(Item).where(Item.invnt_item == "Y")))
        moved = s.scalar(select(func.sum(WarehouseJournal.in_qty) - func.sum(WarehouseJournal.out_qty)).where(WarehouseJournal.item_code == code))
        tb = reports.trial_balance(s, date(2026, 1, 1), date(2026, 12, 31))
        print(f"Inventory account {inv_acct()} = item values {values}; OINM net quantity {moved.normalize()} = on hand "
              f"{item().on_hand.normalize()}; trial balance {'balanced' if tb['balanced'] else 'NOT balanced'}")
        assert inv_acct() == values and qty_ok and moved == item().on_hand and tb["balanced"]
        print("\nOK - document chains, stock, moving average cost and automatic journal entries are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
