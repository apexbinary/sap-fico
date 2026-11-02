"""Financial Statement Version (FSV) — balance sheet / P&L structure.

Tables modelled here:
    T011        Financial statement versions   (+ T011T text folded into VSTXT)
    FAGL_011PC  FSV items (hierarchy nodes)     (+ FAGL_011QT text folded into TXT45)
    FAGL_011ZC  Account assignments to FSV items (account ranges, debit/credit flags)

SAP stores the item tree as linked nodes (PARENT/CHILD/NEXT); here each node
keeps PARENT and an explicit display order (SEQNO). An account range may be
assigned only for debit balances (SOLL) or only for credit balances (HABEN),
so e.g. a bank account in overdraft moves from assets to liabilities.
"""

from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.organizational import MANDT


class FinancialStatementVersion(Base):
    """T011 — Financial statement version (+ T011T description in vstxt)."""

    __tablename__ = "t011"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    versn: Mapped[str] = mapped_column(String(4), primary_key=True)  # Financial statement version
    vstxt: Mapped[str] = mapped_column(String(50))  # Description
    ktopl: Mapped[str] = mapped_column(String(4))  # Chart of accounts
    spras: Mapped[str] = mapped_column(String(1), default="E")  # Maintenance language
    xergs: Mapped[bool] = mapped_column(default=True)  # Item keys assigned automatically
    xfbst: Mapped[bool] = mapped_column(default=False)  # Functional area allowed


class FSVNode(Base):
    """FAGL_011PC — FSV item (hierarchy node), text from FAGL_011QT in txt45."""

    __tablename__ = "fagl_011pc"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "versn"], ["t011.mandt", "t011.versn"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    versn: Mapped[str] = mapped_column(String(4), primary_key=True)  # Financial statement version
    id: Mapped[int] = mapped_column(primary_key=True)  # Node ID
    parent: Mapped[int | None] = mapped_column()  # Parent node ID (None = top level)
    ergsl: Mapped[str] = mapped_column(String(10))  # Item key
    txt45: Mapped[str] = mapped_column(String(45))  # Item text
    seqno: Mapped[int] = mapped_column(default=0)  # Display order among siblings (SAP: NEXT links)
    # Special items: A assets, L liabilities & equity, P profit and loss,
    # N net result (P&L result shown in equity), U not assigned. Not an SAP column:
    # SAP identifies these through the fixed special item keys of the version.
    kind: Mapped[str] = mapped_column(String(1), default="")
    # Display sign: -1 shows credit balances as positive (liabilities, revenue).
    # Inherited by child nodes. Not an SAP column (SAP sets it in the report variant).
    sign: Mapped[int] = mapped_column(default=1)


class FSVAccountAssignment(Base):
    """FAGL_011ZC — Accounts (ranges) assigned to an FSV item."""

    __tablename__ = "fagl_011zc"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "versn"], ["t011.mandt", "t011.versn"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    versn: Mapped[str] = mapped_column(String(4), primary_key=True)  # Financial statement version
    ergsl: Mapped[str] = mapped_column(String(10), primary_key=True)  # Item key of the node
    ktopl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Chart of accounts
    vonkt: Mapped[str] = mapped_column(String(10), primary_key=True)  # Account from
    biskt: Mapped[str] = mapped_column(String(10))  # Account to
    soll: Mapped[bool] = mapped_column(default=True)  # Assign when the balance is a debit
    haben: Mapped[bool] = mapped_column(default=True)  # Assign when the balance is a credit
