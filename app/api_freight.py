"""REST endpoints: freight / additional expenses (OEXD)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.admin import AdditionalExpense, TaxGroup
from app.models.finance import Account

router = APIRouter()


def _out(e: AdditionalExpense) -> dict:
    return {"expns_code": e.expns_code, "expns_name": e.expns_name, "rev_acct": e.rev_acct, "expns_acct": e.expns_acct,
            "vat_group_o": e.vat_group_o, "vat_group_i": e.vat_group_i, "sac_code": e.sac_code, "fix_amnt": e.fix_amnt}


@router.get("/freight", tags=["Freight"], summary="Freight / additional expenses (OEXD)")
def list_freight(s: Session = Depends(get_session)) -> list[dict]:
    return [_out(e) for e in s.scalars(select(AdditionalExpense).order_by(AdditionalExpense.expns_code))]


class FreightIn(BaseModel):
    expns_name: str | None = Field(None, max_length=20)
    rev_acct: str | None = Field(None, max_length=15)
    expns_acct: str | None = Field(None, max_length=15)
    vat_group_o: str | None = Field(None, max_length=8)
    vat_group_i: str | None = Field(None, max_length=8)
    sac_code: str | None = Field(None, max_length=8)
    fix_amnt: Decimal | None = Field(None, ge=0)


def _save(s: Session, e: AdditionalExpense, body: FreightIn) -> dict:
    data = body.model_dump(exclude_unset=True)
    for key in ("rev_acct", "expns_acct"):
        if key in data:
            a = s.get(Account, data[key]) if data[key] else None
            if a is None or a.postable != "Y":
                raise HTTPException(status_code=422, detail=f"Account {data[key]} does not exist or is a title account")
    for key, cat in (("vat_group_o", "O"), ("vat_group_i", "I")):
        if data.get(key):
            tg = s.get(TaxGroup, data[key])
            if tg is None or tg.category != cat:
                raise HTTPException(status_code=422, detail=f"Tax code {data[key]} is not an {'output' if cat == 'O' else 'input'} tax code")
    if "sac_code" in data and data["sac_code"] and not data["sac_code"].isdigit():
        raise HTTPException(status_code=422, detail="The SAC code has digits only")
    for k, v in data.items():
        setattr(e, k, v if v != "" else None)
    if not e.expns_name or not e.rev_acct or not e.expns_acct:
        raise HTTPException(status_code=422, detail="Enter the name, the revenue account and the expense account")
    e.fix_amnt = e.fix_amnt or Decimal("0")
    s.commit()
    return _out(e)


@router.post("/freight", tags=["Freight"], summary="Add a freight / additional expense")
def add_freight(body: FreightIn, s: Session = Depends(get_session)) -> dict:
    e = AdditionalExpense(expns_code=(s.scalar(select(func.max(AdditionalExpense.expns_code))) or 0) + 1)
    s.add(e)
    try:
        return _save(s, e, body)
    except HTTPException:
        s.rollback()
        raise


@router.patch("/freight/{code}", tags=["Freight"], summary="Change a freight / additional expense")
def change_freight(code: int, body: FreightIn, s: Session = Depends(get_session)) -> dict:
    e = s.get(AdditionalExpense, code)
    if e is None:
        raise HTTPException(status_code=404, detail=f"Additional expense {code} does not exist")
    try:
        return _save(s, e, body)
    except HTTPException:
        s.rollback()
        raise
