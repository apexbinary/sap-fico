"""REST endpoints for periodic processing: recurring entries and dunning."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import _request
from app.config import settings
from app.database import get_session
from app.models.dunning import DunningRunControl
from app.schemas import DocumentIn
from app.services import dunning, recurring
from app.services.fiscal import PostingError

router = APIRouter(tags=["Periodic processing"])


def _m(mandt: str | None) -> str:
    return mandt or settings.default_client


def _run_or_422(fn):
    try:
        return fn()
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class RecurringIn(BaseModel):
    document: DocumentIn
    dbbdt: date = Field(..., description="First run date")
    dbedt: date = Field(..., description="Last run date")
    dbmon: int = Field(1, ge=1, le=12, description="Interval in months")
    dbtag: int | None = Field(None, ge=1, le=31, description="Run day (default: day of the first run)")


class RecurringRunIn(BaseModel):
    bukrs: str
    settle_to: date = Field(..., description="Settlement date: post every run date up to here")


@router.get("/recurring", summary="Recurring entry originals with schedule")
def list_recurring(bukrs: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    return recurring.list_recurring(s, _m(mandt), bukrs)


@router.post("/recurring", summary="Create a recurring entry original (FBD1)")
def create_recurring(body: RecurringIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    doc = _run_or_422(lambda: recurring.create_recurring(
        s, _request(body.document, mandt), dbbdt=body.dbbdt, dbedt=body.dbedt, dbmon=body.dbmon, dbtag=body.dbtag))
    return {"belnr": doc.belnr, "gjahr": doc.gjahr, "bstat": doc.bstat}


@router.post("/recurring/run", summary="Recurring entry run (F.14)")
def run_recurring(body: RecurringRunIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    posted = _run_or_422(lambda: recurring.run_recurring(s, _m(mandt), body.bukrs, body.settle_to))
    return {"settle_to": body.settle_to, "posted": posted}


@router.delete("/recurring/{bukrs}/{gjahr}/{belnr}", summary="Delete a recurring entry original")
def delete_recurring(bukrs: str, gjahr: int, belnr: str, mandt: str = Query(default=None),
                     s: Session = Depends(get_session)) -> dict:
    _run_or_422(lambda: recurring.delete_recurring(s, _m(mandt), bukrs, belnr, gjahr))
    return {"deleted": f"{belnr.zfill(10)}/{gjahr}"}


class DunningProposalIn(BaseModel):
    laufd: date = Field(..., description="Run date")
    laufi: str = Field(..., min_length=1, max_length=6, description="Run identification")
    ausdt: date = Field(..., description="Dunning date (issue date of the notices)")
    bukrs: str
    kunnr_low: str | None = None
    kunnr_high: str | None = None


@router.get("/dunning-runs", summary="Dunning runs")
def list_dunning_runs(bukrs: str | None = None, mandt: str = Query(default=None),
                      s: Session = Depends(get_session)) -> list[dict]:
    stmt = select(DunningRunControl).where(DunningRunControl.mandt == _m(mandt))
    if bukrs:
        stmt = stmt.where(DunningRunControl.bukrs == bukrs)
    runs = s.scalars(stmt.order_by(DunningRunControl.laufd.desc(), DunningRunControl.laufi)).all()
    return [dunning.run_summary(r, with_items=False) for r in runs]


@router.post("/dunning-runs/proposal", summary="Create the dunning proposal (F150)")
def dunning_proposal(body: DunningProposalIn, mandt: str = Query(default=None),
                     s: Session = Depends(get_session)) -> dict:
    run = _run_or_422(lambda: dunning.create_proposal(
        s, _m(mandt), laufd=body.laufd, laufi=body.laufi.upper(), ausdt=body.ausdt, bukrs=body.bukrs,
        kunnr_low=body.kunnr_low.zfill(10) if body.kunnr_low else None,
        kunnr_high=body.kunnr_high.zfill(10) if body.kunnr_high else None,
    ))
    return dunning.run_summary(run)


@router.get("/dunning-runs/{laufd}/{laufi}", summary="Display a dunning run")
def get_dunning_run(laufd: date, laufi: str, mandt: str = Query(default=None),
                    s: Session = Depends(get_session)) -> dict:
    return dunning.run_summary(_run_or_422(lambda: dunning.get_run(s, _m(mandt), laufd, laufi)))


@router.delete("/dunning-runs/{laufd}/{laufi}", summary="Delete the dunning proposal")
def delete_dunning_run(laufd: date, laufi: str, mandt: str = Query(default=None),
                       s: Session = Depends(get_session)) -> dict:
    _run_or_422(lambda: dunning.delete_proposal(s, _m(mandt), laufd, laufi))
    return {"deleted": f"{laufd.isoformat()}/{laufi}"}


@router.post("/dunning-runs/{laufd}/{laufi}/execute", summary="Execute the dunning run (set dunning levels)")
def execute_dunning_run(laufd: date, laufi: str, mandt: str = Query(default=None),
                        s: Session = Depends(get_session)) -> dict:
    return dunning.run_summary(_run_or_422(lambda: dunning.execute(s, _m(mandt), laufd, laufi)))


@router.get("/dunning-runs/{laufd}/{laufi}/notice/{kunnr}", response_class=HTMLResponse,
            summary="Printable dunning notice")
def dunning_notice(laufd: date, laufi: str, kunnr: str, mandt: str = Query(default=None),
                   s: Session = Depends(get_session)) -> str:
    return _run_or_422(lambda: dunning.notice_html(s, _m(mandt), laufd, laufi, kunnr))
