"""Cost accounting: dimensions, profit centers and distribution rules.

    ODIM   Dimensions 1-5 (name, active)
    OPRC   Profit centers / cost centers of a dimension
    OOCR   Distribution rules of a dimension (OcrTotal = sum of the shares; Direct Y = the rule of
           one profit center, same code)
    OCR1   Shares of a distribution rule per profit center
Journal lines keep the rule codes (JDT1 ProfitCode for dimension 1, OcrCode2 .. OcrCode5), document
lines OcrCode .. OcrCode5; reports split the amounts by the shares.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Dimension(Base):
    """ODIM — Dimensions of cost accounting."""

    __tablename__ = "odim"

    dim_code: Mapped[int] = mapped_column("DimCode", primary_key=True)  # 1 - 5
    dim_name: Mapped[str] = mapped_column("DimName", String(30))
    dim_desc: Mapped[str | None] = mapped_column("DimDesc", String(100))
    dim_active: Mapped[str] = mapped_column("DimActive", String(1), default="N")


class ProfitCenter(Base):
    """OPRC — Profit centers (cost centers)."""

    __tablename__ = "oprc"

    prc_code: Mapped[str] = mapped_column("PrcCode", String(8), primary_key=True)
    prc_name: Mapped[str] = mapped_column("PrcName", String(30))
    dim_code: Mapped[int] = mapped_column("DimCode", ForeignKey("odim.DimCode"))
    active: Mapped[str] = mapped_column("Active", String(1), default="Y")
    valid_from: Mapped[date | None] = mapped_column("ValidFrom", Date)
    valid_to: Mapped[date | None] = mapped_column("ValidTo", Date)


class DistributionRule(Base):
    """OOCR — Distribution rules."""

    __tablename__ = "oocr"

    ocr_code: Mapped[str] = mapped_column("OcrCode", String(8), primary_key=True)
    ocr_name: Mapped[str] = mapped_column("OcrName", String(30))
    dim_code: Mapped[int] = mapped_column("DimCode", ForeignKey("odim.DimCode"))
    ocr_total: Mapped[Decimal] = mapped_column("OcrTotal", Numeric(19, 6), default=Decimal("100"))
    direct: Mapped[str] = mapped_column("Direct", String(1), default="N")
    active: Mapped[str] = mapped_column("Active", String(1), default="Y")
    shares: Mapped[list["DistributionShare"]] = relationship(cascade="all, delete-orphan", order_by="DistributionShare.prc_code")


class DistributionShare(Base):
    """OCR1 — Share of a profit center in a distribution rule."""

    __tablename__ = "ocr1"

    ocr_code: Mapped[str] = mapped_column("OcrCode", String(8), ForeignKey("oocr.OcrCode"), primary_key=True)
    prc_code: Mapped[str] = mapped_column("PrcCode", String(8), ForeignKey("oprc.PrcCode"), primary_key=True)
    prc_amount: Mapped[Decimal] = mapped_column("PrcAmount", Numeric(19, 6))
