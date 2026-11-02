"""Accounting documents — the core FI posting structures.

Tables modelled here:
    T003   Document types               (+ T003T text folded into LTEXT)
    TBSL   Posting keys                 (+ TBSLT text folded into LTEXT)
    NRIV   Number range intervals
    BKPF   Accounting document header
    BSEG   Accounting document segment (line items)
    GLT0   G/L account transaction figures (period totals)
    BKDF   Recurring entry run schedule (for recurring originals, BKPF-BSTAT 'D')

A posted document is BKPF (one header) + 2..n BSEG rows whose debits equal
credits in every currency. The posting key (BSCHL) on each line decides the
account type and the debit/credit sign (SHKZG), exactly as in SAP.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.organizational import MANDT

# SAP amount domain WERTV8: 13 integer + 2 decimal digits.
AMOUNT = Numeric(23, 2)


class DocumentType(Base):
    """T003 — Document types (+ T003T description in ltext)."""

    __tablename__ = "t003"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    blart: Mapped[str] = mapped_column(String(2), primary_key=True)  # Document type
    ltext: Mapped[str] = mapped_column(String(50))  # Document type description
    numkr: Mapped[str] = mapped_column(String(2))  # Number range
    xsach: Mapped[bool] = mapped_column(default=True)  # G/L account posting allowed
    xkund: Mapped[bool] = mapped_column(default=False)  # Customer posting allowed
    xlief: Mapped[bool] = mapped_column(default=False)  # Vendor posting allowed
    xanlg: Mapped[bool] = mapped_column(default=False)  # Asset posting allowed
    xmate: Mapped[bool] = mapped_column(default=False)  # Material posting allowed
    xnetb: Mapped[bool] = mapped_column(default=False)  # Net document type
    stbla: Mapped[str | None] = mapped_column(String(2))  # Reverse document type
    brgru: Mapped[str | None] = mapped_column(String(4))  # Authorization group
    xkdft: Mapped[bool] = mapped_column(default=False)  # Account type check (cust/vend)
    numkr_ext: Mapped[bool] = mapped_column(default=False)  # External number assignment
    xmkey: Mapped[str | None] = mapped_column(String(1))  # Default value: due date / reference


class PostingKey(Base):
    """TBSL — Posting keys (+ TBSLT description in ltext)."""

    __tablename__ = "tbsl"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bschl: Mapped[str] = mapped_column(String(2), primary_key=True)  # Posting key
    ltext: Mapped[str] = mapped_column(String(30))  # Posting key name
    shkzg: Mapped[str] = mapped_column(String(1))  # Debit/credit indicator S(debit)/H(credit)
    koart: Mapped[str] = mapped_column(String(1))  # Account type S/D/K/A/M
    xumsw: Mapped[bool] = mapped_column(default=False)  # Sales-related (update sales figures)
    xsonu: Mapped[bool] = mapped_column(default=False)  # Special G/L indicator required
    xzahl: Mapped[bool] = mapped_column(default=False)  # Payment transaction
    xnegp: Mapped[bool] = mapped_column(default=False)  # Negative posting allowed
    xskrl: Mapped[bool] = mapped_column(default=False)  # Posting key for reversal/reset
    stbsl: Mapped[str | None] = mapped_column(String(2))  # Posting key for reversal
    bustw: Mapped[str | None] = mapped_column(String(4))  # Posting string (internal)
    fdgrp: Mapped[str | None] = mapped_column(String(10))  # Default planning group


class NumberRange(Base):
    """NRIV — Number range intervals (document numbering per company code/year)."""

    __tablename__ = "nriv"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    object: Mapped[str] = mapped_column(String(10), primary_key=True, default="RF_BELEG")
    subobject: Mapped[str] = mapped_column(String(6), primary_key=True)  # Company code (BUKRS)
    nrrangenr: Mapped[str] = mapped_column(String(2), primary_key=True)  # Number range number
    toyear: Mapped[int] = mapped_column(primary_key=True)  # Fiscal year (0 = year-independent)
    fromnumber: Mapped[str] = mapped_column(String(20))  # From number
    tonumber: Mapped[str] = mapped_column(String(20))  # To number
    nrlevel: Mapped[str] = mapped_column(String(20), default="0")  # Current number (last used)
    externind: Mapped[bool] = mapped_column(default=False)  # External number assignment


class AccountingDocumentHeader(Base):
    """BKPF — Accounting document header."""

    __tablename__ = "bkpf"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    belnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Document number
    gjahr: Mapped[int] = mapped_column(primary_key=True)  # Fiscal year

    blart: Mapped[str] = mapped_column(String(2))  # Document type
    bldat: Mapped[date] = mapped_column()  # Document date
    budat: Mapped[date] = mapped_column()  # Posting date
    monat: Mapped[int] = mapped_column()  # Posting period (fiscal period)
    cpudt: Mapped[date] = mapped_column(default=date.today)  # Entry (CPU) date
    cputm: Mapped[datetime] = mapped_column(default=datetime.utcnow)  # Entry time
    aedat: Mapped[date | None] = mapped_column()  # Last change date
    usnam: Mapped[str] = mapped_column(String(12), default="SYSTEM")  # User name
    tcode: Mapped[str | None] = mapped_column(String(20))  # Transaction code
    bvorg: Mapped[str | None] = mapped_column(String(16))  # Cross-company code number
    xblnr: Mapped[str | None] = mapped_column(String(16))  # Reference document number
    dbblg: Mapped[str | None] = mapped_column(String(10))  # Recurring entry document
    stblg: Mapped[str | None] = mapped_column(String(10))  # Reverse document number
    stjah: Mapped[int | None] = mapped_column()  # Reverse document fiscal year
    bktxt: Mapped[str | None] = mapped_column(String(25))  # Document header text
    waers: Mapped[str] = mapped_column(String(5))  # Document currency
    kursf: Mapped[Decimal] = mapped_column(Numeric(13, 5), default=Decimal("1"))  # Exchange rate
    kzwrs: Mapped[str | None] = mapped_column(String(5))  # Currency key for group figures
    hwaer: Mapped[str | None] = mapped_column(String(5))  # Local currency
    hwae2: Mapped[str | None] = mapped_column(String(5))  # Second local currency
    hwae3: Mapped[str | None] = mapped_column(String(5))  # Third local currency
    bstat: Mapped[str] = mapped_column(String(1), default=" ")  # Document status (' '=normal, 'V'=parked)
    xnetb: Mapped[bool] = mapped_column(default=False)  # Net posting
    wwert: Mapped[date | None] = mapped_column()  # Translation date
    awtyp: Mapped[str | None] = mapped_column(String(5))  # Reference transaction (BKPF/RMRP...)
    awkey: Mapped[str | None] = mapped_column(String(20))  # Reference key
    glvor: Mapped[str | None] = mapped_column(String(4))  # Business transaction
    stgrd: Mapped[str | None] = mapped_column(String(2))  # Reversal reason
    ppnam: Mapped[str | None] = mapped_column(String(12))  # Parked by
    brgru: Mapped[str | None] = mapped_column(String(4))  # Authorization group
    kokrs: Mapped[str | None] = mapped_column(String(4))  # Controlling area

    items: Mapped[list["AccountingDocumentItem"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
        order_by="AccountingDocumentItem.buzei",
    )


class AccountingDocumentItem(Base):
    """BSEG — Accounting document segment (line item)."""

    __tablename__ = "bseg"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mandt", "bukrs", "belnr", "gjahr"],
            ["bkpf.mandt", "bkpf.bukrs", "bkpf.belnr", "bkpf.gjahr"],
        ),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    belnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Document number
    gjahr: Mapped[int] = mapped_column(primary_key=True)  # Fiscal year
    buzei: Mapped[int] = mapped_column(primary_key=True)  # Line item number (3-digit)

    # --- posting control ---
    buzid: Mapped[str | None] = mapped_column(String(1))  # Line item identifier (T=tax, ...)
    bschl: Mapped[str] = mapped_column(String(2))  # Posting key
    koart: Mapped[str] = mapped_column(String(1))  # Account type S/D/K/A/M
    shkzg: Mapped[str] = mapped_column(String(1))  # Debit/credit indicator S/H
    umskz: Mapped[str | None] = mapped_column(String(1))  # Special G/L indicator
    umsks: Mapped[str | None] = mapped_column(String(1))  # Special G/L transaction type
    bstat: Mapped[str | None] = mapped_column(String(1))  # Document status

    # --- account assignment ---
    hkont: Mapped[str] = mapped_column(String(10))  # G/L account (reconciliation acct for subledgers)
    saknr: Mapped[str | None] = mapped_column(String(10))  # G/L account number (as entered)
    kunnr: Mapped[str | None] = mapped_column(String(10))  # Customer number
    lifnr: Mapped[str | None] = mapped_column(String(10))  # Vendor number
    filkd: Mapped[str | None] = mapped_column(String(10))  # Account number of branch
    gsber: Mapped[str | None] = mapped_column(String(4))  # Business area
    pargb: Mapped[str | None] = mapped_column(String(4))  # Trading partner business area
    vbund: Mapped[str | None] = mapped_column(String(6))  # Trading partner (company)

    # --- amounts ---
    wrbtr: Mapped[Decimal] = mapped_column(AMOUNT)  # Amount in document currency
    dmbtr: Mapped[Decimal] = mapped_column(AMOUNT)  # Amount in local currency
    dmbe2: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Amount in second local currency
    dmbe3: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Amount in third local currency
    pswbt: Mapped[Decimal | None] = mapped_column(AMOUNT)  # G/L amount (transaction currency)
    pswsl: Mapped[str | None] = mapped_column(String(5))  # Update currency for G/L figures

    # --- tax ---
    mwskz: Mapped[str | None] = mapped_column(String(2))  # Tax code
    ktosl: Mapped[str | None] = mapped_column(String(3))  # Transaction key (account determination)
    hwbas: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Tax base amount (local currency)
    fwbas: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Tax base amount (document currency)
    wmwst: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Tax amount (document currency)
    mwsts: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Tax amount (local currency)
    txjcd: Mapped[str | None] = mapped_column(String(15))  # Tax jurisdiction code

    # --- open item / payment ---
    augdt: Mapped[date | None] = mapped_column()  # Clearing date
    augbl: Mapped[str | None] = mapped_column(String(10))  # Clearing document number
    auggj: Mapped[int | None] = mapped_column()  # Fiscal year of clearing document
    augcp: Mapped[date | None] = mapped_column()  # Clearing entry date
    zuonr: Mapped[str | None] = mapped_column(String(18))  # Assignment number
    sgtxt: Mapped[str | None] = mapped_column(String(50))  # Item text
    zfbdt: Mapped[date | None] = mapped_column()  # Baseline date for due date
    zterm: Mapped[str | None] = mapped_column(String(4))  # Terms of payment key
    zbd1t: Mapped[int | None] = mapped_column()  # Cash discount days 1
    zbd1p: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))  # Cash discount percentage 1
    zbd2t: Mapped[int | None] = mapped_column()  # Cash discount days 2
    zbd2p: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))  # Cash discount percentage 2
    zbd3t: Mapped[int | None] = mapped_column()  # Net payment terms period
    skfbt: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Amount eligible for cash discount
    sknto: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Cash discount amount (local)
    wskto: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Cash discount amount (document)
    zlsch: Mapped[str | None] = mapped_column(String(1))  # Payment method
    zlspr: Mapped[str | None] = mapped_column(String(1))  # Payment block
    manst: Mapped[int | None] = mapped_column()  # Dunning level
    madat: Mapped[date | None] = mapped_column()  # Last dunned on
    mansp: Mapped[str | None] = mapped_column(String(1))  # Dunning block
    rstgr: Mapped[str | None] = mapped_column(String(3))  # Reason code for payment differences
    rebzg: Mapped[str | None] = mapped_column(String(10))  # Invoice ref (document number)
    rebzj: Mapped[int | None] = mapped_column()  # Invoice ref fiscal year
    rebzz: Mapped[int | None] = mapped_column()  # Invoice ref line item
    valut: Mapped[date | None] = mapped_column()  # Value date
    xopvw: Mapped[bool] = mapped_column(default=False)  # Open item management indicator
    xcpdd: Mapped[bool] = mapped_column(default=False)  # Address/bank data in document

    # --- CO / cost assignment ---
    kostl: Mapped[str | None] = mapped_column(String(10))  # Cost center
    aufnr: Mapped[str | None] = mapped_column(String(12))  # Order number / internal order
    prctr: Mapped[str | None] = mapped_column(String(10))  # Profit center
    projk: Mapped[str | None] = mapped_column(String(24))  # WBS element
    kokrs: Mapped[str | None] = mapped_column(String(4))  # Controlling area
    paobjnr: Mapped[int | None] = mapped_column()  # Profitability segment number
    func_area: Mapped[str | None] = mapped_column(String(16))  # Functional area

    # --- asset accounting ---
    anln1: Mapped[str | None] = mapped_column(String(12))  # Asset main number
    anln2: Mapped[str | None] = mapped_column(String(4))  # Asset sub-number
    anbwa: Mapped[str | None] = mapped_column(String(3))  # Asset transaction type
    bzdat: Mapped[date | None] = mapped_column()  # Asset value date

    # --- logistics / references ---
    matnr: Mapped[str | None] = mapped_column(String(18))  # Material number
    werks: Mapped[str | None] = mapped_column(String(4))  # Plant
    menge: Mapped[Decimal | None] = mapped_column(Numeric(13, 3))  # Quantity
    meins: Mapped[str | None] = mapped_column(String(3))  # Base unit of measure
    vbel2: Mapped[str | None] = mapped_column(String(10))  # Sales document
    posn2: Mapped[int | None] = mapped_column()  # Sales document item
    kdauf: Mapped[str | None] = mapped_column(String(10))  # Sales order number
    xref1: Mapped[str | None] = mapped_column(String(12))  # Reference key 1
    xref2: Mapped[str | None] = mapped_column(String(12))  # Reference key 2
    xref3: Mapped[str | None] = mapped_column(String(20))  # Reference key 3
    xnegp: Mapped[bool] = mapped_column(default=False)  # Negative posting

    header: Mapped["AccountingDocumentHeader"] = relationship(back_populates="items")


class GLAccountTotals(Base):
    """GLT0 — G/L account transaction figures (balances by period).

    One row per company code / fiscal year / business area / G/L account, holding
    the opening balance (HSLVT) and the debit/credit movements for each of the 16
    posting periods. SAP stores one debit and one credit bucket per period; here
    the net movement per period is kept in ``tsl01``..``tsl16`` and the debit/credit
    split in the ``dr_*`` / ``cr_*`` helper columns is derived by the posting engine.
    """

    __tablename__ = "glt0"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    rrcty: Mapped[str] = mapped_column(String(1), primary_key=True, default="0")  # Record type (0=actual)
    rldnr: Mapped[str] = mapped_column(String(2), primary_key=True, default="00")  # Ledger
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    gjahr: Mapped[int] = mapped_column(primary_key=True)  # Fiscal year
    racct: Mapped[str] = mapped_column(String(10), primary_key=True)  # G/L account (HKONT)
    rbusa: Mapped[str] = mapped_column(String(4), primary_key=True, default="")  # Business area
    drcrk: Mapped[str] = mapped_column(String(1), primary_key=True, default=" ")  # Debit/credit bucket
    rtcur: Mapped[str] = mapped_column(String(5))  # Currency key

    hslvt: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Balance carried forward (local)
    # Period movements in local currency, periods 1..16 (12 normal + 4 special)
    tsl01: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl02: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl03: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl04: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl05: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl06: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl07: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl08: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl09: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl10: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl11: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl12: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl13: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl14: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl15: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    tsl16: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))


class RecurringEntrySchedule(Base):
    """BKDF — Run schedule of a recurring entry original document (BSTAT 'D')."""

    __tablename__ = "bkdf"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mandt", "bukrs", "belnr", "gjahr"],
            ["bkpf.mandt", "bkpf.bukrs", "bkpf.belnr", "bkpf.gjahr"],
        ),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    belnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Recurring entry document number
    gjahr: Mapped[int] = mapped_column(primary_key=True)  # Fiscal year
    dbbdt: Mapped[date] = mapped_column()  # First run date
    dbedt: Mapped[date] = mapped_column()  # Last run date
    dbmon: Mapped[int] = mapped_column(default=1)  # Interval in months
    dbtag: Mapped[int] = mapped_column()  # Run day of the month (clamped to month end)
    dbatr: Mapped[date | None] = mapped_column()  # Next run date (None = schedule finished)
