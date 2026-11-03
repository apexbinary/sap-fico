"""REST endpoints: withholding tax codes (OWHT, India TDS) and the TDS report."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.admin import WithholdingTax
from app.services import withholding

router = APIRouter()


@router.get("/withholding-tax", tags=["Withholding tax"], summary="Withholding tax codes (OWHT)")
def codes(s: Session = Depends(get_session)) -> list[dict]:
    return [withholding.code_out(w) for w in s.scalars(select(WithholdingTax).order_by(WithholdingTax.wt_code))]


class CodeIn(BaseModel):
    wt_code: str | None = Field(None, max_length=4)
    wt_name: str | None = Field(None, max_length=50)
    rate: Decimal | None = None
    section: str | None = Field(None, max_length=10)
    account: str | None = Field(None, max_length=15)
    thr_single: Decimal | None = None
    thr_annual: Decimal | None = None
    thr_type: str | None = Field(None, max_length=1)
    rate_no_pan: Decimal | None = None
    inactive: bool | None = None


@router.post("/withholding-tax", tags=["Withholding tax"], summary="Add a withholding tax code")
def add_code(body: CodeIn, s: Session = Depends(get_session)) -> dict:
    return withholding.code_out(run(lambda: withholding.save_code(s, body.model_dump(exclude_unset=True))))


@router.patch("/withholding-tax/{code}", tags=["Withholding tax"], summary="Change a withholding tax code")
def change_code(code: str, body: CodeIn, s: Session = Depends(get_session)) -> dict:
    return withholding.code_out(run(lambda: withholding.save_code(s, body.model_dump(exclude_unset=True), code)))


@router.get("/reports/tds", tags=["Financial reports"], summary="TDS register and summary per section and month")
def tds_report(date_from: date, date_to: date, s: Session = Depends(get_session)) -> dict:
    return withholding.report(s, date_from, date_to)
