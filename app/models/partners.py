"""Business partners.

Tables modelled here (SAP Business One names):
    OCRG   Business partner groups
    OCRD   Business partner master data (customers C, vendors S, leads L)
    OCPR   Contact persons

Each partner posts to its control account (DebPayAcct, an A/R or A/P control
account of the chart of accounts). OCRD-Balance is the partner's account
balance in local currency (debit positive), kept by the journal entry engine.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.admin import AMOUNT


class PartnerGroup(Base):
    """OCRG — Business partner group."""

    __tablename__ = "ocrg"

    group_code: Mapped[int] = mapped_column("GroupCode", primary_key=True)
    group_name: Mapped[str] = mapped_column("GroupName", String(20))
    group_type: Mapped[str] = mapped_column("GroupType", String(1))  # C customers, S vendors


class BusinessPartner(Base):
    """OCRD — Business partner master data."""

    __tablename__ = "ocrd"

    card_code: Mapped[str] = mapped_column("CardCode", String(15), primary_key=True)
    card_name: Mapped[str] = mapped_column("CardName", String(100))
    card_f_name: Mapped[str | None] = mapped_column("CardFName", String(100))  # Foreign name
    card_type: Mapped[str] = mapped_column("CardType", String(1))  # C customer, S vendor (supplier), L lead
    group_code: Mapped[int | None] = mapped_column("GroupCode", ForeignKey("ocrg.GroupCode"))
    currency: Mapped[str] = mapped_column("Currency", String(3), default="##")  # ## all currencies
    deb_pay_acct: Mapped[str] = mapped_column("DebPayAcct", String(15))  # Control account
    group_num: Mapped[int | None] = mapped_column("GroupNum")  # Payment terms (OCTG)
    list_num: Mapped[int | None] = mapped_column("ListNum")  # Price list (OPLN)
    vat_group: Mapped[str | None] = mapped_column("VatGroup", String(8))  # Default tax group
    lic_trad_num: Mapped[str | None] = mapped_column("LicTradNum", String(32))  # Federal tax ID
    phone1: Mapped[str | None] = mapped_column("Phone1", String(20))
    phone2: Mapped[str | None] = mapped_column("Phone2", String(20))
    cellular: Mapped[str | None] = mapped_column("Cellular", String(50))  # Mobile phone
    fax: Mapped[str | None] = mapped_column("Fax", String(20))
    e_mail: Mapped[str | None] = mapped_column("E_Mail", String(100))
    intrnt_site: Mapped[str | None] = mapped_column("IntrntSite", String(100))  # Web site
    slp_code: Mapped[int | None] = mapped_column("SlpCode")  # Sales employee / buyer (OSLP)
    project_cod: Mapped[str | None] = mapped_column("ProjectCod", String(20))  # BP project
    bill_to_def: Mapped[str | None] = mapped_column("BillToDef", String(50))  # Default bill-to address (CRD1)
    ship_to_def: Mapped[str | None] = mapped_column("ShipToDef", String(50))  # Default ship-to address (CRD1)
    discount: Mapped[Decimal] = mapped_column("Discount", AMOUNT, default=Decimal("0"), server_default="0")  # Total discount %
    debt_line: Mapped[Decimal] = mapped_column("DebtLine", AMOUNT, default=Decimal("0"), server_default="0")  # Commitment limit
    free_text: Mapped[str | None] = mapped_column("Free_Text", String(254))  # Remarks tab
    address: Mapped[str | None] = mapped_column("Address", String(100))  # Bill-to street
    zip_code: Mapped[str | None] = mapped_column("ZipCode", String(20))
    city: Mapped[str | None] = mapped_column("City", String(100))
    country: Mapped[str | None] = mapped_column("Country", String(3))
    cntct_prsn: Mapped[str | None] = mapped_column("CntctPrsn", String(90))  # Default contact person
    credit_line: Mapped[Decimal] = mapped_column("CreditLine", AMOUNT, default=Decimal("0"))  # Credit limit
    balance: Mapped[Decimal] = mapped_column("Balance", AMOUNT, default=Decimal("0"))  # Account balance (LC)
    dnotes_bal: Mapped[Decimal] = mapped_column("DNotesBal", AMOUNT, default=Decimal("0"))  # Open deliveries / receipts
    orders_bal: Mapped[Decimal] = mapped_column("OrdersBal", AMOUNT, default=Decimal("0"))  # Open orders
    frozen_for: Mapped[str] = mapped_column("FrozenFor", String(1), default="N")  # Inactive
    notes: Mapped[str | None] = mapped_column("Notes", String(100))


class ContactPerson(Base):
    """OCPR — Contact person of a business partner."""

    __tablename__ = "ocpr"

    cntct_code: Mapped[int] = mapped_column("CntctCode", primary_key=True)
    card_code: Mapped[str] = mapped_column("CardCode", String(15), ForeignKey("ocrd.CardCode"))
    name: Mapped[str] = mapped_column("Name", String(50))  # Contact ID
    first_name: Mapped[str | None] = mapped_column("FirstName", String(50))
    middle_name: Mapped[str | None] = mapped_column("MiddleName", String(50))
    last_name: Mapped[str | None] = mapped_column("LastName", String(50))
    title: Mapped[str | None] = mapped_column("Title", String(10))
    position: Mapped[str | None] = mapped_column("Position", String(90))
    address: Mapped[str | None] = mapped_column("Address", String(100))
    tel1: Mapped[str | None] = mapped_column("Tel1", String(20))
    tel2: Mapped[str | None] = mapped_column("Tel2", String(20))
    cellolar: Mapped[str | None] = mapped_column("Cellolar", String(50))  # Mobile phone (B1 spelling)
    fax: Mapped[str | None] = mapped_column("Fax", String(20))
    e_mail: Mapped[str | None] = mapped_column("E_MailL", String(100))
    notes1: Mapped[str | None] = mapped_column("Notes1", String(100))  # Remarks 1
    active: Mapped[str] = mapped_column("Active", String(1), default="Y", server_default="Y")


class PartnerAddress(Base):
    """CRD1 — Bill-to (B) and ship-to (S) addresses of a business partner."""

    __tablename__ = "crd1"

    card_code: Mapped[str] = mapped_column("CardCode", String(15), ForeignKey("ocrd.CardCode"), primary_key=True)
    adres_type: Mapped[str] = mapped_column("AdresType", String(1), primary_key=True)  # B bill-to, S ship-to
    address: Mapped[str] = mapped_column("Address", String(50), primary_key=True)  # Address ID
    street: Mapped[str | None] = mapped_column("Street", String(100))
    block: Mapped[str | None] = mapped_column("Block", String(100))
    zip_code: Mapped[str | None] = mapped_column("ZipCode", String(20))
    city: Mapped[str | None] = mapped_column("City", String(100))
    county: Mapped[str | None] = mapped_column("County", String(100))
    state: Mapped[str | None] = mapped_column("State", String(3))
    country: Mapped[str | None] = mapped_column("Country", String(3))
    building: Mapped[str | None] = mapped_column("Building", String(100))
    gst_regn_no: Mapped[str | None] = mapped_column("GSTRegnNo", String(15))  # India: GSTIN of this address
    gst_type: Mapped[str | None] = mapped_column("GstType", String(1))  # India: R regular, U unregistered, C composition, E SEZ
