"""Asset Accounting (FI-AA).

Tables modelled here:
    ANKA   Asset classes
    T093   Real depreciation areas
    T095   Asset balance-sheet / account determination
    TABW   Asset transaction types
    ANLA   Asset master record (segment)
    ANLB   Asset depreciation terms (per depreciation area)
    ANLZ   Time-dependent asset allocations (cost center etc.)
    ANLC   Asset value fields (per fiscal year + depreciation area)
    ANEK   Asset posting document header
    ANEP   Asset line items (transactions)
    ANLP   Posted depreciation (periodic)

Acquisitions and retirements flow through the FI posting engine (account type
'A'); the engine resolves the asset's balance-sheet account from T095 using the
asset class account-determination key and writes the ANEP transaction + updates
ANLC. Depreciation is posted by the depreciation run service.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.documents import AMOUNT
from app.models.organizational import MANDT


class AssetClass(Base):
    """ANKA — Asset classes."""

    __tablename__ = "anka"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    anlkl: Mapped[str] = mapped_column(String(8), primary_key=True)  # Asset class
    txk50: Mapped[str] = mapped_column(String(50))  # Description
    ktogr: Mapped[str] = mapped_column(String(8))  # Account determination key
    num_range: Mapped[str | None] = mapped_column(String(2))  # Number range
    xextnum: Mapped[bool] = mapped_column(default=False)  # External number assignment
    xanlgr: Mapped[bool] = mapped_column(default=False)  # Asset under construction
    lvorm: Mapped[bool] = mapped_column(default=False)  # Deletion flag


class DepreciationArea(Base):
    """T093 — Real depreciation areas."""

    __tablename__ = "t093"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    afaber: Mapped[str] = mapped_column(String(2), primary_key=True)  # Depreciation area
    afbe_txt: Mapped[str] = mapped_column(String(50))  # Description
    buhbkt: Mapped[str] = mapped_column(String(1), default="1")  # Posts to G/L (1=realtime)
    wertu: Mapped[bool] = mapped_column(default=True)  # Value maintenance
    xreal: Mapped[bool] = mapped_column(default=True)  # Real depreciation area


class AssetAccountDetermination(Base):
    """T095 — Balance sheet / depreciation account assignment."""

    __tablename__ = "t095"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "afaber"], ["t093.mandt", "t093.afaber"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    ktopl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Chart of accounts
    ktogr: Mapped[str] = mapped_column(String(8), primary_key=True)  # Account determination
    afaber: Mapped[str] = mapped_column(String(2), primary_key=True)  # Depreciation area
    ktansw: Mapped[str] = mapped_column(String(10))  # Acquisition/production cost (APC) account
    ktabg_dep: Mapped[str] = mapped_column(String(10))  # Accumulated depreciation account
    ktaufw_dep: Mapped[str] = mapped_column(String(10))  # Depreciation expense account
    ktvabg: Mapped[str | None] = mapped_column(String(10))  # Clearing account for retirement
    ktgewv: Mapped[str | None] = mapped_column(String(10))  # Gain on retirement
    ktverl: Mapped[str | None] = mapped_column(String(10))  # Loss on retirement


class AssetTransactionType(Base):
    """TABW — Asset transaction types."""

    __tablename__ = "tabw"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bwasl: Mapped[str] = mapped_column(String(3), primary_key=True)  # Transaction type
    bwatxt: Mapped[str] = mapped_column(String(50))  # Description
    # Transaction type group: 10=acquisition, 20=retirement, 30=transfer, 50=dep.
    bwagrp: Mapped[str] = mapped_column(String(2))
    xanz: Mapped[str] = mapped_column(String(1), default="+")  # Debit/credit effect on asset (+/-)
    xafbtr: Mapped[bool] = mapped_column(default=False)  # Posts depreciation


class Asset(Base):
    """ANLA — Asset master record."""

    __tablename__ = "anla"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
        ForeignKeyConstraint(["mandt", "anlkl"], ["anka.mandt", "anka.anlkl"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    anln1: Mapped[str] = mapped_column(String(12), primary_key=True)  # Main asset number
    anln2: Mapped[str] = mapped_column(String(4), primary_key=True, default="0000")  # Sub-number
    anlkl: Mapped[str] = mapped_column(String(8))  # Asset class
    txt50: Mapped[str] = mapped_column(String(50))  # Asset description
    txa50: Mapped[str | None] = mapped_column(String(50))  # Additional description
    sernr: Mapped[str | None] = mapped_column(String(18))  # Serial number
    invnr: Mapped[str | None] = mapped_column(String(25))  # Inventory number
    menge: Mapped[Decimal | None] = mapped_column(Numeric(13, 3))  # Quantity
    meins: Mapped[str | None] = mapped_column(String(3))  # Unit of measure
    aktiv: Mapped[date | None] = mapped_column()  # Capitalization date
    zugdt: Mapped[date | None] = mapped_column()  # Asset value date of first acquisition
    deakt: Mapped[date | None] = mapped_column()  # Deactivation (retirement) date
    ernam: Mapped[str | None] = mapped_column(String(12))  # Created by
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on
    lifnr: Mapped[str | None] = mapped_column(String(10))  # Vendor
    herst: Mapped[str | None] = mapped_column(String(30))  # Manufacturer
    land1: Mapped[str | None] = mapped_column(String(3))  # Country of origin
    eaufn: Mapped[str | None] = mapped_column(String(12))  # Investment order
    lvorm: Mapped[bool] = mapped_column(default=False)  # Deletion flag
    xactive: Mapped[bool] = mapped_column(default=True)  # Active (not retired)

    terms: Mapped[list["AssetDepreciationTerms"]] = relationship(
        primaryjoin=(
            "and_(Asset.mandt==foreign(AssetDepreciationTerms.mandt), "
            "Asset.bukrs==foreign(AssetDepreciationTerms.bukrs), "
            "Asset.anln1==foreign(AssetDepreciationTerms.anln1), "
            "Asset.anln2==foreign(AssetDepreciationTerms.anln2))"
        ),
        viewonly=True,
    )


class AssetDepreciationTerms(Base):
    """ANLB — Depreciation terms per depreciation area."""

    __tablename__ = "anlb"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mandt", "bukrs", "anln1", "anln2"],
            ["anla.mandt", "anla.bukrs", "anla.anln1", "anla.anln2"],
        ),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    anln1: Mapped[str] = mapped_column(String(12), primary_key=True)  # Asset
    anln2: Mapped[str] = mapped_column(String(4), primary_key=True)  # Sub-number
    afabe: Mapped[str] = mapped_column(String(2), primary_key=True)  # Depreciation area
    afasl: Mapped[str] = mapped_column(String(4), default="LINR")  # Depreciation key
    ndjar: Mapped[int] = mapped_column(default=0)  # Planned useful life (years)
    ndper: Mapped[int] = mapped_column(default=0)  # Planned useful life (periods)
    afabg: Mapped[date | None] = mapped_column()  # Depreciation start date
    schrw: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Scrap value
    schrw_proz: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))  # Scrap %


class AssetAllocation(Base):
    """ANLZ — Time-dependent asset allocations."""

    __tablename__ = "anlz"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mandt", "bukrs", "anln1", "anln2"],
            ["anla.mandt", "anla.bukrs", "anla.anln1", "anla.anln2"],
        ),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)
    anln1: Mapped[str] = mapped_column(String(12), primary_key=True)
    anln2: Mapped[str] = mapped_column(String(4), primary_key=True)
    adatu: Mapped[date] = mapped_column(primary_key=True)  # Valid-from date
    bdatu: Mapped[date] = mapped_column()  # Valid-to date
    kostl: Mapped[str | None] = mapped_column(String(10))  # Cost center
    werks: Mapped[str | None] = mapped_column(String(4))  # Plant
    gsber: Mapped[str | None] = mapped_column(String(4))  # Business area
    prctr: Mapped[str | None] = mapped_column(String(10))  # Profit center
    raumn: Mapped[str | None] = mapped_column(String(8))  # Room
    stort: Mapped[str | None] = mapped_column(String(10))  # Location


class AssetValues(Base):
    """ANLC — Asset value fields (per fiscal year + depreciation area)."""

    __tablename__ = "anlc"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mandt", "bukrs", "anln1", "anln2"],
            ["anla.mandt", "anla.bukrs", "anla.anln1", "anla.anln2"],
        ),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)
    anln1: Mapped[str] = mapped_column(String(12), primary_key=True)
    anln2: Mapped[str] = mapped_column(String(4), primary_key=True)
    gjahr: Mapped[int] = mapped_column(primary_key=True)  # Fiscal year
    afabe: Mapped[str] = mapped_column(String(2), primary_key=True)  # Depreciation area
    kansw: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Cumulative APC (start of year)
    answl: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Acquisitions this year
    abgan: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Retirements this year
    knafa: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Accum. ord. depreciation (start)
    nafag: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Ordinary depreciation posted this year
    nafav: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Proportional dep. on retirement


class AssetDocumentHeader(Base):
    """ANEK — Asset posting document header."""

    __tablename__ = "anek"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)
    anln1: Mapped[str] = mapped_column(String(12), primary_key=True)
    anln2: Mapped[str] = mapped_column(String(4), primary_key=True)
    gjahr: Mapped[int] = mapped_column(primary_key=True)
    lnran: Mapped[int] = mapped_column(primary_key=True)  # Sequence number
    belnr: Mapped[str | None] = mapped_column(String(10))  # FI document number
    budat: Mapped[date] = mapped_column()  # Posting date
    bldat: Mapped[date | None] = mapped_column()  # Document date
    bzdat: Mapped[date | None] = mapped_column()  # Asset value date
    xblnr: Mapped[str | None] = mapped_column(String(16))  # Reference
    bktxt: Mapped[str | None] = mapped_column(String(50))  # Text


class AssetLineItem(Base):
    """ANEP — Asset line items (transactions)."""

    __tablename__ = "anep"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)
    anln1: Mapped[str] = mapped_column(String(12), primary_key=True)
    anln2: Mapped[str] = mapped_column(String(4), primary_key=True)
    gjahr: Mapped[int] = mapped_column(primary_key=True)
    lnran: Mapped[int] = mapped_column(primary_key=True)  # Line item sequence
    afabe: Mapped[str] = mapped_column(String(2), primary_key=True)  # Depreciation area
    bwasl: Mapped[str] = mapped_column(String(3))  # Transaction type
    anbtr: Mapped[Decimal] = mapped_column(AMOUNT)  # Amount posted
    lnsan: Mapped[int | None] = mapped_column()  # Related acquisition line
    belnr: Mapped[str | None] = mapped_column(String(10))  # FI document
    buzei: Mapped[int | None] = mapped_column()  # FI line item
    budat: Mapped[date] = mapped_column()  # Posting date
    bzdat: Mapped[date | None] = mapped_column()  # Asset value date
    xawbt: Mapped[str | None] = mapped_column(String(1))  # Proportional values flag


class DepreciationPosting(Base):
    """ANLP — Posted depreciation (periodic)."""

    __tablename__ = "anlp"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)
    gjahr: Mapped[int] = mapped_column(primary_key=True)
    peraf: Mapped[int] = mapped_column(primary_key=True)  # Period posted
    anln1: Mapped[str] = mapped_column(String(12), primary_key=True)
    anln2: Mapped[str] = mapped_column(String(4), primary_key=True)
    afbnr: Mapped[str] = mapped_column(String(5), primary_key=True)  # Depreciation run number
    afabe: Mapped[str] = mapped_column(String(2), primary_key=True)
    nafaz: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Ordinary depreciation
    belnr: Mapped[str | None] = mapped_column(String(10))  # FI document
    xbuchen: Mapped[bool] = mapped_column(default=True)  # Posted
