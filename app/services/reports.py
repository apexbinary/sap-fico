"""Financial reports: trial balance, balance sheet and profit & loss statement.

All figures come from the journal entry lines (JDT1). The balance sheet and the
P&L follow the chart of accounts tree: active accounts roll up into their
title accounts (FatherNum) and drawers (GroupMask). The period's profit or loss
shows on the balance sheet as a line in capital and reserves.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import BALANCE_SHEET_DRAWERS, DRAWERS, Account, JournalEntry, JournalLine

ZERO = Decimal("0")


def _balances(session: Session, date_from: date | None, date_to: date) -> dict[str, tuple[Decimal, Decimal]]:
    stmt = select(JournalLine.account, func.sum(JournalLine.debit), func.sum(JournalLine.credit)).join(
        JournalEntry, JournalEntry.trans_id == JournalLine.trans_id).where(JournalEntry.ref_date <= date_to)
    if date_from:
        stmt = stmt.where(JournalEntry.ref_date >= date_from)
    return {acct: (Decimal(d or 0), Decimal(c or 0)) for acct, d, c in session.execute(stmt.group_by(JournalLine.account))}


def trial_balance(session: Session, date_from: date, date_to: date) -> dict:
    """Opening balance, period debit/credit and closing balance per active account.

    Balance sheet accounts open with everything posted before ``date_from``;
    P&L accounts start from zero.
    """
    accounts = {a.acct_code: a for a in session.scalars(select(Account).where(Account.postable == "Y"))}
    before = _balances(session, None, date.fromordinal(date_from.toordinal() - 1))
    period = _balances(session, date_from, date_to)
    lines = []
    for code in sorted(set(before) | set(period)):
        acct = accounts.get(code)
        opening = ZERO
        if acct is not None and acct.group_mask in BALANCE_SHEET_DRAWERS and code in before:
            d, c = before[code]
            opening = d - c
        d, c = period.get(code, (ZERO, ZERO))
        if not (opening or d or c):
            continue
        lines.append({"acct_code": code, "acct_name": acct.acct_name if acct else code,
                      "group_mask": acct.group_mask if acct else None, "opening": opening,
                      "debit": d, "credit": c, "closing": opening + d - c})
    total_d = sum((l["debit"] for l in lines), ZERO)
    total_c = sum((l["credit"] for l in lines), ZERO)
    return {"date_from": date_from, "date_to": date_to, "lines": lines, "total_debit": total_d,
            "total_credit": total_c, "balanced": total_d == total_c,
            "opening_total": sum((l["opening"] for l in lines), ZERO)}


def _tree(session: Session, drawers: set[int], balances: dict[str, Decimal], sign: int) -> list[dict]:
    accounts = session.scalars(select(Account).where(Account.group_mask.in_(drawers)).order_by(Account.acct_code)).all()
    children: dict[str | None, list[Account]] = defaultdict(list)
    for a in accounts:
        children[a.father_num].append(a)

    def build(acct: Account, depth: int) -> dict:
        kids = [build(k, depth + 1) for k in children[acct.acct_code]]
        own = balances.get(acct.acct_code, ZERO)
        amount = own + sum((k["raw"] for k in kids), ZERO)
        return {"acct_code": acct.acct_code, "acct_name": acct.acct_name, "postable": acct.postable == "Y",
                "depth": depth, "raw": amount, "amount": amount * sign + ZERO, "children": kids}

    roots = [a for a in accounts if a.father_num is None or a.father_num not in {x.acct_code for x in accounts}]
    return [build(r, 0) for r in roots]


def profit_and_loss(session: Session, date_from: date, date_to: date) -> dict:
    period = _balances(session, date_from, date_to)
    bal = {k: d - c for k, (d, c) in period.items()}
    drawers = [{"group_mask": g, "name": DRAWERS[g], "accounts": _tree(session, {g}, bal, -1)} for g in range(4, 10)]
    for d in drawers:
        d["amount"] = sum((a["amount"] for a in d["accounts"]), ZERO)
    net = sum((d["amount"] for d in drawers), ZERO)  # revenue positive, costs negative
    gross = sum((d["amount"] for d in drawers if d["group_mask"] in (4, 5)), ZERO)
    return {"date_from": date_from, "date_to": date_to, "drawers": drawers, "gross_profit": gross, "net_profit": net}


def balance_sheet(session: Session, as_of: date, fiscal_year_start: date) -> dict:
    cumulative = _balances(session, None, as_of)
    bal = {k: d - c for k, (d, c) in cumulative.items()}
    assets = _tree(session, {1}, bal, 1)
    liabilities = _tree(session, {2}, bal, -1)
    capital = _tree(session, {3}, bal, -1)
    # profit of earlier years and of the current year (P&L accounts are not closed here)
    pl_accounts = {a.acct_code for a in session.scalars(select(Account).where(Account.group_mask.notin_(BALANCE_SHEET_DRAWERS)))}
    earlier = -sum((v for k, v in _balance_map(session, None, date.fromordinal(fiscal_year_start.toordinal() - 1)).items()
                    if k in pl_accounts), ZERO)
    current = profit_and_loss(session, fiscal_year_start, as_of)["net_profit"]
    total_assets = sum((a["amount"] for a in assets), ZERO)
    total_liab = sum((a["amount"] for a in liabilities), ZERO)
    total_capital = sum((a["amount"] for a in capital), ZERO) + earlier + current
    return {"as_of": as_of, "assets": assets, "liabilities": liabilities, "capital": capital,
            "retained_profit": earlier, "current_profit": current, "total_assets": total_assets,
            "total_liabilities": total_liab, "total_capital": total_capital,
            "balanced": total_assets == total_liab + total_capital}


def _balance_map(session: Session, date_from: date | None, date_to: date) -> dict[str, Decimal]:
    return {k: d - c for k, (d, c) in _balances(session, date_from, date_to).items()}
