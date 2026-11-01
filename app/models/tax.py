"""Taxes on sales/purchases (VAT / input / output) + withholding basics.

Tables modelled here:
    T005    Countries                        (+ T005T text folded in)
    T007A   Tax codes                        (+ T007S text folded into text1)
    T007K   Tax account key -> posting indicator
    TAXRATE (A003/KONP-style)   Tax rates per code + transaction key
    T030K   Tax accounts (account determination, transaction keys MWS/VST)
    T030R   Rules for tax account determination
    T059P   Withholding tax types
    T059Z   Withholding tax codes
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.organizational import MANDT


class Country(Base):
    """T005 — Country keys (+ T005T name)."""

    __tablename__ = "t005"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    land1: Mapped[str] = mapped_column(String(3), primary_key=True)  # Country key
    landx: Mapped[str] = mapped_column(String(50))  # Country name
    kalsm: Mapped[str | None] = mapped_column(String(6))  # Tax calculation procedure
    xegld: Mapped[bool] = mapped_column(default=False)  # EU country
    intca: Mapped[str | None] = mapped_column(String(2))  # ISO country code
    waers: Mapped[str | None] = mapped_column(String(5))  # Country currency
    spras: Mapped[str] = mapped_column(String(1), default="E")  # Language


class TaxCode(Base):
    """T007A — Tax codes (+ T007S description in text1)."""

    __tablename__ = "t007a"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kalsm: Mapped[str] = mapped_column(String(6), primary_key=True)  # Tax calculation procedure
    mwskz: Mapped[str] = mapped_column(String(2), primary_key=True)  # Tax code
    mwart: Mapped[str] = mapped_column(String(1))  # Tax type A=output V=input
    text1: Mapped[str] = mapped_column(String(50))  # Description
    egrkz: Mapped[str | None] = mapped_column(String(1))  # EU code (acquisition tax ...)
    lstml: Mapped[str | None] = mapped_column(String(3))  # Reporting country
    xinact: Mapped[bool] = mapped_column(default=False)  # Tax code inactive
    zmwsk: Mapped[str | None] = mapped_column(String(2))  # Target tax code (deferred tax)


class TaxRate(Base):
    """A003/KONP-style tax rate per tax code and transaction (condition) key.

    The transaction key KTOSL distinguishes output tax (MWS), input tax (VST),
    non-deductible input tax (NAV), etc. The percentage is held in KBETR.
    """

    __tablename__ = "taxrate"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kalsm: Mapped[str] = mapped_column(String(6), primary_key=True)  # Tax procedure
    mwskz: Mapped[str] = mapped_column(String(2), primary_key=True)  # Tax code
    ktosl: Mapped[str] = mapped_column(String(3), primary_key=True)  # Transaction key (MWS/VST/NAV)
    kschl: Mapped[str] = mapped_column(String(4))  # Condition type (MWAS/MWVS...)
    kbetr: Mapped[Decimal] = mapped_column(Numeric(7, 3))  # Rate percentage (e.g. 19.000)
    deductible: Mapped[bool] = mapped_column(default=True)  # Input tax deductible


class TaxAccount(Base):
    """T030K — Tax accounts (account determination for a transaction key)."""

    __tablename__ = "t030k"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "ktopl"], ["t004.mandt", "t004.ktopl"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    ktopl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Chart of accounts
    ktosl: Mapped[str] = mapped_column(String(3), primary_key=True)  # Transaction key (MWS/VST)
    mwskz: Mapped[str] = mapped_column(String(2), primary_key=True)  # Tax code
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True, default="")  # Company code (if differentiated)
    konts: Mapped[str] = mapped_column(String(10))  # G/L account (debit)
    konth: Mapped[str | None] = mapped_column(String(10))  # G/L account (credit)
    shkzg: Mapped[str | None] = mapped_column(String(1))  # Debit/credit indicator


class WithholdingTaxType(Base):
    """T059P — Withholding tax types."""

    __tablename__ = "t059p"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    land1: Mapped[str] = mapped_column(String(3), primary_key=True)  # Country
    witht: Mapped[str] = mapped_column(String(2), primary_key=True)  # Withholding tax type
    text40: Mapped[str] = mapped_column(String(40))  # Description
    wt_posin: Mapped[str | None] = mapped_column(String(1))  # Posting time (1=invoice/2=payment)
    inherit: Mapped[bool] = mapped_column(default=False)


class WithholdingTaxCode(Base):
    """T059Z — Withholding tax codes (rates)."""

    __tablename__ = "t059z"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mandt", "land1", "witht"],
            ["t059p.mandt", "t059p.land1", "t059p.witht"],
        ),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    land1: Mapped[str] = mapped_column(String(3), primary_key=True)  # Country
    witht: Mapped[str] = mapped_column(String(2), primary_key=True)  # Withholding tax type
    wt_withcd: Mapped[str] = mapped_column(String(2), primary_key=True)  # Withholding tax code
    text40: Mapped[str] = mapped_column(String(40))  # Description
    qsatz: Mapped[Decimal] = mapped_column(Numeric(8, 4))  # Withholding tax rate %
    qproz: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("100"))  # Portion subject to WT
    wt_acckey: Mapped[str | None] = mapped_column(String(3))  # Account key
