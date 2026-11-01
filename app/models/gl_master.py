"""General Ledger master data.

Tables modelled here:
    SKA1    G/L account master — chart of accounts area (COA segment)
    SKAT    G/L account texts
    SKB1    G/L account master — company code area (company code segment)
    T077S   G/L account groups (+ T077Z text)
    T004V   Field status variants
    T004G   Field status groups

A G/L account always has a COA segment (SKA1) and, once extended to a company
code, a company-code segment (SKB1). This two-level structure is central to SAP:
the COA segment is shared by every company code using that chart of accounts.
"""

from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.organizational import MANDT


class GLAccountGroup(Base):
    """T077S — G/L account groups (+ T077Z description).

    The account group controls the allowed number interval and the screen
    (field status) layout for master-data maintenance.
    """

    __tablename__ = "t077s"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "ktopl"], ["t004.mandt", "t004.ktopl"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    ktopl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Chart of accounts
    ktoks: Mapped[str] = mapped_column(String(4), primary_key=True)  # G/L account group
    txt30: Mapped[str] = mapped_column(String(30))  # Account group description
    vonkt: Mapped[str] = mapped_column(String(10))  # From account (number interval)
    biskt: Mapped[str] = mapped_column(String(10))  # To account (number interval)


class FieldStatusVariant(Base):
    """T004V — Field status variants."""

    __tablename__ = "t004v"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    fstva: Mapped[str] = mapped_column(String(4), primary_key=True)  # Field status variant
    txt40: Mapped[str] = mapped_column(String(40))  # Description


class FieldStatusGroup(Base):
    """T004G — Field status groups (field status definition).

    A field status group decides whether each posting field is suppressed,
    required or optional. Stored here as a compact JSON-like status map keyed by
    field group name (e.g. 'text', 'cost_center', 'value_date').
    """

    __tablename__ = "t004g"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "fstva"], ["t004v.mandt", "t004v.fstva"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    fstva: Mapped[str] = mapped_column(String(4), primary_key=True)  # Field status variant
    fstag: Mapped[str] = mapped_column(String(4), primary_key=True)  # Field status group
    txt40: Mapped[str] = mapped_column(String(40))  # Description
    # Status codes per field group: '.'=optional, '+'=required, '-'=suppressed
    status_text: Mapped[str] = mapped_column(String(1), default=".")  # Document text
    status_cost_center: Mapped[str] = mapped_column(String(1), default=".")
    status_value_date: Mapped[str] = mapped_column(String(1), default=".")
    status_assignment: Mapped[str] = mapped_column(String(1), default=".")  # Zuonr
    status_quantity: Mapped[str] = mapped_column(String(1), default="-")


class GLAccountCOA(Base):
    """SKA1 — G/L account master record (chart of accounts area)."""

    __tablename__ = "ska1"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "ktopl"], ["t004.mandt", "t004.ktopl"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    ktopl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Chart of accounts
    saknr: Mapped[str] = mapped_column(String(10), primary_key=True)  # G/L account number
    xbilk: Mapped[bool] = mapped_column(default=False)  # Balance sheet account indicator
    gvtyp: Mapped[str | None] = mapped_column(String(2))  # P&L statement account type
    ktoks: Mapped[str] = mapped_column(String(4))  # G/L account group
    bilkt: Mapped[str | None] = mapped_column(String(10))  # Group account number
    xspeb: Mapped[bool] = mapped_column(default=False)  # Blocked for posting (centrally)
    xloeb: Mapped[bool] = mapped_column(default=False)  # Marked for deletion (centrally)
    mcod1: Mapped[str | None] = mapped_column(String(25))  # Search term
    vbund: Mapped[str | None] = mapped_column(String(6))  # Trading partner
    func_area: Mapped[str | None] = mapped_column(String(16))  # Functional area
    sakan: Mapped[str | None] = mapped_column(String(10))  # G/L account number (short)
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on
    ernam: Mapped[str | None] = mapped_column(String(12))  # Created by

    texts: Mapped[list["GLAccountText"]] = relationship(
        primaryjoin=(
            "and_(GLAccountCOA.mandt==foreign(GLAccountText.mandt), "
            "GLAccountCOA.ktopl==foreign(GLAccountText.ktopl), "
            "GLAccountCOA.saknr==foreign(GLAccountText.saknr))"
        ),
        viewonly=True,
    )


class GLAccountText(Base):
    """SKAT — G/L account names (texts), language dependent."""

    __tablename__ = "skat"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mandt", "ktopl", "saknr"],
            ["ska1.mandt", "ska1.ktopl", "ska1.saknr"],
        ),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    spras: Mapped[str] = mapped_column(String(1), primary_key=True)  # Language key
    ktopl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Chart of accounts
    saknr: Mapped[str] = mapped_column(String(10), primary_key=True)  # G/L account number
    txt20: Mapped[str] = mapped_column(String(20))  # Short text
    txt50: Mapped[str] = mapped_column(String(50))  # G/L account long text
    mcod1: Mapped[str | None] = mapped_column(String(25))  # Search term


class GLAccountCompanyCode(Base):
    """SKB1 — G/L account master record (company code area)."""

    __tablename__ = "skb1"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    saknr: Mapped[str] = mapped_column(String(10), primary_key=True)  # G/L account number
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on
    ernam: Mapped[str | None] = mapped_column(String(12))  # Created by
    waers: Mapped[str | None] = mapped_column(String(5))  # Account currency
    xsalh: Mapped[bool] = mapped_column(default=False)  # Balances in local currency only
    xkres: Mapped[bool] = mapped_column(default=True)  # Line item display
    mwskz: Mapped[str | None] = mapped_column(String(2))  # Tax category
    xmwno: Mapped[bool] = mapped_column(default=False)  # Posting without tax allowed
    mitkz: Mapped[str | None] = mapped_column(String(1))  # Reconciliation acct for acct type (D/K/A/V)
    xopvw: Mapped[bool] = mapped_column(default=False)  # Open item management
    xkont: Mapped[bool] = mapped_column(default=False)  # Account managed on open item basis (legacy)
    zuawa: Mapped[str | None] = mapped_column(String(3))  # Sort key (layout for Assignment field)
    fstag: Mapped[str | None] = mapped_column(String(4))  # Field status group
    xintb: Mapped[bool] = mapped_column(default=False)  # Post automatically only
    fdlev: Mapped[str | None] = mapped_column(String(2))  # Planning level (cash management)
    fdgrv: Mapped[str | None] = mapped_column(String(10))  # Cash management group
    busab: Mapped[str | None] = mapped_column(String(2))  # Accounting clerk
    hbkid: Mapped[str | None] = mapped_column(String(5))  # House bank
    hktid: Mapped[str | None] = mapped_column(String(5))  # Account ID (house bank)
    altkt: Mapped[str | None] = mapped_column(String(10))  # Alternative account number
    bewgp: Mapped[str | None] = mapped_column(String(10))  # Valuation group
    kdfsl: Mapped[str | None] = mapped_column(String(4))  # Exchange rate difference key
    recid: Mapped[str | None] = mapped_column(String(2))  # Recovery indicator
    vzskz: Mapped[str | None] = mapped_column(String(2))  # Interest indicator
    zinrt: Mapped[str | None] = mapped_column(String(2))  # Interest calc frequency
    xspeb: Mapped[bool] = mapped_column(default=False)  # Blocked for posting in company code
    xloeb: Mapped[bool] = mapped_column(default=False)  # Marked for deletion in company code
    mitkz_text: Mapped[str | None] = mapped_column(String(30))  # (helper) reconciliation meaning
