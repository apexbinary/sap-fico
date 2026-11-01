"""Fiscal year / posting period determination and open-period control.

Implements SAP's mapping from a posting date (BUDAT) to a fiscal year (GJAHR)
and posting period (MONAT) using the fiscal year variant (T009/T009B), plus the
open-period check against T001B.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organizational import (
    CompanyCode,
    FiscalYearPeriod,
    FiscalYearVariant,
    PostingPeriodControl,
)


class PostingError(Exception):
    """Raised when a posting violates an FI rule. Message mimics SAP style."""


def determine_period(session: Session, mandt: str, periv: str, budat: date) -> tuple[int, int]:
    """Return (gjahr, monat) for a posting date under a fiscal year variant.

    For a calendar-year variant (XMON) this is simply (year, month). For a
    non-calendar variant the T009B period boundaries are evaluated.
    """
    variant = session.get(FiscalYearVariant, (mandt, periv))
    if variant is None:
        raise PostingError(f"Fiscal year variant {periv} is not defined")

    if variant.xmon:
        return budat.year, budat.month

    rows = session.scalars(
        select(FiscalYearPeriod)
        .where(
            FiscalYearPeriod.mandt == mandt,
            FiscalYearPeriod.periv == periv,
            FiscalYearPeriod.bdatj == 0,
        )
        .order_by(FiscalYearPeriod.bumon, FiscalYearPeriod.butag)
    ).all()
    if not rows:
        raise PostingError(f"No period definition (T009B) for variant {periv}")

    for row in rows:
        if (budat.month, budat.day) <= (row.bumon, row.butag):
            return budat.year + row.reljr, row.perio
    # After the last boundary -> first period of next shifted year.
    last = rows[-1]
    return budat.year + last.reljr + 1, rows[0].perio


def check_period_open(
    session: Session,
    mandt: str,
    bukrs: str,
    koart: str,
    gjahr: int,
    monat: int,
) -> None:
    """Validate the posting period is open for the account type (T001B).

    SAP evaluates the '+' (valid-for-all) entry and the account-type specific
    entry. We fall back to '+' when no account-type specific row exists.
    """
    row = session.get(PostingPeriodControl, (mandt, bukrs, koart, ""))
    if row is None:
        row = session.get(PostingPeriodControl, (mandt, bukrs, "+", ""))
    if row is None:
        raise PostingError(
            f"Posting period control (T001B) missing for company code {bukrs}"
        )

    in_range_1 = _within(monat, gjahr, row.frpe1, row.frgj1, row.tope1, row.tagj1)
    in_range_2 = _within(monat, gjahr, row.frpe2, row.frgj2, row.tope2, row.tagj2)
    if not (in_range_1 or in_range_2):
        raise PostingError(
            f"Posting period {monat}/{gjahr} is not open for account type "
            f"'{koart}' in company code {bukrs}"
        )


def _within(period: int, year: int, frpe: int, frgj: int, tope: int, tagj: int) -> bool:
    """A period/year falls within an open range [from, to]."""
    after_from = (year, period) >= (frgj or year, frpe) if frgj else period >= frpe
    before_to = (year, period) <= (tagj if tagj != 9999 else year, tope) if tagj != 9999 else period <= tope
    return after_from and before_to


def company_code(session: Session, mandt: str, bukrs: str) -> CompanyCode:
    cc = session.get(CompanyCode, (mandt, bukrs))
    if cc is None:
        raise PostingError(f"Company code {bukrs} does not exist")
    return cc
