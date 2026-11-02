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
from app.services.admin import B1Error, company

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
    if req.currency != "##" and session.get(Currency, req.currency) is None:
        raise B1Error(f"Currency {req.currency} does not exist")
    if req.group_num is not None and session.get(PaymentTerms, req.group_num) is None:
        raise B1Error(f"Payment terms {req.group_num} do not exist")
    if req.list_num is not None and session.get(PriceList, req.list_num) is None:
        raise B1Error(f"Price list {req.list_num} does not exist")
    _tax_group(session, req.vat_group, "I" if req.card_type == "S" else "O")

    control = req.deb_pay_acct
    if control is None:
        det = session.scalars(select(AccountDetermination).order_by(AccountDetermination.period_cat.desc())).first()
        if det is None:
            raise B1Error("No G/L account determination is defined")
        control = det.ap_control if req.card_type == "S" else det.ar_control
    _control_account(session, control)

    bp = BusinessPartner(
        card_code=code, card_name=req.card_name, card_type=req.card_type, group_code=req.group_code,
        currency=req.currency, deb_pay_acct=control, group_num=req.group_num, list_num=req.list_num,
        vat_group=req.vat_group, lic_trad_num=req.lic_trad_num, phone1=req.phone1, e_mail=req.e_mail,
        address=req.address, zip_code=req.zip_code, city=req.city, country=req.country,
        cntct_prsn=req.cntct_prsn, credit_line=req.credit_line, notes=req.notes,
        balance=Decimal("0"), dnotes_bal=Decimal("0"), orders_bal=Decimal("0"), frozen_for="N",
    )
    session.add(bp)
    if commit:
        session.commit()
    else:
        session.flush()
    return bp


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
    _tax_group(session, req.vat_gourp_sa, "O")
    _tax_group(session, req.vat_group_pu, "I")
    if req.dflt_wh is not None and session.get(Warehouse, req.dflt_wh) is None:
        raise B1Error(f"Warehouse {req.dflt_wh} does not exist")
    if req.card_code is not None:
        vendor = session.get(BusinessPartner, req.card_code)
        if vendor is None or vendor.card_type != "S":
            raise B1Error(f"Preferred vendor {req.card_code} is not a vendor")

    yn = lambda b: "Y" if b else "N"  # noqa: E731
    item = Item(
        item_code=code, item_name=req.item_name, itms_grp_cod=req.itms_grp_cod, invnt_item=yn(req.invnt_item),
        sell_item=yn(req.sell_item), prchse_item=yn(req.prchse_item), eval_system="A", gl_method="C",
        invntry_uom=req.invntry_uom, vat_gourp_sa=req.vat_gourp_sa, vat_group_pu=req.vat_group_pu,
        dflt_wh=req.dflt_wh, card_code=req.card_code, min_level=req.min_level, on_hand=Decimal("0"),
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


def create_warehouse(session: Session, whs_code: str, whs_name: str, street: str | None = None,
                     city: str | None = None, *, commit: bool = True) -> Warehouse:
    code = whs_code.strip().upper()
    if not code:
        raise B1Error("Enter a warehouse code")
    if session.get(Warehouse, code) is not None:
        raise B1Error(f"Warehouse {code} already exists")
    whs = Warehouse(whs_code=code, whs_name=whs_name, street=street, city=city, inactive="N")
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
