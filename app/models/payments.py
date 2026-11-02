"""Payment transactions customizing.

Tables modelled here:
    T052   Terms of payment            (+ T052U explanation folded into TEXT1)
    T030   Standard accounts table     (automatic postings by transaction key,
                                        e.g. SKT cash discount granted,
                                        SKE cash discount received)
    T042Z  Payment methods per country (automatic payment program, F110)
    T042E  Payment methods per company code (amount limits)
    T042I  Bank determination: ranking of house banks per payment method
    T043G  Tolerances for customers/vendors (permitted payment differences)
    T030H  Exchange rate difference accounts per open-item / reconciliation account
    T044A  Valuation methods for the foreign currency valuation (rate types per balance)
    T043   User -> employee tolerance group
    T043T  Employee tolerances (posting limits, cash discount, payment differences)
    T053R  Reason codes for payment differences
    T042Y  Available amounts per house bank account (payment program)
    PCEC   Check lots (prenumbered checks per house bank account)
    PAYR   Check register (issued, printed and voided checks)
"""

from __future__ import annotations

from datetime import date
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


class PaymentMethod(Base):
    """T042Z — Payment methods in a country (+ T042ZT text in text1)."""

    __tablename__ = "t042z"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    land1: Mapped[str] = mapped_column(String(3), primary_key=True)  # Country key
    zlsch: Mapped[str] = mapped_column(String(1), primary_key=True)  # Payment method
    text1: Mapped[str] = mapped_column(String(30))  # Description of the payment method
    xeinz: Mapped[bool] = mapped_column(default=False)  # Incoming payment (collection)
    xschk: Mapped[bool] = mapped_column(default=False)  # Check payment
    xbkkt: Mapped[bool] = mapped_column(default=False)  # Bank details of payee required
    blart: Mapped[str | None] = mapped_column(String(2))  # Document type for the payment
    progn: Mapped[str | None] = mapped_column(String(40))  # Payment medium program / format


class CompanyCodePaymentMethod(Base):
    """T042E — Payment method per paying company code (amount limits)."""

    __tablename__ = "t042e"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    zbukr: Mapped[str] = mapped_column(String(4), primary_key=True)  # Paying company code
    zlsch: Mapped[str] = mapped_column(String(1), primary_key=True)  # Payment method
    minbt: Mapped[Decimal] = mapped_column(Numeric(13, 2), default=Decimal("0"))  # Minimum payment amount
    maxbt: Mapped[Decimal | None] = mapped_column(Numeric(13, 2))  # Maximum payment amount (blank = none)
    xfore: Mapped[bool] = mapped_column(default=False)  # Foreign currency allowed


class BankDetermination(Base):
    """T042I — Ranking order of house banks per payment method and currency."""

    __tablename__ = "t042i"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    zbukr: Mapped[str] = mapped_column(String(4), primary_key=True)  # Paying company code
    zlsch: Mapped[str] = mapped_column(String(1), primary_key=True)  # Payment method
    waers: Mapped[str] = mapped_column(String(5), primary_key=True)  # Currency
    rangf: Mapped[int] = mapped_column(primary_key=True)  # Rank order
    hbkid: Mapped[str] = mapped_column(String(5))  # House bank
    hktid: Mapped[str] = mapped_column(String(5))  # House bank account ID
    ukont: Mapped[str] = mapped_column(String(10))  # G/L account posted by the payment (bank / sub-account)


class CustomerVendorTolerance(Base):
    """T043G — Customer/vendor tolerances per company code and tolerance group.

    A payment difference is posted automatically (T030 key ZDI) when it is
    within both the amount and the percentage limit of its direction. Gain and
    loss are seen from the company: a customer underpaying is a loss, a vendor
    being underpaid is a gain. Tolerance group '' is the company-code default.
    The amount/percent column names follow the OBA3 screen and still need
    checking against the SAP data dictionary.
    """

    __tablename__ = "t043g"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    togru: Mapped[str] = mapped_column(String(4), primary_key=True, default="")  # Tolerance group
    betrh: Mapped[Decimal] = mapped_column(Numeric(13, 2), default=Decimal("0"))  # Permitted difference: gain, amount
    prozh: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))  # Permitted difference: gain, percent
    betrs: Mapped[Decimal] = mapped_column(Numeric(13, 2), default=Decimal("0"))  # Permitted difference: loss, amount
    prozs: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))  # Permitted difference: loss, percent


class ExchangeDifferenceAccounts(Base):
    """T030H — Accounts for exchange rate differences of an open-item managed account.

    HKONT is a reconciliation account (customers / vendors) or an open-item G/L
    account. Realized differences arise on clearing; valuation differences are
    posted by the foreign currency valuation against the balance sheet
    adjustment account.
    """

    __tablename__ = "t030h"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    ktopl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Chart of accounts
    hkont: Mapped[str] = mapped_column(String(10), primary_key=True)  # Open item / reconciliation account
    lsrea: Mapped[str] = mapped_column(String(10))  # Realized exchange rate loss
    lhrea: Mapped[str] = mapped_column(String(10))  # Realized exchange rate gain
    lsbew: Mapped[str] = mapped_column(String(10))  # Valuation loss
    lhbew: Mapped[str] = mapped_column(String(10))  # Valuation gain
    lkorr: Mapped[str] = mapped_column(String(10))  # Balance sheet adjustment account


class UserToleranceGroup(Base):
    """T043 — Assignment of a user to an employee tolerance group."""

    __tablename__ = "t043"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    usnam: Mapped[str] = mapped_column(String(12), primary_key=True)  # User name
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    togru: Mapped[str] = mapped_column(String(4))  # Tolerance group


class EmployeeTolerance(Base):
    """T043T — Employee tolerances per company code and tolerance group ('' = default).

    Column names other than the keys follow the OBA4 screen and still need
    checking against the SAP data dictionary.
    """

    __tablename__ = "t043t"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    togru: Mapped[str] = mapped_column(String(4), primary_key=True, default="")  # Tolerance group
    waers: Mapped[str] = mapped_column(String(5))  # Currency of the limits
    betrh: Mapped[Decimal] = mapped_column(Numeric(13, 2))  # Maximum amount per document
    betrp: Mapped[Decimal] = mapped_column(Numeric(13, 2))  # Maximum amount per open item (customer/vendor)
    sktpr: Mapped[Decimal] = mapped_column(Numeric(5, 2))  # Maximum cash discount percentage
    zubet: Mapped[Decimal] = mapped_column(Numeric(13, 2), default=Decimal("0"))  # Payment difference: amount
    zuprz: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))  # Payment difference: percent


class PaymentDifferenceReason(Base):
    """T053R — Reason code for payment differences (+ T053S text in txt40)."""

    __tablename__ = "t053r"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    rstgr: Mapped[str] = mapped_column(String(3), primary_key=True)  # Reason code
    txt40: Mapped[str] = mapped_column(String(40))  # Reason text
    xausb: Mapped[bool] = mapped_column(default=False)  # Charge off difference via separate G/L account


class AvailableAmount(Base):
    """T042Y — Amount available for outgoing payments from a house bank account."""

    __tablename__ = "t042y"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    zbukr: Mapped[str] = mapped_column(String(4), primary_key=True)  # Paying company code
    hbkid: Mapped[str] = mapped_column(String(5), primary_key=True)  # House bank
    hktid: Mapped[str] = mapped_column(String(5), primary_key=True)  # Account ID
    waers: Mapped[str] = mapped_column(String(5), primary_key=True)  # Currency
    bfbet: Mapped[Decimal] = mapped_column(Numeric(15, 2))  # Available amount for outgoing payments


class CheckLot(Base):
    """PCEC — Lot of prenumbered checks for a house bank account."""

    __tablename__ = "pcec"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    zbukr: Mapped[str] = mapped_column(String(4), primary_key=True)  # Paying company code
    hbkid: Mapped[str] = mapped_column(String(5), primary_key=True)  # House bank
    hktid: Mapped[str] = mapped_column(String(5), primary_key=True)  # Account ID
    stapl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Lot number
    fstap: Mapped[str] = mapped_column(String(13))  # First check number of the lot
    lstap: Mapped[str] = mapped_column(String(13))  # Last check number of the lot
    checl: Mapped[str | None] = mapped_column(String(13))  # Last check number used


class CheckRegister(Base):
    """PAYR — Check register (payment medium file for checks)."""

    __tablename__ = "payr"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    zbukr: Mapped[str] = mapped_column(String(4), primary_key=True)  # Paying company code
    hbkid: Mapped[str] = mapped_column(String(5), primary_key=True)  # House bank
    hktid: Mapped[str] = mapped_column(String(5), primary_key=True)  # Account ID
    rzawe: Mapped[str] = mapped_column(String(1), primary_key=True)  # Payment method
    chect: Mapped[str] = mapped_column(String(13), primary_key=True)  # Check number
    vblnr: Mapped[str | None] = mapped_column(String(10))  # Payment document number
    gjahr: Mapped[int | None] = mapped_column()  # Fiscal year of the payment document
    lifnr: Mapped[str | None] = mapped_column(String(10))  # Vendor (payee)
    znme1: Mapped[str | None] = mapped_column(String(35))  # Payee name
    rwbtr: Mapped[Decimal] = mapped_column(Numeric(15, 2))  # Amount paid
    waers: Mapped[str] = mapped_column(String(5))  # Currency
    zaldt: Mapped[date] = mapped_column()  # Payment date
    laufd: Mapped[date | None] = mapped_column()  # Payment run date
    laufi: Mapped[str | None] = mapped_column(String(6))  # Payment run identification
    voidr: Mapped[str | None] = mapped_column(String(2))  # Void reason code
    voidd: Mapped[date | None] = mapped_column()  # Voided on
    voidu: Mapped[str | None] = mapped_column(String(12))  # Voided by


class ValuationMethod(Base):
    """T044A — Valuation method: which exchange rate type values debit and credit balances.

    Non-key column names follow the OB59 screen and still need checking against
    the SAP data dictionary.
    """

    __tablename__ = "t044a"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bwmet: Mapped[str] = mapped_column(String(4), primary_key=True)  # Valuation method
    txt: Mapped[str] = mapped_column(String(40))  # Description
    kurst_s: Mapped[str] = mapped_column(String(4), default="M")  # Rate type for debit balances
    kurst_h: Mapped[str] = mapped_column(String(4), default="M")  # Rate type for credit balances
