"""End-to-end check for the standard B1 fields added by the field audit.

Payment terms due dates (based on / start from), journal entry references, projects,
transaction codes, blocked manual posting and automatic reversal; document defaults
from the business partner (sales employee, contact, bill-to / ship-to, discount);
country / state dropdown tables; the seed never resets user data (period lock).

Run after app.seed (rerunnable):  python -m app.verify_fields
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.models.admin import PaymentTerms, PostingPeriod, Project
from app.models.finance import Account, JournalEntry
from app.models.partners import BusinessPartner, ContactPerson
from app.services import documents as docs
from app.services import journal, masterdata
from app.services.admin import B1Error, due_date
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR
from app.services.journal import JournalLineRequest as L
from app.services.journal import JournalRequest

D = Decimal
DAY = date(2026, 5, 4)


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def main() -> None:
    s = SessionLocal()
    try:
        # 1) payment terms: Net 30, end of next month (start from month end), based on document date
        assert due_date(s, 1, DAY) == date(2026, 6, 3)
        assert due_date(s, 3, DAY) == date(2026, 6, 30) and due_date(s, 3, date(2026, 1, 31)) == date(2026, 2, 28)
        t = s.get(PaymentTerms, 1)
        old = t.bsline_date
        t.bsline_date = "T"
        assert due_date(s, 1, DAY, date(2026, 4, 20)) == date(2026, 5, 20), "based on the document date"
        t.bsline_date = old
        s.commit()
        print("1 Due dates: Net 30 -> 2026-06-03, end of next month -> 2026-06-30 (Jan 31 -> Feb 28), "
              "based on document date ok")

        # 2) journal entry: references, project, transaction code, line due date, automatic reversal
        je = journal.post_entry(s, JournalRequest(
            ref_date=DAY, memo="Accrual May", ref1="R1", ref2="R2", ref3="R3", trans_code="AC", project="P001",
            auto_storno=True, storno_date=date(2026, 6, 1), lines=[
                L(account="612000", debit=D("800"), project="P002", ref1="L1", due_date=date(2026, 5, 31)),
                L(account="112000", credit=D("800"))]))
        rev = s.get(JournalEntry, je.storno_to_tr)
        print(f"2 JE {je.number}: Ref3 {je.ref3}, code {je.trans_code}, project {je.project}, series {je.series}; "
              f"reversed automatically by JE {rev.number} on {rev.ref_date}")
        assert (je.ref3, je.trans_code, je.project, je.auto_storno) == ("R3", "AC", "P001", "Y")
        assert je.lines[0].project == "P002" and je.lines[1].project == "P001" and je.lines[0].ref1 == "L1"
        assert je.lines[0].due_date == date(2026, 5, 31) and rev.ref_date == date(2026, 6, 1)
        assert rev.storno_to_tr == je.trans_id and je.series == 1
        _rejects(lambda: journal.post_entry(s, JournalRequest(ref_date=DAY, project="NOPE", lines=[
            L(account="612000", debit=D("1")), L(account="112000", credit=D("1"))])), "unknown project")
        _rejects(lambda: journal.post_entry(s, JournalRequest(ref_date=DAY, trans_code="ZZ", lines=[
            L(account="612000", debit=D("1")), L(account="112000", credit=D("1"))])), "unknown transaction code")
        _rejects(lambda: journal.post_entry(s, JournalRequest(ref_date=DAY, auto_storno=True, lines=[
            L(account="612000", debit=D("1")), L(account="112000", credit=D("1"))])), "reverse without a date")
        _rejects(lambda: journal.post_entry(s, JournalRequest(ref_date=DAY, tax_date=date(2020, 1, 1), lines=[
            L(account="612000", debit=D("1")), L(account="112000", credit=D("1"))])), "document date outside the period range")
        acct = s.get(Account, "613000")
        acct.bloc_man_pos = "Y"
        s.commit()
        _rejects(lambda: journal.post_entry(s, JournalRequest(ref_date=DAY, lines=[
            L(account="613000", debit=D("1")), L(account="112000", credit=D("1"))])), "blocked for manual posting")
        acct.bloc_man_pos = "N"
        s.commit()

        # 3) document defaults from the business partner
        bp = s.get(BusinessPartner, "C10000")
        anna = s.query(ContactPerson).filter_by(card_code="C10000", name="Priya Sharma").one()
        old_discount, bp.discount = bp.discount, D("5")
        s.commit()
        inv = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", lines=[
            DL(item_code="S00001", quantity=D(2), free_txt="On site", project="P002")]))
        line = inv.lines[0]
        print(f"3 A/R invoice {inv.doc_num}: sales employee {inv.slp_code}, contact {inv.cntct_code}, bill-to "
              f"'{inv.address}', ship-to '{inv.address2}', discount {inv.disc_prcnt}%, line delivery {line.ship_date}, "
              f"gross price {line.price_af_vat}")
        assert inv.slp_code == bp.slp_code and inv.cntct_code == anna.cntct_code
        assert inv.pay_to_code == "Main" and inv.ship_to_code == "Main" and "Bengaluru" in inv.address2
        assert inv.disc_prcnt == D("5") and inv.series == 1 and line.ship_date == inv.doc_due_date
        assert line.free_txt == "On site" and line.project == "P002" and line.price_af_vat == D("1770.000000")
        assert inv.doc_total == D("3363.00"), "2 x 1500 = 3000, -5 % = 2850, + CGST 9 % + SGST 9 %"
        bp.discount = old_discount
        s.commit()
        other = s.query(ContactPerson).filter(ContactPerson.card_code != "C10000").first()
        _rejects(lambda: docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", cntct_code=other.cntct_code,
                                                    lines=[DL(item_code="S00001")])), "contact of another partner")
        _rejects(lambda: docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", ship_to_code="Nowhere",
                                                    lines=[DL(item_code="S00001")])), "unknown ship-to address")
        prj = s.get(Project, "P001")
        prj.active = "N"
        s.commit()
        _rejects(lambda: docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", project="P001",
                                                    lines=[DL(item_code="S00001")])), "inactive project")
        prj.active = "Y"
        s.commit()

        # 4) country / state dropdown tables
        _rejects(lambda: masterdata.save_address(s, "C10000", "S", "Bad", {"country": "DE", "state": "TX"}),
                 "state of another country")
        _rejects(lambda: masterdata.create_partner(s, masterdata.PartnerRequest(
            card_code="XCTRY", card_name="x", card_type="C", country="XX")), "unknown country")

        # 5) the seed (run on every start) keeps user data: a locked period stays locked
        from app.seed import seed

        period = s.query(PostingPeriod).filter_by(code="2027-12").one()
        period.period_stat = "Y"
        s.commit()
        seed()
        s.expire_all()
        assert s.query(PostingPeriod).filter_by(code="2027-12").one().period_stat == "Y", "seed reset the lock"
        period = s.query(PostingPeriod).filter_by(code="2027-12").one()
        period.period_stat = "N"
        s.commit()
        print("5 Seed rerun kept the locked period 2027-12 locked")
        print("\nOK - standard fields, defaults and their validations are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
