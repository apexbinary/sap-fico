"""Payment transactions customizing.

Tables modelled here:
    T052   Terms of payment            (+ T052U explanation folded into TEXT1)
    T030   Standard accounts table     (automatic postings by transaction key,
                                        e.g. SKT cash discount granted,
                                        SKE cash discount received)
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.organizational import MANDT


class PaymentTerms(Base):
    """T052 — Terms of payment (+ T052U own explanation in text1)."""

    __tablename__ = "t052"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    zterm: Mapped[str] = mapped_column(String(4), primary_key=True)  # Terms of payment key
    ztagg: Mapped[int] = mapped_column(primary_key=True, default=0)  # Day limit (0 = none)
    text1: Mapped[str | None] = mapped_column(String(50))  # Own explanation of the terms
    koart: Mapped[str | None] = mapped_column(String(1))  # Account type (D/K, blank = both)
    zdart: Mapped[str | None] = mapped_column(String(1))  # Default baseline date (D doc date, B posting date, C entry date)
    zfael: Mapped[int | None] = mapped_column()  # Fixed day for baseline date
    zmona: Mapped[int | None] = mapped_column()  # Additional months for baseline date
    ztag1: Mapped[int] = mapped_column(default=0)  # Cash discount days 1
    zprz1: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0"))  # Cash discount percentage 1
    ztag2: Mapped[int] = mapped_column(default=0)  # Cash discount days 2
    zprz2: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0"))  # Cash discount percentage 2
    ztag3: Mapped[int] = mapped_column(default=0)  # Net payment terms period (days)
    zschf: Mapped[str | None] = mapped_column(String(1))  # Payment block key (default)
    zlsch: Mapped[str | None] = mapped_column(String(1))  # Payment method (default)
    xsplt: Mapped[bool] = mapped_column(default=False)  # Installment payment
    xzbrv: Mapped[bool] = mapped_column(default=False)  # Hold payment terms on residual items


class AutomaticAccountDetermination(Base):
    """T030 — Standard accounts table (G/L accounts for automatic postings)."""

    __tablename__ = "t030"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    ktopl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Chart of accounts
    ktosl: Mapped[str] = mapped_column(String(3), primary_key=True)  # Transaction key (SKT, SKE, ...)
    bwmod: Mapped[str] = mapped_column(String(4), primary_key=True, default="")  # Valuation grouping code
    komok: Mapped[str] = mapped_column(String(3), primary_key=True, default="")  # Account modifier
    bklas: Mapped[str] = mapped_column(String(4), primary_key=True, default="")  # Valuation class
    konts: Mapped[str] = mapped_column(String(10))  # G/L account (debit)
    konth: Mapped[str | None] = mapped_column(String(10))  # G/L account (credit; blank = konts)
