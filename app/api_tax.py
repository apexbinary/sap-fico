"""REST endpoints: tax setup — tax types, tax authorities, tax codes with components, HSN / SAC codes,
tax code determination."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.admin import HsnCode, TaxAuthority, TaxDetermination, TaxGroup, TaxType
from app.services import tax

router = APIRouter()


@router.get("/tax/setup", tags=["Tax setup"], summary="Tax types, authorities, codes, HSN / SAC codes, determination rules")
def tax_setup(s: Session = Depends(get_session)) -> dict:
    return {
        "types": [{"code": t.code, "name": t.name} for t in s.scalars(select(TaxType).order_by(TaxType.code))],
        "authorities": [{"code": a.code, "name": a.name, "type": a.type, "sales_tax": a.sales_tax, "purch_tax": a.purch_tax,
                         "rvs_chrg_act": a.rvs_chrg_act}
                        for a in s.scalars(select(TaxAuthority).order_by(TaxAuthority.code))],
        "codes": [{"code": t.code, "name": t.name, "category": t.category, "rate": t.rate, "account": t.account,
                   "inactive": t.inactive, "rev_charge": t.rev_charge, "gst": tax.gst_kind(s, t), "used": tax.tax_code_used(s, t.code),
                   "components": [{"sta_code": a.code, "rate": r} for a, r in tax.components(s, t)]}
                  for t in s.scalars(select(TaxGroup).order_by(TaxGroup.category.desc(), TaxGroup.rate, TaxGroup.code))],
        "hsn": [{"abs_entry": h.abs_entry, "chapter_id": h.chapter_id, "dscription": h.dscription, "item_type": h.item_type}
                for h in s.scalars(select(HsnCode).order_by(HsnCode.chapter_id))],
        "determination": [{k: getattr(r, k) for k in ["abs_id", *tax.DETERMINATION_FIELDS]}
                          for r in s.scalars(select(TaxDetermination).order_by(TaxDetermination.doc_area,
                                                                               TaxDetermination.priority,
                                                                               TaxDetermination.abs_id))],
    }


class TaxTypeIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=8)
    name: str = Field(..., max_length=50)


@router.post("/tax/types", tags=["Tax setup"], summary="Add / change a tax type (OSTT)")
def save_type(body: TaxTypeIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: tax.save_tax_type(s, body.code, body.name))
    return body.model_dump()


class TaxAuthorityIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=8)
    name: str = Field(..., max_length=50)
    type: str | None = Field(None, max_length=8)
    sales_tax: str
    purch_tax: str
    rvs_chrg_act: str | None = None  # reverse charge liability


@router.post("/tax/authorities", tags=["Tax setup"], summary="Add / change a tax authority (OSTA) with its accounts")
def save_authority(body: TaxAuthorityIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: tax.save_tax_authority(s, body.code, body.name, body.type, body.sales_tax, body.purch_tax, body.rvs_chrg_act))
    return body.model_dump()


class ComponentIn(BaseModel):
    sta_code: str
    rate: Decimal = Field(..., ge=0, lt=100)


class TaxCodeIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=8)
    name: str = Field(..., max_length=30)
    category: str = Field(..., pattern="^[OI]$")
    components: list[ComponentIn] = []
    rate: Decimal | None = Field(None, ge=0, lt=100)  # without components
    account: str | None = None  # without components
    inactive: bool = False
    rev_charge: str = Field("N", pattern="^[NYI]$")  # N normal, Y reverse charge, I import of goods


@router.post("/tax/codes", tags=["Tax setup"], summary="Add / change a tax code (OVTG) and its components (STC1)")
def save_code(body: TaxCodeIn, s: Session = Depends(get_session)) -> dict:
    tg = run(lambda: tax.save_tax_code(s, body.code, body.name, body.category,
                                       [(c.sta_code, c.rate) for c in body.components], body.rate, body.account,
                                       body.inactive, body.rev_charge))
    return {"code": tg.code, "rate": tg.rate}


class HsnIn(BaseModel):
    chapter_id: str = Field(..., max_length=20)
    dscription: str = Field(..., max_length=254)
    item_type: str = Field("I", pattern="^[IS]$")


@router.post("/tax/hsn", tags=["Tax setup"], summary="Add an HSN / SAC code (OCHP)")
def add_hsn(body: HsnIn, s: Session = Depends(get_session)) -> dict:
    h = run(lambda: tax.save_hsn(s, body.chapter_id, body.dscription, body.item_type))
    return {"abs_entry": h.abs_entry, **body.model_dump()}


@router.put("/tax/hsn/{abs_entry}", tags=["Tax setup"], summary="Change an HSN / SAC code")
def update_hsn(abs_entry: int, body: HsnIn, s: Session = Depends(get_session)) -> dict:
    if s.get(HsnCode, abs_entry) is None:
        raise HTTPException(status_code=404, detail="HSN / SAC code not found")
    run(lambda: tax.save_hsn(s, body.chapter_id, body.dscription, body.item_type, abs_entry))
    return {"abs_entry": abs_entry, **body.model_dump()}


class DeterminationIn(BaseModel):
    priority: int = Field(10, ge=0)
    doc_area: str = Field(..., pattern="^[SP]$")
    card_code: str | None = None
    group_code: int | None = None
    item_code: str | None = None
    itms_grp_cod: int | None = None
    chapter_id: str | None = None
    state: str | None = Field(None, max_length=3)
    supply: str | None = Field(None, pattern="^[IO]$")
    tax_code: str
    descr: str | None = Field(None, max_length=100)
    active: bool = True


def _rule_data(body: DeterminationIn) -> dict:
    data = body.model_dump()
    data["active"] = "Y" if data["active"] else "N"
    return data


@router.post("/tax/determination", tags=["Tax setup"], summary="Add a tax code determination rule (OTCD)")
def add_rule(body: DeterminationIn, s: Session = Depends(get_session)) -> dict:
    r = run(lambda: tax.save_determination(s, _rule_data(body)))
    return {"abs_id": r.abs_id, **body.model_dump()}


@router.put("/tax/determination/{abs_id}", tags=["Tax setup"], summary="Change a tax code determination rule")
def update_rule(abs_id: int, body: DeterminationIn, s: Session = Depends(get_session)) -> dict:
    if s.get(TaxDetermination, abs_id) is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    run(lambda: tax.save_determination(s, _rule_data(body), abs_id))
    return {"abs_id": abs_id, **body.model_dump()}


@router.delete("/tax/determination/{abs_id}", tags=["Tax setup"], summary="Remove a tax code determination rule")
def delete_rule(abs_id: int, s: Session = Depends(get_session)) -> dict:
    r = s.get(TaxDetermination, abs_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    s.delete(r)
    s.commit()
    return {"deleted": abs_id}
