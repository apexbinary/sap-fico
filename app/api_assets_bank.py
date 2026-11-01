"""REST endpoints for Asset Accounting and Bank Accounting."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.models.assets import Asset, AssetValues
from app.models.bank import BankStatementHeader, BankStatementItem, HouseBank, HouseBankAccount
from app.services import asset_accounting as aa
from app.services import bank as bank_svc
from app.services.fiscal import PostingError

router = APIRouter(tags=["Assets & Bank"])


def _m(mandt: str | None) -> str:
    return mandt or settings.default_client


# ---------------- Assets ----------------
class AssetIn(BaseModel):
    bukrs: str
    anln1: str
    anlkl: str = "00003000"
    txt50: str
    useful_life_years: int = Field(5, ge=1)
    kostl: str | None = None
    scrap_value: Decimal = Decimal("0")


class AcquisitionIn(BaseModel):
    bukrs: str
    anln1: str
    amount: Decimal
    budat: date
    offset_account: str
    offset_is_vendor: bool = True


class DepRunIn(BaseModel):
    bukrs: str
    gjahr: int
    period: int


@router.get("/assets")
def list_assets(bukrs: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    m = _m(mandt)
    rows = s.scalars(select(Asset).where(Asset.mandt == m, Asset.bukrs == bukrs)).all()
    out = []
    for a in rows:
        val = s.get(AssetValues, (m, bukrs, a.anln1, a.anln2, date.today().year, "01"))
        apc = val.answl if val else Decimal("0")
        dep = val.nafag if val else Decimal("0")
        out.append({
            "anln1": a.anln1, "anln2": a.anln2, "anlkl": a.anlkl, "txt50": a.txt50,
            "aktiv": a.aktiv.isoformat() if a.aktiv else None, "active": a.xactive,
            "apc": str(apc), "depreciation": str(dep), "nbv": str(apc - dep),
        })
    return out


@router.post("/assets")
def create_asset(body: AssetIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    try:
        a = aa.create_asset(s, _m(mandt), body.bukrs, body.anln1, body.anlkl, body.txt50,
                            body.useful_life_years, kostl=body.kostl, scrap_value=body.scrap_value)
        return {"anln1": a.anln1, "anln2": a.anln2, "txt50": a.txt50}
    except PostingError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/assets/acquisition")
def post_acquisition(body: AcquisitionIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    try:
        return aa.post_acquisition(s, _m(mandt), body.bukrs, body.anln1, body.amount, body.budat,
                                   offset_account=body.offset_account, offset_is_vendor=body.offset_is_vendor)
    except PostingError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/assets/depreciation-run")
def depreciation_run(body: DepRunIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    try:
        return aa.run_depreciation(s, _m(mandt), body.bukrs, body.gjahr, body.period)
    except PostingError as e:
        raise HTTPException(422, str(e)) from e


# ---------------- Bank ----------------
class StatementItemIn(BaseModel):
    amount: Decimal
    shkzg: str = Field(..., pattern="^[SH]$")
    kunnr: str | None = None
    lifnr: str | None = None
    note: str | None = None
    partner: str | None = None


class StatementIn(BaseModel):
    bukrs: str
    hbkid: str
    hktid: str
    kukey: str
    statement_date: date
    opening: Decimal = Decimal("0")
    items: list[StatementItemIn]


@router.get("/master/house-banks")
def house_banks(bukrs: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    m = _m(mandt)
    rows = s.scalars(select(HouseBankAccount).where(HouseBankAccount.mandt == m, HouseBankAccount.bukrs == bukrs)).all()
    out = []
    for a in rows:
        hb = s.get(HouseBank, (m, bukrs, a.hbkid))
        out.append({"hbkid": a.hbkid, "hktid": a.hktid, "bankn": a.bankn, "iban": a.iban,
                    "waers": a.waers, "hkont": a.hkont, "bankl": hb.bankl if hb else None})
    return out


@router.get("/bank/statements")
def list_statements(bukrs: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    m = _m(mandt)
    rows = s.scalars(select(BankStatementHeader).where(BankStatementHeader.mandt == m, BankStatementHeader.bukrs == bukrs)).all()
    out = []
    for h in rows:
        n = len(s.scalars(select(BankStatementItem).where(BankStatementItem.mandt == m, BankStatementItem.kukey == h.kukey)).all())
        out.append({"kukey": h.kukey, "adatu": h.adatu.isoformat() if h.adatu else None,
                    "opening": str(h.anfsl), "closing": str(h.ensal), "items": n, "posted": h.xbobl})
    return out


@router.post("/bank/statements")
def import_statement(body: StatementIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    try:
        return bank_svc.import_statement(
            s, _m(mandt), body.bukrs, body.hbkid, body.hktid, body.kukey, body.statement_date,
            items=[i.model_dump() for i in body.items], opening=body.opening)
    except PostingError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/bank/statements/{kukey}/post")
def post_statement(kukey: str, bukrs: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    try:
        return bank_svc.post_statement(s, _m(mandt), bukrs, kukey)
    except PostingError as e:
        raise HTTPException(422, str(e)) from e
