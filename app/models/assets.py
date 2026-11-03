"""Fixed assets (not B1-verified: B1 keeps assets as items of type F with depreciation areas; these
tables keep the same information in a compact form).

    OACS   Asset classes: G/L accounts, depreciation method (SL straight line, WD written-down value),
           useful life in months / WDV rate
    OFAS   Fixed assets: class, capitalization date and value, salvage value, status
    FAS1   Asset transactions: capitalization, depreciation (per month), retirement — with their
           journal entries
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

AMOUNT = Numeric(19, 6)


class AssetClass(Base):
    """OACS — Asset class."""

    __tablename__ = "oacs"

    code: Mapped[str] = mapped_column("Code", String(8), primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(50))
    asset_acct: Mapped[str] = mapped_column("AssetAcct", String(15), ForeignKey("oact.AcctCode"))  # cost
    acc_dep_acct: Mapped[str] = mapped_column("AccDepAcct", String(15), ForeignKey("oact.AcctCode"))  # accumulated depreciation
    dep_acct: Mapped[str] = mapped_column("DepAcct", String(15), ForeignKey("oact.AcctCode"))  # depreciation expense
    retire_acct: Mapped[str] = mapped_column("RetireAcct", String(15), ForeignKey("oact.AcctCode"))  # gain / loss on retirement
    method: Mapped[str] = mapped_column("Method", String(2), default="SL")  # SL straight line, WD written-down value
    useful_life: Mapped[int | None] = mapped_column("UsefulLife", Integer)  # months (SL)
    wdv_rate: Mapped[Decimal | None] = mapped_column("WDVRate", AMOUNT)  # % per year (WD)


class FixedAsset(Base):
    """OFAS — Fixed asset."""

    __tablename__ = "ofas"

    asset_code: Mapped[str] = mapped_column("AssetCode", String(20), primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(100))
    class_code: Mapped[str] = mapped_column("ClassCode", String(8), ForeignKey("oacs.Code"))
    serial: Mapped[str | None] = mapped_column("SerialNum", String(36))
    location: Mapped[str | None] = mapped_column("Location", String(50))
    cap_date: Mapped[date | None] = mapped_column("CapDate", Date)
    cost: Mapped[Decimal] = mapped_column("Cost", AMOUNT, default=Decimal("0"))  # acquisition value
    salvage: Mapped[Decimal] = mapped_column("Salvage", AMOUNT, default=Decimal("0"))  # residual value
    acc_dep: Mapped[Decimal] = mapped_column("AccDep", AMOUNT, default=Decimal("0"))  # accumulated depreciation
    dep_until: Mapped[date | None] = mapped_column("DepUntil", Date)  # depreciated up to (month end)
    status: Mapped[str] = mapped_column("Status", String(1), default="N")  # N new, A active, R retired
    retire_date: Mapped[date | None] = mapped_column("RetireDate", Date)
    transactions: Mapped[list["AssetTransaction"]] = relationship(cascade="all, delete-orphan", order_by="AssetTransaction.line_id")


class AssetTransaction(Base):
    """FAS1 — Transactions of a fixed asset."""

    __tablename__ = "fas1"

    asset_code: Mapped[str] = mapped_column("AssetCode", String(20), ForeignKey("ofas.AssetCode"), primary_key=True)
    line_id: Mapped[int] = mapped_column("LineId", primary_key=True)
    tran_type: Mapped[str] = mapped_column("TranType", String(1))  # C capitalization, D depreciation, R retirement
    doc_date: Mapped[date] = mapped_column("DocDate", Date)
    amount: Mapped[Decimal] = mapped_column("Amount", AMOUNT)
    period: Mapped[str | None] = mapped_column("Period", String(7))  # depreciation month YYYY-MM
    trans_id: Mapped[int | None] = mapped_column("TransId", Integer)  # journal entry
    reversed: Mapped[str] = mapped_column("Reversed", String(1), default="N")
    memo: Mapped[str | None] = mapped_column("Memo", String(100))
