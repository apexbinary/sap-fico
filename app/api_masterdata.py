"""REST endpoints: business partners, inventory master data and the general lookup tables."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api_finance import apply_changes, run
from app.database import get_session
from app.models.admin import Country, Project, SalesEmployee, State, TransactionCode
from app.models.finance import JournalLine
from app.models.inventory import Item, ItemGroup, ItemPrice, ItemWarehouse, Manufacturer, PriceList, Warehouse
from app.models.partners import BusinessPartner, ContactPerson, PartnerAddress, PartnerGroup
from app.services import masterdata

router = APIRouter()
yn = lambda b: "Y" if b else "N"  # noqa: E731


# ------------------------------------------------------------- general lookup tables
@router.get("/master/lookups", tags=["Administration"],
            summary="Sales employees, projects, manufacturers, transaction codes, countries, states")
def lookups(s: Session = Depends(get_session)) -> dict:
    return {
        "sales_employees": [{"slp_code": e.slp_code, "slp_name": e.slp_name, "memo": e.memo, "commission": e.commission,
                             "telephone": e.telephone, "email": e.email, "active": e.active == "Y"}
                            for e in s.scalars(select(SalesEmployee).order_by(SalesEmployee.slp_code))],
        "projects": [{"prj_code": p.prj_code, "prj_name": p.prj_name, "valid_from": p.valid_from, "valid_to": p.valid_to,
                      "active": p.active == "Y"} for p in s.scalars(select(Project).order_by(Project.prj_code))],
        "manufacturers": [{"firm_code": m.firm_code, "firm_name": m.firm_name}
                          for m in s.scalars(select(Manufacturer).order_by(Manufacturer.firm_code))],
        "transaction_codes": [{"trns_code": t.trns_code, "trns_cod_dsc": t.trns_cod_dsc}
                              for t in s.scalars(select(TransactionCode).order_by(TransactionCode.trns_code))],
        "countries": [{"code": c.code, "name": c.name} for c in s.scalars(select(Country).order_by(Country.name))],
        "states": [{"country": t.country, "code": t.code, "name": t.name, "gst_code": t.gst_code}
                   for t in s.scalars(select(State).order_by(State.country, State.name))],
        "item_types": [{"code": "I", "name": "Items"}, {"code": "L", "name": "Labor"}, {"code": "T", "name": "Travel"}],
    }


class SalesEmployeeIn(BaseModel):
    slp_name: str = Field(..., max_length=155)
    memo: str | None = Field(None, max_length=50)
    commission: Decimal = Field(Decimal("0"), ge=0, le=100)
    telephone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=100)
    active: bool = True


@router.post("/sales-employees", tags=["Administration"], summary="Add a sales employee / buyer (OSLP)")
def add_sales_employee(body: SalesEmployeeIn, s: Session = Depends(get_session)) -> dict:
    code = max(s.scalar(select(func.max(SalesEmployee.slp_code))) or 0, 0) + 1
    data = body.model_dump()
    s.add(SalesEmployee(slp_code=code, **{**data, "active": yn(data["active"])}))
    s.commit()
    return {"slp_code": code, **data}


class ProjectIn(BaseModel):
    prj_code: str = Field(..., min_length=1, max_length=20)
    prj_name: str = Field(..., max_length=100)
    valid_from: date | None = None
    valid_to: date | None = None
    active: bool = True


@router.post("/projects", tags=["Administration"], summary="Add a project (OPRJ)")
def add_project(body: ProjectIn, s: Session = Depends(get_session)) -> dict:
    if s.get(Project, body.prj_code) is not None:
        raise HTTPException(status_code=422, detail=f"Project {body.prj_code} already exists")
    if body.valid_from and body.valid_to and body.valid_to < body.valid_from:
        raise HTTPException(status_code=422, detail="Valid to is before valid from")
    data = body.model_dump()
    s.add(Project(**{**data, "active": yn(data["active"])}))
    s.commit()
    return data


class ManufacturerIn(BaseModel):
    firm_name: str = Field(..., max_length=30)


@router.post("/manufacturers", tags=["Inventory"], summary="Add a manufacturer (OMRC)")
def add_manufacturer(body: ManufacturerIn, s: Session = Depends(get_session)) -> dict:
    code = max(s.scalar(select(func.max(Manufacturer.firm_code))) or 0, 0) + 1
    s.add(Manufacturer(firm_code=code, firm_name=body.firm_name))
    s.commit()
    return {"firm_code": code, "firm_name": body.firm_name}


class TransactionCodeIn(BaseModel):
    trns_code: str = Field(..., min_length=1, max_length=4)
    trns_cod_dsc: str = Field(..., max_length=30)


@router.post("/transaction-codes", tags=["Financials"], summary="Add a transaction code (OTRC)")
def add_transaction_code(body: TransactionCodeIn, s: Session = Depends(get_session)) -> dict:
    if s.get(TransactionCode, body.trns_code) is not None:
        raise HTTPException(status_code=422, detail=f"Transaction code {body.trns_code} already exists")
    s.add(TransactionCode(**body.model_dump()))
    s.commit()
    return body.model_dump()


# ------------------------------------------------------------- business partners
def _bp_out(bp: BusinessPartner) -> dict:
    return {"card_code": bp.card_code, "card_name": bp.card_name, "card_f_name": bp.card_f_name,
            "card_type": bp.card_type, "group_code": bp.group_code, "currency": bp.currency,
            "deb_pay_acct": bp.deb_pay_acct, "group_num": bp.group_num, "list_num": bp.list_num,
            "vat_group": bp.vat_group, "lic_trad_num": bp.lic_trad_num, "phone1": bp.phone1, "phone2": bp.phone2,
            "cellular": bp.cellular, "fax": bp.fax, "e_mail": bp.e_mail, "intrnt_site": bp.intrnt_site,
            "address": bp.address, "zip_code": bp.zip_code, "city": bp.city, "country": bp.country,
            "cntct_prsn": bp.cntct_prsn, "slp_code": bp.slp_code, "project_cod": bp.project_cod,
            "bill_to_def": bp.bill_to_def, "ship_to_def": bp.ship_to_def, "credit_line": bp.credit_line,
            "debt_line": bp.debt_line, "discount": bp.discount, "balance": bp.balance, "dnotes_bal": bp.dnotes_bal,
            "orders_bal": bp.orders_bal, "frozen": bp.frozen_for == "Y", "notes": bp.notes, "free_text": bp.free_text,
            "dun_term": bp.dun_term, "intrst_rate": bp.intrst_rate}


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


class PartnerFields(BaseModel):
    card_f_name: str | None = Field(None, max_length=100)
    group_num: int | None = None
    list_num: int | None = None
    vat_group: str | None = None
    lic_trad_num: str | None = Field(None, max_length=32)
    phone1: str | None = Field(None, max_length=20)
    phone2: str | None = Field(None, max_length=20)
    cellular: str | None = Field(None, max_length=50)
    fax: str | None = Field(None, max_length=20)
    e_mail: str | None = Field(None, max_length=100)
    intrnt_site: str | None = Field(None, max_length=100)
    address: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=20)
    city: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=3)
    slp_code: int | None = None
    project_cod: str | None = Field(None, max_length=20)
    credit_line: Decimal | None = Field(None, ge=0)
    debt_line: Decimal | None = Field(None, ge=0)
    discount: Decimal | None = Field(None, ge=0, lt=100)
    notes: str | None = Field(None, max_length=100)
    free_text: str | None = Field(None, max_length=254)
    dun_term: str | None = Field(None, max_length=8)
    intrst_rate: Decimal | None = Field(None, ge=0, lt=100)


class PartnerIn(PartnerFields):
    card_code: str = Field(..., max_length=15)
    card_name: str = Field(..., max_length=100)
    card_type: str = Field(..., pattern="^[CSL]$")
    group_code: int | None = None
    currency: str = Field("##", max_length=3)
    deb_pay_acct: str | None = None
    cntct_prsn: str | None = Field(None, max_length=90)


@router.post("/partners", tags=["Business partners"], summary="Create a business partner")
def create_partner(body: PartnerIn, s: Session = Depends(get_session)) -> dict:
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return _bp_out(run(lambda: masterdata.create_partner(s, masterdata.PartnerRequest(**data))))


def _bp_or_404(s: Session, card_code: str) -> BusinessPartner:
    bp = s.get(BusinessPartner, card_code)
    if bp is None:
        raise HTTPException(status_code=404, detail="Business partner not found")
    return bp


def _addr_out(a: PartnerAddress) -> dict:
    return {"adres_type": a.adres_type, "address": a.address, "street": a.street, "block": a.block,
            "zip_code": a.zip_code, "city": a.city, "county": a.county, "state": a.state, "country": a.country,
            "building": a.building, "gst_regn_no": a.gst_regn_no, "gst_type": a.gst_type}


def _contact_out(c: ContactPerson) -> dict:
    return {"cntct_code": c.cntct_code, "name": c.name, "first_name": c.first_name, "middle_name": c.middle_name,
            "last_name": c.last_name, "title": c.title, "position": c.position, "address": c.address,
            "tel1": c.tel1, "tel2": c.tel2, "cellolar": c.cellolar, "fax": c.fax, "e_mail": c.e_mail,
            "notes1": c.notes1, "active": c.active == "Y"}


@router.get("/partners/{card_code}", tags=["Business partners"],
            summary="Business partner with addresses, contact persons and open items")
def get_partner(card_code: str, s: Session = Depends(get_session)) -> dict:
    bp = _bp_or_404(s, card_code)
    open_lines = s.scalars(select(JournalLine).where(
        JournalLine.short_name == card_code,
        (JournalLine.bal_due_deb != 0) | (JournalLine.bal_due_cred != 0)).order_by(JournalLine.due_date)).all()
    return {**_bp_out(bp),
            "addresses": [_addr_out(a) for a in s.scalars(select(PartnerAddress).where(
                PartnerAddress.card_code == card_code).order_by(PartnerAddress.adres_type, PartnerAddress.address))],
            "contacts": [_contact_out(c) for c in s.scalars(select(ContactPerson).where(
                ContactPerson.card_code == card_code).order_by(ContactPerson.cntct_code))],
            "open_items": [{"trans_id": l.trans_id, "line_id": l.line_id, "trans_type": l.trans_type,
                            "base_ref": l.base_ref, "created_by": l.created_by, "ref_date": l.ref_date,
                            "due_date": l.due_date, "debit": l.debit, "credit": l.credit,
                            "open": l.bal_due_deb - l.bal_due_cred, "line_memo": l.line_memo} for l in open_lines]}


class PartnerUpdate(PartnerFields):
    card_name: str | None = Field(None, max_length=100)
    cntct_prsn: str | None = Field(None, max_length=90)
    bill_to_def: str | None = None
    ship_to_def: str | None = None
    frozen: bool | None = None


@router.patch("/partners/{card_code}", tags=["Business partners"], summary="Change a business partner")
def update_partner(card_code: str, body: PartnerUpdate, s: Session = Depends(get_session)) -> dict:
    bp = _bp_or_404(s, card_code)
    data = body.model_dump(exclude_unset=True)
    if "frozen" in data:
        bp.frozen_for = yn(data.pop("frozen"))
    run(lambda: masterdata.validate_partner_fields(s, data, bp.card_type))
    for kind, key in (("B", "bill_to_def"), ("S", "ship_to_def")):
        if data.get(key) and s.get(PartnerAddress, (card_code, kind, data[key])) is None:
            raise HTTPException(status_code=422, detail=f"Address {data[key]} does not exist")
    if data.get("cntct_prsn") and s.scalar(select(ContactPerson).where(
            ContactPerson.card_code == card_code, ContactPerson.name == data["cntct_prsn"])) is None:
        raise HTTPException(status_code=422, detail=f"Contact person {data['cntct_prsn']} does not exist")
    apply_changes(bp, data)
    s.commit()
    return _bp_out(bp)


class AddressIn(BaseModel):
    adres_type: str = Field(..., pattern="^[BS]$")
    address: str = Field(..., min_length=1, max_length=50)
    street: str | None = Field(None, max_length=100)
    block: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=20)
    city: str | None = Field(None, max_length=100)
    county: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=3)
    country: str | None = Field(None, max_length=3)
    building: str | None = Field(None, max_length=100)
    gst_regn_no: str | None = Field(None, max_length=15)
    gst_type: str | None = Field(None, pattern="^[RUCE]$", description="R regular, U unregistered, C composition, E SEZ")
    make_default: bool = False


@router.post("/partners/{card_code}/addresses", tags=["Business partners"], summary="Add / change an address (CRD1)")
def save_address(card_code: str, body: AddressIn, s: Session = Depends(get_session)) -> dict:
    data = body.model_dump()
    kind, addr, default = data.pop("adres_type"), data.pop("address"), data.pop("make_default")
    run(lambda: masterdata.save_address(s, card_code, kind, addr, data, default))
    return {"adres_type": kind, "address": addr, **data}


class ContactIn(BaseModel):
    name: str = Field(..., max_length=50)
    first_name: str | None = Field(None, max_length=50)
    middle_name: str | None = Field(None, max_length=50)
    last_name: str | None = Field(None, max_length=50)
    title: str | None = Field(None, max_length=10)
    position: str | None = Field(None, max_length=90)
    address: str | None = Field(None, max_length=100)
    tel1: str | None = Field(None, max_length=20)
    tel2: str | None = Field(None, max_length=20)
    cellolar: str | None = Field(None, max_length=50)
    fax: str | None = Field(None, max_length=20)
    e_mail: str | None = Field(None, max_length=100)
    notes1: str | None = Field(None, max_length=100)
    active: bool = True


@router.post("/partners/{card_code}/contacts", tags=["Business partners"], summary="Add a contact person (OCPR)")
def add_contact(card_code: str, body: ContactIn, s: Session = Depends(get_session)) -> dict:
    bp = _bp_or_404(s, card_code)
    if s.scalar(select(ContactPerson).where(ContactPerson.card_code == card_code, ContactPerson.name == body.name)):
        raise HTTPException(status_code=422, detail=f"Contact ID {body.name} already exists for {card_code}")
    code = (s.scalar(select(func.max(ContactPerson.cntct_code))) or 0) + 1
    data = body.model_dump()
    s.add(ContactPerson(cntct_code=code, card_code=bp.card_code, **{**data, "active": yn(data["active"])}))
    if not bp.cntct_prsn:
        bp.cntct_prsn = body.name
    s.commit()
    return {"cntct_code": code, **data}


# ------------------------------------------------------------- inventory master data
@router.get("/item-groups", tags=["Inventory"], summary="Item groups with G/L accounts (OITB)")
def item_groups(s: Session = Depends(get_session)) -> list[dict]:
    return [{"itms_grp_cod": g.itms_grp_cod, "itms_grp_nam": g.itms_grp_nam, "bal_invnt_ac": g.bal_invnt_ac,
             "sale_cost_ac": g.sale_cost_ac, "revenues_ac": g.revenues_ac, "expenses_ac": g.expenses_ac,
             "price_dif_ac": g.price_dif_ac} for g in s.scalars(select(ItemGroup).order_by(ItemGroup.itms_grp_cod))]


def _whs_out(w: Warehouse) -> dict:
    return {"whs_code": w.whs_code, "whs_name": w.whs_name, "street": w.street, "block": w.block,
            "zip_code": w.zip_code, "city": w.city, "county": w.county, "state": w.state, "country": w.country,
            "building": w.building, "drop_ship": w.drop_ship == "Y", "nettable": w.nettable == "Y",
            "inactive": w.inactive == "Y"}


@router.get("/warehouses", tags=["Inventory"], summary="Warehouses (OWHS)")
def warehouses(s: Session = Depends(get_session)) -> list[dict]:
    return [_whs_out(w) for w in s.scalars(select(Warehouse).order_by(Warehouse.whs_code))]


class WarehouseIn(BaseModel):
    whs_code: str = Field(..., max_length=8)
    whs_name: str = Field(..., max_length=100)
    street: str | None = Field(None, max_length=100)
    block: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=20)
    city: str | None = Field(None, max_length=100)
    county: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=3)
    country: str | None = Field(None, max_length=3)
    building: str | None = Field(None, max_length=100)
    drop_ship: bool = False
    nettable: bool = True


@router.post("/warehouses", tags=["Inventory"], summary="Create a warehouse")
def create_warehouse(body: WarehouseIn, s: Session = Depends(get_session)) -> dict:
    data = body.model_dump()
    w = run(lambda: masterdata.create_warehouse(s, data.pop("whs_code"), data.pop("whs_name"), **data))
    return _whs_out(w)


def _pl_out(p: PriceList) -> dict:
    return {"list_num": p.list_num, "list_name": p.list_name, "base_num": p.base_num, "factor": p.factor,
            "prim_curr": p.prim_curr, "active": p.valid_for == "Y"}


@router.get("/price-lists", tags=["Inventory"], summary="Price lists (OPLN)")
def price_lists(s: Session = Depends(get_session)) -> list[dict]:
    return [_pl_out(p) for p in s.scalars(select(PriceList).order_by(PriceList.list_num))]


class PriceListIn(BaseModel):
    list_name: str = Field(..., max_length=32)
    base_num: int | None = None  # empty: a list with its own prices
    factor: Decimal = Field(Decimal("1"), gt=0)
    prim_curr: str | None = Field(None, max_length=3)
    active: bool = True


@router.post("/price-lists", tags=["Inventory"], summary="Add a price list")
def add_price_list(body: PriceListIn, s: Session = Depends(get_session)) -> dict:
    num = (s.scalar(select(func.max(PriceList.list_num))) or 0) + 1
    if body.base_num is not None and s.get(PriceList, body.base_num) is None:
        raise HTTPException(status_code=422, detail=f"Price list {body.base_num} does not exist")
    p = PriceList(list_num=num, list_name=body.list_name, base_num=body.base_num or num, factor=body.factor,
                  prim_curr=body.prim_curr, valid_for=yn(body.active))
    s.add(p)
    s.commit()
    return _pl_out(p)


class PriceListUpdate(BaseModel):
    list_name: str | None = Field(None, max_length=32)
    factor: Decimal | None = Field(None, gt=0)
    prim_curr: str | None = Field(None, max_length=3)
    active: bool | None = None


@router.patch("/price-lists/{list_num}", tags=["Inventory"], summary="Change a price list")
def update_price_list(list_num: int, body: PriceListUpdate, s: Session = Depends(get_session)) -> dict:
    p = s.get(PriceList, list_num)
    if p is None:
        raise HTTPException(status_code=404, detail="Price list not found")
    data = body.model_dump(exclude_unset=True)
    if "active" in data:
        p.valid_for = yn(data.pop("active"))
    apply_changes(p, data)
    s.commit()
    return _pl_out(p)


def _item_out(i: Item, s: Session, detail: bool = False) -> dict:
    out = {"item_code": i.item_code, "item_name": i.item_name, "frgn_name": i.frgn_name, "item_type": i.item_type,
           "itms_grp_cod": i.itms_grp_cod, "code_bars": i.code_bars, "chapter_id": i.chapter_id, "firm_code": i.firm_code,
           "invnt_item": i.invnt_item == "Y", "sell_item": i.sell_item == "Y", "prchse_item": i.prchse_item == "Y",
           "invntry_uom": i.invntry_uom, "vat_gourp_sa": i.vat_gourp_sa, "vat_group_pu": i.vat_group_pu,
           "dflt_wh": i.dflt_wh, "card_code": i.card_code, "supp_cat_num": i.supp_cat_num,
           "buy_unit_msr": i.buy_unit_msr, "num_in_buy": i.num_in_buy, "sal_unit_msr": i.sal_unit_msr,
           "num_in_sale": i.num_in_sale, "by_wh": i.by_wh == "Y", "min_level": i.min_level, "max_level": i.max_level,
           "reorder_qty": i.reorder_qty, "lead_time": i.lead_time, "min_ordr_qty": i.min_ordr_qty,
           "man_ser_num": i.man_ser_num == "Y", "man_btch_num": i.man_btch_num == "Y", "user_text": i.user_text,
           "eval_system": i.eval_system, "gl_method": i.gl_method, "on_hand": i.on_hand,
           "is_commited": i.is_commited, "on_order": i.on_order, "available": i.on_hand - i.is_commited + i.on_order,
           "avg_price": i.avg_price, "stock_value": i.stock_value, "last_pur_prc": i.last_pur_prc,
           "frozen": i.frozen_for == "Y"}
    if detail:
        out["warehouses"] = [{"whs_code": w.whs_code, "on_hand": w.on_hand, "is_commited": w.is_commited,
                              "on_order": w.on_order, "available": w.on_hand - w.is_commited + w.on_order,
                              "min_stock": w.min_stock, "max_stock": w.max_stock, "locked": w.locked == "Y"}
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


class ItemFields(BaseModel):
    frgn_name: str | None = Field(None, max_length=100)
    code_bars: str | None = Field(None, max_length=254)
    chapter_id: str | None = Field(None, max_length=20)
    firm_code: int | None = None
    invntry_uom: str | None = Field(None, max_length=20)
    vat_gourp_sa: str | None = None
    vat_group_pu: str | None = None
    dflt_wh: str | None = None
    card_code: str | None = None
    supp_cat_num: str | None = Field(None, max_length=50)
    buy_unit_msr: str | None = Field(None, max_length=100)
    num_in_buy: Decimal | None = Field(None, gt=0)
    sal_unit_msr: str | None = Field(None, max_length=100)
    num_in_sale: Decimal | None = Field(None, gt=0)
    min_level: Decimal | None = Field(None, ge=0)
    max_level: Decimal | None = Field(None, ge=0)
    reorder_qty: Decimal | None = Field(None, ge=0)
    lead_time: int | None = Field(None, ge=0)
    min_ordr_qty: Decimal | None = Field(None, ge=0)
    user_text: str | None = Field(None, max_length=254)


class ItemIn(ItemFields):
    item_code: str = Field(..., max_length=50)
    item_name: str = Field(..., max_length=100)
    item_type: str = Field("I", pattern="^[ILT]$")
    itms_grp_cod: int
    invnt_item: bool = True
    sell_item: bool = True
    prchse_item: bool = True
    prices: dict[int, Decimal] | None = None


@router.post("/items", tags=["Inventory"], summary="Create an item")
def create_item(body: ItemIn, s: Session = Depends(get_session)) -> dict:
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    item = run(lambda: masterdata.create_item(s, masterdata.ItemRequest(**data)))
    return _item_out(item, s, detail=True)


def _item_or_404(s: Session, item_code: str) -> Item:
    i = s.get(Item, item_code)
    if i is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return i


@router.get("/items/{item_code}", tags=["Inventory"], summary="Item with stock per warehouse and prices")
def get_item(item_code: str, s: Session = Depends(get_session)) -> dict:
    return _item_out(_item_or_404(s, item_code), s, detail=True)


class ItemUpdate(ItemFields):
    item_name: str | None = Field(None, max_length=100)
    item_type: str | None = Field(None, pattern="^[ILT]$")
    sell_item: bool | None = None
    prchse_item: bool | None = None
    by_wh: bool | None = None
    frozen: bool | None = None


@router.patch("/items/{item_code}", tags=["Inventory"], summary="Change an item")
def update_item(item_code: str, body: ItemUpdate, s: Session = Depends(get_session)) -> dict:
    i = _item_or_404(s, item_code)
    data = body.model_dump(exclude_unset=True)
    for flag, attr in (("frozen", "frozen_for"), ("sell_item", "sell_item"), ("prchse_item", "prchse_item"),
                       ("by_wh", "by_wh")):
        if flag in data:
            setattr(i, attr, yn(data.pop(flag)))
    run(lambda: masterdata.validate_item_fields(s, {**{"min_level": i.min_level, "max_level": i.max_level}, **data}))
    apply_changes(i, data)
    s.commit()
    return _item_out(i, s, detail=True)


class ItemWarehouseIn(BaseModel):
    min_stock: Decimal | None = Field(None, ge=0)
    max_stock: Decimal | None = Field(None, ge=0)
    locked: bool | None = None


@router.patch("/items/{item_code}/warehouses/{whs_code}", tags=["Inventory"],
              summary="Minimum / maximum stock and lock of an item in a warehouse")
def update_item_warehouse(item_code: str, whs_code: str, body: ItemWarehouseIn, s: Session = Depends(get_session)) -> dict:
    row = s.get(ItemWarehouse, (item_code, whs_code))
    if row is None:
        raise HTTPException(status_code=404, detail="Item has no row in this warehouse")
    data = body.model_dump(exclude_unset=True)
    if "locked" in data:
        row.locked = yn(data.pop("locked"))
    apply_changes(row, data)
    if row.max_stock and row.max_stock < row.min_stock:
        raise HTTPException(status_code=422, detail="The maximum stock is below the minimum stock")
    s.commit()
    return {"whs_code": whs_code, "min_stock": row.min_stock, "max_stock": row.max_stock, "locked": row.locked == "Y"}


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
