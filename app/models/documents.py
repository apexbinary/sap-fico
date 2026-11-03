"""Marketing and inventory documents, and the warehouse journal.

B1 stores every document type in its own header / lines table pair with the same
structure. Tables modelled here (SAP Business One names):

    Sales A/R        OQUT/QUT1 quotation (23)    ORDR/RDR1 order (17)
                     ODLN/DLN1 delivery (15)     ORDN/RDN1 return (16)
                     OINV/INV1 A/R invoice (13)  ORIN/RIN1 A/R credit memo (14)
    Purchasing A/P   OPQT/PQT1 purchase quotation (540000006)
                     OPOR/POR1 purchase order (22)   OPDN/PDN1 goods receipt PO (20)
                     ORPD/RPD1 goods return (21)     OPCH/PCH1 A/P invoice (18)
                     ORPC/RPC1 A/P credit memo (19)
    Inventory        OIGN/IGN1 goods receipt (59)    OIGE/IGE1 goods issue (60)
                     OWTR/WTR1 inventory transfer (67)
    OINM             warehouse journal: one row per stock movement or revaluation

Copy-from links a line to its base line (BaseType / BaseEntry / BaseLine); the
base line keeps the not yet copied quantity in OpenQty and closes (LineStatus C)
when nothing is open; the document closes (DocStatus C) when all lines are closed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.admin import AMOUNT
from app.models.inventory import QTY

RATE = AMOUNT


class DocumentHeader:
    """Columns shared by every document header table (OINV, ORDR, OPDN, OIGN, ...)."""

    doc_entry: Mapped[int] = mapped_column("DocEntry", primary_key=True)  # Internal key
    doc_num: Mapped[int] = mapped_column("DocNum")  # Document number (NNM1)
    doc_type: Mapped[str] = mapped_column("DocType", String(1), default="I")  # I items, S service
    canceled: Mapped[str] = mapped_column("CANCELED", String(1), default="N")  # Y canceled
    doc_status: Mapped[str] = mapped_column("DocStatus", String(1), default="O")  # O open, C closed
    obj_type: Mapped[str] = mapped_column("ObjType", String(20))
    doc_date: Mapped[date] = mapped_column("DocDate", Date)  # Posting date
    doc_due_date: Mapped[date] = mapped_column("DocDueDate", Date)  # Due / delivery date
    tax_date: Mapped[date] = mapped_column("TaxDate", Date)  # Document date
    card_code: Mapped[str | None] = mapped_column("CardCode", String(15))
    card_name: Mapped[str | None] = mapped_column("CardName", String(100))
    num_at_card: Mapped[str | None] = mapped_column("NumAtCard", String(100))  # BP reference no.
    address: Mapped[str | None] = mapped_column("Address", String(254))  # Bill-to address text
    address2: Mapped[str | None] = mapped_column("Address2", String(254))  # Ship-to address text
    pay_to_code: Mapped[str | None] = mapped_column("PayToCode", String(50))  # Bill-to address ID (CRD1)
    ship_to_code: Mapped[str | None] = mapped_column("ShipToCode", String(50))  # Ship-to address ID (CRD1)
    cntct_code: Mapped[int | None] = mapped_column("CntctCode")  # Contact person (OCPR)
    slp_code: Mapped[int | None] = mapped_column("SlpCode")  # Sales employee / buyer (OSLP)
    lic_trad_num: Mapped[str | None] = mapped_column("LicTradNum", String(32))  # BP federal tax ID
    project: Mapped[str | None] = mapped_column("Project", String(20))
    series: Mapped[int | None] = mapped_column("Series")  # Numbering series (NNM1)
    ref2: Mapped[str | None] = mapped_column("Ref2", String(11))  # Reference 2 (inventory documents)
    doc_cur: Mapped[str] = mapped_column("DocCur", String(3))
    doc_rate: Mapped[Decimal] = mapped_column("DocRate", RATE, default=Decimal("1"))
    group_num: Mapped[int | None] = mapped_column("GroupNum")  # Payment terms
    disc_prcnt: Mapped[Decimal] = mapped_column("DiscPrcnt", RATE, default=Decimal("0"))  # Header discount %
    disc_sum: Mapped[Decimal] = mapped_column("DiscSum", AMOUNT, default=Decimal("0"))
    vat_sum: Mapped[Decimal] = mapped_column("VatSum", AMOUNT, default=Decimal("0"))
    doc_total: Mapped[Decimal] = mapped_column("DocTotal", AMOUNT, default=Decimal("0"))  # Gross total
    paid_to_date: Mapped[Decimal] = mapped_column("PaidToDate", AMOUNT, default=Decimal("0"))
    disc_sum_fc: Mapped[Decimal] = mapped_column("DiscSumFC", AMOUNT, default=Decimal("0"), server_default="0")
    vat_sum_fc: Mapped[Decimal] = mapped_column("VatSumFC", AMOUNT, default=Decimal("0"), server_default="0")
    doc_total_fc: Mapped[Decimal] = mapped_column("DocTotalFC", AMOUNT, default=Decimal("0"), server_default="0")  # Gross total (FC)
    wt_sum: Mapped[Decimal] = mapped_column("WTSum", AMOUNT, default=Decimal("0"), server_default="0")  # Withholding tax (TDS), LC
    wt_sum_fc: Mapped[Decimal] = mapped_column("WTSumFC", AMOUNT, default=Decimal("0"), server_default="0")
    total_expns: Mapped[Decimal] = mapped_column("TotalExpns", AMOUNT, default=Decimal("0"), server_default="0")  # freight, net (LC)
    total_exp_fc: Mapped[Decimal] = mapped_column("TotalExpFC", AMOUNT, default=Decimal("0"), server_default="0")
    dpm_amnt: Mapped[Decimal] = mapped_column("DpmAmnt", AMOUNT, default=Decimal("0"), server_default="0")  # invoices: down payments drawn (LC)
    dpm_appl: Mapped[Decimal] = mapped_column("DpmAppl", AMOUNT, default=Decimal("0"), server_default="0")  # down payments: drawn on invoices
    paid_fc: Mapped[Decimal] = mapped_column("PaidFC", AMOUNT, default=Decimal("0"), server_default="0")  # Paid to date (FC)
    filler: Mapped[str | None] = mapped_column("Filler", String(8))  # From warehouse (transfer)
    to_whs_code: Mapped[str | None] = mapped_column("ToWhsCode", String(8))  # To warehouse (transfer)
    comments: Mapped[str | None] = mapped_column("Comments", String(254))
    jrnl_memo: Mapped[str | None] = mapped_column("JrnlMemo", String(50))
    trans_id: Mapped[int | None] = mapped_column("TransId")  # Journal entry (OJDT)
    user_sign: Mapped[int | None] = mapped_column("UserSign")


class DocumentLine:
    """Columns shared by every document line table (INV1, RDR1, PDN1, IGN1, ...)."""

    line_num: Mapped[int] = mapped_column("LineNum", primary_key=True)
    line_status: Mapped[str] = mapped_column("LineStatus", String(1), default="O")
    item_code: Mapped[str | None] = mapped_column("ItemCode", String(50))
    dscription: Mapped[str | None] = mapped_column("Dscription", String(100))  # B1 spelling
    quantity: Mapped[Decimal] = mapped_column("Quantity", QTY)
    open_qty: Mapped[Decimal] = mapped_column("OpenQty", QTY)  # Not yet copied to a target document
    price_bef_di: Mapped[Decimal] = mapped_column("PriceBefDi", AMOUNT)  # Unit price before discount (document currency)
    disc_prcnt: Mapped[Decimal] = mapped_column("DiscPrcnt", RATE, default=Decimal("0"))
    price: Mapped[Decimal] = mapped_column("Price", AMOUNT)  # Unit price after discount
    line_total: Mapped[Decimal] = mapped_column("LineTotal", AMOUNT)  # Net (LC), before header discount
    total_frgn: Mapped[Decimal] = mapped_column("TotalFrgn", AMOUNT, default=Decimal("0"), server_default="0")  # Net (FC)
    currency: Mapped[str | None] = mapped_column("Currency", String(3))  # Price currency of the line
    rate: Mapped[Decimal] = mapped_column("Rate", RATE, default=Decimal("0"), server_default="0")  # Line rate (FC lines)
    vat_group: Mapped[str | None] = mapped_column("VatGroup", String(8))
    vat_prcnt: Mapped[Decimal] = mapped_column("VatPrcnt", RATE, default=Decimal("0"))
    vat_sum: Mapped[Decimal] = mapped_column("VatSum", AMOUNT, default=Decimal("0"))
    gtotal: Mapped[Decimal] = mapped_column("GTotal", AMOUNT, default=Decimal("0"))  # Gross line total (LC)
    vat_sum_frgn: Mapped[Decimal] = mapped_column("VatSumFrgn", AMOUNT, default=Decimal("0"), server_default="0")
    gtotal_fc: Mapped[Decimal] = mapped_column("GTotalFC", AMOUNT, default=Decimal("0"), server_default="0")
    whs_code: Mapped[str | None] = mapped_column("WhsCode", String(8))
    from_whs_cod: Mapped[str | None] = mapped_column("FromWhsCod", String(8))  # Transfer: from warehouse
    acct_code: Mapped[str | None] = mapped_column("AcctCode", String(15))  # G/L account (service lines, offsets)
    unit_msr: Mapped[str | None] = mapped_column("unitMsr", String(100))
    num_per_msr: Mapped[Decimal] = mapped_column("NumPerMsr", QTY, default=Decimal("1"), server_default="1")  # inventory units per unit of the line
    ship_date: Mapped[date | None] = mapped_column("ShipDate", Date)  # Line delivery date
    free_txt: Mapped[str | None] = mapped_column("FreeTxt", String(100))  # Free text
    project: Mapped[str | None] = mapped_column("Project", String(20))
    slp_code: Mapped[int | None] = mapped_column("SlpCode")  # Sales employee of the line
    price_af_vat: Mapped[Decimal] = mapped_column("PriceAfVAT", AMOUNT, default=Decimal("0"), server_default="0")  # Gross price after discount
    stock_price: Mapped[Decimal] = mapped_column("StockPrice", AMOUNT, default=Decimal("0"))  # Item cost per unit
    grss_profit: Mapped[Decimal] = mapped_column("GrssProfit", AMOUNT, default=Decimal("0"))
    base_type: Mapped[str | None] = mapped_column("BaseType", String(20))  # Copied from: object type
    base_entry: Mapped[int | None] = mapped_column("BaseEntry")
    base_line: Mapped[int | None] = mapped_column("BaseLine")
    base_ref: Mapped[str | None] = mapped_column("BaseRef", String(16))  # Base document number
    target_type: Mapped[str | None] = mapped_column("TargetType", String(20))  # Last copied to
    trget_entry: Mapped[int | None] = mapped_column("TrgetEntry")  # B1 spelling


# (class prefix, object type, header table, line table)
DOCUMENT_TABLES = [
    ("SalesQuotation", "23", "oqut", "qut1"),
    ("SalesOrder", "17", "ordr", "rdr1"),
    ("Delivery", "15", "odln", "dln1"),
    ("SalesReturn", "16", "ordn", "rdn1"),
    ("ARInvoice", "13", "oinv", "inv1"),
    ("ARCreditMemo", "14", "orin", "rin1"),
    ("PurchaseQuotation", "540000006", "opqt", "pqt1"),
    ("PurchaseOrder", "22", "opor", "por1"),
    ("GoodsReceiptPO", "20", "opdn", "pdn1"),
    ("GoodsReturn", "21", "orpd", "rpd1"),
    ("APInvoice", "18", "opch", "pch1"),
    ("APCreditMemo", "19", "orpc", "rpc1"),
    ("ARDownPayment", "203", "odpi", "dpi1"),
    ("APDownPayment", "204", "odpo", "dpo1"),
    ("GoodsReceipt", "59", "oign", "ign1"),
    ("GoodsIssue", "60", "oige", "ige1"),
    ("InventoryTransfer", "67", "owtr", "wtr1"),
]

# object type -> (header class, line class)
DOCUMENT_CLASSES: dict[str, tuple[type, type]] = {}


def _define(prefix: str, obj: str, header: str, lines: str) -> tuple[type, type]:
    line_cls = type(f"{prefix}Line", (DocumentLine, Base), {
        "__tablename__": lines,
        "__doc__": f"{lines.upper()} - lines of {header.upper()}.",
        "doc_entry": mapped_column("DocEntry", Integer, ForeignKey(f"{header}.DocEntry"), primary_key=True),
    })
    header_cls = type(prefix, (DocumentHeader, Base), {
        "__tablename__": header,
        "__doc__": f"{header.upper()} - document header (object {obj}).",
        "lines": relationship(line_cls, order_by=line_cls.line_num, cascade="all, delete-orphan"),
    })
    return header_cls, line_cls


for _prefix, _obj, _header, _lines in DOCUMENT_TABLES:
    DOCUMENT_CLASSES[_obj] = _define(_prefix, _obj, _header, _lines)
    globals()[_prefix], globals()[f"{_prefix}Line"] = DOCUMENT_CLASSES[_obj]


class DocumentInstallment:
    """Columns shared by INV6 and PCH6: one installment (due date, amount, paid) of an invoice."""

    instlmnt_id: Mapped[int] = mapped_column("InstlmntID", primary_key=True)  # 1..n
    due_date: Mapped[date] = mapped_column("DueDate", Date)
    ins_total: Mapped[Decimal] = mapped_column("InsTotal", AMOUNT)  # LC
    ins_total_fc: Mapped[Decimal] = mapped_column("InsTotalFC", AMOUNT, default=Decimal("0"))
    paid_to_date: Mapped[Decimal] = mapped_column("PaidToDate", AMOUNT, default=Decimal("0"))
    paid_fc: Mapped[Decimal] = mapped_column("PaidFC", AMOUNT, default=Decimal("0"))
    status: Mapped[str] = mapped_column("Status", String(1), default="O")  # O open, C closed
    inst_prcnt: Mapped[Decimal] = mapped_column("InstPrcnt", RATE, default=Decimal("0"))


# object type -> installment class (A/R invoice INV6, A/P invoice PCH6)
DOCUMENT_INSTALLMENTS: dict[str, type] = {}
for _obj, _table, _header in (("13", "inv6", "oinv"), ("18", "pch6", "opch")):
    DOCUMENT_INSTALLMENTS[_obj] = type(f"{_table.upper()}Installment", (DocumentInstallment, Base), {
        "__tablename__": _table,
        "__doc__": f"{_table.upper()} - installments of {_header.upper()}.",
        "doc_entry": mapped_column("DocEntry", Integer, ForeignKey(f"{_header}.DocEntry"), primary_key=True),
    })


class DocumentExpense:
    """Columns shared by QUT3 ... RPC3: freight / additional expenses of a marketing document."""

    line_num: Mapped[int] = mapped_column("LineNum", primary_key=True)
    expns_code: Mapped[int] = mapped_column("ExpnsCode", Integer)  # OEXD
    line_total: Mapped[Decimal] = mapped_column("LineTotal", AMOUNT)  # net (LC)
    total_frgn: Mapped[Decimal] = mapped_column("TotalFrgn", AMOUNT, default=Decimal("0"))  # net (FC)
    vat_group: Mapped[str | None] = mapped_column("VatGroup", String(8))
    vat_prcnt: Mapped[Decimal] = mapped_column("VatPrcnt", RATE, default=Decimal("0"))
    vat_sum: Mapped[Decimal] = mapped_column("VatSum", AMOUNT, default=Decimal("0"))
    vat_sum_frgn: Mapped[Decimal] = mapped_column("VatSumFrgn", AMOUNT, default=Decimal("0"))
    grs_amount: Mapped[Decimal] = mapped_column("GrsAmount", AMOUNT, default=Decimal("0"))  # gross (LC)


# object type -> freight class; the header gets .expenses
FREIGHT_TABLES = [('23', 'qut3', 'oqut'), ('17', 'rdr3', 'ordr'), ('15', 'dln3', 'odln'), ('16', 'rdn3', 'ordn'), ('13', 'inv3', 'oinv'), ('14', 'rin3', 'orin'), ('540000006', 'pqt3', 'opqt'), ('22', 'por3', 'opor'), ('20', 'pdn3', 'opdn'), ('21', 'rpd3', 'orpd'), ('18', 'pch3', 'opch'), ('19', 'rpc3', 'orpc')]
DOCUMENT_EXPENSES: dict[str, type] = {}
for _obj, _table, _header in FREIGHT_TABLES:
    DOCUMENT_EXPENSES[_obj] = type(f"{_table.upper()}Expense", (DocumentExpense, Base), {
        "__tablename__": _table,
        "__doc__": f"{_table.upper()} - freight of {_header.upper()}.",
        "doc_entry": mapped_column("DocEntry", Integer, ForeignKey(f"{_header}.DocEntry"), primary_key=True),
    })
    DOCUMENT_CLASSES[_obj][0].expenses = relationship(DOCUMENT_EXPENSES[_obj], order_by=DOCUMENT_EXPENSES[_obj].line_num,
                                                      cascade="all, delete-orphan")


class DocumentDownPayment:
    """Columns shared by INV9 and PCH9: down payment drawn on an invoice, with the reconciled lines."""

    line_num: Mapped[int] = mapped_column("LineNum", primary_key=True)
    base_abs: Mapped[int] = mapped_column("BaseAbs", Integer)  # down payment document (ODPI / ODPO DocEntry)
    drawn_sum: Mapped[Decimal] = mapped_column("DrawnSum", AMOUNT)  # LC, gross
    pay_type: Mapped[str] = mapped_column("PayType", String(20))  # 24 incoming / 46 outgoing payment that paid it
    pay_entry: Mapped[int] = mapped_column("PayEntry", Integer)
    pay_trans: Mapped[int] = mapped_column("PayTrans", Integer)  # reconciled payment partner line (JDT1)
    pay_line: Mapped[int] = mapped_column("PayLine", Integer)
    doc_line: Mapped[int] = mapped_column("DocLine", Integer)  # reconciled invoice partner line (JDT1 Line_ID)


# object type -> down payments drawn class (A/R invoice INV9, A/P invoice PCH9)
DOCUMENT_DOWN_PAYMENTS: dict[str, type] = {}
for _obj, _table, _header in (("13", "inv9", "oinv"), ("18", "pch9", "opch")):
    DOCUMENT_DOWN_PAYMENTS[_obj] = type(f"{_table.upper()}DownPayment", (DocumentDownPayment, Base), {
        "__tablename__": _table,
        "__doc__": f"{_table.upper()} - down payments drawn on {_header.upper()}.",
        "doc_entry": mapped_column("DocEntry", Integer, ForeignKey(f"{_header}.DocEntry"), primary_key=True),
    })


class DocumentWithholding:
    """Columns shared by PCH5 and RPC5: withholding tax (TDS) of an A/P invoice / credit memo."""

    line_num: Mapped[int] = mapped_column("LineNum", primary_key=True)
    wt_code: Mapped[str] = mapped_column("WTCode", String(4))
    rate: Mapped[Decimal] = mapped_column("Rate", RATE)
    taxble_amnt: Mapped[Decimal] = mapped_column("TaxbleAmnt", AMOUNT)  # base (net, LC)
    wt_amnt: Mapped[Decimal] = mapped_column("WTAmnt", AMOUNT)  # deducted (LC, whole rupees)
    wt_amnt_fc: Mapped[Decimal] = mapped_column("WTAmntFC", AMOUNT, default=Decimal("0"))
    account: Mapped[str] = mapped_column("Account", String(15))
    category: Mapped[str] = mapped_column("Category", String(1), default="I")  # I invoice
    section: Mapped[str | None] = mapped_column("Section", String(10))  # India: TDS section (194C ...)
    no_pan: Mapped[str] = mapped_column("NoPAN", String(1), default="N")  # higher rate, section 206AA


# object type -> withholding tax class (A/P invoice PCH5, A/P credit memo RPC5)
DOCUMENT_WITHHOLDING: dict[str, type] = {}
for _obj, _table, _header in (("18", "pch5", "opch"), ("19", "rpc5", "orpc")):
    DOCUMENT_WITHHOLDING[_obj] = type(f"{_table.upper()}Withholding", (DocumentWithholding, Base), {
        "__tablename__": _table,
        "__doc__": f"{_table.upper()} - withholding tax of {_header.upper()}.",
        "doc_entry": mapped_column("DocEntry", Integer, ForeignKey(f"{_header}.DocEntry"), primary_key=True),
    })


class WarehouseJournal(Base):
    """OINM — Warehouse journal: every stock movement and revaluation with its value."""

    __tablename__ = "oinm"

    trans_num: Mapped[int] = mapped_column("TransNum", primary_key=True)
    doc_date: Mapped[date] = mapped_column("DocDate", Date)
    trans_type: Mapped[str] = mapped_column("TransType", String(20))  # Object type of the document
    created_by: Mapped[int] = mapped_column("CreatedBy")  # DocEntry of the document
    base_ref: Mapped[str] = mapped_column("BASE_REF", String(16))  # DocNum of the document
    doc_line_num: Mapped[int] = mapped_column("DocLineNum")
    item_code: Mapped[str] = mapped_column("ItemCode", String(50))
    warehouse: Mapped[str] = mapped_column("Warehouse", String(8))
    in_qty: Mapped[Decimal] = mapped_column("InQty", QTY, default=Decimal("0"))
    out_qty: Mapped[Decimal] = mapped_column("OutQty", QTY, default=Decimal("0"))
    price: Mapped[Decimal] = mapped_column("Price", AMOUNT, default=Decimal("0"))  # Unit value of the movement
    trans_value: Mapped[Decimal] = mapped_column("TransValue", AMOUNT, default=Decimal("0"))  # Change of stock value
    calc_price: Mapped[Decimal] = mapped_column("CalcPrice", AMOUNT, default=Decimal("0"))  # Item cost afterwards
    card_code: Mapped[str | None] = mapped_column("CardCode", String(15))
    jrnl_memo: Mapped[str | None] = mapped_column("JrnlMemo", String(50))
    trans_id: Mapped[int | None] = mapped_column("TransId")  # Journal entry of the document
