"""End-to-end check for the period-end closing (scratch year 2025: no other check posts in it).

Closing 2025 posts every P&L account's balance to zero against 312000 on 31-12-2025 (TransType
-3) and locks the periods; P&L accounts are 0 afterwards, the P&L report still shows the year's
result (closing entries excluded), the balance sheet stays balanced and the trial balance zero; a
second closing is refused, postings into 2025 are refused; canceling reverses the entry and
reopens December, after which the year can be closed again.

Run after app.seed (rerunnable):  python -m app.verify_closing
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.admin import PostingPeriod
from app.models.finance import Account, JournalEntry, JournalLine
from app.services import closing, journal, reports
from app.services.admin import B1Error
from app.services.journal import JournalLineRequest as JL
from app.services.journal import JournalRequest as JR

D = Decimal
Y = 2025


def _pl_net(s) -> D:
    return s.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).join(Account, Account.acct_code == JournalLine.account)
                    .where(Account.group_mask.notin_([1, 2, 3]), JournalLine.ref_date >= date(Y, 1, 1), JournalLine.ref_date <= date(Y, 12, 31)))


def main() -> None:
    s = SessionLocal()
    try:
        if closing.preview(s, Y)["closed"]:  # rerun: start open
            closing.cancel(s, Y)
        for p in s.scalars(select(PostingPeriod).where(PostingPeriod.category == str(Y))):
            p.period_stat = "N"
        s.commit()
        journal.post_entry(s, JR(ref_date=date(Y, 6, 30), memo="Service income", lines=[JL(account="112000", debit=D(50000)), JL(account="412000", credit=D(50000))]))
        journal.post_entry(s, JR(ref_date=date(Y, 7, 31), memo="Rent", lines=[JL(account="612000", debit=D(20000)), JL(account="112000", credit=D(20000))]))
        pv = closing.preview(s, Y)
        result = pv["net_profit"]
        assert result == -_pl_net(s) and result != 0
        je = closing.run(s, Y, "312000", lock=True)
        assert je.trans_type == "-3" and je.ref_date == date(Y, 12, 31) and _pl_net(s) == 0
        pl = reports.profit_and_loss(s, date(Y, 1, 1), date(Y, 12, 31))
        assert pl["net_profit"] == result
        bs = reports.balance_sheet(s, date(Y, 12, 31), date(Y, 1, 1))
        assert bs["balanced"], (bs["total_assets"], bs["total_liabilities"], bs["total_capital"])
        assert s.scalar(select(func.sum(Account.curr_total)).where(Account.postable == "Y")) == 0
        for fn, text in [(lambda: closing.run(s, Y, "312000"), "already closed"),
                         (lambda: journal.post_entry(s, JR(ref_date=date(Y, 8, 1), lines=[JL(account="612000", debit=D(1)), JL(account="112000", credit=D(1))])), "locked"),
                         (lambda: closing.run(s, 2026, "112000"), "capital and reserves")]:
            try:
                fn()
                raise AssertionError(text)
            except B1Error as exc:
                assert text in str(exc), exc
                s.rollback()
        print(f"1 Closing {Y}: result {result} to 312000 in JE {je.number} (TransType -3), P&L accounts 0, periods locked; the P&L report "
              "still shows the result, balance sheet balanced, trial balance 0; second closing, postings into the year and a non-capital "
              "closing account refused")
        closing.cancel(s, Y)
        assert _pl_net(s) == -result and not closing.preview(s, Y)["closed"]
        je2 = closing.run(s, Y, "312000", lock=False)
        closing.cancel(s, Y)
        assert s.scalar(select(func.count()).select_from(JournalEntry).where(JournalEntry.ref3 == f"PEC:{Y}")) >= 4 and je2.number
        assert all(p.period_stat == "N" for p in s.scalars(select(PostingPeriod).where(PostingPeriod.category == str(Y))))
        print("2 Canceling reverses the closing (P&L balances back) and unlocks the year; it can be closed and canceled again")
        print("\nOK - period-end closing works like B1.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
