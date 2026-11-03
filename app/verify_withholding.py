"""End-to-end check for withholding tax (India TDS) on A/P invoices.

194C (2 %, 30,000 per invoice / 1,00,000 a year): no TDS below both, TDS on an invoice above
30,000, catch-up of the earlier invoices when the year crosses 1,00,000; no PAN: 20 % (206AA);
codes overridden on the document; a credit memo copied from an invoice reverses its TDS;
194Q only on the excess over 50 lakh; the vendor line = total - TDS, TDS payable credited, the
vendor balance = its open items; canceled invoices leave the TDS register; deposit due dates.

Run after app.seed (rerunnable: fresh vendors each run):  python -m app.verify_withholding
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.documents import DOCUMENT_WITHHOLDING
from app.models.finance import Account, JournalLine
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import documents as docs
from app.services import withholding as wh
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 7, 5)


def _vendor(s, name: str, codes: list[str], pan: str | None) -> BusinessPartner:
    n = s.scalar(select(func.count()).select_from(BusinessPartner).where(BusinessPartner.card_code.like("V9%"))) + 1
    code = f"V9{n:04d}"
    bp = BusinessPartner(card_code=code, card_name=name, card_type="S", group_code=102, currency="##", deb_pay_acct="211000",
                         group_num=1, list_num=3, vat_group="ICS18", country="IN", balance=D(0), dnotes_bal=D(0),
                         orders_bal=D(0), frozen_for="N", bill_to_def="Main", ship_to_def="Main", credit_line=D(0))
    s.add(bp)
    s.flush()
    for kind in ("B", "S"):
        s.add(PartnerAddress(card_code=code, adres_type=kind, address="Main", street="5 Industrial Estate", city="Bengaluru",
                             zip_code="560058", state="KA", country="IN", gst_type="U"))
    s.flush()
    wh.set_partner(s, bp, {"wt_liable": True, "pan_no": pan, "wt_codes": codes})
    s.commit()
    return bp


def _ap(s, card: str, amount: int, obj: str = "18", wt_codes=None, base=None):
    lines = [DL(base_type="18", base_entry=base.doc_entry, base_line=0)] if base else [
        DL(item_code="C00001", quantity=D(1), price=D(amount))]
    return docs.create_document(s, DR(obj=obj, doc_date=DAY, card_code=card, disc_prcnt=D(0), lines=lines, wt_codes=wt_codes))


def _vendor_line(s, doc) -> JournalLine:
    return s.scalar(select(JournalLine).where(JournalLine.trans_id == doc.trans_id, JournalLine.short_name == doc.card_code))


def _tds_line(s, doc) -> D:
    l = s.scalar(select(JournalLine).where(JournalLine.trans_id == doc.trans_id, JournalLine.account == "217000"))
    return (l.credit - l.debit) if l else D(0)


def main() -> None:
    assert wh.rupees(D("212.50")) == 213 and wh.rupees(D("212.49")) == 212
    assert wh.due_date(date(2027, 3, 1)) == date(2027, 4, 30) and wh.due_date(date(2027, 12, 1)) == date(2028, 1, 7)
    assert wh.fy_start(date(2027, 3, 31)) == date(2026, 4, 1) and wh.fy_start(date(2027, 4, 1)) == date(2027, 4, 1)
    print("1 Whole rupees (288B); deposit due 7th of next month, March by 30 April; financial year from 1 April")

    s = SessionLocal()
    try:
        tb_before = s.scalar(select(Account.curr_total).where(Account.acct_code == "217000")) or D(0)
        a = _vendor(s, "Ravi Contractors", ["C2"], "ABCPR1234K")
        try:
            wh.set_partner(s, a, {"pan_no": "12345"})
            raise AssertionError("bad PAN accepted")
        except B1Error:
            s.rollback()
        inv1, inv2, inv3 = _ap(s, a.card_code, 20000), _ap(s, a.card_code, 25000), _ap(s, a.card_code, 40000)
        assert inv1.wt_sum == 0 and inv2.wt_sum == 0 and inv3.wt_sum == 800, (inv1.wt_sum, inv2.wt_sum, inv3.wt_sum)
        inv4 = _ap(s, a.card_code, 20000)
        assert inv4.wt_sum == 1300, inv4.wt_sum  # 2 % of 1,05,000 = 2,100 less 800 already deducted
        gross4 = D(20000) * D("1.18")
        vl = _vendor_line(s, inv4)
        assert inv4.doc_total == gross4 - 1300 and vl.credit == inv4.doc_total and vl.bal_due_cred == inv4.doc_total
        assert _tds_line(s, inv4) == 1300
        base, tds = wh.year_to_date(s, a.card_code, "C2", date(2027, 4, 1))
        assert base == 105000 and tds == 2100
        print(f"2 194C 2 %: invoices 20,000 / 25,000 no TDS, 40,000 (> 30,000) TDS 800, 20,000 crossing 1,00,000 TDS 1,300 "
              f"(catch-up); vendor line {vl.credit} = 23,600 - 1,300, TDS payable credited")

        b = _vendor(s, "Dr. Mehta (no PAN)", ["J2"], None)
        inv5 = _ap(s, b.card_code, 60000)
        row = wh.rows_of(s, "18", inv5.doc_entry)[0]
        assert inv5.wt_sum == 12000 and row["rate"] == 20 and row["no_pan"] and row["section"] == "194J(b)"
        none = _ap(s, b.card_code, 60000, wt_codes=[])
        assert none.wt_sum == 0 and not wh.rows_of(s, "18", none.doc_entry)
        print("3 194J(b) without PAN: 20 % (206AA) = 12,000; codes overridden on the document ([]): no TDS")

        cm = _ap(s, a.card_code, 0, obj="19", base=inv4)
        assert cm.wt_sum == 1300 and _tds_line(s, cm) == -1300 and cm.doc_total == gross4 - 1300
        base, tds = wh.year_to_date(s, a.card_code, "C2", date(2027, 4, 1))
        assert base == 85000 and tds == 800
        print("4 Credit memo copied from the 20,000 invoice reverses its 1,300 TDS; year to date 85,000 / 800")

        q = _vendor(s, "Steel Traders", ["Q"], "AAACS1234Q")
        big = _ap(s, q.card_code, 4500000)
        more = _ap(s, q.card_code, 1000000)
        assert big.wt_sum == 0 and more.wt_sum == 500, (big.wt_sum, more.wt_sum)  # 0.1 % of the 5 lakh above 50 lakh
        print("5 194Q: 45 lakh no TDS; next 10 lakh: 0.1 % of the 5 lakh above 50 lakh = 500")

        docs.cancel_document(s, "18", inv5.doc_entry, DAY)
        rep = wh.report(s, date(2027, 7, 1), date(2027, 7, 31))
        mine = [r for r in rep["rows"] if r["card_code"] in {a.card_code, b.card_code, q.card_code}]
        assert not any(r["doc_entry"] == inv5.doc_entry and r["obj"] == "18" for r in mine)
        assert sum(r["tds"] for r in mine) == 800 + 1300 - 1300 + 500
        jul = [x for x in rep["summary"] if x["month"] == "2027-07"]
        assert all(x["due_date"] == date(2027, 8, 7) for x in jul)
        print(f"6 Canceled invoice leaves the register; July TDS of these vendors {sum(r['tds'] for r in mine)}, due 07-08-2027")

        for bp in (a, b, q):
            s.refresh(bp)
            open_items = s.scalar(select(func.coalesce(func.sum(JournalLine.bal_due_deb - JournalLine.bal_due_cred), 0)).where(
                JournalLine.short_name == bp.card_code, JournalLine.account != JournalLine.short_name))
            assert bp.balance == open_items, (bp.card_code, bp.balance, open_items)
        tb_after = s.scalar(select(Account.curr_total).where(Account.acct_code == "217000"))
        assert tb_before - tb_after == 800 + 1300 - 1300 + 500, (tb_before, tb_after)  # liability: credit balance (negative)
        total = s.scalar(select(func.sum(Account.curr_total)).where(Account.postable == "Y"))
        assert total == 0, total
        cnt = s.scalar(select(func.count()).select_from(DOCUMENT_WITHHOLDING["18"]))
        print(f"7 Vendor balances = open items; TDS payable +1,300 net; trial balance 0; {cnt} PCH5 rows")
        print("\nOK - withholding tax (TDS) follows the thresholds and posts correctly.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
