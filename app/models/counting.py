"""Inventory counting and inventory posting.

    OINC / INC1   Inventory counting: items per warehouse with the quantity in the warehouse when
                  the counting was created (InWhsQty) and the counted quantity
    OIQR / IQR1   Inventory posting: posts the differences of a counting; surpluses go through a
                  goods receipt, shortages through a goods issue (at the item cost, against the
                  inventory offset accounts) — GrEntry / GiEntry link them (not B1-verified: B1
                  posts the inventory posting itself)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

QTY = Numeric(19, 6)


class InventoryCounting(Base):
    """OINC — Inventory counting."""

    __tablename__ = "oinc"

    doc_entry: Mapped[int] = mapped_column("DocEntry", primary_key=True)
    doc_num: Mapped[int] = mapped_column("DocNum", Integer)
    count_date: Mapped[date] = mapped_column("CountDate", Date)
    status: Mapped[str] = mapped_column("Status", String(1), default="O")  # O open, C closed (posted)
    remarks: Mapped[str | None] = mapped_column("Remarks", String(254))
    user_sign: Mapped[str | None] = mapped_column("UserSign", String(25))
    lines: Mapped[list["InventoryCountingLine"]] = relationship(cascade="all, delete-orphan", order_by="InventoryCountingLine.line_num")


class InventoryCountingLine(Base):
    """INC1 — Lines of an inventory counting."""

    __tablename__ = "inc1"

    doc_entry: Mapped[int] = mapped_column("DocEntry", Integer, ForeignKey("oinc.DocEntry"), primary_key=True)
    line_num: Mapped[int] = mapped_column("LineNum", primary_key=True)
    item_code: Mapped[str] = mapped_column("ItemCode", String(50))
    whs_code: Mapped[str] = mapped_column("WhsCode", String(8))
    in_whs_qty: Mapped[Decimal] = mapped_column("InWhsQty", QTY)  # in the warehouse when the counting was created
    counted: Mapped[str] = mapped_column("Counted", String(1), default="N")
    count_qty: Mapped[Decimal] = mapped_column("CountQty", QTY, default=Decimal("0"))
    difference: Mapped[Decimal] = mapped_column("Difference", QTY, default=Decimal("0"))  # counted - in warehouse
    batches: Mapped[str | None] = mapped_column("Batches", Text)  # surplus of managed items: JSON numbers (not B1-verified)
    remarks: Mapped[str | None] = mapped_column("Remarks", String(254))


class InventoryPosting(Base):
    """OIQR — Inventory posting of a counting."""

    __tablename__ = "oiqr"

    doc_entry: Mapped[int] = mapped_column("DocEntry", primary_key=True)
    doc_num: Mapped[int] = mapped_column("DocNum", Integer)
    doc_date: Mapped[date] = mapped_column("DocDate", Date)
    base_entry: Mapped[int] = mapped_column("BaseEntry", Integer, ForeignKey("oinc.DocEntry"))  # the counting
    gr_entry: Mapped[int | None] = mapped_column("GrEntry", Integer)  # goods receipt (OIGN) of the surpluses
    gi_entry: Mapped[int | None] = mapped_column("GiEntry", Integer)  # goods issue (OIGE) of the shortages
    value_in: Mapped[Decimal] = mapped_column("ValueIn", Numeric(19, 6), default=Decimal("0"))
    value_out: Mapped[Decimal] = mapped_column("ValueOut", Numeric(19, 6), default=Decimal("0"))
    user_sign: Mapped[str | None] = mapped_column("UserSign", String(25))
    lines: Mapped[list["InventoryPostingLine"]] = relationship(cascade="all, delete-orphan", order_by="InventoryPostingLine.line_num")


class InventoryPostingLine(Base):
    """IQR1 — Lines of an inventory posting."""

    __tablename__ = "iqr1"

    doc_entry: Mapped[int] = mapped_column("DocEntry", Integer, ForeignKey("oiqr.DocEntry"), primary_key=True)
    line_num: Mapped[int] = mapped_column("LineNum", primary_key=True)
    item_code: Mapped[str] = mapped_column("ItemCode", String(50))
    whs_code: Mapped[str] = mapped_column("WhsCode", String(8))
    in_whs_qty: Mapped[Decimal] = mapped_column("InWhsQty", QTY)
    count_qty: Mapped[Decimal] = mapped_column("CountQty", QTY)
    quantity: Mapped[Decimal] = mapped_column("Quantity", QTY)  # difference posted
    price: Mapped[Decimal] = mapped_column("Price", Numeric(19, 6))  # item cost
    line_total: Mapped[Decimal] = mapped_column("LineTotal", Numeric(19, 6))
    base_line: Mapped[int] = mapped_column("BaseLine", Integer)  # INC1 line
