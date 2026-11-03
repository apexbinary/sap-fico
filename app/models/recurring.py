"""Recurring postings.

    ORCR   Recurring posting template: frequency, next due date, end (date or number of postings)
    RCR1   Template lines: G/L account or business partner, debit / credit, line memo, distribution rules
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

AMOUNT = Numeric(19, 6)


class RecurringPosting(Base):
    """ORCR — Recurring posting template."""

    __tablename__ = "orcr"

    rcur_code: Mapped[str] = mapped_column("RcurCode", String(8), primary_key=True)
    rcur_desc: Mapped[str] = mapped_column("RcurDesc", String(50))
    frequency: Mapped[str] = mapped_column("Frequency", String(1))  # D daily, W weekly, M monthly, Q quarterly, H semiannual, A annual, O one time
    next_deu: Mapped[date] = mapped_column("NextDeu", Date)  # next due date
    day: Mapped[int | None] = mapped_column("Day", Integer)  # day of the month to post (not B1-verified); 31 = month end
    last_date: Mapped[date | None] = mapped_column("LastDate", Date)  # last posted
    valid_until: Mapped[date | None] = mapped_column("ValidUntil", Date)
    limit_rtrns: Mapped[int | None] = mapped_column("LimitRtrns", Integer)  # number of postings (None = no limit)
    instance: Mapped[int] = mapped_column("Instance", Integer, default=0)  # postings made
    memo: Mapped[str | None] = mapped_column("Memo", String(50))
    active: Mapped[str] = mapped_column("Active", String(1), default="Y")
    lines: Mapped[list["RecurringPostingLine"]] = relationship(cascade="all, delete-orphan", order_by="RecurringPostingLine.line_id")


class RecurringPostingLine(Base):
    """RCR1 — Lines of a recurring posting template."""

    __tablename__ = "rcr1"

    rcur_code: Mapped[str] = mapped_column("RcurCode", String(8), ForeignKey("orcr.RcurCode"), primary_key=True)
    line_id: Mapped[int] = mapped_column("LineId", primary_key=True)
    account: Mapped[str | None] = mapped_column("AcctCode", String(15))
    card_code: Mapped[str | None] = mapped_column("ShortName", String(15))  # business partner
    debit: Mapped[Decimal] = mapped_column("Debit", AMOUNT, default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column("Credit", AMOUNT, default=Decimal("0"))
    line_memo: Mapped[str | None] = mapped_column("LineMemo", String(50))
    ocr_code: Mapped[str | None] = mapped_column("OcrCode", String(8))
    ocr_code2: Mapped[str | None] = mapped_column("OcrCode2", String(8))
