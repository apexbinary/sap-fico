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


def posting_period(session: Session, ref_date: date) -> PostingPeriod:
    """The unlocked posting period that contains a posting date (OFPR)."""
    period = session.scalars(select(PostingPeriod).where(
        PostingPeriod.f_ref_date <= ref_date, PostingPeriod.t_ref_date >= ref_date)).first()
    if period is None:
        raise B1Error(f"No posting period is defined for {ref_date.isoformat()}")
    if period.period_stat != "N":
        raise B1Error(f"Posting period {period.code} is locked")
    return period


def exchange_rate(session: Session, currency: str, on: date) -> Decimal:
    """Local currency per unit of ``currency`` on a date (ORTT); 1 for the local currency."""
    if currency == company(session).main_curncy:
        return Decimal("1")
    row = session.get(ExchangeRate, (on, currency))
    if row is None:
        raise B1Error(f"Update the exchange rate of {currency} for {on.isoformat()} (ORTT)")
    return row.rate


def due_date(session: Session, group_num: int | None, doc_date: date) -> date:
    """Due date from payment terms (OCTG): document date + extra months + extra days."""
    terms = session.get(PaymentTerms, group_num) if group_num is not None else None
    if terms is None:
        return doc_date
    month_index = doc_date.month - 1 + terms.extra_month
    year, month = doc_date.year + month_index // 12, month_index % 12 + 1
    day = min(doc_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day) + timedelta(days=terms.extra_days)
