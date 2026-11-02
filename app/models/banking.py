"""Banking: incoming / outgoing payments, checks for receipt and deposits.

Tables modelled here (SAP Business One names):
    ORCT / OVPM   Incoming (24) / outgoing (46) payment header with the payment means:
                  cash (CashAcct, CashSum), bank transfer (TrsfrAcct, TrsfrSum, TrsfrDate,
                  TrsfrRef, BankChrg), checks total (CheckAcct, CheckSum), payment on
                  account (PayNoDoc, NoDocSum, OpenBal)
    RCT1 / VPM1   Checks of a payment
    RCT2 / VPM2   Paid open items (invoices, credit memos, journal entries, payments on account)
    RCT4 / VPM4   G/L account lines of an account payment (DocType A)
    OCHH          Checks for receipt (the register deposits draw from)
    ODPS          Deposits (checks or cash) to a bank account

A payment posts one journal entry: the means against the business partner (or the
G/L accounts). Its applied amounts reduce the open amounts (JDT1 BalDueDeb /
BalDueCred) of the paid items and their documents' PaidToDate; the rest stays open
on the payment's own partner line (payment on account).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.admin import AMOUNT


class PaymentHeader:
    """Columns shared by ORCT and OVPM."""

    doc_entry: Mapped[int] = mapped_column("DocEntry", primary_key=True)
    doc_num: Mapped[int] = mapped_column("DocNum")
    doc_type: Mapped[str] = mapped_column("DocType", String(1))  # C customer, S vendor, A account
    canceled: Mapped[str] = mapped_column("Canceled", String(1), default="N")
    obj_type: Mapped[str] = mapped_column("ObjType", String(20))
    series: Mapped[int | None] = mapped_column("Series")
    doc_date: Mapped[date] = mapped_column("DocDate", Date)  # Posting date
    doc_due_date: Mapped[date] = mapped_column("DocDueDate", Date)  # Due date
    tax_date: Mapped[date] = mapped_column("TaxDate", Date)  # Document date
    card_code: Mapped[str | None] = mapped_column("CardCode", String(15))
    card_name: Mapped[str | None] = mapped_column("CardName", String(100))
    address: Mapped[str | None] = mapped_column("Address", String(254))
    cntct_code: Mapped[int | None] = mapped_column("CntctCode")
    doc_curr: Mapped[str] = mapped_column("DocCurr", String(3))  # Payment currency
    doc_rate: Mapped[Decimal] = mapped_column("DocRate", AMOUNT, default=Decimal("1"))
    cash_acct: Mapped[str | None] = mapped_column("CashAcct", String(15))
    cash_sum: Mapped[Decimal] = mapped_column("CashSum", AMOUNT, default=Decimal("0"))  # LC
    cash_sum_fc: Mapped[Decimal] = mapped_column("CashSumFC", AMOUNT, default=Decimal("0"))
    trsfr_acct: Mapped[str | None] = mapped_column("TrsfrAcct", String(15))
    trsfr_sum: Mapped[Decimal] = mapped_column("TrsfrSum", AMOUNT, default=Decimal("0"))
    trsfr_sum_fc: Mapped[Decimal] = mapped_column("TrsfrSumFC", AMOUNT, default=Decimal("0"))
    trsfr_date: Mapped[date | None] = mapped_column("TrsfrDate", Date)
    trsfr_ref: Mapped[str | None] = mapped_column("TrsfrRef", String(27))
    bank_chrg: Mapped[Decimal] = mapped_column("BankChrg", AMOUNT, default=Decimal("0"))  # Bank charges (LC)
    check_acct: Mapped[str | None] = mapped_column("CheckAcct", String(15))
    check_sum: Mapped[Decimal] = mapped_column("CheckSum", AMOUNT, default=Decimal("0"))
    check_sum_fc: Mapped[Decimal] = mapped_column("CheckSumFC", AMOUNT, default=Decimal("0"))
    doc_total: Mapped[Decimal] = mapped_column("DocTotal", AMOUNT, default=Decimal("0"))  # Total (LC)
    doc_total_fc: Mapped[Decimal] = mapped_column("DocTotalFC", AMOUNT, default=Decimal("0"))
    pay_no_doc: Mapped[str] = mapped_column("PayNoDoc", String(1), default="N")  # Payment on account
    no_doc_sum: Mapped[Decimal] = mapped_column("NoDocSum", AMOUNT, default=Decimal("0"))  # Amount on account (LC)
    open_bal: Mapped[Decimal] = mapped_column("OpenBal", AMOUNT, default=Decimal("0"))  # Still open on account
    counter_ref: Mapped[str | None] = mapped_column("CounterRef", String(8))  # Reference
    ref2: Mapped[str | None] = mapped_column("Ref2", String(11))
    prj_code: Mapped[str | None] = mapped_column("PrjCode", String(20))  # Project
    comments: Mapped[str | None] = mapped_column("Comments", String(254))
    jrnl_memo: Mapped[str | None] = mapped_column("JrnlMemo", String(50))
    trans_id: Mapped[int | None] = mapped_column("TransId")


class PaymentCheck:
    """Columns shared by RCT1 and VPM1."""

    line_id: Mapped[int] = mapped_column("LineID", primary_key=True)
    due_date: Mapped[date] = mapped_column("DueDate", Date)
    check_num: Mapped[int] = mapped_column("CheckNum")
    bank_code: Mapped[str | None] = mapped_column("BankCode", String(30))
    branch: Mapped[str | None] = mapped_column("Branch", String(50))
    acct_num: Mapped[str | None] = mapped_column("AcctNum", String(50))
    country_cod: Mapped[str | None] = mapped_column("CountryCod", String(3))
    check_sum: Mapped[Decimal] = mapped_column("CheckSum", AMOUNT)  # Payment currency
    trnsfrable: Mapped[str] = mapped_column("Trnsfrable", String(1), default="N")  # Endorsable
    check_act: Mapped[str | None] = mapped_column("CheckAct", String(15))
    check_abs: Mapped[int | None] = mapped_column("CheckAbs")  # OCHH CheckKey (incoming checks)


class PaymentInvoice:
    """Columns shared by RCT2 and VPM2 (one paid open item)."""

    invoice_id: Mapped[int] = mapped_column("InvoiceId", primary_key=True)
    doc_entry: Mapped[int] = mapped_column("DocEntry")  # Paid document (or TransId of a journal entry)
    inv_type: Mapped[str] = mapped_column("InvType", String(20))  # 13, 14, 18, 19, 24, 46, 30 ...
    doc_trans_id: Mapped[int] = mapped_column("DocTransId")  # Journal entry of the paid item
    doc_line: Mapped[int] = mapped_column("DocLine")  # JDT1 Line_ID of the partner line
    sum_applied: Mapped[Decimal] = mapped_column("SumApplied", AMOUNT)  # LC; negative for credits
    applied_fc: Mapped[Decimal] = mapped_column("AppliedFC", AMOUNT, default=Decimal("0"))
    dcnt_sum: Mapped[Decimal] = mapped_column("DcntSum", AMOUNT, default=Decimal("0"))  # Cash discount (LC)
    inst_id: Mapped[int | None] = mapped_column("InstId")  # Paid installment of the document (INV6 / PCH6)


class PaymentAccount:
    """Columns shared by RCT4 and VPM4 (account payment lines)."""

    line_id: Mapped[int] = mapped_column("LineId", primary_key=True)
    acct_code: Mapped[str] = mapped_column("AcctCode", String(15))
    sum_applied: Mapped[Decimal] = mapped_column("SumApplied", AMOUNT)  # LC
    applied_fc: Mapped[Decimal] = mapped_column("AppliedFC", AMOUNT, default=Decimal("0"))
    descrip: Mapped[str | None] = mapped_column("Descrip", String(254))
    prj_code: Mapped[str | None] = mapped_column("PrjCode", String(20))


def _child(name: str, mixin: type, table: str, header: str, doc_col: str) -> type:
    return type(name, (mixin, Base), {
        "__tablename__": table,
        "__doc__": f"{table.upper()} - lines of {header.upper()}.",
        "doc_num": mapped_column(doc_col, Integer, ForeignKey(f"{header}.DocEntry"), primary_key=True),
    })


IncomingPaymentCheck = _child("IncomingPaymentCheck", PaymentCheck, "rct1", "orct", "DocNum")
IncomingPaymentInvoice = _child("IncomingPaymentInvoice", PaymentInvoice, "rct2", "orct", "DocNum")
IncomingPaymentAccount = _child("IncomingPaymentAccount", PaymentAccount, "rct4", "orct", "DocNum")
OutgoingPaymentCheck = _child("OutgoingPaymentCheck", PaymentCheck, "vpm1", "ovpm", "DocNum")
OutgoingPaymentInvoice = _child("OutgoingPaymentInvoice", PaymentInvoice, "vpm2", "ovpm", "DocNum")
OutgoingPaymentAccount = _child("OutgoingPaymentAccount", PaymentAccount, "vpm4", "ovpm", "DocNum")


class IncomingPayment(PaymentHeader, Base):
    """ORCT — Incoming payment (object 24)."""

    __tablename__ = "orct"
    checks = relationship(IncomingPaymentCheck, order_by=IncomingPaymentCheck.line_id, cascade="all, delete-orphan")
    invoices = relationship(IncomingPaymentInvoice, order_by=IncomingPaymentInvoice.invoice_id, cascade="all, delete-orphan")
    accounts = relationship(IncomingPaymentAccount, order_by=IncomingPaymentAccount.line_id, cascade="all, delete-orphan")


class OutgoingPayment(PaymentHeader, Base):
    """OVPM — Outgoing payment (object 46)."""

    __tablename__ = "ovpm"
    checks = relationship(OutgoingPaymentCheck, order_by=OutgoingPaymentCheck.line_id, cascade="all, delete-orphan")
    invoices = relationship(OutgoingPaymentInvoice, order_by=OutgoingPaymentInvoice.invoice_id, cascade="all, delete-orphan")
    accounts = relationship(OutgoingPaymentAccount, order_by=OutgoingPaymentAccount.line_id, cascade="all, delete-orphan")


PAYMENT_CLASSES = {"24": (IncomingPayment, IncomingPaymentCheck, IncomingPaymentInvoice, IncomingPaymentAccount),
                   "46": (OutgoingPayment, OutgoingPaymentCheck, OutgoingPaymentInvoice, OutgoingPaymentAccount)}


class CheckForReceipt(Base):
    """OCHH — Check received with an incoming payment, until it is deposited."""

    __tablename__ = "ochh"

    check_key: Mapped[int] = mapped_column("CheckKey", primary_key=True)
    check_num: Mapped[int] = mapped_column("CheckNum")
    bank_code: Mapped[str | None] = mapped_column("BankCode", String(30))
    branch: Mapped[str | None] = mapped_column("Branch", String(50))
    acct_num: Mapped[str | None] = mapped_column("AcctNum", String(50))
    check_date: Mapped[date] = mapped_column("CheckDate", Date)  # Due date of the check
    check_sum: Mapped[Decimal] = mapped_column("CheckSum", AMOUNT)  # LC
    currency: Mapped[str] = mapped_column("Currency", String(3))
    check_act: Mapped[str] = mapped_column("CheckAct", String(15))  # Checks received account
    card_code: Mapped[str | None] = mapped_column("CardCode", String(15))
    rcpt_num: Mapped[int] = mapped_column("RcptNum")  # ORCT DocEntry
    deposited: Mapped[str] = mapped_column("Deposited", String(1), default="N")  # N not, C deposited
    dpst_abs: Mapped[int | None] = mapped_column("DpstAbs")  # ODPS DeposId
    canceled: Mapped[str] = mapped_column("Canceled", String(1), default="N")


class Deposit(Base):
    """ODPS — Deposit of checks (K) or cash (C) to a bank account (object 25)."""

    __tablename__ = "odps"

    depos_id: Mapped[int] = mapped_column("DeposId", primary_key=True)
    depos_num: Mapped[int] = mapped_column("DeposNum")
    depos_type: Mapped[str] = mapped_column("DeposType", String(1))  # K checks, C cash
    depos_date: Mapped[date] = mapped_column("DeposDate", Date)
    depos_curr: Mapped[str] = mapped_column("DeposCurr", String(3))
    banck_acct: Mapped[str] = mapped_column("BanckAcct", String(15))  # Bank G/L account (B1 spelling)
    alloc_acct: Mapped[str | None] = mapped_column("AllocAcct", String(15))  # Cash account (cash deposit)
    loc_total: Mapped[Decimal] = mapped_column("LocTotal", AMOUNT)
    bank_acc_num: Mapped[str | None] = mapped_column("BankAccNum", String(50))  # Bank account no. (reference)
    memo: Mapped[str | None] = mapped_column("Memo", String(254))  # Journal remarks
    trans_abs: Mapped[int | None] = mapped_column("TransAbs")  # Journal entry
    canceled: Mapped[str] = mapped_column("Canceled", String(1), default="N")
    project: Mapped[str | None] = mapped_column("Project", String(20))


# ------------------------------------------------------------- bank statements and external reconciliation
class Bank(Base):
    """ODSC — Bank (house banks and partners' banks)."""

    __tablename__ = "odsc"

    abs_entry: Mapped[int] = mapped_column("AbsEntry", primary_key=True)
    bank_code: Mapped[str] = mapped_column("BankCode", String(30), unique=True)
    bank_name: Mapped[str] = mapped_column("BankName", String(250))
    country_cod: Mapped[str | None] = mapped_column("CountryCod", String(3))
    swift_num: Mapped[str | None] = mapped_column("SwiftNum", String(50))  # BIC / SWIFT


class HouseBankAccount(Base):
    """DSC1 — House bank account of the company, linked to its G/L bank account."""

    __tablename__ = "dsc1"

    abs_entry: Mapped[int] = mapped_column("AbsEntry", primary_key=True)
    bank_code: Mapped[str] = mapped_column("BankCode", String(30), ForeignKey("odsc.BankCode"))
    account: Mapped[str] = mapped_column("Account", String(50))  # Bank account number
    branch: Mapped[str | None] = mapped_column("Branch", String(50))  # Branch (India: IFSC)
    iban: Mapped[str | None] = mapped_column("IBAN", String(50))
    gl_account: Mapped[str] = mapped_column("GLAccount", String(15))  # G/L bank account
    acct_name: Mapped[str | None] = mapped_column("AcctName", String(250))
    country: Mapped[str | None] = mapped_column("Country", String(3))
    currency: Mapped[str | None] = mapped_column("Currency", String(3))


class BankStatement(Base):
    """OBNH — Bank statement of a G/L bank account with its opening and closing balance.

    Not B1-verified: B1 keeps the statement number on the rows (OBNK StatemNo); the header table
    holding the balances is named here OBNH.
    """

    __tablename__ = "obnh"

    abs_entry: Mapped[int] = mapped_column("AbsEntry", primary_key=True)
    acct_code: Mapped[str] = mapped_column("AcctCode", String(15))  # G/L bank account
    house_bank: Mapped[int | None] = mapped_column("HouseBank")  # DSC1 AbsEntry
    statem_no: Mapped[int] = mapped_column("StatemNo")  # Statement number per account
    stat_date: Mapped[date] = mapped_column("StatDate", Date)
    start_bal: Mapped[Decimal] = mapped_column("StartBal", AMOUNT)  # Opening balance
    end_bal: Mapped[Decimal] = mapped_column("EndBal", AMOUNT)  # Closing balance
    currency: Mapped[str] = mapped_column("Currency", String(3))
    data_source: Mapped[str] = mapped_column("DataSource", String(1), default="M")  # M manual, I imported
    rows = relationship("BankStatementRow", order_by="BankStatementRow.vis_order", cascade="all, delete-orphan")


class BankStatementRow(Base):
    """OBNK — Bank statement row (bank page): money in (CredAmnt) or out (DebAmount)."""

    __tablename__ = "obnk"

    sequence: Mapped[int] = mapped_column("Sequence", primary_key=True)
    statement: Mapped[int] = mapped_column("StatemAbs", ForeignKey("obnh.AbsEntry"))
    acct_code: Mapped[str] = mapped_column("AcctCode", String(15))
    statem_no: Mapped[int] = mapped_column("StatemNo")
    vis_order: Mapped[int] = mapped_column("VisOrder")
    due_date: Mapped[date] = mapped_column("DueDate", Date)  # Value date
    ref: Mapped[str | None] = mapped_column("Ref", String(100))  # Bank reference / cheque no.
    memo: Mapped[str | None] = mapped_column("Memo", String(254))
    deb_amount: Mapped[Decimal] = mapped_column("DebAmount", AMOUNT, default=Decimal("0"))  # Money out
    cred_amnt: Mapped[Decimal] = mapped_column("CredAmnt", AMOUNT, default=Decimal("0"))  # Money in
    extern_code: Mapped[str | None] = mapped_column("ExternCode", String(20))  # Bank transaction code
    card_code: Mapped[str | None] = mapped_column("CardCode", String(15))
    bank_match: Mapped[int | None] = mapped_column("BankMatch")  # External reconciliation number (OMTH)
    doc_num_type: Mapped[str | None] = mapped_column("DocNumType", String(20))  # Object posted from the row
    doc_num: Mapped[int | None] = mapped_column("DocNum")  # DocEntry / TransId posted from the row


class ExternalReconciliation(Base):
    """OMTH — External reconciliation: bank statement rows matched with G/L bank account lines."""

    __tablename__ = "omth"

    mth_num: Mapped[int] = mapped_column("MthNum", primary_key=True)
    mth_date: Mapped[date] = mapped_column("MthDate", Date)
    acct_code: Mapped[str] = mapped_column("AcctCode", String(15))
    total: Mapped[Decimal] = mapped_column("Total", AMOUNT)
    auto: Mapped[str] = mapped_column("Auto", String(1), default="N")  # Y automatic matching
    canceled: Mapped[str] = mapped_column("Canceled", String(1), default="N")
    lines = relationship("ExternalReconciliationLine", order_by="ExternalReconciliationLine.line_num",
                         cascade="all, delete-orphan")


class ExternalReconciliationLine(Base):
    """MTH1 — Line of an external reconciliation: a journal line or a bank statement row."""

    __tablename__ = "mth1"

    mth_num: Mapped[int] = mapped_column("MthNum", ForeignKey("omth.MthNum"), primary_key=True)
    line_num: Mapped[int] = mapped_column("LineNum", primary_key=True)
    trans_id: Mapped[int | None] = mapped_column("TransId")
    trans_row_id: Mapped[int | None] = mapped_column("TransRowId")  # JDT1 Line_ID
    bank_seq: Mapped[int | None] = mapped_column("BankSeq")  # OBNK Sequence
    recon_sum: Mapped[Decimal] = mapped_column("ReconSum", AMOUNT)  # +money in / -money out
