"""End-to-end check for the payment wizard.

Two new vendors: due invoices, one invoice due after the cut-off, a credit memo offsetting, a
vendor on cash discount terms paid with the discount; one item deselected. Executing creates
one outgoing payment per vendor (bank transfer), closes the paid invoices and leaves the
deselected and not yet due ones open; executing again is refused; a run whose item was paid
meanwhile is outdated; a check run numbers the checks. Customers' collection run.

Run after app.seed (rerunnable, new partners each run):  python -m app.verify_paywiz
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.banking import OutgoingPayment
from app.models.finance import JournalLine
from app.models.partners import BusinessPartner
from app.services import banking, masterdata, paywiz, reports
from app.services import documents as docs
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
D0 = date(2027, 9, 1)


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def _bp(s, tag: str, kind: str, terms: int) -> str:
    n = (s.scalar(select(func.count()).select_from(BusinessPartner).where(BusinessPartner.card_code.like(f"{tag}%"))) or 0) + 1
    code = f"{tag}{n:03d}"
    masterdata.create_partner(s, masterdata.PartnerRequest(card_code=code, card_name=f"Verify {code}", card_type=kind,
                                                           group_num=terms, country="IN"))
    return code


def _doc(s, obj: str, card: str, day: date, amount: str):
    return docs.create_document(s, DR(obj=obj, doc_date=day, card_code=card, doc_type="S", disc_prcnt=D(0), lines=[
        DL(dscription="Service", acct_code="611000" if obj in ("18", "19") else "412000", price=D(amount),
           vat_group="ICS18" if obj in ("18", "19") else "OCS18")]))


def _line(s, doc) -> JournalLine:
    return s.scalars(select(JournalLine).where(JournalLine.trans_id == doc.trans_id, JournalLine.short_name == doc.card_code)).one()


def main() -> None:
    s = SessionLocal()
    try:
        v1, v2 = _bp(s, "VPWZ", "S", 1), _bp(s, "VPWD", "S", 4)   # net 30; 2 % 10 days
        i1 = _doc(s, "18", v1, D0 - timedelta(days=40), "1000")   # due D0 - 10
        i2 = _doc(s, "18", v1, D0 - timedelta(days=35), "500")    # due D0 - 5 (deselected below)
        late = _doc(s, "18", v1, D0 + timedelta(days=5), "800")   # due D0 + 35: after the cut-off
        cm = _doc(s, "19", v1, D0 - timedelta(days=30), "200")    # credit memo offsets
        i3 = _doc(s, "18", v2, D0 - timedelta(days=3), "1000")    # discount terms, within 10 days

        # 1) recommendation
        run = paywiz.create_run(s, paywiz.RunRequest(pmnt_date=D0, due_date_to=D0 + timedelta(days=30), bank_acct="112000",
                                                     card_codes=[v1, v2]))
        rec = {(it.card_code, it.doc_num, it.trans_type): it for it in run.items}
        key = lambda bp, doc, obj: (bp, str(doc.doc_num), obj)  # noqa: E731
        print(f"1 Run {run.id_entry}: {len(run.items)} items, nets {paywiz.totals(run)}")
        assert key(v1, late, "18") not in rec
        assert rec[key(v1, cm, "19")].direction == -1 and rec[key(v2, i3, "18")].discount == D("23.60")

        # 2) deselect one invoice, execute
        paywiz.select_items(s, run.id_entry, [rec[key(v1, i2, "18")].line_num], False)
        assert paywiz.totals(run) == {v1: D(1180) - D(236), v2: D(1180) - D("23.60")}
        paywiz.execute(s, run.id_entry)
        pays = s.scalars(select(OutgoingPayment).where(OutgoingPayment.card_code.in_([v1, v2]))).all()
        print(f"2 Executed: payments " + ", ".join(f"{p.card_code} {p.doc_total}" for p in pays)
              + f"; invoices {i1.doc_status}/{i2.doc_status}/{late.doc_status}/{i3.doc_status}, credit memo {cm.doc_status}")
        assert sorted(p.doc_total for p in pays) == [D("944"), D("1156.40")]
        assert (i1.doc_status, i2.doc_status, late.doc_status, i3.doc_status, cm.doc_status) == ("C", "O", "O", "C", "C")
        _rejects(lambda: paywiz.execute(s, run.id_entry), "run already executed")

        # 3) outdated run: an item paid in between
        run2 = paywiz.create_run(s, paywiz.RunRequest(pmnt_date=D0, due_date_to=D0 + timedelta(days=30), bank_acct="112000",
                                                      card_codes=[v1]))
        l2 = _line(s, i2)
        banking.create_payment(s, banking.PaymentRequest(obj="46", doc_date=D0, doc_type="S", card_code=v1, cash_acct="111000",
                                                         cash_sum=D(100), items=[banking.PaidItem(l2.trans_id, l2.line_id, D(100))]))
        _rejects(lambda: paywiz.execute(s, run2.id_entry), "item changed since the recommendation")
        paywiz.cancel(s, run2.id_entry)

        # 4) check run: checks numbered from the first check number
        run3 = paywiz.create_run(s, paywiz.RunRequest(pmnt_date=D0 + timedelta(days=40), due_date_to=D0 + timedelta(days=40),
                                                      bank_acct="112000", pay_means="C", first_check=7001, card_codes=[v1]))
        paywiz.execute(s, run3.id_entry)
        p3 = s.get(OutgoingPayment, run3.items[0].pay_entry)
        print(f"3 Check run {run3.id_entry}: payment {p3.doc_num} check {p3.checks[0].check_num} for {p3.doc_total}")
        assert p3.checks[0].check_num == 7001 and p3.doc_total == D(944) + D(590) - D(100)  # i2 rest 490 + late 944

        # 5) collection from customers
        c1 = _bp(s, "CPWZ", "C", 1)
        inv = _doc(s, "13", c1, D0 - timedelta(days=40), "2000")
        run4 = paywiz.create_run(s, paywiz.RunRequest(pmnt_date=D0, due_date_to=D0, bank_acct="112000", pay_type="C",
                                                      card_codes=[c1]))
        paywiz.execute(s, run4.id_entry)
        print(f"4 Collection run {run4.id_entry}: invoice {inv.doc_num} {inv.doc_status}")
        assert inv.doc_status == "C"

        assert reports.trial_balance(s, date(2027, 1, 1), date(2027, 12, 31))["balanced"]
        print("\nOK - payment wizard recommendation, selection and execution are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
