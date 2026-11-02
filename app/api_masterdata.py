"""REST endpoints: business partners and inventory master data."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.finance import JournalLine
from app.models.inventory import Item, ItemGroup, ItemPrice, ItemWarehouse, PriceList, Warehouse
from app.models.partners import BusinessPartner, ContactPerson, PartnerGroup
from app.services import masterdata

router = APIRouter()


# ------------------------------------------------------------- business partners
def _bp_out(bp: BusinessPartner) -> dict:
    return {"card_code": bp.card_code, "card_name": bp.card_name, "card_type": bp.card_type,
            "group_code": bp.group_code, "currency": bp.currency, "deb_pay_acct": bp.deb_pay_acct,
            "group_num": bp.group_num, "list_num": bp.list_num, "vat_group": bp.vat_group,
            "lic_trad_num": bp.lic_trad_num, "phone1": bp.phone1, "e_mail": bp.e_mail, "address": bp.address,
            "zip_code": bp.zip_code, "city": bp.city, "country": bp.country, "cntct_prsn": bp.cntct_prsn,
            "credit_line": bp.credit_line, "balance": bp.balance, "dnotes_bal": bp.dnotes_bal,
            "orders_bal": bp.orders_bal, "frozen": bp.frozen_for == "Y", "notes": bp.notes}


@router.get("/partner-groups", tags=["Business partners"], summary="Business partner groups (OCRG)")
def partner_groups(s: Session = Depends(get_session)) -> list[dict]:
    return [{"group_code": g.group_code, "group_name": g.group_name, "group_type": g.group_type}
            for g in s.scalars(select(PartnerGroup).order_by(PartnerGroup.group_code))]


@router.get("/partners", tags=["Business partners"], summary="Business partners (OCRD)")
def partners(card_type: str | None = None, s: Session = Depends(get_session)) -> list[dict]:
    q = select(BusinessPartner).order_by(BusinessPartner.card_code)
    if card_type:
        q = q.where(BusinessPartner.card_type == card_type.upper())
    return [_bp_out(bp) for bp in s.scalars(q)]


class PartnerIn(BaseModel):
    card_code: str = Field(..., max_length=15)
    card_name: str = Field(..., max_length=100)
    card_type: str = Field(..., pattern="^[CSL]$")
    group_code: int | None = None
    currency: str = Field("##", max_length=3)
    deb_pay_acct: str | None = None
    group_num: int | None = None
    list_num: int | None = None
    vat_group: str | None = None
    lic_trad_num: str | None = Field(None, max_length=32)
    phone1: str | None = Field(None, max_length=20)
    e_mail: str | None = Field(None, max_length=100)
    address: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=20)
    city: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=3)
    cntct_prsn: str | None = Field(None, max_length=90)
    credit_line: Decimal = Decimal("0")
    notes: str | None = Field(None, max_length=100)


@router.post("/partners", tags=["Business partners"], summary="Create a business partner")
def create_partner(body: PartnerIn, s: Session = Depends(get_session)) -> dict:
    return _bp_out(run(lambda: masterdata.create_partner(s, masterdata.PartnerRequest(**body.model_dump()))))


def _bp_or_404(s: Session, card_code: str) -> BusinessPartner:
    bp = s.get(BusinessPartner, card_code)
    if bp is None:
        raise HTTPException(status_code=404, detail="Business partner not found")
    return bp


@router.get("/partners/{card_code}", tags=["Business partners"], summary="Business partner with contacts and open items")
def get_partner(card_code: str, s: Session = Depends(get_session)) -> dict:
    bp = _bp_or_404(s, card_code)
    contacts = s.scalars(select(ContactPerson).where(ContactPerson.card_code == card_code)).all()
    open_lines = s.scalars(select(JournalLine).where(
        JournalLine.short_name == card_code,
        (JournalLine.bal_due_deb != 0) | (JournalLine.bal_due_cred != 0)).order_by(JournalLine.due_date)).all()
    return {**_bp_out(bp),
            "contacts": [{"cntct_code": c.cntct_code, "name": c.name, "position": c.position, "tel1": c.tel1,
                          "e_mail": c.e_mail} for c in contacts],
            "open_items": [{"trans_id": l.trans_id, "line_id": l.line_id, "trans_type": l.trans_type,
                            "ref_date": l.ref_date, "due_date": l.due_date, "debit": l.debit, "credit": l.credit,
                            "open": l.bal_due_deb - l.bal_due_cred, "line_memo": l.line_memo} for l in open_lines]}


class PartnerUpdate(BaseModel):
    card_name: str | None = Field(None, max_length=100)
    group_num: int | None = None
    list_num: int | None = None
    phone1: str | None = Field(None, max_length=20)
    e_mail: str | None = Field(None, max_length=100)
    address: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=20)
    city: str | None = Field(None, max_length=100)
    credit_line: Decimal | None = None
    frozen: bool | None = None
    notes: str | None = Field(None, max_length=100)


@router.patch("/partners/{card_code}", tags=["Business partners"], summary="Change a business partner")
def update_partner(card_code: str, body: PartnerUpdate, s: Session = Depends(get_session)) -> dict:
    bp = _bp_or_404(s, card_code)
    data = body.model_dump(exclude_unset=True)
    if "frozen" in data:
        bp.frozen_for = "Y" if data.pop("frozen") else "N"
    if data.get("list_num") is not None and s.get(PriceList, data["list_num"]) is None:
        raise HTTPException(status_code=422, detail=f"Price list {data['list_num']} does not exist")
    for key, value in data.items():
        setattr(bp, key, value)
    s.commit()
    return _bp_out(bp)


class ContactIn(BaseModel):
    name: str = Field(..., max_length=50)
    position: str | None = Field(None, max_length=90)
    tel1: str | None = Field(None, max_length=20)
    e_mail: str | None = Field(None, max_length=100)


@router.post("/partners/{card_code}/contacts", tags=["Business partners"], summary="Add a contact person (OCPR)")
def add_contact(card_code: str, body: ContactIn, s: Session = Depends(get_session)) -> dict:
    from sqlalchemy import func

    bp = _bp_or_404(s, card_code)
    code = (s.scalar(select(func.max(ContactPerson.cntct_code))) or 0) + 1
    s.add(ContactPerson(cntct_code=code, card_code=bp.card_code, **body.model_dump()))
    if not bp.cntct_prsn:
        bp.cntct_prsn = body.name
    s.commit()
    return {"cntct_code": code, **body.model_dump()}


# ------------------------------------------------------------- inventory master data
@router.get("/item-groups", tags=["Inventory"], summary="Item groups with G/L accounts (OITB)")
def item_groups(s: Session = Depends(get_session)) -> list[dict]:
    return [{"itms_grp_cod": g.itms_grp_cod, "itms_grp_nam": g.itms_grp_nam, "bal_invnt_ac": g.bal_invnt_ac,
             "sale_cost_ac": g.sale_cost_ac, "revenues_ac": g.revenues_ac, "expenses_ac": g.expenses_ac,
             "price_dif_ac": g.price_dif_ac} for g in s.scalars(select(ItemGroup).order_by(ItemGroup.itms_grp_cod))]


@router.get("/warehouses", tags=["Inventory"], summary="Warehouses (OWHS)")
def warehouses(s: Session = Depends(get_session)) -> list[dict]:
    return [{"whs_code": w.whs_code, "whs_name": w.whs_name, "street": w.street, "city": w.city,
             "inactive": w.inactive == "Y"} for w in s.scalars(select(Warehouse).order_by(Warehouse.whs_code))]


class WarehouseIn(BaseModel):
    whs_code: str = Field(..., max_length=8)
    whs_name: str = Field(..., max_length=100)
    street: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)


@router.post("/warehouses", tags=["Inventory"], summary="Create a warehouse")
def create_warehouse(body: WarehouseIn, s: Session = Depends(get_session)) -> dict:
    w = run(lambda: masterdata.create_warehouse(s, body.whs_code, body.whs_name, body.street, body.city))
    return {"whs_code": w.whs_code, "whs_name": w.whs_name, "street": w.street, "city": w.city, "inactive": False}


@router.get("/price-lists", tags=["Inventory"], summary="Price lists (OPLN)")
def price_lists(s: Session = Depends(get_session)) -> list[dict]:
    return [{"list_num": p.list_num, "list_name": p.list_name, "base_num": p.base_num, "factor": p.factor}
            for p in s.scalars(select(PriceList).order_by(PriceList.list_num))]


def _item_out(i: Item, s: Session, detail: bool = False) -> dict:
    out = {"item_code": i.item_code, "item_name": i.item_name, "itms_grp_cod": i.itms_grp_cod,
           "invnt_item": i.invnt_item == "Y", "sell_item": i.sell_item == "Y", "prchse_item": i.prchse_item == "Y",
           "invntry_uom": i.invntry_uom, "vat_gourp_sa": i.vat_gourp_sa, "vat_group_pu": i.vat_group_pu,
           "dflt_wh": i.dflt_wh, "card_code": i.card_code, "min_level": i.min_level, "on_hand": i.on_hand,
           "is_commited": i.is_commited, "on_order": i.on_order,
           "available": i.on_hand - i.is_commited + i.on_order, "avg_price": i.avg_price,
           "last_pur_prc": i.last_pur_prc, "frozen": i.frozen_for == "Y"}
    if detail:
        out["warehouses"] = [{"whs_code": w.whs_code, "on_hand": w.on_hand, "is_commited": w.is_commited,
                              "on_order": w.on_order, "available": w.on_hand - w.is_commited + w.on_order,
                              "min_stock": w.min_stock}
                             for w in s.scalars(select(ItemWarehouse).where(ItemWarehouse.item_code == i.item_code)
                                                .order_by(ItemWarehouse.whs_code))]
        out["prices"] = [{"list_num": p.list_num, "list_name": p.list_name,
                          "price": masterdata.item_price(s, i.item_code, p.list_num),
                          "own": s.get(ItemPrice, (i.item_code, p.list_num)) is not None}
                         for p in s.scalars(select(PriceList).order_by(PriceList.list_num))]
    return out


@router.get("/items", tags=["Inventory"], summary="Items (OITM)")
def items(s: Session = Depends(get_session)) -> list[dict]:
    return [_item_out(i, s) for i in s.scalars(select(Item).order_by(Item.item_code))]


class ItemIn(BaseModel):
    item_code: str = Field(..., max_length=50)
    item_name: str = Field(..., max_length=100)
    itms_grp_cod: int
    invnt_item: bool = True
    sell_item: bool = True
    prchse_item: bool = True
    invntry_uom: str | None = Field(None, max_length=20)
    vat_gourp_sa: str | None = None
    vat_group_pu: str | None = None
    dflt_wh: str | None = None
    card_code: str | None = None
    min_level: Decimal = Decimal("0")
    prices: dict[int, Decimal] | None = None


@router.post("/items", tags=["Inventory"], summary="Create an item")
def create_item(body: ItemIn, s: Session = Depends(get_session)) -> dict:
    item = run(lambda: masterdata.create_item(s, masterdata.ItemRequest(**body.model_dump())))
    return _item_out(item, s, detail=True)


@router.get("/items/{item_code}", tags=["Inventory"], summary="Item with stock per warehouse and prices")
def get_item(item_code: str, s: Session = Depends(get_session)) -> dict:
    i = s.get(Item, item_code)
    if i is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return _item_out(i, s, detail=True)


class PriceIn(BaseModel):
    price: Decimal = Field(..., ge=0)


@router.put("/items/{item_code}/prices/{list_num}", tags=["Inventory"], summary="Set an item price (ITM1)")
def set_price(item_code: str, list_num: int, body: PriceIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: masterdata.set_price(s, item_code, list_num, body.price))
    return {"item_code": item_code, "list_num": list_num, "price": body.price}


@router.get("/items/{item_code}/price", tags=["Inventory"], summary="Unit price for a business partner or price list")
def price_for(item_code: str, card_code: str | None = None, list_num: int | None = None,
              s: Session = Depends(get_session)) -> dict:
    if card_code:
        price = run(lambda: masterdata.partner_price(s, card_code, item_code))
    else:
        price = run(lambda: masterdata.item_price(s, item_code, list_num or 1))
    return {"item_code": item_code, "price": price}
