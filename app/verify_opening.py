"""End-to-end check for opening balances.

G/L accounts: bank 5,00,000 Dr and share capital 3,00,000 Cr post one TransType -2 entry, the difference
on the opening balance account 313000; control, title, duplicate and two-sided rows are refused.
Business partners: a customer's open invoice (Dr 50,000, due date, reference) and a vendor's (Cr 30,000)
post open items on the control accounts; the customer item is paid by an incoming payment, after which the
entry cannot be canceled; leads are refused. Items: 10 x A00001 at 20,000 enter as a goods receipt
against 313000 (stock account Dr 2,00,000). The listing shows the entries and what is left on 313000;
canceling reverses the G/L entry and cancels the goods receipt.

Run after app.seed (rerunnable):  python -m app.verify_opening
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models.finance import JournalLine
from app.models.inventory import Item
from app.models.partners import BusinessPartner
from app.services import banking, opening
from app.services.admin import B1Error
from app.services.banking import PaidItem
from app.services.banking import PaymentRequest as PR

D = Decimal
ON = "2027-01-02"


def _refused(s, fn, text: str) -> None:
    try:
        fn()
    except B1Error as exc:
        assert text in str(exc), exc
        s.rollback()
        return
    raise AssertionError(f"expected refusal: {text}")


def _lines(s, trans_id) -> dict:
    out = {}
    for l in s.scalars(select(JournalLine).where(JournalLine.trans_id == trans_id)):
        out[l.short_name] = out.get(l.short_name, D(0)) + l.debit - l.credit
    return out


def main() -> None:
    with SessionLocal() as s:
        gl = lambda rows: opening.post_accounts(s, {"ref_date": ON, "rows": rows})  # noqa: E731
        _refused(s, lambda: gl([{"account": "114000", "debit": 1}]), "control account")
        _refused(s, lambda: gl([{"account": "11", "debit": 1}]), "not a title account")
        _refused(s, lambda: gl([{"account": "112000", "debit": 1, "credit": 1}]), "either a debit or a credit")
        _refused(s, lambda: gl([{"account": "112000", "debit": 1}, {"account": "112000", "debit": 2}]), "entered twice")
        _refused(s, lambda: gl([{"account": "313000", "debit": 1}]), "opening balance account itself")
        _refused(s, lambda: gl([]), "at least one account")
        je = gl([{"account": "112000", "debit": 500000}, {"account": "311000", "credit": 300000}])
        assert je.trans_type == "-2" and _lines(s, je.trans_id) == {"112000": 500000, "311000": -300000, "313000": -200000}
        print(f"1 G/L opening balances: JE {je.number} (TransType -2) bank 5,00,000 / capital 3,00,000 / 313000 2,00,000; "
              "control, title, duplicate, two-sided and offset-account rows refused")

        cust_before = s.get(BusinessPartner, "C10000").balance
        _refused(s, lambda: opening.post_partners(s, {"ref_date": ON, "rows": [{"card_code": "NOPE", "debit": 1}]}), "choose a business partner")
        bp = opening.post_partners(s, {"ref_date": ON, "rows": [
            {"card_code": "C10000", "debit": 50000, "due_date": "2027-01-31", "ref": "OLD/1"},
            {"card_code": "V10000", "credit": 30000, "due_date": "2027-02-15", "ref": "V-OLD/7"}]})
        lines = s.scalars(select(JournalLine).where(JournalLine.trans_id == bp.trans_id)).all()
        cust = next(l for l in lines if l.short_name == "C10000")
        vend = next(l for l in lines if l.short_name == "V10000")
        assert cust.account == "114000" and cust.bal_due_deb == 50000 and cust.due_date == date(2027, 1, 31) and cust.ref1 == "OLD/1"
        assert vend.account == "211000" and vend.bal_due_cred == 30000
        assert _lines(s, bp.trans_id)["313000"] == -20000
        assert s.get(BusinessPartner, "C10000").balance - cust_before == 50000
        pay = banking.create_payment(s, PR(obj="24", doc_date=date(2027, 1, 20), card_code="C10000", trsfr_acct="112000", trsfr_sum=D(50000),
                                           items=[PaidItem(trans_id=cust.trans_id, line_id=cust.line_id, sum_applied=D(50000))]))
        s.refresh(cust)
        assert cust.bal_due_deb == 0
        _refused(s, lambda: opening.cancel(s, "partners", bp.trans_id), "paid or reconciled")
        print(f"2 BP opening balances: JE {bp.number} with open items C10000 50,000 (due 31.01.2027, OLD/1) / V10000 30,000; "
              f"incoming payment {pay.doc_num} pays the customer item; the entry is then locked")

        item = s.get(Item, "A00001")
        on_hand, value = item.on_hand, item.stock_value
        _refused(s, lambda: opening.post_stock(s, {"ref_date": ON, "rows": [{"item_code": "S00001", "quantity": 1, "price": 1}]}), "inventory item")
        _refused(s, lambda: opening.post_stock(s, {"ref_date": ON, "rows": [{"item_code": "A00001", "quantity": 0, "price": 1}]}), "positive quantity")
        gr = opening.post_stock(s, {"ref_date": ON, "rows": [{"item_code": "A00001", "whs_code": "01", "quantity": 10, "price": 20000}]})
        s.refresh(item)
        assert item.on_hand - on_hand == 10 and item.stock_value - value == 200000 and gr.ref2 == "OPENING"
        assert _lines(s, gr.trans_id) == {"115000": 200000, "313000": -200000}, _lines(s, gr.trans_id)
        print(f"3 Opening stock: goods receipt {gr.doc_num} 10 x A00001 at 20,000: stock 115000 Dr 2,00,000 / 313000; "
              "non-inventory items and zero quantities refused")

        lst = opening.listing(s)
        kinds = {(e["kind"], e["number"]) for e in lst["entries"]}
        assert ("accounts", je.number) in kinds and ("partners", bp.number) in kinds and ("items", gr.doc_num) in kinds
        bal = s.scalar(select(JournalLine.account).where(JournalLine.account == "313000").limit(1))
        assert bal == "313000" and lst["opening_account"] == "313000"
        opening.cancel(s, "accounts", je.trans_id)
        opening.cancel(s, "items", gr.doc_entry)
        s.refresh(item)
        assert item.on_hand == on_hand and item.stock_value == value
        lst2 = {(e["kind"], e["number"]): e for e in opening.listing(s)["entries"]}
        assert lst2[("accounts", je.number)]["canceled"] and lst2[("items", gr.doc_num)]["canceled"]
        print(f"4 Listing with the three entries (313000 difference {lst['difference']:,.2f}); G/L entry reversed and goods receipt canceled")
    print("\nOK - opening balances of G/L accounts, business partners and items work.")


if __name__ == "__main__":
    main()
