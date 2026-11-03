"""Budgets.

    OBGS   Budget scenarios (Main Budget per financial year, further scenarios as a ratio of it)
    OBGT   Budget of a G/L account in a scenario: annual debit / credit
    BGT1   Monthly budget amounts (Line_ID 1-12 = months of the financial year)
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

AMOUNT = Numeric(19, 6)


class BudgetScenario(Base):
    """OBGS — Budget scenario."""

    __tablename__ = "obgs"

    abs_id: Mapped[int] = mapped_column("AbsId", primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(30))
    financ_year: Mapped[int] = mapped_column("FinancYear", Integer)  # period category (calendar year)
    init_ratio: Mapped[Decimal] = mapped_column("InitRatio", AMOUNT, default=Decimal("100"))  # % of the main budget
    main_budget: Mapped[str] = mapped_column("MainBudget", String(1), default="N")  # not B1-verified


class Budget(Base):
    """OBGT — Budget of an account in a scenario."""

    __tablename__ = "obgt"
    __table_args__ = (UniqueConstraint("AcctCode", "Instance", name="uq_obgt_account_scenario"),)

    abs_id: Mapped[int] = mapped_column("AbsId", primary_key=True)
    acct_code: Mapped[str] = mapped_column("AcctCode", String(15), ForeignKey("oact.AcctCode"))
    instance: Mapped[int] = mapped_column("Instance", Integer, ForeignKey("obgs.AbsId"))  # scenario
    financ_year: Mapped[int] = mapped_column("FinancYear", Integer)
    deb_l_total: Mapped[Decimal] = mapped_column("DebLTotal", AMOUNT, default=Decimal("0"))
    crd_l_total: Mapped[Decimal] = mapped_column("CrdLTotal", AMOUNT, default=Decimal("0"))
    months: Mapped[list["BudgetMonth"]] = relationship(cascade="all, delete-orphan", order_by="BudgetMonth.line_id")


class BudgetMonth(Base):
    """BGT1 — Monthly amounts of a budget."""

    __tablename__ = "bgt1"

    budg_id: Mapped[int] = mapped_column("BudgId", Integer, ForeignKey("obgt.AbsId"), primary_key=True)
    line_id: Mapped[int] = mapped_column("Line_ID", primary_key=True)  # 1-12
    deb_l_total: Mapped[Decimal] = mapped_column("DebLTotal", AMOUNT, default=Decimal("0"))
    crd_l_total: Mapped[Decimal] = mapped_column("CrdLTotal", AMOUNT, default=Decimal("0"))
