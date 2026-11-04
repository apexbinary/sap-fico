"""REST endpoints: GST returns GSTR-1 and GSTR-3B (India) and their JSON for the GST portal."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import gst_itc, gst_returns

router = APIRouter()
YEAR = Query(..., ge=2000, le=2100)
MONTH = Query(..., ge=1, le=12)


@router.get("/gst-returns/gstr1", tags=["GST returns"], summary="GSTR-1: outward supplies of a month")
def gstr1(year: int = YEAR, month: int = MONTH, s: Session = Depends(get_session)) -> dict:
    return run(lambda: gst_returns.gstr1(s, year, month))


@router.get("/gst-returns/gstr3b", tags=["GST returns"], summary="GSTR-3B: summary return with ITC set-off")
def gstr3b(year: int = YEAR, month: int = MONTH, s: Session = Depends(get_session)) -> dict:
    return run(lambda: gst_returns.gstr3b(s, year, month))


def _download(data: dict, name: str) -> JSONResponse:
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/gst-returns/gstr1/json", tags=["GST returns"], summary="GSTR-1 JSON (GSTN offline tool layout)")
def gstr1_json(year: int = YEAR, month: int = MONTH, s: Session = Depends(get_session)) -> JSONResponse:
    data = run(lambda: gst_returns.gstr1_json(s, year, month))
    return _download(data, f"GSTR1_{data['gstin']}_{data['fp']}.json")


@router.get("/gst-returns/gstr3b/json", tags=["GST returns"], summary="GSTR-3B JSON (GSTN offline tool layout)")
def gstr3b_json(year: int = YEAR, month: int = MONTH, s: Session = Depends(get_session)) -> JSONResponse:
    data = run(lambda: gst_returns.gstr3b_json(s, year, month))
    return _download(data, f"GSTR3B_{data['gstin']}_{data['ret_period']}.json")


@router.post("/gst-returns/gstr2b/reconcile", tags=["GST returns"], summary="Reconcile the GSTR-2B JSON of the portal with the A/P documents")
def gstr2b_reconcile(year: int = YEAR, month: int = MONTH, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return run(lambda: gst_itc.reconcile(s, year, month, body))


class ItcIn(BaseModel):
    kind: str = Field(..., pattern="^(B1|B2|D1)$")
    ref_date: date
    igst: Decimal = Field(Decimal("0"), ge=0)
    cgst: Decimal = Field(Decimal("0"), ge=0)
    sgst: Decimal = Field(Decimal("0"), ge=0)
    cess: Decimal = Field(Decimal("0"), ge=0)
    memo: str | None = Field(None, max_length=50)


@router.get("/gst-itc/reversals", tags=["GST returns"], summary="ITC reversals and reclaims (journal entries)")
def itc_list(date_from: date | None = None, date_to: date | None = None, s: Session = Depends(get_session)) -> dict:
    return gst_itc.listing(s, date_from, date_to)


@router.post("/gst-itc/reversals", tags=["GST returns"], summary="Post an ITC reversal (B1 / B2) or reclaim (D1)")
def itc_post(body: ItcIn, s: Session = Depends(get_session)) -> dict:
    je = run(lambda: gst_itc.post(s, body.kind, body.ref_date, body.model_dump(), body.memo))
    return {"trans_id": je.trans_id, "number": je.number}


@router.post("/gst-itc/reversals/{trans_id}/cancel", tags=["GST returns"], summary="Cancel an ITC reversal / reclaim")
def itc_cancel(trans_id: int, s: Session = Depends(get_session)) -> dict:
    je = run(lambda: gst_itc.cancel(s, trans_id))
    return {"trans_id": je.trans_id, "number": je.number}
