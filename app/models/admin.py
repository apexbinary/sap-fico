"""Administration — company setup.

Tables modelled here (SAP Business One names):
    OADM   Company details (local and system currency, company name)
    OCRN   Currencies
    ORTT   Exchange rates (local currency per unit of a foreign currency, per day)
    OFPR   Posting periods
    NNM1   Document numbering series per object type
    OVTG   Tax (VAT) groups
    OCTG   Payment terms

B1 table and field names are used throughout. B1 keys most master data by a
code (AcctCode, CardCode, ItemCode) and documents by an internal DocEntry
plus a visible DocNum from a numbering series.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

AMOUNT = Numeric(19, 6)  # B1 stores amounts with 6 decimals
RATE = Numeric(19, 6)


class Company(Base):
    """OADM — Company details (one row)."""

    __tablename__ = "oadm"

    code: Mapped[int] = mapped_column("Code", primary_key=True, default=1)
    company_name: Mapped[str] = mapped_column("CompnyName", String(100))  # Company name
    main_curncy: Mapped[str] = mapped_column("MainCurncy", String(3))  # Local currency
    sys_curncy: Mapped[str] = mapped_column("SysCurrncy", String(3))  # System currency
    country: Mapped[str | None] = mapped_column("Country", String(3))  # Country
    state: Mapped[str | None] = mapped_column("State", String(3))  # State (GST: place of business)
    tax_id: Mapped[str | None] = mapped_column("TaxIdNum", String(32))  # Federal tax ID
    address: Mapped[str | None] = mapped_column("CompnyAddr", String(254))  # Address
    phone: Mapped[str | None] = mapped_column("Phone1", String(20))  # Telephone
    phone2: Mapped[str | None] = mapped_column("Phone2", String(20))  # Telephone 2
    fax: Mapped[str | None] = mapped_column("Fax", String(20))
    e_mail: Mapped[str | None] = mapped_column("E_Mail", String(100))
    manager: Mapped[str | None] = mapped_column("Manager", String(100))  # Manager / contact


class Currency(Base):
    """OCRN — Currency."""

    __tablename__ = "ocrn"

    curr_code: Mapped[str] = mapped_column("CurrCode", String(3), primary_key=True)
    curr_name: Mapped[str] = mapped_column("CurrName", String(20))
    iso: Mapped[str | None] = mapped_column("ISOCurrCod", String(3))
    decimals: Mapped[int] = mapped_column("Decimals", default=2)


class ExchangeRate(Base):
    """ORTT — Exchange rate of a foreign currency on a date (local currency per unit)."""

    __tablename__ = "ortt"

    rate_date: Mapped[date] = mapped_column("RateDate", primary_key=True)
    currency: Mapped[str] = mapped_column("Currency", String(3), primary_key=True)
    rate: Mapped[Decimal] = mapped_column("Rate", RATE)


class PostingPeriod(Base):
    """OFPR — Posting period (one per month); PeriodStat N unlocked, Y locked, C closing."""

    __tablename__ = "ofpr"

    abs_entry: Mapped[int] = mapped_column("AbsEntry", primary_key=True)
    code: Mapped[str] = mapped_column("Code", String(20), unique=True)  # e.g. 2026-11
    name: Mapped[str] = mapped_column("Name", String(20))
    f_ref_date: Mapped[date] = mapped_column("F_RefDate")  # Posting date from
    t_ref_date: Mapped[date] = mapped_column("T_RefDate")  # Posting date to
    category: Mapped[str] = mapped_column("Category", String(10))  # Period category (fiscal year)
    period_stat: Mapped[str] = mapped_column("PeriodStat", String(1), default="N")
    f_due_date: Mapped[date | None] = mapped_column("F_DueDate")  # Due date from
    t_due_date: Mapped[date | None] = mapped_column("T_DueDate")  # Due date to
    f_tax_date: Mapped[date | None] = mapped_column("F_TaxDate")  # Document date from
    t_tax_date: Mapped[date | None] = mapped_column("T_TaxDate")  # Document date to


class NumberingSeries(Base):
    """NNM1 — Numbering series of a document object type."""

    __tablename__ = "nnm1"

    object_code: Mapped[str] = mapped_column("ObjectCode", String(20), primary_key=True)  # e.g. 13 A/R invoice
    series: Mapped[int] = mapped_column("Series", primary_key=True)
    series_name: Mapped[str] = mapped_column("SeriesName", String(8))
    initial_num: Mapped[int] = mapped_column("InitialNum")
    next_number: Mapped[int] = mapped_column("NextNumber")
    last_num: Mapped[int | None] = mapped_column("LastNum")
    is_default: Mapped[bool] = mapped_column("IsDefault", default=True)


class TaxGroup(Base):
    """OVTG — Tax group (VAT): output tax for sales, input tax for purchasing."""

    __tablename__ = "ovtg"

    code: Mapped[str] = mapped_column("Code", String(8), primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(30))
    category: Mapped[str] = mapped_column("Category", String(1))  # O output (sales), I input (purchasing)
    rate: Mapped[Decimal] = mapped_column("Rate", Numeric(19, 6))  # Percent
    account: Mapped[str] = mapped_column("Account", String(15))  # Tax G/L account
    inactive: Mapped[bool] = mapped_column("Inactive", default=False)
    effec_date: Mapped[date | None] = mapped_column("EffecDate")  # Effective from


class PaymentTerms(Base):
    """OCTG — Payment terms: due date = document date + extra months + extra days."""

    __tablename__ = "octg"

    group_num: Mapped[int] = mapped_column("GroupNum", primary_key=True)
    pymnt_group: Mapped[str] = mapped_column("PymntGroup", String(100))  # Name
    extra_month: Mapped[int] = mapped_column("ExtraMonth", default=0)
    extra_days: Mapped[int] = mapped_column("ExtraDays", default=0)
    discount_pct: Mapped[Decimal] = mapped_column("VolumDscnt", Numeric(19, 6), default=Decimal("0"))  # Total discount %
    bsline_date: Mapped[str] = mapped_column("BslineDate", String(1), default="P", server_default="P")  # Due date based on: P posting, T document date, S system date
    pay_du_month: Mapped[str] = mapped_column("PayDuMonth", String(1), default="N", server_default="N")  # Start from: N posting date, S month start, H half month, E month end
    tol_days: Mapped[int] = mapped_column("TolDays", default=0, server_default="0")  # Tolerance days
    list_num: Mapped[int | None] = mapped_column("ListNum")  # Default price list
    cred_limit: Mapped[Decimal] = mapped_column("CredLimit", Numeric(19, 6), default=Decimal("0"), server_default="0")  # Max. credit
    oblig_limit: Mapped[Decimal] = mapped_column("ObligLimit", Numeric(19, 6), default=Decimal("0"), server_default="0")  # Commitment limit
    cdc_code: Mapped[str | None] = mapped_column("CdcCode", String(8))  # Cash discount (OCDC)
    inst_num: Mapped[int] = mapped_column("InstNum", default=0, server_default="0")  # Number of installments (CTG1)


class PaymentTermsInstallment(Base):
    """CTG1 — Installment of payment terms: due months / days after the base date and its share."""

    __tablename__ = "ctg1"

    ctg_code: Mapped[int] = mapped_column("CTGCode", ForeignKey("octg.GroupNum"), primary_key=True)
    ints_no: Mapped[int] = mapped_column("IntsNo", primary_key=True)  # Installment number (1..n)
    inst_month: Mapped[int] = mapped_column("InstMonth", default=0)
    inst_days: Mapped[int] = mapped_column("InstDays", default=0)
    inst_prcnt: Mapped[Decimal] = mapped_column("InstPrcnt", Numeric(19, 6))  # Share of the total %


class DunningTerm(Base):
    """ODUT — Dunning term: levels (DUT1) and the annual interest on arrears."""

    __tablename__ = "odut"

    code: Mapped[str] = mapped_column("Code", String(8), primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(50))
    interest: Mapped[Decimal] = mapped_column("Interest", Numeric(19, 6), default=Decimal("0"))  # % p.a. on arrears
    highest: Mapped[str] = mapped_column("Highest", String(1), default="N")  # Y: straight to the highest level due
    days_between: Mapped[int] = mapped_column("DaysBtwn", default=7, server_default="7")  # minimum days between letters


class DunningLevel(Base):
    """DUT1 — Level of a dunning term: reached after a number of days overdue, with a fee and a letter."""

    __tablename__ = "dut1"

    term_code: Mapped[str] = mapped_column("TermCode", String(8), ForeignKey("odut.Code"), primary_key=True)
    level: Mapped[int] = mapped_column("Level", primary_key=True)  # 1..n
    days: Mapped[int] = mapped_column("Days")  # effective after days overdue
    fee: Mapped[Decimal] = mapped_column("Fee", Numeric(19, 6), default=Decimal("0"))  # LC
    min_balance: Mapped[Decimal] = mapped_column("MinBal", Numeric(19, 6), default=Decimal("0"))  # minimum overdue total
    letter_text: Mapped[str | None] = mapped_column("LetterText", String(1000))


class CashDiscount(Base):
    """OCDC — Cash discount: discount % when paid within a number of days (tiers in CDC1)."""

    __tablename__ = "ocdc"

    code: Mapped[str] = mapped_column("Code", String(8), primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(30))
    by_date: Mapped[str] = mapped_column("ByDate", String(1), default="N")  # N: days counted from the document date


class CashDiscountLine(Base):
    """CDC1 — Tier of a cash discount: paid within NumOfDays -> Discount %."""

    __tablename__ = "cdc1"

    cdc_code: Mapped[str] = mapped_column("CdcCode", String(8), ForeignKey("ocdc.Code"), primary_key=True)
    line_id: Mapped[int] = mapped_column("LineId", primary_key=True)
    num_of_days: Mapped[int] = mapped_column("NumOfDays")
    discount: Mapped[Decimal] = mapped_column("Discount", Numeric(19, 6))  # %


class Country(Base):
    """OCRY — Countries (dropdown of every country field)."""

    __tablename__ = "ocry"

    code: Mapped[str] = mapped_column("Code", String(3), primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(100))


class State(Base):
    """OCST — States of a country (dropdown of the state fields)."""

    __tablename__ = "ocst"

    country: Mapped[str] = mapped_column("Country", String(3), primary_key=True)
    code: Mapped[str] = mapped_column("Code", String(3), primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(100))
    gst_code: Mapped[str | None] = mapped_column("GSTCode", String(2))  # India: GST state code (first digits of the GSTIN)


class TaxType(Base):
    """OSTT — Tax type (India: CGST, SGST, IGST, Cess)."""

    __tablename__ = "ostt"

    code: Mapped[str] = mapped_column("Code", String(8), primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(50))


class TaxAuthority(Base):
    """OSTA — Tax authority of a tax type with its output and input accounts."""

    __tablename__ = "osta"

    code: Mapped[str] = mapped_column("Code", String(8), primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(50))
    type: Mapped[str | None] = mapped_column("Type", String(8), ForeignKey("ostt.Code"))  # Tax type
    sales_tax: Mapped[str] = mapped_column("SalesTax", String(15))  # Output tax account
    purch_tax: Mapped[str] = mapped_column("PurchTax", String(15))  # Input tax account


class TaxComponent(Base):
    """STC1 — Component of a tax code: tax authority and its rate (CGST 9 % + SGST 9 % = 18 %)."""

    __tablename__ = "stc1"

    stc_code: Mapped[str] = mapped_column("STCCode", String(8), ForeignKey("ovtg.Code"), primary_key=True)  # Tax code
    line: Mapped[int] = mapped_column("Line", primary_key=True)
    sta_code: Mapped[str] = mapped_column("STACode", String(8), ForeignKey("osta.Code"))  # Tax authority
    efctiv_rate: Mapped[Decimal] = mapped_column("EfctivRate", Numeric(19, 6))  # Component rate %


class HsnCode(Base):
    """OCHP — HSN (goods) / SAC (services) code that items are classified by (India)."""

    __tablename__ = "ochp"

    abs_entry: Mapped[int] = mapped_column("AbsEntry", primary_key=True)
    chapter_id: Mapped[str] = mapped_column("ChapterID", String(20), unique=True)  # HSN / SAC code
    dscription: Mapped[str] = mapped_column("Dscription", String(254))
    item_type: Mapped[str] = mapped_column("ItemType", String(1), default="I", server_default="I")  # I goods (HSN), S services (SAC)


class TaxDetermination(Base):
    """OTCD — Tax code determination rule: the first matching active rule (lowest priority number)
    decides a line's tax code when the user does not enter one. Empty conditions match everything.

    Not B1-verified: B1 stores the conditions as generic key fields; the columns here are named
    after the conditions instead.
    """

    __tablename__ = "otcd"

    abs_id: Mapped[int] = mapped_column("AbsId", primary_key=True)
    priority: Mapped[int] = mapped_column("Priority", default=10)
    doc_area: Mapped[str] = mapped_column("DocArea", String(1), default="S")  # S sales, P purchasing
    card_code: Mapped[str | None] = mapped_column("CardCode", String(15))
    group_code: Mapped[int | None] = mapped_column("GroupCode")  # BP group
    item_code: Mapped[str | None] = mapped_column("ItemCode", String(50))
    itms_grp_cod: Mapped[int | None] = mapped_column("ItmsGrpCod")
    chapter_id: Mapped[str | None] = mapped_column("ChapterID", String(20))  # HSN / SAC
    state: Mapped[str | None] = mapped_column("State", String(3))  # place-of-supply state
    supply: Mapped[str | None] = mapped_column("Supply", String(1))  # I intra-state, O inter-state
    tax_code: Mapped[str] = mapped_column("TaxCode", String(8), ForeignKey("ovtg.Code"))
    descr: Mapped[str | None] = mapped_column("Descr", String(100))
    active: Mapped[str] = mapped_column("Active", String(1), default="Y")


class SalesEmployee(Base):
    """OSLP — Sales employees / buyers (documents and business partners)."""

    __tablename__ = "oslp"

    slp_code: Mapped[int] = mapped_column("SlpCode", primary_key=True)  # -1 = "No Sales Employee"
    slp_name: Mapped[str] = mapped_column("SlpName", String(155))
    memo: Mapped[str | None] = mapped_column("Memo", String(50))
    commission: Mapped[Decimal] = mapped_column("Commission", Numeric(19, 6), default=Decimal("0"))  # Commission %
    telephone: Mapped[str | None] = mapped_column("Telephone", String(20))
    email: Mapped[str | None] = mapped_column("Email", String(100))
    active: Mapped[str] = mapped_column("Active", String(1), default="Y")


class Project(Base):
    """OPRJ — Projects (journal entries and documents)."""

    __tablename__ = "oprj"

    prj_code: Mapped[str] = mapped_column("PrjCode", String(20), primary_key=True)
    prj_name: Mapped[str] = mapped_column("PrjName", String(100))
    valid_from: Mapped[date | None] = mapped_column("ValidFrom")
    valid_to: Mapped[date | None] = mapped_column("ValidTo")
    active: Mapped[str] = mapped_column("Active", String(1), default="Y")


class TransactionCode(Base):
    """OTRC — Transaction codes of journal entries."""

    __tablename__ = "otrc"

    trns_code: Mapped[str] = mapped_column("TrnsCode", String(4), primary_key=True)
    trns_cod_dsc: Mapped[str] = mapped_column("TrnsCodDsc", String(30))
