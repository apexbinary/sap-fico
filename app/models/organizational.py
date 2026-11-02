"""Enterprise Structure — SAP organizational units.

Mirrors the SAP data dictionary for the FI/CO org structure. Field names use the
original SAP technical names (BUKRS, KTOPL, PERIV, KOKRS, ...) with the English
data-element meaning in the comment. Lengths match the SAP domains.

Tables modelled here:
    T000   Clients
    T001   Company Codes
    T004   Chart of Accounts (directory)   + T004T text
    T009   Fiscal Year Variants            + T009B period definition
    TKA01  Controlling Areas
    TKA02  Controlling Area -> Company Code assignment
    TGSB   Business Areas                  + TGSBT text
    T014   Credit Control Areas
    TCURC  Currency Codes                  + TCURT text
    TCURR  Exchange Rates
    T001B  Permitted Posting Periods (open period control)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# SAP client (MANDT) is CHAR 3 and is the leading key of nearly every table.
MANDT = String(3)


class Client(Base):
    """T000 — Clients."""

    __tablename__ = "t000"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)  # Client
    mtext: Mapped[str] = mapped_column(String(25))  # Name of client
    ort01: Mapped[str | None] = mapped_column(String(25))  # City
    mwaer: Mapped[str | None] = mapped_column(String(5))  # Std currency (EURO conversion)
    adrnr: Mapped[str | None] = mapped_column(String(10))  # Address
    cccategory: Mapped[str | None] = mapped_column(String(1))  # Client role (P/T/C/D)
    cccoractiv: Mapped[str | None] = mapped_column(String(1))  # Changes to Customizing

    company_codes: Mapped[list["CompanyCode"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class ChartOfAccounts(Base):
    """T004 — Chart of accounts (list) + T004T description."""

    __tablename__ = "t004"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    ktopl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Chart of accounts
    ktplt: Mapped[str] = mapped_column(String(50))  # Chart of accounts description
    seona: Mapped[int] = mapped_column(default=10)  # Length of G/L account number
    xgpdr: Mapped[bool] = mapped_column(default=False)  # Group chart of accounts maintained
    ktop2: Mapped[str | None] = mapped_column(String(4))  # Group chart of accounts
    xbilk_manual: Mapped[bool] = mapped_column(default=False)  # Manual creation of cost elements
    spras: Mapped[str] = mapped_column(String(1), default="E")  # Maintenance language


class FiscalYearVariant(Base):
    """T009 — Fiscal year variants."""

    __tablename__ = "t009"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    periv: Mapped[str] = mapped_column(String(2), primary_key=True)  # Fiscal year variant
    xkale: Mapped[bool] = mapped_column(default=False)  # Year-dependent
    xjabh: Mapped[bool] = mapped_column(default=False)  # Fiscal year is year-dependent
    anzbp: Mapped[int] = mapped_column(default=12)  # Number of posting periods
    anzsp: Mapped[int] = mapped_column(default=4)  # Number of special periods
    xmon: Mapped[bool] = mapped_column(default=True)  # Calendar year = fiscal year
    beztx: Mapped[str | None] = mapped_column(String(30))  # Description

    periods: Mapped[list["FiscalYearPeriod"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )


class FiscalYearPeriod(Base):
    """T009B — Period definition for a fiscal year variant.

    Maps a calendar day boundary (BUMON/BUTAG) to a posting period (PERIO) with a
    year shift (RELJR). For a calendar-year variant this is one row per month.
    """

    __tablename__ = "t009b"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "periv"], ["t009.mandt", "t009.periv"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    periv: Mapped[str] = mapped_column(String(2), primary_key=True)  # Fiscal year variant
    bdatj: Mapped[int] = mapped_column(primary_key=True, default=0)  # Posting date year (0 = generic)
    bumon: Mapped[int] = mapped_column(primary_key=True)  # Upper limit month
    butag: Mapped[int] = mapped_column(default=31)  # Upper limit day
    reljr: Mapped[int] = mapped_column(default=0)  # Year shift (-1/0/+1)
    perio: Mapped[int] = mapped_column()  # Posting period

    variant: Mapped["FiscalYearVariant"] = relationship(back_populates="periods")


class CompanyCode(Base):
    """T001 — Company codes (the FI posting unit)."""

    __tablename__ = "t001"
    __table_args__ = (
        ForeignKeyConstraint(["mandt"], ["t000.mandt"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    butxt: Mapped[str] = mapped_column(String(25))  # Company name
    ort01: Mapped[str | None] = mapped_column(String(25))  # City
    land1: Mapped[str] = mapped_column(String(3))  # Country key
    waers: Mapped[str] = mapped_column(String(5))  # Local (company code) currency
    spras: Mapped[str] = mapped_column(String(1), default="E")  # Language key
    ktopl: Mapped[str] = mapped_column(String(4))  # Chart of accounts
    periv: Mapped[str] = mapped_column(String(2))  # Fiscal year variant
    waabw: Mapped[int] = mapped_column(default=10)  # Max exchange-rate deviation %
    kokfi: Mapped[str | None] = mapped_column(String(1))  # Allocation indicator (CO area = company code: 1)
    rcomp: Mapped[str | None] = mapped_column(String(6))  # Company (trading partner)
    adrnr: Mapped[str | None] = mapped_column(String(10))  # Address
    stceg: Mapped[str | None] = mapped_column(String(20))  # VAT registration number
    fikrs: Mapped[str | None] = mapped_column(String(4))  # Financial management (FM) area
    xfdmm: Mapped[bool] = mapped_column(default=False)  # Financial budgeting active
    xvglt: Mapped[bool] = mapped_column(default=True)  # Propose fiscal year
    buvar: Mapped[str | None] = mapped_column(String(1))  # Company code screen variant
    opvar: Mapped[str | None] = mapped_column(String(4))  # Posting period variant
    kkber: Mapped[str | None] = mapped_column(String(4))  # Credit control area
    xausz: Mapped[int] = mapped_column(default=0)  # Create bank-statement balances
    xgjrv: Mapped[bool] = mapped_column(default=False)  # Fiscal year variant is year-dependent
    bukrs_glob: Mapped[str | None] = mapped_column(String(6))  # Global company code
    land1_iso: Mapped[str | None] = mapped_column(String(2))  # ISO country code
    waers_iso: Mapped[str | None] = mapped_column(String(3))  # ISO currency code

    client: Mapped["Client"] = relationship(back_populates="company_codes")


class ControllingArea(Base):
    """TKA01 — Controlling areas."""

    __tablename__ = "tka01"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kokrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Controlling area
    bezei: Mapped[str] = mapped_column(String(25))  # Name
    waers: Mapped[str] = mapped_column(String(5))  # Controlling area currency
    ctyp: Mapped[str] = mapped_column(String(2), default="10")  # Currency type (10=company code)
    khinr: Mapped[str | None] = mapped_column(String(12))  # Standard hierarchy (cost centers)
    ktopl: Mapped[str] = mapped_column(String(4))  # Chart of accounts
    lmona: Mapped[str] = mapped_column(String(2))  # Fiscal year variant
    bukrs: Mapped[str | None] = mapped_column(String(4))  # Company code (if 1:1 assignment)
    xwbuk: Mapped[bool] = mapped_column(default=True)  # Cross-company-code cost accounting
    pcrec: Mapped[str | None] = mapped_column(String(1))  # Profit center accounting active
    erkrs: Mapped[str | None] = mapped_column(String(4))  # Operating concern (CO-PA)


class ControllingAreaAssignment(Base):
    """TKA02 — Assignment of company codes to a controlling area."""

    __tablename__ = "tka02"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kokrs"], ["tka01.mandt", "tka01.kokrs"]),
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kokrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Controlling area
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    gsber: Mapped[str | None] = mapped_column(String(4))  # Business area


class BusinessArea(Base):
    """TGSB — Business areas (+ TGSBT text)."""

    __tablename__ = "tgsb"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    gsber: Mapped[str] = mapped_column(String(4), primary_key=True)  # Business area
    gtext: Mapped[str] = mapped_column(String(30))  # Business area description
    spras: Mapped[str] = mapped_column(String(1), default="E")


class CreditControlArea(Base):
    """T014 — Credit control areas."""

    __tablename__ = "t014"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kkber: Mapped[str] = mapped_column(String(4), primary_key=True)  # Credit control area
    waers: Mapped[str] = mapped_column(String(5))  # Currency
    ktext: Mapped[str] = mapped_column(String(25))  # Description
    klimk: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))  # Default credit limit
    xdtm: Mapped[int] = mapped_column(default=0)  # Reaction (risk category)
    ctlpc: Mapped[str | None] = mapped_column(String(1))  # Update group


class Currency(Base):
    """TCURC — Currency codes (+ TCURT text)."""

    __tablename__ = "tcurc"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    waers: Mapped[str] = mapped_column(String(5), primary_key=True)  # Currency key
    isocd: Mapped[str | None] = mapped_column(String(3))  # ISO currency code
    altwr: Mapped[str | None] = mapped_column(String(3))  # Alternative key
    gdatu: Mapped[str | None] = mapped_column(String(8))  # Valid-from date
    ltext: Mapped[str] = mapped_column(String(40))  # Long text
    ktext: Mapped[str | None] = mapped_column(String(15))  # Short text
    currdec: Mapped[int] = mapped_column(default=2)  # Number of decimal places


class ExchangeRate(Base):
    """TCURR — Exchange rates."""

    __tablename__ = "tcurr"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kurst: Mapped[str] = mapped_column(String(4), primary_key=True)  # Exchange rate type (M/B/G)
    fcurr: Mapped[str] = mapped_column(String(5), primary_key=True)  # From currency
    tcurr: Mapped[str] = mapped_column(String(5), primary_key=True)  # To currency
    gdatu: Mapped[date] = mapped_column(primary_key=True)  # Valid-from date
    ukurs: Mapped[Decimal] = mapped_column(Numeric(13, 5))  # Exchange rate
    ffact: Mapped[int] = mapped_column(default=1)  # Ratio for 'from' currency
    tfact: Mapped[int] = mapped_column(default=1)  # Ratio for 'to' currency


class PostingPeriodControl(Base):
    """T001B — Permitted posting periods (open/close period control).

    SAP keys posting-period control by posting-period variant (here keyed by
    company code for simplicity) and account type. KOART '+' is the valid-for-all
    entry. Two period ranges (FRPE1/TOPE1 and FRPE2/TOPE2) support normal + special
    periods and a second, more restrictive range.
    """

    __tablename__ = "t001b"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code (posting period variant)
    koart: Mapped[str] = mapped_column(String(1), primary_key=True)  # Account type (+ A D K M S)
    konti_von: Mapped[str] = mapped_column(String(10), primary_key=True, default="")  # From account
    konti_bis: Mapped[str | None] = mapped_column(String(10))  # To account
    frpe1: Mapped[int] = mapped_column(default=1)  # From period 1
    frgj1: Mapped[int] = mapped_column(default=0)  # From year 1
    tope1: Mapped[int] = mapped_column(default=12)  # To period 1
    tagj1: Mapped[int] = mapped_column(default=9999)  # To year 1
    frpe2: Mapped[int] = mapped_column(default=13)  # From period 2 (special)
    frgj2: Mapped[int] = mapped_column(default=0)  # From year 2
    tope2: Mapped[int] = mapped_column(default=16)  # To period 2 (special)
    tagj2: Mapped[int] = mapped_column(default=9999)  # To year 2
