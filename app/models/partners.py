"""Sub-ledger master data — Accounts Receivable (customers) and Payable (vendors).

Tables modelled here:
    KNA1   Customer master — general (client) data
    KNB1   Customer master — company code data
    LFA1   Vendor master   — general (client) data
    LFB1   Vendor master   — company code data

Open items are not stored in separate BSID/BSIK index tables here; they are
derived from BSEG line items where the account type is D/K and the clearing
document (AUGBL) is empty. This keeps a single owner for every posted fact.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.organizational import MANDT


class Customer(Base):
    """KNA1 — Customer master, general data (client level)."""

    __tablename__ = "kna1"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kunnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Customer number
    ktokd: Mapped[str] = mapped_column(String(4))  # Customer account group
    name1: Mapped[str] = mapped_column(String(35))  # Name 1
    name2: Mapped[str | None] = mapped_column(String(35))  # Name 2
    sortl: Mapped[str | None] = mapped_column(String(10))  # Sort field
    land1: Mapped[str] = mapped_column(String(3))  # Country key
    ort01: Mapped[str | None] = mapped_column(String(35))  # City
    pstlz: Mapped[str | None] = mapped_column(String(10))  # Postal code
    regio: Mapped[str | None] = mapped_column(String(3))  # Region (state/province)
    stras: Mapped[str | None] = mapped_column(String(35))  # Street and house number
    telf1: Mapped[str | None] = mapped_column(String(16))  # Telephone 1
    spras: Mapped[str] = mapped_column(String(1), default="E")  # Language
    anred: Mapped[str | None] = mapped_column(String(15))  # Title
    adrnr: Mapped[str | None] = mapped_column(String(10))  # Address number
    stcd1: Mapped[str | None] = mapped_column(String(16))  # Tax number 1
    stcd2: Mapped[str | None] = mapped_column(String(11))  # Tax number 2
    stceg: Mapped[str | None] = mapped_column(String(20))  # VAT registration number
    brsch: Mapped[str | None] = mapped_column(String(4))  # Industry key
    kukla: Mapped[str | None] = mapped_column(String(2))  # Customer classification
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on
    ernam: Mapped[str | None] = mapped_column(String(12))  # Created by
    sperr: Mapped[bool] = mapped_column(default=False)  # Central posting block
    loevm: Mapped[bool] = mapped_column(default=False)  # Central deletion flag


class CustomerCompanyCode(Base):
    """KNB1 — Customer master, company code data."""

    __tablename__ = "knb1"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kunnr"], ["kna1.mandt", "kna1.kunnr"]),
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kunnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Customer number
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    akont: Mapped[str] = mapped_column(String(10))  # Reconciliation account in G/L
    zuawa: Mapped[str | None] = mapped_column(String(3))  # Sort key
    zterm: Mapped[str | None] = mapped_column(String(4))  # Terms of payment key
    zwels: Mapped[str | None] = mapped_column(String(10))  # List of payment methods
    zahls: Mapped[str | None] = mapped_column(String(1))  # Payment block
    busab: Mapped[str | None] = mapped_column(String(2))  # Accounting clerk
    fdgrv: Mapped[str | None] = mapped_column(String(10))  # Cash management group
    knrzb: Mapped[str | None] = mapped_column(String(10))  # Alternative payer
    togru: Mapped[str | None] = mapped_column(String(4))  # Tolerance group
    vzskz: Mapped[str | None] = mapped_column(String(2))  # Interest indicator
    altkn: Mapped[str | None] = mapped_column(String(10))  # Previous account number
    mahna: Mapped[str | None] = mapped_column(String(4))  # Dunning procedure
    mgruo: Mapped[str | None] = mapped_column(String(2))  # Dunning group
    eikto: Mapped[str | None] = mapped_column(String(12))  # Our account number at the customer
    xverr: Mapped[bool] = mapped_column(default=False)  # Clearing between customer and vendor
    sperr: Mapped[bool] = mapped_column(default=False)  # Posting block for this company code
    loevm: Mapped[bool] = mapped_column(default=False)  # Deletion flag for this company code
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on


class Vendor(Base):
    """LFA1 — Vendor master, general data (client level)."""

    __tablename__ = "lfa1"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Vendor number
    ktokk: Mapped[str] = mapped_column(String(4))  # Vendor account group
    name1: Mapped[str] = mapped_column(String(35))  # Name 1
    name2: Mapped[str | None] = mapped_column(String(35))  # Name 2
    sortl: Mapped[str | None] = mapped_column(String(10))  # Sort field
    land1: Mapped[str] = mapped_column(String(3))  # Country key
    ort01: Mapped[str | None] = mapped_column(String(35))  # City
    pstlz: Mapped[str | None] = mapped_column(String(10))  # Postal code
    regio: Mapped[str | None] = mapped_column(String(3))  # Region
    stras: Mapped[str | None] = mapped_column(String(35))  # Street
    telf1: Mapped[str | None] = mapped_column(String(16))  # Telephone
    spras: Mapped[str] = mapped_column(String(1), default="E")  # Language
    adrnr: Mapped[str | None] = mapped_column(String(10))  # Address number
    stcd1: Mapped[str | None] = mapped_column(String(16))  # Tax number 1
    stcd2: Mapped[str | None] = mapped_column(String(11))  # Tax number 2
    stceg: Mapped[str | None] = mapped_column(String(20))  # VAT registration number
    brsch: Mapped[str | None] = mapped_column(String(4))  # Industry key
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on
    ernam: Mapped[str | None] = mapped_column(String(12))  # Created by
    sperr: Mapped[bool] = mapped_column(default=False)  # Central posting block
    sperm: Mapped[bool] = mapped_column(default=False)  # Central purchasing block
    loevm: Mapped[bool] = mapped_column(default=False)  # Central deletion flag


class VendorCompanyCode(Base):
    """LFB1 — Vendor master, company code data."""

    __tablename__ = "lfb1"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "lifnr"], ["lfa1.mandt", "lfa1.lifnr"]),
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Vendor number
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    akont: Mapped[str] = mapped_column(String(10))  # Reconciliation account in G/L
    zuawa: Mapped[str | None] = mapped_column(String(3))  # Sort key
    zterm: Mapped[str | None] = mapped_column(String(4))  # Terms of payment key
    zwels: Mapped[str | None] = mapped_column(String(10))  # List of payment methods
    zahls: Mapped[str | None] = mapped_column(String(1))  # Payment block
    busab: Mapped[str | None] = mapped_column(String(2))  # Accounting clerk
    fdgrv: Mapped[str | None] = mapped_column(String(10))  # Cash management group
    lnrzb: Mapped[str | None] = mapped_column(String(10))  # Alternative payee
    togru: Mapped[str | None] = mapped_column(String(4))  # Tolerance group
    reprf: Mapped[bool] = mapped_column(default=False)  # Check for double invoices
    zgrup: Mapped[str | None] = mapped_column(String(2))  # Payment grouping key
    xpore: Mapped[bool] = mapped_column(default=False)  # Pay all items separately
    sperr: Mapped[bool] = mapped_column(default=False)  # Posting block for this company code
    loevm: Mapped[bool] = mapped_column(default=False)  # Deletion flag for this company code
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on
    mindk: Mapped[str | None] = mapped_column(String(2))  # Memo (minority indicator)
    qland: Mapped[str | None] = mapped_column(String(3))  # Withholding tax country
