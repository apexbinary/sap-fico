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


def partner_balances(session: Session, mandt: str, bukrs: str, koart: str, gjahr: int, period_to: int = 16) -> dict:
    """Customer (D) / vendor (K) balances from KNC1/LFC1, reconciled against the G/L (FD10N / FK10N).

    Each reconciliation account's G/L balance must equal the sum of its
    partners' balances; a difference means the sub-ledger and G/L disagree.
    """
    from app.models.partners import (
        Customer,
        CustomerCompanyCode,
        CustomerTotals,
        Vendor,
        VendorCompanyCode,
        VendorTotals,
    )
    from app.services.fsv import partner_closing

    if koart == "D":
        model, key, master, names = CustomerTotals, "kunnr", CustomerCompanyCode, Customer
    elif koart == "K":
        model, key, master, names = VendorTotals, "lifnr", VendorCompanyCode, Vendor
    else:
        raise ValueError("koart must be D or K")
    lines, per_recon = [], {}
    for row in session.scalars(select(model).where(model.mandt == mandt, model.bukrs == bukrs, model.gjahr == gjahr)
                               .order_by(getattr(model, key))):
        partner = getattr(row, key)
        debit = sum((getattr(row, f"um{p:02d}s") or Decimal("0") for p in range(1, period_to + 1)), Decimal("0"))
        credit = sum((getattr(row, f"um{p:02d}h") or Decimal("0") for p in range(1, period_to + 1)), Decimal("0"))
        balance = partner_closing(row, period_to)
        m = session.get(master, (mandt, partner, bukrs))
        recon = m.akont if m else None
        per_recon[recon] = per_recon.get(recon, Decimal("0")) + balance
        n = session.get(names, (mandt, partner))
        lines.append({"partner": partner, "name": n.name1 if n else None, "akont": recon,
                      "carryforward": row.umsav, "debit": debit, "credit": credit, "balance": balance})
    recon = []
    for akont, sub_total in sorted(per_recon.items(), key=lambda kv: kv[0] or ""):
        gl = account_balance(session, mandt, bukrs, gjahr, akont, period_to)["balance"] if akont else Decimal("0")
        recon.append({"akont": akont, "subledger": sub_total, "gl": gl, "difference": gl - sub_total})
    return {"koart": koart, "bukrs": bukrs, "gjahr": gjahr, "period_to": period_to, "lines": lines,
            "reconciliation": recon, "reconciled": all(r["difference"] == 0 for r in recon)}


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
