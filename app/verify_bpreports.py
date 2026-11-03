"""End-to-end check for aging, account statement and cash flow.

A new customer with invoices due long ago, recently and in the future: the aging puts them in
their buckets by due date and nets a payment on account in its bucket; the statement's running balance ends at the
partner's balance and its open items add up to it; the cash flow's opening + receipts - payments
equals the closing balance of the cash and bank accounts.

Run after app.seed (rerunnable: a fresh customer each run):  python -m app.verify_bpreports
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.finance import Account, JournalLine
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import banking, bp_reports
from app.services import documents as docs
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
ON = date(2027, 6, 30)


def main() -> None:
    s = SessionLocal()
    try:
        n = s.scalar(select(func.count()).select_from(BusinessPartner).where(BusinessPartner.card_code.like("C7%"))) + 1
        code = f"C7{n:04d}"
        s.add(BusinessPartner(card_code=code, card_name="Aging Test Traders", card_type="C", group_code=100, currency="##", deb_pay_acct="114000",
                              group_num=1, list_num=1, vat_group="OCS18", country="IN", balance=D(0), dnotes_bal=D(0), orders_bal=D(0),
                              frozen_for="N", bill_to_def="Main", ship_to_def="Main", credit_line=D(0)))
        s.flush()
        for kind in ("B", "S"):
            s.add(PartnerAddress(card_code=code, adres_type=kind, address="Main", street="3 MG Road", city="Bengaluru", zip_code="560001",
                                 state="KA", country="IN", gst_type="U"))
        s.commit()
        inv = lambda d, due, price: docs.create_document(s, DR(obj="13", doc_date=d, doc_due_date=due, card_code=code, disc_prcnt=D(0),  # noqa: E731
                                                               lines=[DL(item_code="S00001", quantity=D(1), price=D(price))]))
        inv(date(2027, 1, 10), date(2027, 2, 9), 1000)     # 141 days overdue -> 120+
        inv(date(2027, 5, 10), date(2027, 6, 9), 2000)     # 21 days -> 1-30
        inv(date(2027, 6, 20), date(2027, 7, 20), 3000)    # not due
        banking.create_payment(s, banking.PaymentRequest(obj="24", doc_date=date(2027, 6, 25), card_code=code, trsfr_acct="112000",
                                                         trsfr_sum=D(500)))  # on account
        ag = next(p for p in bp_reports.aging(s, ON, "C")["partners"] if p["card_code"] == code)
        assert ag["120+"] == 1180 and ag["1-30"] == 2360 - 500 and ag["current"] == 3540 and ag["total"] == 1180 + 2360 + 3540 - 500, ag
        print(f"1 Aging of {code} on {ON}: over 120 days 1,180, 1-30 days 2,360 less the 500 on account (due 25-06), not due 3,540; "
              f"total {ag['total']}")

        st = bp_reports.statement(s, code, date(2027, 1, 1), ON)
        bp = s.get(BusinessPartner, code)
        assert st["opening"] == 0 and st["closing"] == bp.balance == ag["total"] and len(st["lines"]) == 4
        assert sum((i["open"] for i in st["open_items"]), D(0)) == bp.balance
        print(f"2 Statement: opening 0, 4 movements, closing {st['closing']} = partner balance = open items")

        cf = bp_reports.cash_flow(s, date(2027, 1, 1), date(2027, 12, 31))
        cash = [a.acct_code for a in s.scalars(select(Account).where(Account.finanse == "Y"))]
        end = s.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
            JournalLine.account.in_(cash), JournalLine.ref_date <= date(2027, 12, 31)))
        assert cf["closing"] == end and cf["opening"] + cf["total_in"] - cf["total_out"] == cf["closing"]
        assert any(f["origin"] == "Incoming payments" and f["in"] >= 500 for f in cf["flows"])
        print(f"3 Cash flow 2027: opening {cf['opening']} + receipts {cf['total_in']} - payments {cf['total_out']} = closing {cf['closing']}")
        print("\nOK - aging, statements and cash flow agree with the journal.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
