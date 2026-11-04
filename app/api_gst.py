"""REST endpoints: GST returns GSTR-1 and GSTR-3B (India) and their JSON for the GST portal."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import gst_filing, gst_itc, gst_returns

router = APIRouter()
YEAR = Query(..., ge=2000, le=2100)
MONTH = Query(..., ge=1, le=12)


def _with_filing(s: Session, ret: str, year: int, month: int, filed: bool, build) -> dict:
    """The return computed now, or (filed=true) as it was filed; with the filing status."""
    snap = gst_filing.snapshot(s, ret, year, month) if filed else None
    if filed and snap is None:
        raise HTTPException(status_code=404, detail=f"{gst_filing.RETURNS[ret]} for {month:02d}/{year} is not filed")
    data = snap or run(build)
    return {**data, "filing": gst_filing.status(s, ret, year, month), "as_filed": bool(snap)}


@router.get("/gst-returns/gstr1", tags=["GST returns"], summary="GSTR-1: outward supplies of a month (filed=true: as filed)")
def gstr1(year: int = YEAR, month: int = MONTH, filed: bool = False, s: Session = Depends(get_session)) -> dict:
    return _with_filing(s, "GSTR1", year, month, filed, lambda: gst_returns.gstr1(s, year, month))


@router.get("/gst-returns/gstr3b", tags=["GST returns"], summary="GSTR-3B: summary return with ITC set-off (filed=true: as filed)")
def gstr3b(year: int = YEAR, month: int = MONTH, filed: bool = False, s: Session = Depends(get_session)) -> dict:
    return _with_filing(s, "GSTR3B", year, month, filed, lambda: gst_returns.gstr3b(s, year, month))


class FilingIn(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    filed_date: date | None = None
    arn: str | None = Field(None, max_length=20)


@router.get("/gst-returns/filings", tags=["GST returns"], summary="Filing status of the GST returns")
def filings(s: Session = Depends(get_session)) -> list[dict]:
    from sqlalchemy import select

    from app.models.edocs import GstReturnFiling

    return [{"ret_type": f.ret_type, "period": f.period, "filed_date": f.filed_date, "arn": f.arn, "user_sign": f.user_sign}
            for f in s.scalars(select(GstReturnFiling).order_by(GstReturnFiling.period.desc(), GstReturnFiling.ret_type))]


@router.post("/gst-returns/{ret}/file", tags=["GST returns"], summary="Mark GSTR-1 / GSTR-3B of a month as filed (locks the month)")
def file_return(ret: str, body: FilingIn, s: Session = Depends(get_session)) -> dict:
    f = run(lambda: gst_filing.file_return(s, ret.upper(), body.year, body.month, body.filed_date, body.arn))
    return gst_filing.status(s, f.ret_type, body.year, body.month)


@router.post("/gst-returns/{ret}/unfile", tags=["GST returns"], summary="Undo the filing status (unlocks the month)")
def unfile_return(ret: str, body: FilingIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: gst_filing.unfile(s, ret.upper(), body.year, body.month))
    return {"ok": True}


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
