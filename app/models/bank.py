"""Bank Accounting (FI-BL).

Tables modelled here:
    BNKA    Bank master data (bank directory)
    T012    House banks
    T012K   House bank accounts
    FEBKO   Electronic bank statement — header
    FEBEP   Electronic bank statement — line items

A house bank account (T012K) links a bank account to a G/L account. Electronic
bank statement items (FEBEP) are reconciled against the bank G/L account and
posted to the sub-ledger via the FI posting engine.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.documents import AMOUNT
from app.models.organizational import MANDT


class Bank(Base):
    """BNKA — Bank master data."""

    __tablename__ = "bnka"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    banks: Mapped[str] = mapped_column(String(3), primary_key=True)  # Bank country key
    bankl: Mapped[str] = mapped_column(String(15), primary_key=True)  # Bank key (sort/routing code)
    banka: Mapped[str] = mapped_column(String(60))  # Name of bank
    provz: Mapped[str | None] = mapped_column(String(3))  # Region
    ort01: Mapped[str | None] = mapped_column(String(35))  # City
    stras: Mapped[str | None] = mapped_column(String(35))  # Street
    swift: Mapped[str | None] = mapped_column(String(11))  # SWIFT/BIC code
    bnklz: Mapped[str | None] = mapped_column(String(15))  # Bank number
    loevm: Mapped[bool] = mapped_column(default=False)  # Deletion flag


class HouseBank(Base):
    """T012 — House banks."""

    __tablename__ = "t012"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    hbkid: Mapped[str] = mapped_column(String(5), primary_key=True)  # House bank ID
    banks: Mapped[str] = mapped_column(String(3))  # Bank country
    bankl: Mapped[str] = mapped_column(String(15))  # Bank key
    bankn_default: Mapped[str | None] = mapped_column(String(18))  # Default account number
    swift: Mapped[str | None] = mapped_column(String(11))  # SWIFT/BIC
    bnkkz: Mapped[str | None] = mapped_column(String(1))  # Bank branch indicator


class HouseBankAccount(Base):
    """T012K — House bank accounts."""

    __tablename__ = "t012k"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mandt", "bukrs", "hbkid"],
            ["t012.mandt", "t012.bukrs", "t012.hbkid"],
        ),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    hbkid: Mapped[str] = mapped_column(String(5), primary_key=True)  # House bank ID
    hktid: Mapped[str] = mapped_column(String(5), primary_key=True)  # Account ID
    bankn: Mapped[str] = mapped_column(String(18))  # Bank account number
    iban: Mapped[str | None] = mapped_column(String(34))  # IBAN
    waers: Mapped[str] = mapped_column(String(5))  # Currency
    hkont: Mapped[str] = mapped_column(String(10))  # G/L account for the bank account
    hktid_clearing: Mapped[str | None] = mapped_column(String(10))  # Bank clearing (sub) account
    refzl: Mapped[str | None] = mapped_column(String(1))  # Reference for payment transactions


class BankStatementHeader(Base):
    """FEBKO — Electronic bank statement header."""

    __tablename__ = "febko"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kukey: Mapped[str] = mapped_column(String(12), primary_key=True)  # Short key for statement
    bukrs: Mapped[str] = mapped_column(String(4))  # Company code
    hbkid: Mapped[str | None] = mapped_column(String(5))  # House bank
    hktid: Mapped[str | None] = mapped_column(String(5))  # Account ID
    banks: Mapped[str | None] = mapped_column(String(3))  # Bank country
    bankl: Mapped[str | None] = mapped_column(String(15))  # Bank key
    bankn: Mapped[str | None] = mapped_column(String(18))  # Bank account number
    waers: Mapped[str | None] = mapped_column(String(5))  # Currency
    aznum: Mapped[str | None] = mapped_column(String(5))  # Statement number
    absnd: Mapped[str | None] = mapped_column(String(40))  # Sender
    adatu: Mapped[date | None] = mapped_column()  # Statement date
    anfsl: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Opening balance
    ensal: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Closing balance
    xbobl: Mapped[bool] = mapped_column(default=False)  # Fully posted


class BankStatementItem(Base):
    """FEBEP — Electronic bank statement line items."""

    __tablename__ = "febep"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kukey"], ["febko.mandt", "febko.kukey"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kukey: Mapped[str] = mapped_column(String(12), primary_key=True)  # Statement key
    esnum: Mapped[int] = mapped_column(primary_key=True)  # Line item number
    vgint: Mapped[str | None] = mapped_column(String(4))  # Internal transaction (posting rule)
    vgext: Mapped[str | None] = mapped_column(String(4))  # External business transaction code
    kwbtr: Mapped[Decimal] = mapped_column(AMOUNT)  # Amount in statement currency
    kwaer: Mapped[str | None] = mapped_column(String(5))  # Currency
    shkzg: Mapped[str] = mapped_column(String(1))  # Debit/credit (S/H)
    valut: Mapped[date | None] = mapped_column()  # Value date
    budat: Mapped[date | None] = mapped_column()  # Entry/posting date
    vwzw1: Mapped[str | None] = mapped_column(String(27))  # Note to payee 1 (reference)
    partn: Mapped[str | None] = mapped_column(String(35))  # Partner name
    kunnr: Mapped[str | None] = mapped_column(String(10))  # Matched customer
    lifnr: Mapped[str | None] = mapped_column(String(10))  # Matched vendor
    belnr: Mapped[str | None] = mapped_column(String(10))  # Posted FI document
    gjahr: Mapped[int | None] = mapped_column()  # Fiscal year
    xbenr: Mapped[bool] = mapped_column(default=False)  # Posted / cleared
    nbbln: Mapped[str | None] = mapped_column(String(10))  # Sub-ledger clearing document
