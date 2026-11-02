"""Automatic payment program (F110) — run control and payment data.

Tables modelled here:
    REGUV  Payment run control: parameters and status of a run (LAUFD + LAUFI)
    REGUH  Payment data: one row per payee group (company code, vendor, method)
    REGUP  Payment data: the open items paid (or blocked) within a group

A run is identified by its run date (LAUFD) and identification (LAUFI). The
proposal fills REGUH/REGUP; the payment run posts one payment document per
REGUH group without exception and writes its number to VBLNR.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.documents import AMOUNT
from app.models.organizational import MANDT


class PaymentRunControl(Base):
    """REGUV — Payment run control (F110 parameters folded in)."""

    __tablename__ = "reguv"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    laufd: Mapped[date] = mapped_column(primary_key=True)  # Run date
    laufi: Mapped[str] = mapped_column(String(6), primary_key=True)  # Run identification
    zbukr: Mapped[str] = mapped_column(String(4))  # Paying company code (parameter)
    zwels: Mapped[str] = mapped_column(String(10))  # Payment methods to use (parameter)
    zaldt: Mapped[date] = mapped_column()  # Posting date of the payment documents (parameter)
    nedat: Mapped[date] = mapped_column()  # Next payment run date (parameter)
    cpudt: Mapped[date] = mapped_column()  # Documents entered up to (parameter)
    lifnr_low: Mapped[str | None] = mapped_column(String(10))  # Vendor selection from (parameter)
    lifnr_high: Mapped[str | None] = mapped_column(String(10))  # Vendor selection to (parameter)
    xvore: Mapped[bool] = mapped_column(default=False)  # Proposal run carried out
    xecht: Mapped[bool] = mapped_column(default=False)  # Payment run carried out
    usnam: Mapped[str] = mapped_column(String(12), default="SYSTEM")  # User
    vorer: Mapped[datetime | None] = mapped_column()  # Proposal created at
    echer: Mapped[datetime | None] = mapped_column()  # Payment run executed at

    payees: Mapped[list["PaymentRunPayee"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
        order_by="[PaymentRunPayee.lifnr, PaymentRunPayee.zlsch]",
    )


class PaymentRunPayee(Base):
    """REGUH — Payment data per payee (one payment document per row)."""

    __tablename__ = "reguh"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "laufd", "laufi"], ["reguv.mandt", "reguv.laufd", "reguv.laufi"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    laufd: Mapped[date] = mapped_column(primary_key=True)  # Run date
    laufi: Mapped[str] = mapped_column(String(6), primary_key=True)  # Run identification
    zbukr: Mapped[str] = mapped_column(String(4), primary_key=True)  # Paying company code
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Vendor
    zlsch: Mapped[str] = mapped_column(String(1), primary_key=True)  # Payment method ('' = none found)
    name1: Mapped[str | None] = mapped_column(String(35))  # Payee name
    waers: Mapped[str] = mapped_column(String(5))  # Payment currency
    zaldt: Mapped[date] = mapped_column()  # Payment (posting) date
    hbkid: Mapped[str | None] = mapped_column(String(5))  # House bank
    hktid: Mapped[str | None] = mapped_column(String(5))  # House bank account ID
    ubknt: Mapped[str | None] = mapped_column(String(18))  # Our bank account number
    ubiban: Mapped[str | None] = mapped_column(String(34))  # Our IBAN
    ukont: Mapped[str | None] = mapped_column(String(10))  # G/L account posted (bank / sub-account)
    zbnks: Mapped[str | None] = mapped_column(String(3))  # Payee bank country
    zbnkl: Mapped[str | None] = mapped_column(String(15))  # Payee bank key
    zbnkn: Mapped[str | None] = mapped_column(String(18))  # Payee bank account number
    ziban: Mapped[str | None] = mapped_column(String(34))  # Payee IBAN
    zswif: Mapped[str | None] = mapped_column(String(11))  # Payee SWIFT/BIC
    rwbtr: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Amount paid (payment currency)
    rskon: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Cash discount taken
    vblnr: Mapped[str | None] = mapped_column(String(10))  # Payment document number
    gjahr: Mapped[int | None] = mapped_column()  # Fiscal year of the payment document
    # Why the group is not paid (proposal exception list). Not an SAP column:
    # SAP keeps this in the F110 application log.
    exception: Mapped[str | None] = mapped_column(String(120))

    run: Mapped["PaymentRunControl"] = relationship(back_populates="payees")
    items: Mapped[list["PaymentRunItem"]] = relationship(
        back_populates="payee", cascade="all, delete-orphan",
        order_by="[PaymentRunItem.gjahr, PaymentRunItem.belnr, PaymentRunItem.buzei]",
    )


class PaymentRunItem(Base):
    """REGUP — Paid (or blocked) open item within a payee group."""

    __tablename__ = "regup"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mandt", "laufd", "laufi", "zbukr", "lifnr", "zlsch"],
            ["reguh.mandt", "reguh.laufd", "reguh.laufi", "reguh.zbukr", "reguh.lifnr", "reguh.zlsch"],
        ),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    laufd: Mapped[date] = mapped_column(primary_key=True)  # Run date
    laufi: Mapped[str] = mapped_column(String(6), primary_key=True)  # Run identification
    zbukr: Mapped[str] = mapped_column(String(4), primary_key=True)  # Paying company code
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Vendor
    zlsch: Mapped[str] = mapped_column(String(1), primary_key=True)  # Payment method of the group
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code of the item
    belnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Document number
    gjahr: Mapped[int] = mapped_column(primary_key=True)  # Fiscal year
    buzei: Mapped[int] = mapped_column(primary_key=True)  # Line item
    shkzg: Mapped[str] = mapped_column(String(1))  # Debit/credit indicator of the item
    wrbtr: Mapped[Decimal] = mapped_column(AMOUNT)  # Open amount, invoices positive / credit memos negative
    wskto: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Cash discount taken
    faedt: Mapped[date | None] = mapped_column()  # Net due date
    zlspr: Mapped[str | None] = mapped_column(String(1))  # Payment block of the item
    xblnr: Mapped[str | None] = mapped_column(String(16))  # Reference document (invoice number)
    sgtxt: Mapped[str | None] = mapped_column(String(50))  # Item text

    payee: Mapped["PaymentRunPayee"] = relationship(back_populates="items")
