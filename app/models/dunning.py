"""Dunning (FBMP customizing, F150 dunning run).

Tables modelled here:
    T047A  Dunning procedures            (+ T047T text folded into TEXT1)
    T047B  Dunning levels per procedure  (days in arrears, interest flag)
    T047C  Dunning charges per level and currency
    T047M  Dunning areas per company code
    T056   Interest indicators            (+ T056X text folded into TEXT1)
    T056P  Interest rates per indicator, currency and valid-from date
    MAHNV  Dunning run control (parameters and status of a run, LAUFD + LAUFI)
    MHNK   Dunning data per account and dunning area (one dunning notice)
    MHND   Dunning data per line item

Customer / vendor dunning data per company code and dunning area are KNB5 /
LFB5 (models.partners); the dunning level, last dunning date, block and area
of a line item are BSEG-MANST, MADAT, MANSP and MABER. Column names other
than the keys, MAHNG and the BSEG/KNB5/LFB5 fields follow the FBMP / F150
screens and still need checking against the SAP data dictionary.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.documents import AMOUNT
from app.models.organizational import MANDT


class DunningProcedure(Base):
    """T047A — Dunning procedure (+ T047T name in text1)."""

    __tablename__ = "t047a"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    mahna: Mapped[str] = mapped_column(String(4), primary_key=True)  # Dunning procedure
    text1: Mapped[str] = mapped_column(String(30))  # Name of the procedure
    rhytm: Mapped[int] = mapped_column(default=14)  # Dunning interval in days
    mstuf: Mapped[int] = mapped_column(default=4)  # Number of dunning levels
    gracp: Mapped[int] = mapped_column(default=0)  # Line item grace period (days)
    minbt: Mapped[Decimal] = mapped_column(Numeric(13, 2), default=Decimal("0"))  # Minimum amount to dun


class DunningLevel(Base):
    """T047B — Dunning level of a procedure."""

    __tablename__ = "t047b"
    __table_args__ = (ForeignKeyConstraint(["mandt", "mahna"], ["t047a.mandt", "t047a.mahna"]),)

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    mahna: Mapped[str] = mapped_column(String(4), primary_key=True)  # Dunning procedure
    mahns: Mapped[int] = mapped_column(primary_key=True)  # Dunning level
    verzn: Mapped[int] = mapped_column()  # Days in arrears from which the level applies
    text1: Mapped[str] = mapped_column(String(40))  # Notice title for the level
    xalwy: Mapped[bool] = mapped_column(default=False)  # Always dun at this level (even without level change)
    xzins: Mapped[bool] = mapped_column(default=False)  # Calculate dunning interest at this level


class DunningCharge(Base):
    """T047C — Dunning charge per level and currency."""

    __tablename__ = "t047c"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    mahna: Mapped[str] = mapped_column(String(4), primary_key=True)  # Dunning procedure
    mahns: Mapped[int] = mapped_column(primary_key=True)  # Dunning level
    waers: Mapped[str] = mapped_column(String(5), primary_key=True)  # Currency
    mahng: Mapped[Decimal] = mapped_column(Numeric(13, 2), default=Decimal("0"))  # Dunning charge


class DunningArea(Base):
    """T047M — Dunning area of a company code."""

    __tablename__ = "t047m"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    maber: Mapped[str] = mapped_column(String(2), primary_key=True)  # Dunning area
    text1: Mapped[str] = mapped_column(String(30))  # Name of the dunning area


class InterestIndicator(Base):
    """T056 — Interest indicator (+ T056X text in text1)."""

    __tablename__ = "t056"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    vzskz: Mapped[str] = mapped_column(String(2), primary_key=True)  # Interest indicator
    text1: Mapped[str] = mapped_column(String(30))  # Name
    zbase: Mapped[int] = mapped_column(default=360)  # Days per year for the interest calculation


class InterestRate(Base):
    """T056P — Debit interest rate of an interest indicator from a date."""

    __tablename__ = "t056p"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    vzskz: Mapped[str] = mapped_column(String(2), primary_key=True)  # Interest indicator
    waers: Mapped[str] = mapped_column(String(5), primary_key=True)  # Currency
    datab: Mapped[date] = mapped_column(primary_key=True)  # Valid from
    zsoll: Mapped[Decimal] = mapped_column(Numeric(7, 4))  # Debit interest rate in % per year


class DunningRunControl(Base):
    """MAHNV — Dunning run control (F150 parameters folded in)."""

    __tablename__ = "mahnv"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    laufd: Mapped[date] = mapped_column(primary_key=True)  # Run date
    laufi: Mapped[str] = mapped_column(String(6), primary_key=True)  # Run identification
    ausdt: Mapped[date] = mapped_column()  # Dunning date (issue date of the notices)
    bukrs: Mapped[str] = mapped_column(String(4))  # Company code (parameter)
    kunnr_low: Mapped[str | None] = mapped_column(String(10))  # Customer from (parameter)
    kunnr_high: Mapped[str | None] = mapped_column(String(10))  # Customer to (parameter)
    lifnr_low: Mapped[str | None] = mapped_column(String(10))  # Vendor from (parameter)
    lifnr_high: Mapped[str | None] = mapped_column(String(10))  # Vendor to (parameter)
    xvore: Mapped[bool] = mapped_column(default=False)  # Proposal created
    xecht: Mapped[bool] = mapped_column(default=False)  # Dunning run (print) carried out
    usnam: Mapped[str] = mapped_column(String(12), default="SYSTEM")  # User
    vorer: Mapped[datetime | None] = mapped_column()  # Proposal created at
    echer: Mapped[datetime | None] = mapped_column()  # Run executed at

    accounts: Mapped[list["DunningAccount"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
        order_by="[DunningAccount.koart, DunningAccount.kunnr, DunningAccount.lifnr, DunningAccount.maber]")


class DunningAccount(Base):
    """MHNK — Dunning data per account and dunning area (one notice).

    Exactly one of KUNNR (customer) and LIFNR (vendor with a debit balance) is
    filled; the other is ''.
    """

    __tablename__ = "mhnk"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "laufd", "laufi"], ["mahnv.mandt", "mahnv.laufd", "mahnv.laufi"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    laufd: Mapped[date] = mapped_column(primary_key=True)  # Run date
    laufi: Mapped[str] = mapped_column(String(6), primary_key=True)  # Run identification
    koart: Mapped[str] = mapped_column(String(1), primary_key=True, default="D")  # Account type
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    kunnr: Mapped[str] = mapped_column(String(10), primary_key=True, default="")  # Customer
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True, default="")  # Vendor
    maber: Mapped[str] = mapped_column(String(2), primary_key=True, default="")  # Dunning area
    mahna: Mapped[str] = mapped_column(String(4))  # Dunning procedure
    mahns: Mapped[int] = mapped_column(default=0)  # Dunning level of the notice (highest item level)
    mahnv: Mapped[int] = mapped_column(default=0)  # Previous account dunning level
    waers: Mapped[str] = mapped_column(String(5))  # Currency
    salhw: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Total overdue (net of credits)
    mahng: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Dunning charge
    zinsb: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Dunning interest
    xmflg: Mapped[bool] = mapped_column(default=True)  # Notice is issued (False: listed, not dunned)
    # Why no notice is issued. Not an SAP column (SAP writes it to the dunning log).
    reason: Mapped[str | None] = mapped_column(String(120))

    run: Mapped["DunningRunControl"] = relationship(back_populates="accounts")
    items: Mapped[list["DunningItem"]] = relationship(
        back_populates="account", cascade="all, delete-orphan",
        order_by="[DunningItem.gjahr, DunningItem.belnr, DunningItem.buzei]")

    @property
    def partner(self) -> str:
        return self.kunnr or self.lifnr


class DunningItem(Base):
    """MHND — Dunning data per line item."""

    __tablename__ = "mhnd"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mandt", "laufd", "laufi", "koart", "bukrs", "kunnr", "lifnr", "maber"],
            ["mhnk.mandt", "mhnk.laufd", "mhnk.laufi", "mhnk.koart", "mhnk.bukrs", "mhnk.kunnr", "mhnk.lifnr",
             "mhnk.maber"],
        ),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    laufd: Mapped[date] = mapped_column(primary_key=True)  # Run date
    laufi: Mapped[str] = mapped_column(String(6), primary_key=True)  # Run identification
    koart: Mapped[str] = mapped_column(String(1), primary_key=True, default="D")  # Account type
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    kunnr: Mapped[str] = mapped_column(String(10), primary_key=True, default="")  # Customer
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True, default="")  # Vendor
    maber: Mapped[str] = mapped_column(String(2), primary_key=True, default="")  # Dunning area
    belnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Document number
    gjahr: Mapped[int] = mapped_column(primary_key=True)  # Fiscal year
    buzei: Mapped[int] = mapped_column(primary_key=True)  # Line item
    shkzg: Mapped[str] = mapped_column(String(1))  # Debit/credit indicator
    dmshb: Mapped[Decimal] = mapped_column(AMOUNT)  # Amount (dunned side positive, offsetting items negative)
    faedt: Mapped[date | None] = mapped_column()  # Net due date
    verzn: Mapped[int] = mapped_column(default=0)  # Days in arrears on the dunning date
    mahnn: Mapped[int] = mapped_column(default=0)  # New dunning level of the item
    manst: Mapped[int] = mapped_column(default=0)  # Previous dunning level of the item
    mansp: Mapped[str | None] = mapped_column(String(1))  # Dunning block of the item
    zinsb: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Dunning interest on the item
    xblnr: Mapped[str | None] = mapped_column(String(16))  # Reference
    sgtxt: Mapped[str | None] = mapped_column(String(50))  # Item text

    account: Mapped["DunningAccount"] = relationship(back_populates="items")
