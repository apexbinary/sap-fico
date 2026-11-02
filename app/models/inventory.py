"""Inventory master data.

Tables modelled here (SAP Business One names):
    OITB   Item groups (with the G/L accounts of their items)
    OITM   Item master data
    OWHS   Warehouses
    OITW   Item stock per warehouse
    OPLN   Price lists (a list can derive from a base list by a factor)
    ITM1   Item prices per price list

Items are valued at a company-wide moving average price (OITM-EvalSystem A):
StockValue is the exact inventory value and AvgPrice = StockValue / OnHand. G/L accounts for stock postings come from the item group (GLMethod C,
B1's "set G/L accounts by item group"); OnHand / IsCommited / OnOrder are kept
per item and per warehouse by the documents.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.admin import AMOUNT

QTY = Numeric(19, 6)


class ItemGroup(Base):
    """OITB — Item group with its G/L accounts."""

    __tablename__ = "oitb"

    itms_grp_cod: Mapped[int] = mapped_column("ItmsGrpCod", primary_key=True)
    itms_grp_nam: Mapped[str] = mapped_column("ItmsGrpNam", String(20))
    bal_invnt_ac: Mapped[str] = mapped_column("BalInvntAc", String(15))  # Inventory account
    sale_cost_ac: Mapped[str] = mapped_column("SaleCostAc", String(15))  # Cost of goods sold
    revenues_ac: Mapped[str] = mapped_column("RevenuesAc", String(15))  # Revenue account
    expenses_ac: Mapped[str] = mapped_column("ExpensesAc", String(15))  # Expense account (non-inventory purchases)
    price_dif_ac: Mapped[str] = mapped_column("PriceDifAc", String(15))  # Price difference account


class Item(Base):
    """OITM — Item master data."""

    __tablename__ = "oitm"

    item_code: Mapped[str] = mapped_column("ItemCode", String(50), primary_key=True)
    item_name: Mapped[str] = mapped_column("ItemName", String(100))
    frgn_name: Mapped[str | None] = mapped_column("FrgnName", String(100))  # Foreign name
    item_type: Mapped[str] = mapped_column("ItemType", String(1), default="I", server_default="I")  # I items, L labor, T travel
    code_bars: Mapped[str | None] = mapped_column("CodeBars", String(254))  # Bar code
    firm_code: Mapped[int | None] = mapped_column("FirmCode")  # Manufacturer (OMRC)
    supp_cat_num: Mapped[str | None] = mapped_column("SuppCatNum", String(50))  # Mfr catalog no.
    buy_unit_msr: Mapped[str | None] = mapped_column("BuyUnitMsr", String(100))  # Purchasing UoM
    num_in_buy: Mapped[Decimal] = mapped_column("NumInBuy", QTY, default=Decimal("1"), server_default="1")  # Items per purchase unit
    sal_unit_msr: Mapped[str | None] = mapped_column("SalUnitMsr", String(100))  # Sales UoM
    num_in_sale: Mapped[Decimal] = mapped_column("NumInSale", QTY, default=Decimal("1"), server_default="1")  # Items per sales unit
    by_wh: Mapped[str] = mapped_column("ByWh", String(1), default="N", server_default="N")  # Manage min/max by warehouse
    max_level: Mapped[Decimal] = mapped_column("MaxLevel", QTY, default=Decimal("0"), server_default="0")  # Maximum inventory
    reorder_qty: Mapped[Decimal] = mapped_column("ReorderQty", QTY, default=Decimal("0"), server_default="0")  # Required (reorder) quantity
    lead_time: Mapped[int | None] = mapped_column("LeadTime")  # Lead time (days)
    min_ordr_qty: Mapped[Decimal] = mapped_column("MinOrdrQty", QTY, default=Decimal("0"), server_default="0")  # Minimum order quantity
    man_ser_num: Mapped[str] = mapped_column("ManSerNum", String(1), default="N", server_default="N")  # Manage serial numbers
    man_btch_num: Mapped[str] = mapped_column("ManBtchNum", String(1), default="N", server_default="N")  # Manage batch numbers
    user_text: Mapped[str | None] = mapped_column("UserText", String(254))  # Remarks
    itms_grp_cod: Mapped[int] = mapped_column("ItmsGrpCod", ForeignKey("oitb.ItmsGrpCod"))
    invnt_item: Mapped[str] = mapped_column("InvntItem", String(1), default="Y")  # Inventory item
    sell_item: Mapped[str] = mapped_column("SellItem", String(1), default="Y")  # Sales item
    prchse_item: Mapped[str] = mapped_column("PrchseItem", String(1), default="Y")  # Purchase item
    eval_system: Mapped[str] = mapped_column("EvalSystem", String(1), default="A")  # A moving average
    gl_method: Mapped[str] = mapped_column("GLMethod", String(1), default="C")  # C by item group
    invntry_uom: Mapped[str | None] = mapped_column("InvntryUom", String(20))  # Inventory unit
    vat_gourp_sa: Mapped[str | None] = mapped_column("VatGourpSa", String(8))  # Sales tax group (B1 spelling)
    vat_group_pu: Mapped[str | None] = mapped_column("VatGroupPu", String(8))  # Purchase tax group
    dflt_wh: Mapped[str | None] = mapped_column("DfltWH", String(8))  # Default warehouse
    card_code: Mapped[str | None] = mapped_column("CardCode", String(15))  # Preferred vendor
    min_level: Mapped[Decimal] = mapped_column("MinLevel", QTY, default=Decimal("0"))  # Minimum stock
    on_hand: Mapped[Decimal] = mapped_column("OnHand", QTY, default=Decimal("0"))  # In stock
    is_commited: Mapped[Decimal] = mapped_column("IsCommited", QTY, default=Decimal("0"))  # Committed (open sales orders)
    on_order: Mapped[Decimal] = mapped_column("OnOrder", QTY, default=Decimal("0"))  # Ordered (open purchase orders)
    avg_price: Mapped[Decimal] = mapped_column("AvgPrice", AMOUNT, default=Decimal("0"))  # Moving average price
    stock_value: Mapped[Decimal] = mapped_column("StockValue", AMOUNT, default=Decimal("0"))  # Inventory value (LC)
    last_pur_prc: Mapped[Decimal] = mapped_column("LastPurPrc", AMOUNT, default=Decimal("0"))  # Last purchase price
    frozen_for: Mapped[str] = mapped_column("frozenFor", String(1), default="N")  # Inactive (B1 spelling)


class Manufacturer(Base):
    """OMRC — Manufacturers."""

    __tablename__ = "omrc"

    firm_code: Mapped[int] = mapped_column("FirmCode", primary_key=True)  # -1 = "- No Manufacturer -"
    firm_name: Mapped[str] = mapped_column("FirmName", String(30))


class Warehouse(Base):
    """OWHS — Warehouse."""

    __tablename__ = "owhs"

    whs_code: Mapped[str] = mapped_column("WhsCode", String(8), primary_key=True)
    whs_name: Mapped[str] = mapped_column("WhsName", String(100))
    street: Mapped[str | None] = mapped_column("Street", String(100))
    city: Mapped[str | None] = mapped_column("City", String(100))
    block: Mapped[str | None] = mapped_column("Block", String(100))
    zip_code: Mapped[str | None] = mapped_column("ZipCode", String(20))
    county: Mapped[str | None] = mapped_column("County", String(100))
    state: Mapped[str | None] = mapped_column("State", String(3))
    country: Mapped[str | None] = mapped_column("Country", String(3))
    building: Mapped[str | None] = mapped_column("Building", String(100))
    drop_ship: Mapped[str] = mapped_column("DropShip", String(1), default="N", server_default="N")  # Drop-ship warehouse
    nettable: Mapped[str] = mapped_column("Nettable", String(1), default="Y", server_default="Y")  # Counts for MRP
    inactive: Mapped[str] = mapped_column("Inactive", String(1), default="N")


class ItemWarehouse(Base):
    """OITW — Stock of an item in a warehouse."""

    __tablename__ = "oitw"

    item_code: Mapped[str] = mapped_column("ItemCode", String(50), ForeignKey("oitm.ItemCode"), primary_key=True)
    whs_code: Mapped[str] = mapped_column("WhsCode", String(8), ForeignKey("owhs.WhsCode"), primary_key=True)
    on_hand: Mapped[Decimal] = mapped_column("OnHand", QTY, default=Decimal("0"))
    is_commited: Mapped[Decimal] = mapped_column("IsCommited", QTY, default=Decimal("0"))
    on_order: Mapped[Decimal] = mapped_column("OnOrder", QTY, default=Decimal("0"))
    min_stock: Mapped[Decimal] = mapped_column("MinStock", QTY, default=Decimal("0"))
    max_stock: Mapped[Decimal] = mapped_column("MaxStock", QTY, default=Decimal("0"), server_default="0")
    locked: Mapped[str] = mapped_column("Locked", String(1), default="N", server_default="N")  # Item locked in this warehouse


class PriceList(Base):
    """OPLN — Price list; without an own price an item takes base list price x factor."""

    __tablename__ = "opln"

    list_num: Mapped[int] = mapped_column("ListNum", primary_key=True)
    list_name: Mapped[str] = mapped_column("ListName", String(32))
    base_num: Mapped[int] = mapped_column("BASE_NUM")  # Base price list (itself for a base list)
    factor: Mapped[Decimal] = mapped_column("Factor", Numeric(19, 6), default=Decimal("1"))
    prim_curr: Mapped[str | None] = mapped_column("PrimCurr", String(3))  # Primary currency
    valid_for: Mapped[str] = mapped_column("ValidFor", String(1), default="Y", server_default="Y")  # Active


class ItemPrice(Base):
    """ITM1 — Price of an item in a price list."""

    __tablename__ = "itm1"

    item_code: Mapped[str] = mapped_column("ItemCode", String(50), ForeignKey("oitm.ItemCode"), primary_key=True)
    price_list: Mapped[int] = mapped_column("PriceList", ForeignKey("opln.ListNum"), primary_key=True)
    price: Mapped[Decimal] = mapped_column("Price", AMOUNT)
    currency: Mapped[str] = mapped_column("Currency", String(3))
