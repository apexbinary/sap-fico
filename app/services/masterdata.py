"""Business partner and item master data: validation, stock rows, price lookup."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import Currency, PaymentTerms, TaxGroup
from app.models.finance import Account
from app.models.inventory import Item, ItemGroup, ItemPrice, ItemWarehouse, PriceList, Warehouse
from app.models.partners import BusinessPartner, PartnerGroup
from app.services.admin import B1Error, check_project, check_sales_employee, company

CARD_TYPES = {"C": "Customer", "S": "Vendor", "L": "Lead"}


def _control_account(session: Session, code: str) -> Account:
    acct = session.get(Account, code)
    if acct is None or acct.postable != "Y" or acct.loc_man_tran != "Y":
        raise B1Error(f"G/L account {code} is not an active control account")
    return acct


def _tax_group(session: Session, code: str | None, category: str) -> None:
    if code is None:
        return
    tg = session.get(TaxGroup, code)
    if tg is None or tg.category != category or tg.inactive == "Y":
        kind = "an output" if category == "O" else "an input"
        raise B1Error(f"Tax group {code} is not {kind} tax group")


def check_country(session: Session, country: str | None, state: str | None = None) -> None:
    """Country (OCRY) and state (OCST) come from their dropdown tables."""
    from app.models.admin import Country, State

    if country and session.get(Country, country) is None:
        raise B1Error(f"Country {country} does not exist")
    if state:
        if not country or session.get(State, (country, state)) is None:
            raise B1Error(f"State {state} does not exist in country {country or '-'}")


GSTIN_FORMAT = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"


def check_gstin(session: Session, gstin: str | None, state: str | None) -> None:
    """India: a GSTIN has 15 characters and starts with the GST code of the address state."""
    import re

    from app.models.admin import State

    if not gstin:
        return
    if not re.match(GSTIN_FORMAT, gstin):
        raise B1Error(f"GSTIN {gstin} is not valid (15 characters: state code, PAN, entity, Z, check digit)")
    st = session.get(State, ("IN", state)) if state else None
    if st is not None and st.gst_code and gstin[:2] != st.gst_code:
        raise B1Error(f"GSTIN {gstin} does not belong to {st.name} (state code {st.gst_code})")


# ------------------------------------------------------------- business partners
@dataclass
class PartnerRequest:
    card_code: str
    card_name: str
    card_type: str
    group_code: int | None = None
    currency: str = "##"
    deb_pay_acct: str | None = None  # defaults to the A/R or A/P control account of the determination
    group_num: int | None = None
    list_num: int | None = None
    vat_group: str | None = None
    lic_trad_num: str | None = None
    phone1: str | None = None
    e_mail: str | None = None
    address: str | None = None
    zip_code: str | None = None
    city: str | None = None
    country: str | None = None
    cntct_prsn: str | None = None
    credit_line: Decimal = Decimal("0")
    notes: str | None = None
    card_f_name: str | None = None
    phone2: str | None = None
    cellular: str | None = None
    fax: str | None = None
    intrnt_site: str | None = None
    slp_code: int | None = None
    project_cod: str | None = None
    discount: Decimal = Decimal("0")
    debt_line: Decimal = Decimal("0")
    free_text: str | None = None


# fields copied unchanged from the request to OCRD
PARTNER_FIELDS = ["card_name", "card_type", "group_code", "currency", "group_num", "list_num", "vat_group",
                  "lic_trad_num", "phone1", "phone2", "cellular", "fax", "e_mail", "intrnt_site", "address",
                  "zip_code", "city", "country", "cntct_prsn", "credit_line", "notes", "card_f_name", "slp_code",
                  "project_cod", "discount", "debt_line", "free_text"]


def validate_partner_fields(session: Session, data: dict, card_type: str) -> None:
    """Checks shared by create and change."""
    if data.get("currency") not in (None, "##") and session.get(Currency, data["currency"]) is None:
        raise B1Error(f"Currency {data['currency']} does not exist")
    if data.get("group_num") is not None and session.get(PaymentTerms, data["group_num"]) is None:
        raise B1Error(f"Payment terms {data['group_num']} do not exist")
    if data.get("list_num") is not None:
        pl = session.get(PriceList, data["list_num"])
        if pl is None or pl.valid_for != "Y":
            raise B1Error(f"Price list {data['list_num']} does not exist or is inactive")
    _tax_group(session, data.get("vat_group"), "I" if card_type == "S" else "O")
    check_sales_employee(session, data.get("slp_code"))
    check_project(session, data.get("project_cod"))
    check_country(session, data.get("country"))
    for key in ("discount",):
        if data.get(key) is not None and not (0 <= Decimal(data[key]) < 100):
            raise B1Error("The total discount must be between 0 and 100 %")
    for key in ("credit_line", "debt_line"):
        if data.get(key) is not None and Decimal(data[key]) < 0:
            raise B1Error("Credit and commitment limits cannot be negative")


def create_partner(session: Session, req: PartnerRequest, *, commit: bool = True) -> BusinessPartner:
    from app.models.finance import AccountDetermination

    code = req.card_code.strip().upper()
    if not code:
        raise B1Error("Enter a BP code")
    if session.get(BusinessPartner, code) is not None:
        raise B1Error(f"Business partner {code} already exists")
    if req.card_type not in CARD_TYPES:
        raise B1Error("BP type must be C (customer), S (vendor) or L (lead)")
    if req.group_code is not None:
        group = session.get(PartnerGroup, req.group_code)
        # leads use customer groups
        if group is None or group.group_type != ("S" if req.card_type == "S" else "C"):
            raise B1Error(f"Group {req.group_code} is not a {CARD_TYPES[req.card_type].lower()} group")
    validate_partner_fields(session, {f: getattr(req, f) for f in PARTNER_FIELDS}, req.card_type)

    control = req.deb_pay_acct
    if control is None:
        det = session.scalars(select(AccountDetermination).order_by(AccountDetermination.period_cat.desc())).first()
        if det is None:
            raise B1Error("No G/L account determination is defined")
        control = det.ap_control if req.card_type == "S" else det.ar_control
    _control_account(session, control)

    bp = BusinessPartner(
        card_code=code, deb_pay_acct=control, **{f: getattr(req, f) for f in PARTNER_FIELDS},
        balance=Decimal("0"), dnotes_bal=Decimal("0"), orders_bal=Decimal("0"), frozen_for="N",
    )
    session.add(bp)
    if commit:
        session.commit()
    else:
        session.flush()
    return bp


def save_address(session: Session, card_code: str, adres_type: str, address: str, data: dict,
                 make_default: bool = False) -> None:
    """Add or change a bill-to (B) / ship-to (S) address (CRD1); the first one becomes the default."""
    from app.models.partners import PartnerAddress

    bp = session.get(BusinessPartner, card_code)
    if bp is None:
        raise B1Error(f"Business partner {card_code} does not exist")
    if adres_type not in {"B", "S"} or not address.strip():
        raise B1Error("An address needs a type (B bill-to, S ship-to) and an address ID")
    check_country(session, data.get("country"), data.get("state"))
    check_gstin(session, data.get("gst_regn_no"), data.get("state") if data.get("country") == "IN" else None)
    session.merge(PartnerAddress(card_code=card_code, adres_type=adres_type, address=address.strip(), **data))
    if adres_type == "B" and (make_default or not bp.bill_to_def):
        bp.bill_to_def = address.strip()
    if adres_type == "S" and (make_default or not bp.ship_to_def):
        bp.ship_to_def = address.strip()
    session.commit()


# ------------------------------------------------------------- items and warehouses
@dataclass
class ItemRequest:
    item_code: str
    item_name: str
    itms_grp_cod: int
    invnt_item: bool = True
    sell_item: bool = True
    prchse_item: bool = True
    invntry_uom: str | None = None
    vat_gourp_sa: str | None = None
    vat_group_pu: str | None = None
    dflt_wh: str | None = None
    card_code: str | None = None
    min_level: Decimal = Decimal("0")
    prices: dict[int, Decimal] | None = None  # price list -> price in local currency
    frgn_name: str | None = None
    item_type: str = "I"  # I items, L labor, T travel
    code_bars: str | None = None
    chapter_id: str | None = None  # HSN / SAC
    firm_code: int | None = None
    supp_cat_num: str | None = None
    buy_unit_msr: str | None = None
    num_in_buy: Decimal = Decimal("1")
    sal_unit_msr: str | None = None
    num_in_sale: Decimal = Decimal("1")
    max_level: Decimal = Decimal("0")
    reorder_qty: Decimal = Decimal("0")
    lead_time: int | None = None
    min_ordr_qty: Decimal = Decimal("0")
    user_text: str | None = None


ITEM_FIELDS = ["frgn_name", "item_type", "code_bars", "chapter_id", "firm_code", "supp_cat_num", "buy_unit_msr", "num_in_buy",
               "sal_unit_msr", "num_in_sale", "max_level", "reorder_qty", "lead_time", "min_ordr_qty", "user_text",
               "invntry_uom", "vat_gourp_sa", "vat_group_pu", "dflt_wh", "card_code", "min_level", "item_name"]


def validate_item_fields(session: Session, data: dict) -> None:
    from app.models.inventory import Manufacturer

    if data.get("chapter_id"):
        from app.models.admin import HsnCode

        if session.scalar(select(HsnCode).where(HsnCode.chapter_id == data["chapter_id"])) is None:
            raise B1Error(f"HSN / SAC code {data['chapter_id']} does not exist")
    if data.get("item_type", "I") not in {"I", "L", "T"}:
        raise B1Error("Item type must be I (items), L (labor) or T (travel)")
    if data.get("firm_code") not in (None, -1) and session.get(Manufacturer, data["firm_code"]) is None:
        raise B1Error(f"Manufacturer {data['firm_code']} does not exist")
    for key in ("num_in_buy", "num_in_sale"):
        if data.get(key) is not None and Decimal(data[key]) <= 0:
            raise B1Error("Items per purchase / sales unit must be positive")
    for key in ("min_level", "max_level", "reorder_qty", "min_ordr_qty"):
        if data.get(key) is not None and Decimal(data[key]) < 0:
            raise B1Error("Inventory levels and quantities cannot be negative")
    if data.get("max_level") and data.get("min_level") and Decimal(data["max_level"]) < Decimal(data["min_level"]):
        raise B1Error("The maximum inventory is below the minimum inventory")
    _tax_group(session, data.get("vat_gourp_sa"), "O")
    _tax_group(session, data.get("vat_group_pu"), "I")
    if data.get("dflt_wh") is not None and session.get(Warehouse, data["dflt_wh"]) is None:
        raise B1Error(f"Warehouse {data['dflt_wh']} does not exist")
    if data.get("card_code") is not None:
        vendor = session.get(BusinessPartner, data["card_code"])
        if vendor is None or vendor.card_type != "S":
            raise B1Error(f"Preferred vendor {data['card_code']} is not a vendor")


def create_item(session: Session, req: ItemRequest, *, commit: bool = True) -> Item:
    code = req.item_code.strip().upper()
    if not code:
        raise B1Error("Enter an item number")
    if session.get(Item, code) is not None:
        raise B1Error(f"Item {code} already exists")
    if session.get(ItemGroup, req.itms_grp_cod) is None:
        raise B1Error(f"Item group {req.itms_grp_cod} does not exist")
    if not (req.sell_item or req.prchse_item or req.invnt_item):
        raise B1Error("An item must be an inventory, sales or purchase item")
    validate_item_fields(session, {f: getattr(req, f) for f in ITEM_FIELDS})

    yn = lambda b: "Y" if b else "N"  # noqa: E731
    item = Item(
        item_code=code, itms_grp_cod=req.itms_grp_cod, invnt_item=yn(req.invnt_item),
        sell_item=yn(req.sell_item), prchse_item=yn(req.prchse_item), eval_system="A", gl_method="C",
        **{f: getattr(req, f) for f in ITEM_FIELDS}, on_hand=Decimal("0"),
        is_commited=Decimal("0"), on_order=Decimal("0"), avg_price=Decimal("0"), stock_value=Decimal("0"), last_pur_prc=Decimal("0"),
        frozen_for="N",
    )
    session.add(item)
    session.flush()
    if item.invnt_item == "Y":  # like B1, an inventory item gets a stock row in every warehouse
        for whs in session.scalars(select(Warehouse)):
            session.add(ItemWarehouse(item_code=code, whs_code=whs.whs_code))
    main = company(session).main_curncy
    for list_num, price in (req.prices or {}).items():
        if session.get(PriceList, list_num) is None:
            raise B1Error(f"Price list {list_num} does not exist")
        session.add(ItemPrice(item_code=code, price_list=list_num, price=Decimal(price), currency=main))
    if commit:
        session.commit()
    else:
        session.flush()
    return item


WAREHOUSE_FIELDS = ["street", "block", "zip_code", "city", "county", "state", "country", "building"]


def create_warehouse(session: Session, whs_code: str, whs_name: str, street: str | None = None,
                     city: str | None = None, *, commit: bool = True, drop_ship: bool = False, nettable: bool = True,
                     **address) -> Warehouse:
    code = whs_code.strip().upper()
    if not code:
        raise B1Error("Enter a warehouse code")
    if session.get(Warehouse, code) is not None:
        raise B1Error(f"Warehouse {code} already exists")
    check_country(session, address.get("country"), address.get("state"))
    whs = Warehouse(whs_code=code, whs_name=whs_name, street=street, city=city, inactive="N",
                    drop_ship="Y" if drop_ship else "N", nettable="Y" if nettable else "N",
                    **{k: v for k, v in address.items() if k in WAREHOUSE_FIELDS})
    session.add(whs)
    session.flush()
    for item in session.scalars(select(Item).where(Item.invnt_item == "Y")):
        session.add(ItemWarehouse(item_code=item.item_code, whs_code=code))
    if commit:
        session.commit()
    else:
        session.flush()
    return whs


def set_price(session: Session, item_code: str, list_num: int, price: Decimal, *, commit: bool = True) -> ItemPrice:
    if session.get(Item, item_code) is None:
        raise B1Error(f"Item {item_code} does not exist")
    if session.get(PriceList, list_num) is None:
        raise B1Error(f"Price list {list_num} does not exist")
    if price < 0:
        raise B1Error("A price cannot be negative")
    row = session.merge(ItemPrice(item_code=item_code, price_list=list_num, price=price,
                                  currency=company(session).main_curncy))
    if commit:
        session.commit()
    return row


def item_price(session: Session, item_code: str, list_num: int) -> Decimal:
    """Price of an item in a price list: its own ITM1 price, else base list price x factor (recursively)."""
    seen: set[int] = set()
    factor = Decimal("1")
    current = list_num
    while True:
        if current in seen:
            raise B1Error(f"Price list {list_num} has a circular base price list")
        seen.add(current)
        own = session.get(ItemPrice, (item_code, current))
        if own is not None:
            return (own.price * factor).quantize(Decimal("0.01"))
        pl = session.get(PriceList, current)
        if pl is None:
            raise B1Error(f"Price list {current} does not exist")
        if pl.base_num == pl.list_num:
            return Decimal("0.00")
        factor *= pl.factor
        current = pl.base_num


def partner_price(session: Session, card_code: str, item_code: str) -> Decimal:
    """Default unit price for a business partner: the item price in the partner's price list."""
    bp = session.get(BusinessPartner, card_code)
    if bp is None:
        raise B1Error(f"Business partner {card_code} does not exist")
    list_num = bp.list_num or session.scalar(select(PriceList.list_num).order_by(PriceList.list_num))
    return item_price(session, item_code, list_num)
