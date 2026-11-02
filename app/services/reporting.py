"""Reporting — trial balance, G/L account balances, and open items.

Reads the posted facts (GLT0 totals and BSEG line items) and projects the
standard FI reports. Debit/credit split follows the GLT0 record's debit/credit
indicator (DRCRK), as in SAP.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import AccountingDocumentItem, GLAccountTotals
from app.models.gl_master import GLAccountText
from app.services.payment_terms import net_due_date

_PERIOD_COLS = [f"tsl{p:02d}" for p in range(1, 17)]


def _sum_periods(row: GLAccountTotals, period_to: int) -> Decimal:
    total = row.hslvt or Decimal("0")
    for p in range(1, min(period_to, 16) + 1):
        total += getattr(row, f"tsl{p:02d}") or Decimal("0")
    return total


def account_balance(
    session: Session, mandt: str, bukrs: str, gjahr: int, saknr: str, period_to: int = 16
) -> dict:
    """Debit, credit and net balance for one G/L account up to a period."""
    rows = session.scalars(
        select(GLAccountTotals).where(
            GLAccountTotals.mandt == mandt,
            GLAccountTotals.bukrs == bukrs,
            GLAccountTotals.gjahr == gjahr,
            GLAccountTotals.racct == saknr,
        )
    ).all()
    debit = sum((_sum_periods(r, period_to) for r in rows if r.drcrk == "S"), Decimal("0"))
    credit = sum((_sum_periods(r, period_to) for r in rows if r.drcrk == "H"), Decimal("0"))
    return {
        "saknr": saknr,
        "debit": debit,
        "credit": credit,
        "balance": debit - credit,
        "currency": rows[0].rtcur if rows else None,
    }


def trial_balance(
    session: Session, mandt: str, bukrs: str, gjahr: int, period_to: int = 16
) -> dict:
    """Trial balance: every account with its debit, credit and balance."""
    rows = session.scalars(
        select(GLAccountTotals).where(
            GLAccountTotals.mandt == mandt,
            GLAccountTotals.bukrs == bukrs,
            GLAccountTotals.gjahr == gjahr,
        )
    ).all()

    by_account: dict[str, dict] = {}
    for r in rows:
        acc = by_account.setdefault(
            r.racct, {"saknr": r.racct, "debit": Decimal("0"), "credit": Decimal("0")}
        )
        amount = _sum_periods(r, period_to)
        if r.drcrk == "S":
            acc["debit"] += amount
        else:
            acc["credit"] += amount

    lines = []
    total_debit = total_credit = Decimal("0")
    for acc in sorted(by_account.values(), key=lambda a: a["saknr"]):
        balance = acc["debit"] - acc["credit"]
        text = session.scalars(
            select(GLAccountText.txt50).where(
                GLAccountText.mandt == mandt, GLAccountText.saknr == acc["saknr"]
            )
        ).first()
        total_debit += acc["debit"]
        total_credit += acc["credit"]
        lines.append(
            {
                "saknr": acc["saknr"],
                "name": text,
                "debit": acc["debit"],
                "credit": acc["credit"],
                "balance": balance,
            }
        )

    return {
        "bukrs": bukrs,
        "gjahr": gjahr,
        "period_to": period_to,
        "lines": lines,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balanced": total_debit == total_credit,
    }


def open_items(
    session: Session,
    mandt: str,
    bukrs: str,
    koart: str,
    account: str,
    only_open: bool = True,
) -> list[dict]:
    """Open (or all) items of a customer (D), vendor (K) or open-item G/L account (S).

    Open items are open-item-managed BSEG rows of the account with no clearing document.
    """
    field = {"D": AccountingDocumentItem.kunnr, "K": AccountingDocumentItem.lifnr,
             "S": AccountingDocumentItem.hkont}[koart]
    stmt = select(AccountingDocumentItem).where(
        AccountingDocumentItem.mandt == mandt,
        AccountingDocumentItem.bukrs == bukrs,
        AccountingDocumentItem.koart == koart,
        field == account,
        AccountingDocumentItem.xopvw.is_(True),
    )
    if only_open:
        stmt = stmt.where(AccountingDocumentItem.augbl.is_(None))

    items = session.scalars(stmt).all()
    result = []
    for it in items:
        signed = it.dmbtr if it.shkzg == "S" else -it.dmbtr
        result.append(
            {
                "belnr": it.belnr,
                "gjahr": it.gjahr,
                "buzei": it.buzei,
                "shkzg": it.shkzg,
                "amount": signed,
                "wrbtr": it.wrbtr,
                "waers": it.header.waers,
                "budat": it.header.budat,
                "zfbdt": it.zfbdt,
                "zterm": it.zterm,
                "faedt": net_due_date(it),
                "rebzg": it.rebzg,
                "zuonr": it.zuonr,
                "sgtxt": it.sgtxt,
                "augbl": it.augbl,
                "augdt": it.augdt,
                "cleared": it.augbl is not None,
            }
        )
    return result
