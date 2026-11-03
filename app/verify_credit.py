"""End-to-end check for the credit limit / commitment limit check of customers.

Credit limit 1,00,000, commitment limit 50,000. Warn mode: an order that raises the exposure
above the limit is refused with a warning and nothing is posted, and is added when confirmed;
a delivery copied from the order adds no exposure and passes; block mode refuses new value even
when confirmed; the commitment limit stops an invoice that raises the balance above it; no
check lets everything pass; documents of other types are not checked. Settings are restored.

Run after app.seed (rerunnable: a fresh customer each run):  python -m app.verify_credit
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.documents import DOCUMENT_CLASSES
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import credit
from app.services import documents as docs
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 8, 2)


def _customer(s) -> str:
    n = s.scalar(select(func.count()).select_from(BusinessPartner).where(BusinessPartner.card_code.like("C8%"))) + 1
    code = f"C8{n:04d}"
    s.add(BusinessPartner(card_code=code, card_name="Credit Test Retail", card_type="C", group_code=100, currency="##",
                          deb_pay_acct="114000", group_num=1, list_num=1, vat_group="OCS18", country="IN", balance=D(0),
                          dnotes_bal=D(0), orders_bal=D(0), frozen_for="N", bill_to_def="Main", ship_to_def="Main",
                          credit_line=D(100000), debt_line=D(50000)))
    s.flush()
    for kind in ("B", "S"):
        s.add(PartnerAddress(card_code=code, adres_type=kind, address="Main", street="9 Brigade Road", city="Bengaluru",
                             zip_code="560025", state="KA", country="IN", gst_type="U"))
    s.commit()
    return code


def _expect(fn, cls, text: str):
    try:
        fn()
    except cls as exc:
        assert text in str(exc), exc
        return exc
    raise AssertionError(f"expected {cls.__name__}: {text}")


def main() -> None:
    s = SessionLocal()
    before = credit.settings(s)
    try:
        code = _customer(s)
        credit.save_settings(s, {"credit_check": "W", "commitment_check": "N", "documents": ["17", "15", "13"]})
        order = lambda price, confirm=False: docs.create_document(s, DR(  # noqa: E731
            obj="17", doc_date=DAY, card_code=code, disc_prcnt=D(0), confirm_credit=confirm,
            lines=[DL(item_code="A00001", quantity=D(1), price=D(price))]))
        docs.create_document(s, DR(obj="20", doc_date=DAY, card_code="V10000", lines=[DL(item_code="A00001", quantity=D(5), price=D(20000))]))
        o1 = order(60000)  # 70,800 gross: within 1,00,000
        n_orders = s.scalar(select(func.count()).select_from(DOCUMENT_CLASSES["17"][0]))
        exc = _expect(lambda: order(30000), credit.CreditLimitWarning, "Credit limit of")
        assert credit.CONFIRM in str(exc) and "1,06,200.00" in str(exc) and "1,00,000.00" in str(exc)
        assert credit.amount_text(D("12345678.5"), True) == "1,23,45,678.50" and credit.amount_text(D("999"), True) == "999.00"
        assert s.scalar(select(func.count()).select_from(DOCUMENT_CLASSES["17"][0])) == n_orders, "nothing posted"
        bp = s.get(BusinessPartner, code)
        assert bp.orders_bal == D("70800"), bp.orders_bal
        o2 = order(30000, confirm=True)
        bp = s.get(BusinessPartner, code)
        assert bp.orders_bal == D("106200")
        print(f"1 Warn: order 70,800 passes; order of 35,400 (exposure 1,06,200 > 1,00,000) refused with a warning, nothing "
              f"posted; confirmed: order {o2.doc_num} added")

        dn = docs.create_document(s, DR(obj="15", doc_date=DAY, card_code=code, lines=[DL(base_type="17", base_entry=o1.doc_entry, base_line=0)]))
        bp = s.get(BusinessPartner, code)
        assert bp.dnotes_bal == D("70800") and credit.exposure(bp) == D("106200")
        print(f"2 Delivery {dn.doc_num} copied from the order adds no exposure (1,06,200 stays) and passes")

        credit.save_settings(s, {"credit_check": "B"})
        _expect(lambda: order(1000, confirm=True), B1Error, "Credit limit of")
        quote = docs.create_document(s, DR(obj="23", doc_date=DAY, card_code=code, lines=[
            DL(item_code="S00001", quantity=D(1), price=D(1000))]))  # quotations are not checked
        assert quote.doc_entry
        print("3 Block: new value refused even when confirmed; quotations are not checked")

        credit.save_settings(s, {"credit_check": "N", "commitment_check": "B"})
        _expect(lambda: docs.create_document(s, DR(obj="13", doc_date=DAY, card_code=code, lines=[
            DL(base_type="15", base_entry=dn.doc_entry, base_line=0)])), B1Error, "Commitment limit of")
        credit.save_settings(s, {"commitment_check": "N"})
        inv = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code=code, lines=[DL(base_type="15", base_entry=dn.doc_entry, base_line=0)]))
        bp = s.get(BusinessPartner, code)
        assert bp.balance == D("70800") and credit.exposure(bp) == D("106200")
        print(f"4 Commitment limit 50,000 stops the invoice (balance would be 70,800); without checks invoice {inv.doc_num} passes")
        print("\nOK - credit and commitment limits are checked like B1.")
    finally:
        s.rollback()
        credit.save_settings(s, {"credit_check": before["credit_check"], "commitment_check": before["commitment_check"],
                                 "documents": before["documents"]})
        s.close()


if __name__ == "__main__":
    main()
