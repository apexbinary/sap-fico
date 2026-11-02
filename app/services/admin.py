"""Administration services: numbering series, posting periods, exchange rates, due dates."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import Company, ExchangeRate, NumberingSeries, PaymentTerms, PostingPeriod


class B1Error(Exception):
    """A business rule was violated; surfaces as HTTP 422 with the message."""


def company(session: Session) -> Company:
    comp = session.get(Company, 1)
    if comp is None:
        raise B1Error("Company details (OADM) are not set up; run the seed")
    return comp


def next_number(session: Session, object_code: str) -> int:
    """Next number of the default numbering series of an object type (NNM1)."""
    series = session.scalars(select(NumberingSeries).where(
        NumberingSeries.object_code == object_code, NumberingSeries.is_default.is_(True))).first()
    if series is None:
        raise B1Error(f"No numbering series for object type {object_code} (NNM1)")
    number = series.next_number
    if series.last_num and number > series.last_num:
        raise B1Error(f"Numbering series {series.series_name} of object {object_code} is exhausted")
    series.next_number = number + 1
    return number


def posting_period(session: Session, ref_date: date, due: date | None = None, doc: date | None = None) -> PostingPeriod:
    """The unlocked posting period that contains a posting date (OFPR); the due date and the
    document date must lie in the period's due date and document date ranges."""
    period = session.scalars(select(PostingPeriod).where(
        PostingPeriod.f_ref_date <= ref_date, PostingPeriod.t_ref_date >= ref_date)).first()
    if period is None:
        raise B1Error(f"No posting period is defined for {ref_date.isoformat()}")
    if period.period_stat != "N":
        raise B1Error(f"Posting period {period.code} is locked")
    for label, value, low, high in (("Due date", due, period.f_due_date, period.t_due_date),
                                    ("Document date", doc, period.f_tax_date, period.t_tax_date)):
        if value and ((low and value < low) or (high and value > high)):
            raise B1Error(f"{label} {value.isoformat()} is outside the range of posting period {period.code} "
                          f"({low.isoformat() if low else '-'} - {high.isoformat() if high else '-'})")
    return period


def exchange_rate(session: Session, currency: str, on: date) -> Decimal:
    """Local currency per unit of ``currency`` on a date (ORTT); 1 for the local currency."""
    if currency == company(session).main_curncy:
        return Decimal("1")
    row = session.get(ExchangeRate, (on, currency))
    if row is None:
        raise B1Error(f"Update the exchange rate of {currency} for {on.isoformat()} (ORTT)")
    return row.rate


def due_date(session: Session, group_num: int | None, doc_date: date, tax_date: date | None = None) -> date:
    """Due date from payment terms (OCTG).

    Base date: posting date (BslineDate P), document date (T) or today (S); then
    "start from" (PayDuMonth): S month start, H half month (15th or month end),
    E month end, N the base date itself; then + extra months + extra days.
    """
    terms = session.get(PaymentTerms, group_num) if group_num is not None else None
    if terms is None:
        return doc_date
    base = {"T": tax_date or doc_date, "S": date.today()}.get(terms.bsline_date, doc_date)
    last = calendar.monthrange(base.year, base.month)[1]
    if terms.pay_du_month == "S":
        base = base.replace(day=1)
    elif terms.pay_du_month == "E":
        base = base.replace(day=last)
    elif terms.pay_du_month == "H":
        base = base.replace(day=15 if base.day <= 15 else last)
    month_index = base.month - 1 + terms.extra_month
    year, month = base.year + month_index // 12, month_index % 12 + 1
    end_of_month = base.day == last and terms.pay_du_month == "E"
    day = calendar.monthrange(year, month)[1] if end_of_month else min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day) + timedelta(days=terms.extra_days)


def default_series(session: Session, object_code: str) -> int | None:
    """Series number of the default numbering series of an object type."""
    return session.scalar(select(NumberingSeries.series).where(
        NumberingSeries.object_code == object_code, NumberingSeries.is_default.is_(True)))


def check_project(session: Session, code: str | None, on: date | None = None) -> None:
    """A project (OPRJ) must exist, be active and valid on the posting date."""
    if not code:
        return
    from app.models.admin import Project

    prj = session.get(Project, code)
    if prj is None or prj.active != "Y":
        raise B1Error(f"Project {code} does not exist or is inactive")
    if on and ((prj.valid_from and on < prj.valid_from) or (prj.valid_to and on > prj.valid_to)):
        raise B1Error(f"Project {code} is not valid on {on.isoformat()}")


def check_sales_employee(session: Session, slp_code: int | None) -> None:
    if slp_code is None or slp_code == -1:
        return
    from app.models.admin import SalesEmployee

    slp = session.get(SalesEmployee, slp_code)
    if slp is None or slp.active != "Y":
        raise B1Error(f"Sales employee {slp_code} does not exist or is inactive")
