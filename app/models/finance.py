"""Financials — chart of accounts, journal entries, G/L account determination.

Tables modelled here (SAP Business One names):
    OACT   G/L accounts (chart of accounts as a tree of title and active accounts)
    OJDT   Journal entry header
    JDT1   Journal entry lines
    OACP   G/L account determination (default accounts per posting period category)

Every posting in B1 — a manual journal entry or the automatic entry of a
delivery, invoice or payment — is one OJDT/JDT1 journal entry. A line on a
business partner carries the partner in ShortName and the partner's control
account in Account; its open amount (BalDueDeb / BalDueCred) is reduced when
the line is reconciled, e.g. by a payment.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.admin import AMOUNT

# OACT-GroupMask: drawer of the chart of accounts
DRAWERS = {1: "Assets", 2: "Liabilities", 3: "Capital and Reserves", 4: "Turnover", 5: "Cost of Sales",
           6: "Operating Costs", 7: "Non-Operating Income and Expenditure", 8: "Taxation and Extraordinary Items",
           9: "Other"}
BALANCE_SHEET_DRAWERS = {1, 2, 3}


class Account(Base):
    """OACT — G/L account. Title accounts (Postable N) structure the tree; active accounts take postings."""

    __tablename__ = "oact"

    acct_code: Mapped[str] = mapped_column("AcctCode", String(15), primary_key=True)
    acct_name: Mapped[str] = mapped_column("AcctName", String(100))
    group_mask: Mapped[int] = mapped_column("GroupMask")  # Drawer 1-9 (assets ... other)
    father_num: Mapped[str | None] = mapped_column("FatherNum", String(15))  # Parent title account
    levels: Mapped[int] = mapped_column("Levels")  # Level in the tree (1 = drawer)
    postable: Mapped[str] = mapped_column("Postable", String(1), default="Y")  # Y active account, N title
    act_type: Mapped[str] = mapped_column("ActType", String(1), default="N")  # I revenue, E expenditure, N other
    loc_man_tran: Mapped[str] = mapped_column("LocManTran", String(1), default="N")  # Control account (BP postings)
    finanse: Mapped[str] = mapped_column("Finanse", String(1), default="N")  # Cash account
    act_curr: Mapped[str] = mapped_column("ActCurr", String(3), default="##")  # Account currency (## all)
    curr_total: Mapped[Decimal] = mapped_column("CurrTotal", AMOUNT, default=Decimal("0"))  # Balance (LC)
    frozen: Mapped[str] = mapped_column("FrozenFor", String(1), default="N")  # Inactive
    frgn_name: Mapped[str | None] = mapped_column("FrgnName", String(100))  # Foreign name
    details: Mapped[str | None] = mapped_column("Details", String(254))  # Remarks
    bloc_man_pos: Mapped[str] = mapped_column("BlocManPos", String(1), default="N", server_default="N")  # Block manual posting
    project: Mapped[str | None] = mapped_column("Project", String(20))  # Default project


class JournalEntry(Base):
    """OJDT — Journal entry header."""

    __tablename__ = "ojdt"

    trans_id: Mapped[int] = mapped_column("TransId", primary_key=True)
    number: Mapped[int] = mapped_column("Number")  # Journal entry number (series 30)
    ref_date: Mapped[date] = mapped_column("RefDate")  # Posting date
    due_date: Mapped[date] = mapped_column("DueDate")  # Due date
    tax_date: Mapped[date] = mapped_column("TaxDate")  # Document date
    memo: Mapped[str | None] = mapped_column("Memo", String(50))  # Remarks
    ref1: Mapped[str | None] = mapped_column("Ref1", String(100))  # Reference 1 (source DocNum)
    ref2: Mapped[str | None] = mapped_column("Ref2", String(100))  # Reference 2
    ref3: Mapped[str | None] = mapped_column("Ref3", String(27))  # Reference 3
    trans_code: Mapped[str | None] = mapped_column("TransCode", String(4))  # Transaction code (OTRC)
    project: Mapped[str | None] = mapped_column("Project", String(20))
    series: Mapped[int | None] = mapped_column("Series")  # Numbering series (NNM1)
    storno_date: Mapped[date | None] = mapped_column("StornoDate")  # Reversal date (Reverse checkbox)
    trans_type: Mapped[str] = mapped_column("TransType", String(20))  # Source object type (30 manual, 13 A/R invoice ...)
    base_ref: Mapped[str | None] = mapped_column("BaseRef", String(11))  # Source document number
    created_by: Mapped[int | None] = mapped_column("CreatedBy")  # Source DocEntry
    loc_total: Mapped[Decimal] = mapped_column("LocTotal", AMOUNT)  # Total (LC)
    fc_total: Mapped[Decimal] = mapped_column("FcTotal", AMOUNT, default=Decimal("0"))  # Total (FC)
    trans_curr: Mapped[str | None] = mapped_column("TransCurr", String(3))  # Foreign currency of the entry
    storno_to_tr: Mapped[int | None] = mapped_column("StornoToTr")  # Reversed by / reversal of
    auto_storno: Mapped[str] = mapped_column("AutoStorno", String(1), default="N")  # Reversal entry
    user_sign: Mapped[str] = mapped_column("UserSign", String(25), default="manager")  # User

    lines: Mapped[list["JournalLine"]] = relationship(back_populates="entry", cascade="all, delete-orphan",
                                                      order_by="JournalLine.line_id")


class JournalLine(Base):
    """JDT1 — Journal entry line."""

    __tablename__ = "jdt1"

    trans_id: Mapped[int] = mapped_column("TransId", ForeignKey("ojdt.TransId"), primary_key=True)
    line_id: Mapped[int] = mapped_column("Line_ID", primary_key=True)
    account: Mapped[str] = mapped_column("Account", String(15))  # G/L account (control account for BPs)
    short_name: Mapped[str] = mapped_column("ShortName", String(15))  # BP code, or the G/L account again
    contra_act: Mapped[str | None] = mapped_column("ContraAct", String(15))  # Offset account / BP
    debit: Mapped[Decimal] = mapped_column("Debit", AMOUNT, default=Decimal("0"))  # Debit (LC)
    credit: Mapped[Decimal] = mapped_column("Credit", AMOUNT, default=Decimal("0"))  # Credit (LC)
    fc_debit: Mapped[Decimal] = mapped_column("FCDebit", AMOUNT, default=Decimal("0"))  # Debit (FC)
    fc_credit: Mapped[Decimal] = mapped_column("FCCredit", AMOUNT, default=Decimal("0"))  # Credit (FC)
    fc_currency: Mapped[str | None] = mapped_column("FCCurrency", String(3))
    bal_due_deb: Mapped[Decimal] = mapped_column("BalDueDeb", AMOUNT, default=Decimal("0"))  # Open debit (BP lines)
    bal_due_cred: Mapped[Decimal] = mapped_column("BalDueCred", AMOUNT, default=Decimal("0"))  # Open credit
    bal_fc_deb: Mapped[Decimal] = mapped_column("BalFcDeb", AMOUNT, default=Decimal("0"), server_default="0")  # Open debit (FC)
    bal_fc_cred: Mapped[Decimal] = mapped_column("BalFcCred", AMOUNT, default=Decimal("0"), server_default="0")  # Open credit (FC)
    extr_match: Mapped[int | None] = mapped_column("ExtrMatch")  # External (bank) reconciliation number (OMTH)
    dunn_level: Mapped[int] = mapped_column("DunnLevel", default=0, server_default="0")  # Dunning level of the open item
    dun_date: Mapped[date | None] = mapped_column("DunDate")  # Last dunning date
    mth_date: Mapped[date | None] = mapped_column("MthDate")  # Date of the external reconciliation
    line_memo: Mapped[str | None] = mapped_column("LineMemo", String(50))
    ref_date: Mapped[date] = mapped_column("RefDate")
    due_date: Mapped[date] = mapped_column("DueDate")
    trans_type: Mapped[str] = mapped_column("TransType", String(20))
    created_by: Mapped[int | None] = mapped_column("CreatedBy")  # Source DocEntry
    base_ref: Mapped[str | None] = mapped_column("BaseRef", String(11))  # Source DocNum
    vat_group: Mapped[str | None] = mapped_column("VatGroup", String(8))  # Tax group of a tax line
    project: Mapped[str | None] = mapped_column("Project", String(20))
    ref1: Mapped[str | None] = mapped_column("Ref1", String(100))  # Line reference 1
    ref2: Mapped[str | None] = mapped_column("Ref2", String(100))  # Line reference 2
    ref3_line: Mapped[str | None] = mapped_column("Ref3Line", String(27))  # Line reference 3

    entry: Mapped["JournalEntry"] = relationship(back_populates="lines")


class AccountDetermination(Base):
    """OACP — G/L account determination: default accounts for automatic postings.

    One row per posting period category (fiscal year). B1 has many more
    default accounts; the column names here are descriptive and not B1's.
    """

    __tablename__ = "oacp"

    period_cat: Mapped[str] = mapped_column("PeriodCat", String(10), primary_key=True)
    ar_control: Mapped[str] = mapped_column("ArCtrlAcct", String(15))  # Accounts receivable (default control)
    ap_control: Mapped[str] = mapped_column("ApCtrlAcct", String(15))  # Accounts payable (default control)
    revenue: Mapped[str] = mapped_column("RevenueAcct", String(15))  # Revenue
    cogs: Mapped[str] = mapped_column("CogsAcct", String(15))  # Cost of goods sold
    inventory: Mapped[str] = mapped_column("InventoryAcct", String(15))  # Inventory
    allocation: Mapped[str] = mapped_column("AllocationAcct", String(15))  # Goods received not invoiced
    price_diff: Mapped[str] = mapped_column("PriceDiffAcct", String(15))  # Price difference on A/P invoices
    expense: Mapped[str] = mapped_column("ExpenseAcct", String(15))  # Expense (non-inventory purchases)
    inv_offset_inc: Mapped[str] = mapped_column("InvOffsetIncAcct", String(15))  # Goods receipt offset
    inv_offset_dec: Mapped[str] = mapped_column("InvOffsetDecAcct", String(15))  # Goods issue offset
    exch_gain: Mapped[str] = mapped_column("ExchGainAcct", String(15))  # Realized exchange gain
    exch_loss: Mapped[str] = mapped_column("ExchLossAcct", String(15))  # Realized exchange loss
    opening_bal: Mapped[str] = mapped_column("OpenBalAcct", String(15))  # Opening balances offset
    bank_charges: Mapped[str] = mapped_column("BankChgAcct", String(15), server_default="613000")  # Bank charges
    checks_received: Mapped[str] = mapped_column("ChecksRcvdAcct", String(15), server_default="117000")  # Incoming checks
    unreal_gain: Mapped[str] = mapped_column("UnrlzGainAcct", String(15), server_default="713000")  # Unrealized exchange gain
    unreal_loss: Mapped[str] = mapped_column("UnrlzLossAcct", String(15), server_default="714000")  # Unrealized exchange loss
    cash_disc_allowed: Mapped[str] = mapped_column("CashDiscAlwAcct", String(15), server_default="615000")  # Customers' cash discount
    cash_disc_received: Mapped[str] = mapped_column("CashDiscRcvAcct", String(15), server_default="722000")  # Vendors' cash discount
    dunning_interest: Mapped[str] = mapped_column("DunIntrstAcct", String(15), server_default="721000")  # Interest on arrears
    dunning_fee: Mapped[str] = mapped_column("DunFeeAcct", String(15), server_default="723000")  # Dunning fees


class ExchangeRateRun(Base):
    """OEXR — Exchange rate differences run: revaluation of open FC items of business partners
    (unrealized, reversed on StornoDate) or of FC G/L accounts (permanent) on a date.

    Not B1-verified: B1 posts the journal entries of the run; this table keeps the run and its lines.
    """

    __tablename__ = "oexr"

    abs_entry: Mapped[int] = mapped_column("AbsEntry", primary_key=True)
    run_date: Mapped[date] = mapped_column("RunDate")
    category: Mapped[str] = mapped_column("Category", String(1))  # B business partner open items, G G/L accounts in FC
    storno_date: Mapped[date | None] = mapped_column("StornoDate")  # Reversal date (business partners)
    trans_id: Mapped[int | None] = mapped_column("TransId")
    total_gain: Mapped[Decimal] = mapped_column("TotalGain", AMOUNT, default=Decimal("0"))
    total_loss: Mapped[Decimal] = mapped_column("TotalLoss", AMOUNT, default=Decimal("0"))
    lines: Mapped[list["ExchangeRateRunLine"]] = relationship(order_by="ExchangeRateRunLine.line_num",
                                                              cascade="all, delete-orphan")


class ExchangeRateRunLine(Base):
    """EXR1 — Line of an exchange rate differences run: one open item or one FC G/L account."""

    __tablename__ = "exr1"

    abs_entry: Mapped[int] = mapped_column("AbsEntry", ForeignKey("oexr.AbsEntry"), primary_key=True)
    line_num: Mapped[int] = mapped_column("LineNum", primary_key=True)
    short_name: Mapped[str] = mapped_column("ShortName", String(15))  # BP code or G/L account
    account: Mapped[str] = mapped_column("Account", String(15))  # control account / G/L account posted
    trans_id: Mapped[int | None] = mapped_column("TransId")  # revalued open item (JDT1)
    line_id: Mapped[int | None] = mapped_column("Line_ID")
    currency: Mapped[str] = mapped_column("Currency", String(3))
    open_fc: Mapped[Decimal] = mapped_column("OpenFC", AMOUNT)
    open_lc: Mapped[Decimal] = mapped_column("OpenLC", AMOUNT)
    rate: Mapped[Decimal] = mapped_column("Rate", AMOUNT)
    new_lc: Mapped[Decimal] = mapped_column("NewLC", AMOUNT)
    difference: Mapped[Decimal] = mapped_column("Difference", AMOUNT)  # new - open (LC)
