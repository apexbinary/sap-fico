"""End-to-end check for financials: journal entries, reversal, period lock, reports.

Run after app.seed (rerunnable):  python -m app.verify_finance
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.models.admin import PostingPeriod
from app.models.finance import Account
from app.services import journal, reports
from app.services.admin import B1Error
from app.services.journal import JournalLineRequest as L
from app.services.journal import JournalRequest

D = Decimal


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
        bank_before = s.get(Account, "112000").curr_total

        # 1) opening capital and a rent payment
        cap = journal.post_entry(s, JournalRequest(ref_date=date(2026, 1, 2), memo="Share capital paid in", lines=[
            L(account="112000", debit=D("50000")), L(account="311000", credit=D("50000"))]))
        rent = journal.post_entry(s, JournalRequest(ref_date=date(2026, 1, 31), memo="Rent January", lines=[
            L(account="612000", debit=D("1500")), L(account="112000", credit=D("1500"))]))
        print(f"1 JE {cap.number} (TransId {cap.trans_id}) and JE {rent.number}: bank balance "
              f"{s.get(Account, '112000').curr_total}")
        assert s.get(Account, "112000").curr_total == bank_before + D("48500")
        assert rent.lines[0].contra_act == "112000" and rent.lines[1].contra_act == "612000"

        # 2) validation rules
        _rejects(lambda: journal.post_entry(s, JournalRequest(ref_date=date(2026, 2, 1), lines=[
            L(account="612000", debit=D("10")), L(account="112000", credit=D("9"))])), "not balanced")
        _rejects(lambda: journal.post_entry(s, JournalRequest(ref_date=date(2026, 2, 1), lines=[
            L(account="61", debit=D("10")), L(account="112000", credit=D("10"))])), "title account")
        _rejects(lambda: journal.post_entry(s, JournalRequest(ref_date=date(2026, 2, 1), lines=[
            L(account="114000", debit=D("10")), L(account="112000", credit=D("10"))])), "control account")
        period = s.query(PostingPeriod).filter_by(code="2026-02").one()
        period.period_stat = "Y"
        s.commit()
        _rejects(lambda: journal.post_entry(s, JournalRequest(ref_date=date(2026, 2, 10), lines=[
            L(account="612000", debit=D("10")), L(account="112000", credit=D("10"))])), "period locked")
        period.period_stat = "N"
        s.commit()

        # 3) reversal
        wrong = journal.post_entry(s, JournalRequest(ref_date=date(2026, 3, 5), memo="Booked twice", lines=[
            L(account="611000", debit=D("200")), L(account="112000", credit=D("200"))]))
        rev = journal.reverse_entry(s, wrong.trans_id)
        print(f"3 JE {wrong.number} reversed by JE {rev.number}")
        assert wrong.storno_to_tr == rev.trans_id and rev.auto_storno == "Y"
        _rejects(lambda: journal.reverse_entry(s, wrong.trans_id), "already reversed")

        # 4) reports
        tb = reports.trial_balance(s, date(2026, 1, 1), date(2026, 12, 31))
        pl = reports.profit_and_loss(s, date(2026, 1, 1), date(2026, 12, 31))
        bs = reports.balance_sheet(s, date(2026, 12, 31), date(2026, 1, 1))
        print(f"4 Trial balance debit {tb['total_debit']} credit {tb['total_credit']}; net profit {pl['net_profit']};"
              f" assets {bs['total_assets']} = liabilities {bs['total_liabilities']} + capital {bs['total_capital']}")
        assert tb["balanced"] and bs["balanced"]
        assert bs["current_profit"] == pl["net_profit"]
        print("\nOK - journal entries, validation, reversal and financial reports are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
