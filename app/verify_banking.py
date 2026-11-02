"""End-to-end check for banking: payments, partial payments, payments on account, checks, deposits.

Partial / full incoming payments (transfer, cash, checks), credit memo offset in a payment,
payment on account and its later reconciliation, outgoing payment with bank charges,
account payment, foreign-currency payment with exchange difference, check deposit, cash
deposit, cancellations; invariants: every BP balance = sum of its open items, trial
balance balanced.

Run after app.seed (rerunnable):  python -m app.verify_banking
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.finance import Account, JournalLine
from app.models.partners import BusinessPartner
from app.services import banking, reports
from app.services import documents as docs
from app.services.admin import B1Error, exchange_rate
from app.services.banking import CheckRequest, PaidItem, PaymentRequest
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2026, 7, 6)


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def _service_doc(s, obj: str, card: str, amount: str, base=None):
    lines = [DL(base_type=base.obj_type, base_entry=base.doc_entry, base_line=0)] if base else [
        DL(dscription="Services", acct_code="412000" if obj in ("13", "14") else "611000", price=D(amount),
           vat_group="OCS18" if obj in ("13", "14") else "ICS18")]
    return docs.create_document(s, DR(obj=obj, doc_date=DAY, card_code=card, doc_type="S", disc_prcnt=D(0), lines=lines))


def _item(s, doc) -> PaidItem:
    line = s.scalars(select(JournalLine).where(JournalLine.trans_id == doc.trans_id,
                                               JournalLine.short_name == doc.card_code)).one()
    return PaidItem(trans_id=line.trans_id, line_id=line.line_id, sum_applied=line.bal_due_deb or line.bal_due_cred)


def _pay_item(s, pay) -> PaidItem:
    line = s.scalars(select(JournalLine).where(JournalLine.trans_id == pay.trans_id,
                                               JournalLine.short_name == pay.card_code)).one()
    return PaidItem(trans_id=line.trans_id, line_id=line.line_id, sum_applied=line.bal_due_deb or line.bal_due_cred)


def main() -> None:
    s = SessionLocal()
    try:
        bal = lambda code: s.get(Account, code).curr_total  # noqa: E731
        cust = s.get(BusinessPartner, "C30000")
        bank0, chk0, cash0, cbal0 = bal("112000"), bal("117000"), bal("111000"), cust.balance

        # 1) invoice 1,180 paid partly by transfer (500), then cash 280 + check 400
        inv = _service_doc(s, "13", "C30000", "1000")
        it = _item(s, inv)
        p1 = banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000", trsfr_acct="112000",
                                                      trsfr_sum=D(500), trsfr_ref="TRX-1",
                                                      items=[PaidItem(it.trans_id, it.line_id, D(500))]))
        assert inv.paid_to_date == D(500) and inv.doc_status == "O" and bal("112000") == bank0 + 500
        p2 = banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000", cash_acct="111000",
                                                      cash_sum=D(280), checks=[CheckRequest(check_num=1001, check_sum=D(400),
                                                                                             bank_code="DEUTDE")],
                                                      items=[PaidItem(it.trans_id, it.line_id, D(680))]))
        print(f"1 Invoice {inv.doc_num} 1180: payment {p1.doc_num} transfer 500, payment {p2.doc_num} cash 280 + check 400 "
              f"-> paid {inv.paid_to_date}, status {inv.doc_status}")
        assert inv.paid_to_date == D(1180) and inv.doc_status == "C" and cust.balance == cbal0
        assert bal("111000") == cash0 + 280 and bal("117000") == chk0 + 400
        _rejects(lambda: banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000",
                 cash_acct="111000", cash_sum=D(1), items=[PaidItem(it.trans_id, it.line_id, D(1))])), "item already paid")

        # 2) deposit the check, cancel and redo
        key = p2.checks[0].check_abs
        dep = banking.deposit_checks(s, DAY, "112000", [key], memo="Checks July")
        assert bal("117000") == chk0 and bal("112000") == bank0 + 900
        _rejects(lambda: banking.cancel_payment(s, "24", p2.doc_entry), "check deposited")
        banking.cancel_deposit(s, dep.depos_id)
        assert bal("117000") == chk0 + 400
        dep = banking.deposit_checks(s, DAY, "112000", [key])
        cdep = banking.deposit_cash(s, DAY, "112000", "111000", D(280))
        print(f"2 Check deposit {dep.depos_num} (after one canceled), cash deposit {cdep.depos_num}: checks account back to "
              f"{bal('117000')}, cash {bal('111000')}")
        assert bal("111000") == cash0 and bal("112000") == bank0 + 1180

        # 3) credit memo offset: invoice 1,000 net + credit memo 200 net -> payment of the difference
        inv2, cm = _service_doc(s, "13", "C30000", "1000"), None
        cm = _service_doc(s, "14", "C30000", "200")
        p3 = banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000", trsfr_acct="112000",
                                                      trsfr_sum=D("944"), items=[_item(s, inv2), _item(s, cm)]))
        print(f"3 Invoice {inv2.doc_num} 1180 - credit memo {cm.doc_num} 236 = payment {p3.doc_num} {p3.doc_total}")
        assert inv2.doc_status == "C" and cm.paid_to_date == D(236) and [i.sum_applied for i in p3.invoices] == [D(1180), D(-236)]

        # 4) payment on account, reconciled later with an invoice by a payment without means
        p4 = banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000", trsfr_acct="112000",
                                                      trsfr_sum=D(354), pay_no_doc=True))
        assert p4.no_doc_sum == D(354) and cust.balance == cbal0 - 354
        inv3 = _service_doc(s, "13", "C30000", "300")
        p5 = banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000",
                                                      items=[_item(s, inv3), _pay_item(s, p4)]))
        print(f"4 Payment on account {p4.doc_num} 354 reconciled with invoice {inv3.doc_num} by payment {p5.doc_num} "
              f"(no journal entry: {p5.trans_id is None})")
        assert inv3.doc_status == "C" and p4.open_bal == 0 and p5.trans_id is None and cust.balance == cbal0
        _rejects(lambda: banking.cancel_payment(s, "24", p4.doc_entry), "amount on account used")
        _rejects(lambda: docs.cancel_document(s, "14", cm.doc_entry), "credit memo used in a payment")

        # 5) outgoing payment to a vendor with bank charges; account payment
        vend = s.get(BusinessPartner, "V20000")
        vbal0, chg0 = vend.balance, bal("613000")
        ap = _service_doc(s, "18", "V20000", "500")
        bank1 = bal("112000")
        p6 = banking.create_payment(s, PaymentRequest(obj="46", doc_date=DAY, doc_type="S", card_code="V20000",
                                                      trsfr_acct="112000", trsfr_sum=D(590), bank_chrg=D("4.50"),
                                                      items=[_item(s, ap)]))
        assert ap.doc_status == "C" and vend.balance == vbal0 and bal("112000") == bank1 - D("594.50")
        assert bal("613000") == chg0 + D("4.50")
        rent0 = bal("612000")
        p7 = banking.create_payment(s, PaymentRequest(obj="46", doc_date=DAY, doc_type="A", cash_acct="111000",
                                                      cash_sum=D(800), accounts=[banking.AccountLine("612000", D(800), "Rent July")]))
        print(f"5 Outgoing payment {p6.doc_num} 590 + bank charges 4.50; account payment {p7.doc_num} rent 800")
        assert bal("612000") == rent0 + 800

        # 6) foreign-currency payment: invoice in INR paid in USD, exchange difference posted
        inv4 = _service_doc(s, "13", "C30000", "1000")
        rate = exchange_rate(s, "USD", DAY)
        usd = (D(1180) / rate).quantize(D("0.01")) + D("0.05")  # 5 cents more than needed (exchange difference)
        gain0 = bal("711000")
        p8 = banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000", doc_curr="USD",
                                                      trsfr_acct="112000", trsfr_sum=usd, items=[_item(s, inv4)]))
        print(f"6 Payment {p8.doc_num}: USD {usd} at {rate} = INR {p8.doc_total} for invoice 1180; exchange gain "
              f"{gain0 - bal('711000')}")
        assert inv4.doc_status == "C" and p8.doc_total_fc == usd and bal("711000") - gain0 == -(p8.doc_total - 1180)

        # 7) cancel a payment: the invoice reopens
        inv5 = _service_doc(s, "13", "C30000", "84.74")
        p9 = banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000", cash_acct="111000",
                                                      cash_sum=inv5.doc_total, items=[_item(s, inv5)]))
        target = s.get(type(inv), p9.invoices[0].doc_entry)
        banking.cancel_payment(s, "24", p9.doc_entry)
        print(f"7 Payment {p9.doc_num} canceled: invoice {target.doc_num} open again, paid {target.paid_to_date}")
        assert target.doc_status == "O" and target.paid_to_date == 0 and p9.canceled == "Y"

        # 8) rules
        _rejects(lambda: banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000", cash_acct="111000",
                 cash_sum=D(50), items=[_item(s, target)])), "means lower than the amount to pay")
        _rejects(lambda: banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000", cash_acct="111000",
                 cash_sum=D(500), items=[_item(s, target)])), "excess without payment on account")
        _rejects(lambda: banking.create_payment(s, PaymentRequest(obj="46", doc_date=DAY, doc_type="S", card_code="C30000",
                 cash_acct="111000", cash_sum=D(1))), "customer on a vendor payment")
        _rejects(lambda: banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY, card_code="C30000",
                 cash_acct="114000", cash_sum=D(1))), "control account as cash account")

        # invariants
        s.flush()
        for bp in s.scalars(select(BusinessPartner)):
            open_sum = s.scalar(select(func.coalesce(func.sum(JournalLine.bal_due_deb - JournalLine.bal_due_cred), 0))
                                .where(JournalLine.short_name == bp.card_code, JournalLine.short_name != JournalLine.account))
            assert Decimal(open_sum) == bp.balance, f"{bp.card_code}: balance {bp.balance} != open items {open_sum}"
        tb = reports.trial_balance(s, date(2026, 1, 1), date(2026, 12, 31))
        assert tb["balanced"]
        print("Every business partner balance equals its open items; trial balance balanced")
        print("\nOK - payments, reconciliation, checks, deposits and cancellations are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
