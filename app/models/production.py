"""Production: bills of materials and production orders.

    OITT / ITT1   Bill of materials of a parent item (type P production, S sales, A assembly, T template),
                  quantity it makes, warehouse; components with quantity, warehouse, issue method
                  (M manual, B backflush)
    OWOR / WOR1   Production order: product, planned / completed / rejected quantity, status (P planned,
                  R released, L closed, C canceled), warehouse, dates; components with base and planned
                  quantity, issued quantity and value. IssuedVal / RcptVal (not B1-verified) keep the
                  work in progress of the order.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

QTY = Numeric(19, 6)


class BillOfMaterials(Base):
    """OITT — Bill of materials."""

    __tablename__ = "oitt"

    code: Mapped[str] = mapped_column("Code", String(50), ForeignKey("oitm.ItemCode"), primary_key=True)  # parent item
    tree_type: Mapped[str] = mapped_column("TreeType", String(1), default="P")
    qauntity: Mapped[Decimal] = mapped_column("Qauntity", QTY, default=Decimal("1"))  # B1 spelling: quantity the BOM makes
    to_wh: Mapped[str | None] = mapped_column("ToWH", String(8))
    lines: Mapped[list["BomLine"]] = relationship(cascade="all, delete-orphan", order_by="BomLine.child_num")


class BomLine(Base):
    """ITT1 — Component of a bill of materials."""

    __tablename__ = "itt1"

    father: Mapped[str] = mapped_column("Father", String(50), ForeignKey("oitt.Code"), primary_key=True)
    child_num: Mapped[int] = mapped_column("ChildNum", primary_key=True)
    code: Mapped[str] = mapped_column("Code", String(50))  # component item
    quantity: Mapped[Decimal] = mapped_column("Quantity", QTY)  # per BOM quantity
    warehouse: Mapped[str | None] = mapped_column("Warehouse", String(8))
    issue_mthd: Mapped[str] = mapped_column("IssueMthd", String(1), default="M")  # M manual, B backflush


class ProductionOrder(Base):
    """OWOR — Production order."""

    __tablename__ = "owor"

    doc_entry: Mapped[int] = mapped_column("DocEntry", primary_key=True)
    doc_num: Mapped[int] = mapped_column("DocNum", Integer)
    type: Mapped[str] = mapped_column("Type", String(1), default="S")  # S standard
    status: Mapped[str] = mapped_column("Status", String(1), default="P")  # P planned, R released, L closed, C canceled
    item_code: Mapped[str] = mapped_column("ItemCode", String(50))
    planned_qty: Mapped[Decimal] = mapped_column("PlannedQty", QTY)
    cmplt_qty: Mapped[Decimal] = mapped_column("CmpltQty", QTY, default=Decimal("0"))
    rjct_qty: Mapped[Decimal] = mapped_column("RjctQty", QTY, default=Decimal("0"))
    warehouse: Mapped[str] = mapped_column("Warehouse", String(8))
    post_date: Mapped[date] = mapped_column("PostDate", Date)
    due_date: Mapped[date] = mapped_column("DueDate", Date)
    close_date: Mapped[date | None] = mapped_column("CloseDate", Date)
    card_code: Mapped[str | None] = mapped_column("CardCode", String(15))  # customer (made to order)
    origin_num: Mapped[int | None] = mapped_column("OriginNum", Integer)  # sales order DocNum
    comments: Mapped[str | None] = mapped_column("Comments", String(254))
    project: Mapped[str | None] = mapped_column("Project", String(20))  # carried to the issues / receipts and the variance
    ocr_code: Mapped[str | None] = mapped_column("OcrCode", String(8))  # distribution rule (dimension 1) of the variance
    issued_val: Mapped[Decimal] = mapped_column("IssuedVal", Numeric(19, 6), default=Decimal("0"))  # components issued (WIP debit)
    rcpt_val: Mapped[Decimal] = mapped_column("RcptVal", Numeric(19, 6), default=Decimal("0"))  # products received (WIP credit)
    var_trans: Mapped[int | None] = mapped_column("VarTrans", Integer)  # journal entry of the variance at close
    lines: Mapped[list["ProductionOrderLine"]] = relationship(cascade="all, delete-orphan", order_by="ProductionOrderLine.line_num")


class ProductionOrderLine(Base):
    """WOR1 — Component of a production order."""

    __tablename__ = "wor1"

    doc_entry: Mapped[int] = mapped_column("DocEntry", Integer, ForeignKey("owor.DocEntry"), primary_key=True)
    line_num: Mapped[int] = mapped_column("LineNum", primary_key=True)
    item_code: Mapped[str] = mapped_column("ItemCode", String(50))
    base_qty: Mapped[Decimal] = mapped_column("BaseQty", QTY)  # per unit of the product
    planned_qty: Mapped[Decimal] = mapped_column("PlannedQty", QTY)
    issued_qty: Mapped[Decimal] = mapped_column("IssuedQty", QTY, default=Decimal("0"))
    issued_val: Mapped[Decimal] = mapped_column("IssuedVal", Numeric(19, 6), default=Decimal("0"))
    warehouse: Mapped[str] = mapped_column("wareHouse", String(8))
    issue_type: Mapped[str] = mapped_column("IssueType", String(1), default="M")  # M manual, B backflush
