"""End-to-end check for down payments (A/R ODPI 203, A/P ODPO 204).

A down payment request is not posted; an incoming payment pays it (the amount stays on account,
the request's PaidToDate rises); the final invoice draws it: its partner line is reconciled with
the payment's amount on account, PaidToDate of the invoice rises, the request is closed when
fully drawn; the payment can no longer be canceled; canceling the invoice releases the down
payment. Errors: overpaying, drawing more than paid, another partner's request, an FC invoice.
A/P: partial draws on two invoices. Partner balances equal their open items; trial balance 0.

Run after app.seed (rerunnable):  python -m app.verify_downpayments
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.banking import PAYMENT_CLASSES
from app.models.finance import Account, JournalLine
from app.models.partners import BusinessPartner
from app.services import banking
from app.services import documents as docs
from app.services.admin import B1Error
from app.services.banking import DownPaymentPay as DPP
from app.services.banking import PaymentRequest as PR
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR
from app.services.documents import DownPaymentDraw as DPD

D = Decimal
DAY = date(2027, 10, 11)


def _refused(fn, text: str) -> None:
    try:
        fn()
    except B1Error as exc:
        assert text in str(exc), exc
        return
    raise AssertionError(f"expected refusal: {text}")


def _open_items(s, code: str) -> D:
    return s.scalar(select(func.coalesce(func.sum(JournalLine.bal_due_deb - JournalLine.bal_due_cred), 0)).where(
        JournalLine.short_name == code, JournalLine.account != JournalLine.short_name))


def _balanced(s, *codes: str) -> None:
    for c in codes:
        bp = s.get(BusinessPartner, c)
        s.refresh(bp)
        assert bp.balance == _open_items(s, c), (c, bp.balance, _open_items(s, c))
    assert s.scalar(select(func.sum(Account.curr_total)).where(Account.postable == "Y")) == 0


def main() -> None:
    s = SessionLocal()
    try:
        dp = docs.create_document(s, DR(obj="203", doc_date=DAY, card_code="C10000", disc_prcnt=D(0), comments="Advance for order",
                                        lines=[DL(item_code="S00001", quantity=D(1), price=D(10000))]))
        assert dp.doc_total == 11800 and dp.trans_id is None and dp.doc_status == "O"
        bal0 = s.get(BusinessPartner, "C10000").balance
        _refused(lambda: banking.create_payment(s, PR(obj="24", doc_date=DAY, card_code="C10000", trsfr_acct="112000", trsfr_sum=D(20000),
                                                      down_payments=[DPP(dp.doc_entry, D(12000))])), "between 0 and the unpaid")
        pay = banking.create_payment(s, PR(obj="24", doc_date=DAY, card_code="C10000", trsfr_acct="112000", trsfr_sum=D(11800),
                                           down_payments=[DPP(dp.doc_entry, D(11800))]))
        s.refresh(dp)
        assert pay.open_bal == 11800 and dp.paid_to_date == 11800 and s.get(BusinessPartner, "C10000").balance == bal0 - 11800
        _balanced(s, "C10000")
        print(f"1 Down payment request {dp.doc_num} 11,800 (not posted); incoming payment {pay.doc_num} pays it: 11,800 on account")

        inv = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", disc_prcnt=D(0),
                                         lines=[DL(item_code="S00001", quantity=D(3), price=D(10000))], down_payments=[DPD(dp.doc_entry)]))
        s.refresh(dp)
        s.refresh(pay)
        assert inv.doc_total == 35400 and inv.dpm_amnt == 11800 and inv.paid_to_date == 11800 and inv.doc_status == "O"
        assert pay.open_bal == 0 and dp.dpm_appl == 11800 and dp.doc_status == "C"
        assert s.get(BusinessPartner, "C10000").balance == bal0 + 35400 - 11800
        _balanced(s, "C10000")
        _refused(lambda: banking.cancel_payment(s, "24", pay.doc_entry, DAY), "was used")
        print(f"2 Invoice {inv.doc_num} 35,400 draws it: paid 11,800, due 23,600; payment on account used up, request closed; "
              "the payment cannot be canceled")

        docs.cancel_document(s, "13", inv.doc_entry, DAY)
        s.refresh(dp)
        s.refresh(pay)
        assert pay.open_bal == 11800 and dp.dpm_appl == 0 and dp.doc_status == "O"
        _balanced(s, "C10000")
        again = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", disc_prcnt=D(0),
                                           lines=[DL(item_code="S00001", quantity=D(1), price=D(5000))], down_payments=[DPD(dp.doc_entry, D(5900))]))
        assert again.paid_to_date == 5900 and again.doc_status == "C"
        _refused(lambda: docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", lines=[DL(item_code="S00001", quantity=D(1), price=D(1000))],
                                                    down_payments=[DPD(dp.doc_entry, D(9000))])), "paid and not yet drawn")
        _refused(lambda: docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C20000", lines=[DL(item_code="S00001", quantity=D(1), price=D(1000))],
                                                    down_payments=[DPD(dp.doc_entry)])), "is not a down payment of C20000")
        _refused(lambda: docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", doc_cur="USD",
                                                    lines=[DL(item_code="S00001", quantity=D(1), price=D(100))], down_payments=[DPD(dp.doc_entry)])),
                 "local currency")
        _refused(lambda: docs.cancel_document(s, "203", dp.doc_entry, DAY), "drawn on an invoice")  # partly drawn (5,900 by the invoice above)
        _balanced(s, "C10000")
        print(f"3 Canceling the invoice releases the down payment; invoice {again.doc_num} draws 5,900 of it (closed, fully paid); "
              "drawing more than is left, another customer, an FC invoice and canceling a paid request are refused")

        # A/P: one down payment drawn partly on two invoices
        vdp = docs.create_document(s, DR(obj="204", doc_date=DAY, card_code="V20000", disc_prcnt=D(0),
                                         lines=[DL(item_code="C00001", quantity=D(1), price=D(5000))]))
        vpay = banking.create_payment(s, PR(obj="46", doc_date=DAY, doc_type="S", card_code="V20000", trsfr_acct="112000", trsfr_sum=D(5900),
                                            down_payments=[DPP(vdp.doc_entry, D(5900))]))
        a1 = docs.create_document(s, DR(obj="18", doc_date=DAY, card_code="V20000", disc_prcnt=D(0),
                                        lines=[DL(item_code="C00001", quantity=D(2), price=D(5000))], down_payments=[DPD(vdp.doc_entry, D(3000))]))
        a2 = docs.create_document(s, DR(obj="18", doc_date=DAY, card_code="V20000", disc_prcnt=D(0),
                                        lines=[DL(item_code="C00001", quantity=D(1), price=D(5000))], down_payments=[DPD(vdp.doc_entry)]))
        s.refresh(vdp)
        s.refresh(vpay)
        assert a1.paid_to_date == 3000 and a2.paid_to_date == 2900 and vdp.dpm_appl == 5900 and vdp.doc_status == "C" and vpay.open_bal == 0
        _balanced(s, "V20000", "C10000")
        print(f"4 A/P down payment {vdp.doc_num} 5,900 paid by outgoing payment {vpay.doc_num}; drawn 3,000 on invoice {a1.doc_num} "
              f"and the rest 2,900 on invoice {a2.doc_num}")

        unpaid = docs.create_document(s, DR(obj="204", doc_date=DAY, card_code="V20000", lines=[DL(item_code="C00001", quantity=D(1), price=D(100))]))
        p2 = banking.create_payment(s, PR(obj="46", doc_date=DAY, doc_type="S", card_code="V20000", trsfr_acct="112000", trsfr_sum=D(118),
                                          down_payments=[DPP(unpaid.doc_entry, D(118))]))
        banking.cancel_payment(s, "46", p2.doc_entry, DAY)
        s.refresh(unpaid)
        assert unpaid.paid_to_date == 0
        docs.cancel_document(s, "204", unpaid.doc_entry, DAY)
        cnt = s.scalar(select(func.count()).select_from(PAYMENT_CLASSES["24"][2]).where(PAYMENT_CLASSES["24"][2].inv_type == "203"))
        _balanced(s, "V20000")
        print(f"5 Canceling the payment of an undrawn request resets it; the unpaid request is canceled; {cnt} RCT2 down payment rows")
        print("\nOK - down payments are paid, drawn and released like B1; balances equal open items.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
