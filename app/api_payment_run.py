"""REST endpoints for the automatic payment program (F110)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.models.payment_run import PaymentRunControl
from app.services import payment_run as f110
from app.services.fiscal import PostingError

router = APIRouter(prefix="/payment-runs", tags=["Automatic Payment Program (F110)"])


def _m(mandt: str | None) -> str:
    return mandt or settings.default_client


class ProposalIn(BaseModel):
    laufd: date = Field(..., description="Run date")
    laufi: str = Field(..., min_length=1, max_length=6, description="Run identification")
    zbukr: str = Field(..., description="Paying company code")
    zwels: str = Field("T", min_length=1, description="Payment methods, e.g. 'T'")
    zaldt: date = Field(..., description="Posting date of the payments")
    nedat: date = Field(..., description="Next payment run date")
    cpudt: date | None = Field(None, description="Documents entered up to (default today)")
    lifnr_low: str | None = None
    lifnr_high: str | None = None


def _run_or_422(fn):
    try:
        return fn()
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", summary="Payment runs")
def list_runs(zbukr: str | None = None, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    stmt = select(PaymentRunControl).where(PaymentRunControl.mandt == _m(mandt))
    if zbukr:
        stmt = stmt.where(PaymentRunControl.zbukr == zbukr)
    runs = s.scalars(stmt.order_by(PaymentRunControl.laufd.desc(), PaymentRunControl.laufi)).all()
    return [f110.run_summary(r, with_items=False) for r in runs]


@router.post("/proposal", summary="Enter parameters and create the payment proposal")
def proposal(body: ProposalIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    run = _run_or_422(lambda: f110.create_proposal(
        s, _m(mandt), laufd=body.laufd, laufi=body.laufi.upper(), zbukr=body.zbukr,
        zwels=body.zwels.upper(), zaldt=body.zaldt, nedat=body.nedat, cpudt=body.cpudt,
        lifnr_low=body.lifnr_low.zfill(10) if body.lifnr_low else None,
        lifnr_high=body.lifnr_high.zfill(10) if body.lifnr_high else None,
    ))
    return f110.run_summary(run)


@router.get("/{laufd}/{laufi}", summary="Display payment run (proposal or payments)")
def get_run(laufd: date, laufi: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    return f110.run_summary(_run_or_422(lambda: f110.get_run(s, _m(mandt), laufd, laufi)))


@router.delete("/{laufd}/{laufi}", summary="Delete the payment proposal")
def delete_run(laufd: date, laufi: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    _run_or_422(lambda: f110.delete_proposal(s, _m(mandt), laufd, laufi))
    return {"deleted": f"{laufd.isoformat()}/{laufi}"}


@router.post("/{laufd}/{laufi}/execute", summary="Execute the payment run")
def execute(laufd: date, laufi: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    return f110.run_summary(_run_or_422(lambda: f110.execute(s, _m(mandt), laufd, laufi)))


@router.get("/{laufd}/{laufi}/sepa", summary="Payment medium: SEPA credit transfer (pain.001.001.03)")
def sepa(laufd: date, laufi: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> Response:
    xml = _run_or_422(lambda: f110.sepa_credit_transfer(s, _m(mandt), laufd, laufi))
    name = f"F110_{laufd:%Y%m%d}_{laufi}_pain001.xml"
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
