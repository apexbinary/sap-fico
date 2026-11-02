"""Administration — company setup.

Tables modelled here (SAP Business One names):
    OADM   Company details (local and system currency, company name)
    OCRN   Currencies
    ORTT   Exchange rates (local currency per unit of a foreign currency, per day)
    OFPR   Posting periods
    NNM1   Document numbering series per object type
    OVTG   Tax (VAT) groups
    OCTG   Payment terms

B1 table and field names are used throughout. B1 keys most master data by a
code (AcctCode, CardCode, ItemCode) and documents by an internal DocEntry
plus a visible DocNum from a numbering series.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

AMOUNT = Numeric(19, 6)  # B1 stores amounts with 6 decimals
RATE = Numeric(19, 6)


class Company(Base):
    """OADM — Company details (one row)."""

    __tablename__ = "oadm"

    code: Mapped[int] = mapped_column("Code", primary_key=True, default=1)
    company_name: Mapped[str] = mapped_column("CompnyName", String(100))  # Company name
    main_curncy: Mapped[str] = mapped_column("MainCurncy", String(3))  # Local currency
    sys_curncy: Mapped[str] = mapped_column("SysCurrncy", String(3))  # System currency
    country: Mapped[str | None] = mapped_column("Country", String(3))  # Country
    tax_id: Mapped[str | None] = mapped_column("TaxIdNum", String(32))  # Federal tax ID
    address: Mapped[str | None] = mapped_column("CompnyAddr", String(254))  # Address
    phone: Mapped[str | None] = mapped_column("Phone1", String(20))  # Telephone


class Currency(Base):
    """OCRN — Currency."""

    __tablename__ = "ocrn"

    curr_code: Mapped[str] = mapped_column("CurrCode", String(3), primary_key=True)
    curr_name: Mapped[str] = mapped_column("CurrName", String(20))
    iso: Mapped[str | None] = mapped_column("ISOCurrCod", String(3))
    decimals: Mapped[int] = mapped_column("Decimals", default=2)


class ExchangeRate(Base):
    """ORTT — Exchange rate of a foreign currency on a date (local currency per unit)."""

    __tablename__ = "ortt"

    rate_date: Mapped[date] = mapped_column("RateDate", primary_key=True)
    currency: Mapped[str] = mapped_column("Currency", String(3), primary_key=True)
    rate: Mapped[Decimal] = mapped_column("Rate", RATE)


class PostingPeriod(Base):
    """OFPR — Posting period (one per month); PeriodStat N unlocked, Y locked, C closing."""

    __tablename__ = "ofpr"

    abs_entry: Mapped[int] = mapped_column("AbsEntry", primary_key=True)
    code: Mapped[str] = mapped_column("Code", String(20), unique=True)  # e.g. 2026-11
    name: Mapped[str] = mapped_column("Name", String(20))
    f_ref_date: Mapped[date] = mapped_column("F_RefDate")  # Posting date from
    t_ref_date: Mapped[date] = mapped_column("T_RefDate")  # Posting date to
    category: Mapped[str] = mapped_column("Category", String(10))  # Period category (fiscal year)
    period_stat: Mapped[str] = mapped_column("PeriodStat", String(1), default="N")


class NumberingSeries(Base):
    """NNM1 — Numbering series of a document object type."""

    __tablename__ = "nnm1"

    object_code: Mapped[str] = mapped_column("ObjectCode", String(20), primary_key=True)  # e.g. 13 A/R invoice
    series: Mapped[int] = mapped_column("Series", primary_key=True)
    series_name: Mapped[str] = mapped_column("SeriesName", String(8))
    initial_num: Mapped[int] = mapped_column("InitialNum")
    next_number: Mapped[int] = mapped_column("NextNumber")
    last_num: Mapped[int | None] = mapped_column("LastNum")
    is_default: Mapped[bool] = mapped_column("IsDefault", default=True)


class TaxGroup(Base):
    """OVTG — Tax group (VAT): output tax for sales, input tax for purchasing."""

    __tablename__ = "ovtg"

    code: Mapped[str] = mapped_column("Code", String(8), primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(30))
    category: Mapped[str] = mapped_column("Category", String(1))  # O output (sales), I input (purchasing)
    rate: Mapped[Decimal] = mapped_column("Rate", Numeric(19, 6))  # Percent
    account: Mapped[str] = mapped_column("Account", String(15))  # Tax G/L account
    inactive: Mapped[bool] = mapped_column("Inactive", default=False)


class PaymentTerms(Base):
    """OCTG — Payment terms: due date = document date + extra months + extra days."""

    __tablename__ = "octg"

    group_num: Mapped[int] = mapped_column("GroupNum", primary_key=True)
    pymnt_group: Mapped[str] = mapped_column("PymntGroup", String(100))  # Name
    extra_month: Mapped[int] = mapped_column("ExtraMonth", default=0)
    extra_days: Mapped[int] = mapped_column("ExtraDays", default=0)
    discount_pct: Mapped[Decimal] = mapped_column("VolumDscnt", Numeric(19, 6), default=Decimal("0"))  # Total discount %
