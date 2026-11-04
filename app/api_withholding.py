"""REST endpoints: withholding tax codes (OWHT, India TDS / TCS), the TDS / TCS register, challans,
quarterly returns (26Q / 27EQ) and certificates (16A / 27D)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
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
    wt_kind: str | None = Field(None, pattern="^[DC]$")  # D TDS, C TCS
    base_type: str | None = Field(None, pattern="^[NG]$")  # N net, G gross incl. GST
    inactive: bool | None = None


@router.post("/withholding-tax", tags=["Withholding tax"], summary="Add a withholding tax code")
def add_code(body: CodeIn, s: Session = Depends(get_session)) -> dict:
    return withholding.code_out(run(lambda: withholding.save_code(s, body.model_dump(exclude_unset=True))))


@router.patch("/withholding-tax/{code}", tags=["Withholding tax"], summary="Change a withholding tax code")
def change_code(code: str, body: CodeIn, s: Session = Depends(get_session)) -> dict:
    return withholding.code_out(run(lambda: withholding.save_code(s, body.model_dump(exclude_unset=True), code)))


@router.get("/reports/tds", tags=["Financial reports"], summary="TDS / TCS register and summary per section and month, challans")
def tds_report(date_from: date, date_to: date, kind: str | None = Query(None, pattern="^[DC]$"), s: Session = Depends(get_session)) -> dict:
    return withholding.report(s, date_from, date_to, kind)


class ChallanIn(BaseModel):
    wt_kind: str = Field("D", pattern="^[DC]$")
    section: str = Field(..., max_length=10)
    period_to: date
    dep_date: date
    bsr_code: str | None = Field(None, max_length=7)
    challan_no: str | None = Field(None, max_length=5)
    bank_acct: str | None = Field(None, max_length=15)
    interest: Decimal | None = Field(None, ge=0)
    fee: Decimal | None = Field(None, ge=0)


@router.get("/withholding-tax/challans/preview", tags=["Withholding tax"], summary="Deductions a challan would deposit, with interest")
def challan_preview(section: str, period_to: date, dep_date: date, wt_kind: str = Query("D", pattern="^[DC]$"),
                    s: Session = Depends(get_session)) -> dict:
    return withholding.challan_preview(s, wt_kind, section, period_to, dep_date)


@router.post("/withholding-tax/challans", tags=["Withholding tax"], summary="Deposit TDS / TCS: challan with its bank journal entry")
def challan_add(body: ChallanIn, s: Session = Depends(get_session)) -> dict:
    return withholding.challan_out(run(lambda: withholding.create_challan(s, body.model_dump())))


@router.post("/withholding-tax/challans/{abs_entry}/cancel", tags=["Withholding tax"], summary="Cancel a challan (reverses its journal entry)")
def challan_cancel(abs_entry: int, s: Session = Depends(get_session)) -> dict:
    run(lambda: withholding.cancel_challan(s, abs_entry))
    return {"ok": True}


FY = Query(..., ge=2000, le=2100)
QTR = Query(..., ge=1, le=4)
KIND = Query("D", pattern="^[DC]$")


@router.get("/withholding-tax/returns", tags=["Withholding tax"], summary="Form 26Q (TDS) / 27EQ (TCS) of a quarter")
def quarterly_return(fy: int = FY, quarter: int = QTR, kind: str = KIND, s: Session = Depends(get_session)) -> dict:
    return run(lambda: withholding.quarterly_return(s, kind, fy, quarter))


@router.get("/withholding-tax/returns/csv", tags=["Withholding tax"], summary="Deductee records of 26Q / 27EQ as CSV")
def quarterly_csv(fy: int = FY, quarter: int = QTR, kind: str = KIND, s: Session = Depends(get_session)) -> Response:
    data = run(lambda: withholding.quarterly_csv(s, kind, fy, quarter))
    name = f"{'26Q' if kind == 'D' else '27EQ'}_{fy}_Q{quarter}.csv"
    return Response(data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/withholding-tax/certificate", tags=["Withholding tax"], summary="Form 16A (TDS) / 27D (TCS) of a deductee for a quarter")
def certificate(card_code: str, fy: int = FY, quarter: int = QTR, kind: str = KIND, s: Session = Depends(get_session)) -> dict:
    return run(lambda: withholding.certificate(s, kind, card_code, fy, quarter))
