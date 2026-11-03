"""Period-end closing of a financial year (B1: Period-End Closing, transaction type -3).

The closing entry, dated the last day of the year, posts every profit and loss account's balance of
the year (drawers 4-9) to zero against the closing account (retained earnings, a capital account);
balance sheet accounts carry forward as they are. The year's periods can be locked with it. One
closing per year; canceling reverses the entry and unlocks the year's periods. The P&L report
leaves closing entries out by default; the balance sheet includes them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.admin import PostingPeriod
from app.models.finance import Account, JournalEntry, JournalLine
from app.services import journal
from app.services.admin import B1Error

ZERO = Decimal("0")
CLOSING = "-3"
BALANCE_SHEET = {1, 2, 3}


def _pl_balances(session: Session, year: int) -> list[tuple[Account, Decimal]]:
    rows = session.execute(select(JournalLine.account, func.sum(JournalLine.debit - JournalLine.credit)).join(
        JournalEntry, JournalEntry.trans_id == JournalLine.trans_id).where(
        JournalEntry.ref_date >= date(year, 1, 1), JournalEntry.ref_date <= date(year, 12, 31),
        JournalEntry.trans_type != CLOSING).group_by(JournalLine.account)).all()
    out = []
    for acct_code, net in rows:
        a = session.get(Account, acct_code)
        if a is not None and a.group_mask not in BALANCE_SHEET and Decimal(net or 0):
            out.append((a, Decimal(net)))
    return sorted(out, key=lambda x: x[0].acct_code)


def _closing_entry(session: Session, year: int) -> JournalEntry | None:
    return session.scalar(select(JournalEntry).where(JournalEntry.trans_type == CLOSING, JournalEntry.ref3 == f"PEC:{year}",
                                                     JournalEntry.storno_to_tr.is_(None))
                          .order_by(JournalEntry.trans_id.desc()))


def _active_closing(session: Session, year: int) -> JournalEntry | None:
    e = _closing_entry(session, year)
    if e is None:
        return None
    reversed_ = session.scalar(select(JournalEntry.trans_id).where(JournalEntry.storno_to_tr == e.trans_id))
    return None if reversed_ else e


def preview(session: Session, year: int) -> dict:
    rows = _pl_balances(session, year)
    done = _active_closing(session, year)
    return {"year": year, "accounts": [{"acct_code": a.acct_code, "acct_name": a.acct_name, "balance": net} for a, net in rows],
            "net_profit": -sum((net for _, net in rows), ZERO), "closed": done is not None,
            "closing_trans": done.number if done else None}


def run(session: Session, year: int, closing_account: str, lock: bool = True) -> JournalEntry:
    if _active_closing(session, year) is not None:
        raise B1Error(f"The year {year} is already closed; cancel the closing first")
    acct = session.get(Account, closing_account)
    if acct is None or acct.postable != "Y" or acct.group_mask != 3:
        raise B1Error("The closing account must be a postable capital and reserves account (drawer 3)")
    rows = _pl_balances(session, year)
    if not rows:
        raise B1Error(f"No profit and loss balances in {year}")
    net = sum((n for _, n in rows), ZERO)  # debit - credit of the P&L accounts (negative = profit)
    lines = [journal.JournalLineRequest(account=a.acct_code, debit=-n if n < 0 else ZERO, credit=n if n > 0 else ZERO,
                                        line_memo=f"Closing {year}") for a, n in rows]
    lines.append(journal.JournalLineRequest(account=closing_account, debit=net if net > 0 else ZERO, credit=-net if net < 0 else ZERO,
                                            line_memo=f"Result {year}"))
    try:
        je = journal.post_entry(session, journal.JournalRequest(ref_date=date(year, 12, 31), memo=f"Period-end closing {year}",
                                                                ref3=f"PEC:{year}", trans_type=CLOSING, manual=False, lines=lines),
                                commit=False)
        if lock:
            for p in session.scalars(select(PostingPeriod).where(PostingPeriod.category == str(year))):
                p.period_stat = "Y"
        session.commit()
        return je
    except Exception:
        session.rollback()
        raise


def cancel(session: Session, year: int) -> JournalEntry:
    e = _active_closing(session, year)
    if e is None:
        raise B1Error(f"The year {year} is not closed")
    try:
        for p in session.scalars(select(PostingPeriod).where(PostingPeriod.category == str(year))):
            p.period_stat = "N"  # the closing locked the year; the reversal is posted on the closing date
        rev = journal.reverse_entry(session, e.trans_id, ref_date=e.ref_date, commit=False)
        session.commit()
        return rev
    except Exception:
        session.rollback()
        raise
