"""End-to-end check for cash discount and installments.

Terms "2 % within 10 days, 1 % within 20 days, net 30": an invoice paid on day 5 with 2 % cash
discount (discount allowed account), canceled and paid again on day 15 with 1 %; too much
discount and a discount on a partial payment are refused; a vendor invoice paid with the
discount received. Terms "3 installments 30/60/90": one partner line per installment with its
due date, paid installment by installment (INV6 status); a credit memo is reconciled with an
installment through a payment. Invariants: BP balance = open items, trial balance.

Run after app.seed (rerunnable):  python -m app.verify_cashdisc
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.documents import DOCUMENT_INSTALLMENTS
from app.models.finance import Account, JournalLine
from app.models.partners import BusinessPartner
from app.services import banking, masterdata, reports
from app.services import documents as docs
from app.services.admin import B1Error
from app.services.banking import PaidItem, PaymentRequest
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 8, 2)


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def _partner(s, code: str, kind: str, terms: int) -> BusinessPartner:
    if s.get(BusinessPartner, code) is None:
        masterdata.create_partner(s, masterdata.PartnerRequest(card_code=code, card_name=f"Verify {code}", card_type=kind,
                                                               group_num=terms, country="IN"))
    return s.get(BusinessPartner, code)


def _service(s, obj: str, card: str, amount: str, day: date = DAY, base=None):
    lines = [DL(base_type=base.obj_type, base_entry=base.doc_entry, base_line=0)] if base else [
        DL(dscription="Service", acct_code="412000" if obj in ("13", "14") else "611000", price=D(amount),
           vat_group="OCS18" if obj in ("13", "14") else "ICS18")]
    return docs.create_document(s, DR(obj=obj, doc_date=day, card_code=card, doc_type="S", disc_prcnt=D(0), lines=lines))


def _lines(s, doc) -> list[JournalLine]:
    return s.scalars(select(JournalLine).where(JournalLine.trans_id == doc.trans_id, JournalLine.short_name == doc.card_code)
                     .order_by(JournalLine.line_id)).all()


def main() -> None:
    s = SessionLocal()
    try:
        bal = lambda code: s.get(Account, code).curr_total  # noqa: E731
        cust = _partner(s, "CDISC01", "C", 4)
        vend = _partner(s, "VDISC01", "S", 4)
        cbal0, alw0, rcv0 = cust.balance, bal("615000"), bal("722000")

        # 1) paid on day 5: 2 % cash discount
        inv = _service(s, "13", cust.card_code, "1000")
        line = _lines(s, inv)[0]
        items = {(x["trans_id"], x["line_id"]): x for x in banking.open_items(s, cust.card_code, DAY + timedelta(days=5))}
        x = items[(line.trans_id, line.line_id)]
        print(f"1 Invoice {inv.doc_num} {inv.doc_total}, due {inv.doc_due_date}: on day 5 discount {x['discount_pct']}% = {x['discount']}")
        assert x["discount_pct"] == D(2) and x["discount"] == D("23.60") and inv.doc_due_date == DAY + timedelta(days=30)
        _rejects(lambda: banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY + timedelta(days=5), card_code=cust.card_code,
                 trsfr_acct="112000", trsfr_sum=D("500"), items=[PaidItem(line.trans_id, line.line_id, D("500"), D("23.60"))])),
                 "cash discount on a partial payment")
        p1 = banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY + timedelta(days=5), card_code=cust.card_code,
                                                      trsfr_acct="112000", trsfr_sum=D("1156.40"),
                                                      items=[PaidItem(line.trans_id, line.line_id, D("1156.40"), D("23.60"))]))
        print(f"   payment {p1.doc_num} 1156.40 + discount {p1.invoices[0].dcnt_sum}: invoice {inv.doc_status}, discount allowed "
              f"{bal('615000') - alw0}")
        assert inv.doc_status == "C" and bal("615000") - alw0 == D("23.60") and cust.balance == cbal0

        # 2) canceled, then paid on day 15: only 1 %
        banking.cancel_payment(s, "24", p1.doc_entry)
        assert inv.doc_status == "O" and line.bal_due_deb == D(1180) and bal("615000") == alw0
        late = DAY + timedelta(days=15)
        _rejects(lambda: banking.create_payment(s, PaymentRequest(obj="24", doc_date=late, card_code=cust.card_code,
                 trsfr_acct="112000", trsfr_sum=D("1156.40"), items=[PaidItem(line.trans_id, line.line_id, D("1156.40"), D("23.60"))])),
                 "2 % after 10 days")
        banking.create_payment(s, PaymentRequest(obj="24", doc_date=late, card_code=cust.card_code, trsfr_acct="112000",
                                                 trsfr_sum=D("1168.20"), items=[PaidItem(line.trans_id, line.line_id, D("1168.20"), D("11.80"))]))
        print(f"2 Paid on day 15 with 1 %: discount allowed {bal('615000') - alw0}, invoice {inv.doc_status}")
        assert inv.doc_status == "C" and bal("615000") - alw0 == D("11.80")

        # 3) vendor invoice paid within 10 days: cash discount received
        ap = _service(s, "18", vend.card_code, "500")
        al = _lines(s, ap)[0]
        banking.create_payment(s, PaymentRequest(obj="46", doc_date=DAY + timedelta(days=3), doc_type="S", card_code=vend.card_code,
                                                 trsfr_acct="112000", trsfr_sum=D("578.20"),
                                                 items=[PaidItem(al.trans_id, al.line_id, D("578.20"), D("11.80"))]))
        print(f"3 A/P invoice {ap.doc_num} 590 paid 578.20: discount received {rcv0 - bal('722000')}")
        assert ap.doc_status == "C" and rcv0 - bal("722000") == D("11.80")

        # 4) installments 30/60/90
        inst_bp = _partner(s, "CINST01", "C", 5)
        inv2 = _service(s, "13", inst_bp.card_code, "1000")
        parts = _lines(s, inv2)
        cls = DOCUMENT_INSTALLMENTS["13"]
        insts = s.scalars(select(cls).where(cls.doc_entry == inv2.doc_entry).order_by(cls.instlmnt_id)).all()
        print(f"4 Invoice {inv2.doc_num} {inv2.doc_total} in installments: "
              + ", ".join(f"{i.instlmnt_id}: {i.ins_total} due {i.due_date}" for i in insts))
        assert [l.debit for l in parts] == [i.ins_total for i in insts] == [D("393.29"), D("393.29"), D("393.42")]
        assert [l.due_date for l in parts] == [DAY + timedelta(days=d) for d in (30, 60, 90)]
        banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY + timedelta(days=30), card_code=inst_bp.card_code,
                                                 cash_acct="111000", cash_sum=D("393.29"),
                                                 items=[PaidItem(parts[0].trans_id, parts[0].line_id, D("393.29"))]))
        assert [i.status for i in insts] == ["C", "O", "O"] and inv2.doc_status == "O"
        cm = _service(s, "14", inst_bp.card_code, "", base=inv2)  # not auto-reconciled with installments
        cml = _lines(s, cm)[0]
        assert cm.paid_to_date == 0 and cml.bal_due_cred == D(1180)
        p = banking.create_payment(s, PaymentRequest(obj="24", doc_date=DAY + timedelta(days=31), card_code=inst_bp.card_code,
                                                     items=[PaidItem(parts[1].trans_id, parts[1].line_id, D("393.29")),
                                                            PaidItem(parts[2].trans_id, parts[2].line_id, D("393.42")),
                                                            PaidItem(cml.trans_id, cml.line_id, D("786.71"))]))
        print(f"   installment 1 paid; credit memo {cm.doc_num} reconciled with installments 2 and 3 by payment {p.doc_num}: "
              f"statuses {[i.status for i in insts]}, invoice {inv2.doc_status}, credit memo open {cml.bal_due_cred}")
        assert [i.status for i in insts] == ["C", "C", "C"] and inv2.doc_status == "C" and cml.bal_due_cred == D("393.29")

        # invariants
        s.flush()
        for bp in (cust, vend, inst_bp):
            open_sum = s.scalar(select(func.coalesce(func.sum(JournalLine.bal_due_deb - JournalLine.bal_due_cred), 0))
                                .where(JournalLine.short_name == bp.card_code, JournalLine.short_name != JournalLine.account))
            assert Decimal(open_sum) == bp.balance, f"{bp.card_code}: {bp.balance} != {open_sum}"
        assert reports.trial_balance(s, date(2027, 1, 1), date(2027, 12, 31))["balanced"]
        print("\nOK - cash discount and installments are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
