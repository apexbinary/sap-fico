"""Batch and serial numbers.

    OBTN / OSRN   Batch / serial number master data (item, number, expiry and manufacturing date)
    OBTQ / OSRQ   Quantity of a batch / serial number per warehouse
    OITL / ITL1   Inventory transaction log of managed items: one log per document line and warehouse
                  move (StockEff +1 in / -1 out), with the quantity per batch / serial number
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

QTY = Numeric(19, 6)


class _Number:
    abs_entry: Mapped[int] = mapped_column("AbsEntry", primary_key=True)
    item_code: Mapped[str] = mapped_column("ItemCode", String(50), ForeignKey("oitm.ItemCode"), index=True)
    sys_number: Mapped[int] = mapped_column("SysNumber", Integer)  # per item 1, 2, 3 ...
    dist_number: Mapped[str] = mapped_column("DistNumber", String(36))  # batch / serial number
    exp_date: Mapped[date | None] = mapped_column("ExpDate", Date)
    mnf_date: Mapped[date | None] = mapped_column("MnfDate", Date)
    in_date: Mapped[date | None] = mapped_column("InDate", Date)  # admission date
    notes: Mapped[str | None] = mapped_column("Notes", String(254))


class Batch(_Number, Base):
    """OBTN — Batch numbers."""

    __tablename__ = "obtn"
    __table_args__ = (UniqueConstraint("ItemCode", "DistNumber", name="uq_obtn_item_number"),)


class SerialNumber(_Number, Base):
    """OSRN — Serial numbers."""

    __tablename__ = "osrn"
    __table_args__ = (UniqueConstraint("ItemCode", "DistNumber", name="uq_osrn_item_number"),)


class _Quantity:
    abs_entry: Mapped[int] = mapped_column("AbsEntry", primary_key=True)
    item_code: Mapped[str] = mapped_column("ItemCode", String(50), index=True)
    sys_number: Mapped[int] = mapped_column("SysNumber", Integer)
    whs_code: Mapped[str] = mapped_column("WhsCode", String(8))
    quantity: Mapped[Decimal] = mapped_column("Quantity", QTY, default=Decimal("0"))


class BatchQuantity(_Quantity, Base):
    """OBTQ — Quantity of a batch per warehouse."""

    __tablename__ = "obtq"
    md_abs_entry: Mapped[int] = mapped_column("MdAbsEntry", Integer, ForeignKey("obtn.AbsEntry"), index=True)


class SerialQuantity(_Quantity, Base):
    """OSRQ — Quantity (0 / 1) of a serial number per warehouse."""

    __tablename__ = "osrq"
    md_abs_entry: Mapped[int] = mapped_column("MdAbsEntry", Integer, ForeignKey("osrn.AbsEntry"), index=True)


class InventoryLog(Base):
    """OITL — Inventory transaction log of batch / serial managed items."""

    __tablename__ = "oitl"

    log_entry: Mapped[int] = mapped_column("LogEntry", primary_key=True)
    item_code: Mapped[str] = mapped_column("ItemCode", String(50), index=True)
    doc_type: Mapped[str] = mapped_column("DocType", String(20))
    doc_entry: Mapped[int] = mapped_column("DocEntry", Integer)
    doc_line: Mapped[int] = mapped_column("DocLine", Integer)
    doc_num: Mapped[int | None] = mapped_column("DocNum", Integer)
    doc_date: Mapped[date] = mapped_column("DocDate", Date)
    loc_code: Mapped[str] = mapped_column("LocCode", String(8))  # warehouse
    stock_eff: Mapped[int] = mapped_column("StockEff", Integer)  # 1 in, -1 out
    doc_qty: Mapped[Decimal] = mapped_column("DocQty", QTY)  # inventory units
    managed_by: Mapped[str] = mapped_column("ManagedBy", String(10))  # 10000044 batches, 10000045 serial numbers
    reversed: Mapped[str] = mapped_column("Reversed", String(1), default="N")  # canceled document (not B1-verified)
    lines: Mapped[list["InventoryLogLine"]] = relationship(cascade="all, delete-orphan", order_by="InventoryLogLine.md_abs_entry")


class InventoryLogLine(Base):
    """ITL1 — Quantity per batch / serial number of an inventory transaction log."""

    __tablename__ = "itl1"

    log_entry: Mapped[int] = mapped_column("LogEntry", Integer, ForeignKey("oitl.LogEntry"), primary_key=True)
    md_abs_entry: Mapped[int] = mapped_column("MdAbsEntry", Integer, primary_key=True)  # OBTN / OSRN AbsEntry
    item_code: Mapped[str] = mapped_column("ItemCode", String(50))
    sys_number: Mapped[int] = mapped_column("SysNumber", Integer)
    quantity: Mapped[Decimal] = mapped_column("Quantity", QTY)  # signed like the move
