"""REST endpoints: fixed assets — classes, assets, capitalization, depreciation runs, retirement, register."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.assets import AssetClass, FixedAsset
from app.services import assets

router = APIRouter()


@router.get("/fixed-assets", tags=["Fixed assets"], summary="Asset classes and the asset register")
def register(s: Session = Depends(get_session)) -> dict:
    rows = [assets.out(a) for a in s.scalars(select(FixedAsset).order_by(FixedAsset.asset_code))]
    return {"classes": [assets.class_out(c) for c in s.scalars(select(AssetClass).order_by(AssetClass.code))], "assets": rows,
            "totals": {k: sum((Decimal(r[k]) for r in rows if r["status"] != "R"), Decimal(0)) for k in ("cost", "acc_dep", "book_value")}}


@router.post("/fixed-assets/classes", tags=["Fixed assets"], summary="Add an asset class")
def add_class(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return assets.class_out(run(lambda: assets.save_class(s, body)))


@router.patch("/fixed-assets/classes/{code}", tags=["Fixed assets"], summary="Change an asset class")
def change_class(code: str, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return assets.class_out(run(lambda: assets.save_class(s, body, code)))


@router.post("/fixed-assets", tags=["Fixed assets"], summary="Add a fixed asset")
def add_asset(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return assets.out(run(lambda: assets.save_asset(s, body)))


@router.patch("/fixed-assets/{code}", tags=["Fixed assets"], summary="Change a fixed asset")
def change_asset(code: str, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return assets.out(run(lambda: assets.save_asset(s, body, code)))


class CapIn(BaseModel):
    doc_date: date
    amount: Decimal = Field(..., gt=0)
    offset_acct: str


@router.post("/fixed-assets/{code}/capitalize", tags=["Fixed assets"], summary="Capitalize an acquisition value")
def capitalize(code: str, body: CapIn, s: Session = Depends(get_session)) -> dict:
    return assets.out(run(lambda: assets.capitalize(s, code, body.doc_date, body.amount, body.offset_acct)))


class RetireIn(BaseModel):
    doc_date: date
    proceeds: Decimal = Decimal("0")
    offset_acct: str | None = None


@router.post("/fixed-assets/{code}/retire", tags=["Fixed assets"], summary="Retire (sell / scrap) an asset")
def retire(code: str, body: RetireIn, s: Session = Depends(get_session)) -> dict:
    return assets.out(run(lambda: assets.retire(s, code, body.doc_date, body.proceeds, body.offset_acct)))


@router.get("/fixed-assets/depreciation", tags=["Fixed assets"], summary="Depreciation of a month (preview)")
def dep_preview(month: date, s: Session = Depends(get_session)) -> list[dict]:
    return run(lambda: assets.depreciation_preview(s, month))


class MonthIn(BaseModel):
    month: date


@router.post("/fixed-assets/depreciation", tags=["Fixed assets"], summary="Post the depreciation of a month")
def dep_run(body: MonthIn, s: Session = Depends(get_session)) -> dict:
    return {"trans_id": run(lambda: assets.run_depreciation(s, body.month))}


@router.post("/fixed-assets/depreciation/reverse", tags=["Fixed assets"], summary="Reverse the depreciation of a month")
def dep_reverse(body: MonthIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: assets.reverse_depreciation(s, body.month))
    return {"reversed": body.month}
