"""REST endpoints: GST returns GSTR-1 and GSTR-3B (India) and their JSON for the GST portal."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import gst_returns

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
