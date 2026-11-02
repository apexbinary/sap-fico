"""REST endpoints for the automatic payment program (F110)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
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
    zwels: str = Field("T", min_length=1, description="Payment methods, e.g. 'TE' (transfer + direct debit)")
    zaldt: date = Field(..., description="Posting date of the payments")
    nedat: date = Field(..., description="Next payment run date")
    cpudt: date | None = Field(None, description="Documents entered up to (default today)")
    lifnr_low: str | None = None
    lifnr_high: str | None = None
    kunnr_low: str | None = None
    kunnr_high: str | None = None


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
        kunnr_low=body.kunnr_low.zfill(10) if body.kunnr_low else None,
        kunnr_high=body.kunnr_high.zfill(10) if body.kunnr_high else None,
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


@router.get("/{laufd}/{laufi}/sepa-dd", summary="Payment medium: SEPA direct debit (pain.008.001.02)")
def sepa_dd(laufd: date, laufi: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> Response:
    xml = _run_or_422(lambda: f110.sepa_direct_debit(s, _m(mandt), laufd, laufi))
    name = f"F110_{laufd:%Y%m%d}_{laufi}_pain008.xml"
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


class ItemBlockIn(BaseModel):
    bukrs: str
    belnr: str
    gjahr: int
    buzei: int
    block: bool = True


@router.post("/{laufd}/{laufi}/items/block", summary="Block / release an item in the payment proposal")
def block_item(laufd: date, laufi: str, body: ItemBlockIn, mandt: str = Query(default=None),
               s: Session = Depends(get_session)) -> dict:
    run = _run_or_422(lambda: f110.set_item_block(s, _m(mandt), laufd, laufi, body.bukrs, body.belnr, body.gjahr,
                                                  body.buzei, block=body.block))
    return f110.run_summary(run)


@router.get("/{laufd}/{laufi}/checks", response_class=HTMLResponse, summary="Printable checks of a payment run")
def print_checks(laufd: date, laufi: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> str:
    return _run_or_422(lambda: f110.checks_html(s, _m(mandt), laufd, laufi))


check_router = APIRouter(prefix="/checks", tags=["Automatic Payment Program (F110)"])


@check_router.get("", summary="Check register (PAYR)")
def check_register(mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    return [{"zbukr": c.zbukr, "hbkid": c.hbkid, "hktid": c.hktid, "chect": c.chect, "vblnr": c.vblnr,
             "gjahr": c.gjahr, "znme1": c.znme1, "rwbtr": c.rwbtr, "waers": c.waers, "zaldt": c.zaldt,
             "laufd": c.laufd, "laufi": c.laufi, "voidr": c.voidr, "voidd": c.voidd}
            for c in f110.checks_of(s, _m(mandt))]


class VoidIn(BaseModel):
    zbukr: str
    hbkid: str
    hktid: str
    chect: str
    voidr: str = Field("01", description="Void reason")
    reverse_payment: bool = Field(False, description="Also reset and reverse the payment document (FCH8)")


@check_router.post("/void", summary="Void a check (FCH9), optionally reversing the payment (FCH8)")
def void(body: VoidIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    return _run_or_422(lambda: f110.void_check(s, _m(mandt), body.zbukr, body.hbkid, body.hktid, body.chect,
                                               voidr=body.voidr, reverse_payment=body.reverse_payment))
