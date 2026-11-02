"""REST endpoints for Controlling (CO)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.models.controlling import CODocumentHeader, COLineItem
from app.services import allocation, controlling, copa, settlement
from app.services.fiscal import PostingError

router = APIRouter(prefix="/co", tags=["Controlling"])


def _m(mandt: str | None) -> str:
    return mandt or settings.default_client


def _run_or_422(fn):
    try:
        return fn()
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/actuals", summary="Actual costs by cost center / internal order (S_ALR_87013611 / KOB1)")
def actuals(
    kokrs: str, gjahr: int, kind: Literal["KS", "OR"] = "KS", perio_from: int = 1, perio_to: int = 16,
    mandt: str = Query(default=None), s: Session = Depends(get_session),
) -> list[dict]:
    return _run_or_422(lambda: controlling.actuals(
        s, _m(mandt), kokrs, gjahr, kind=kind, perio_from=perio_from, perio_to=perio_to))


@router.get("/documents", summary="CO documents (COBK) with their lines")
def documents(
    kokrs: str, limit: int = 30, mandt: str = Query(default=None), s: Session = Depends(get_session),
) -> list[dict]:
    m = _m(mandt)
    docs = s.scalars(select(CODocumentHeader).where(
        CODocumentHeader.mandt == m, CODocumentHeader.kokrs == kokrs,
    ).order_by(CODocumentHeader.belnr.desc()).limit(limit)).all()
    out = []
    for d in docs:
        lines = s.scalars(select(COLineItem).where(
            COLineItem.mandt == m, COLineItem.kokrs == kokrs, COLineItem.belnr == d.belnr,
        ).order_by(COLineItem.buzei)).all()
        out.append({
            "belnr": d.belnr, "gjahr": d.gjahr, "perab": d.perab, "vrgng": d.vrgng, "budat": d.budat,
            "bltxt": d.bltxt, "refbn": d.refbn, "refgj": d.refgj, "kscyc": d.kscyc, "stokz": d.stokz,
            "stflg": d.stflg,
            "lines": [{"buzei": l.buzei, "objnr": l.objnr, "kstar": l.kstar, "amount": l.wkgbtr} for l in lines],
        })
    return out


class CycleRunIn(BaseModel):
    kokrs: str
    gjahr: int
    perio: int = Field(..., ge=1, le=16)
    test: bool = Field(True, description="Test run: show the allocation without posting")


@router.get("/cycles", summary="Assessment / distribution cycles with segments and runs")
def cycles(kokrs: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    return allocation.list_cycles(s, _m(mandt), kokrs)


@router.post("/cycles/{cycle}/run", summary="Run an assessment (KSU5) / distribution (KSV5) cycle")
def run_cycle(cycle: str, body: CycleRunIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    return _run_or_422(lambda: allocation.run_cycle(s, _m(mandt), body.kokrs, cycle, body.gjahr, body.perio,
                                                    test=body.test))


@router.post("/cycles/{cycle}/reverse", summary="Reverse a cycle run")
def reverse_cycle(cycle: str, body: CycleRunIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    return _run_or_422(lambda: allocation.reverse_run(s, _m(mandt), body.kokrs, cycle, body.gjahr, body.perio))


class SettleIn(BaseModel):
    kokrs: str
    gjahr: int
    perio: int = Field(..., ge=1, le=16)
    test: bool = Field(True, description="Test run: show the settlement without posting")


@router.get("/orders/{aufnr}/settlement-rule", summary="Settlement rule of an internal order (COBRB)")
def settlement_rule(aufnr: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    return settlement.rules_of(s, _m(mandt), aufnr)


@router.post("/orders/{aufnr}/settle", summary="Settle an internal order (KO88)")
def settle(aufnr: str, body: SettleIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    return _run_or_422(lambda: settlement.settle_order(s, _m(mandt), body.kokrs, aufnr, body.gjahr, body.perio,
                                                       test=body.test))


@router.get("/pa/contribution", summary="CO-PA contribution report by characteristic (KE30)")
def contribution(
    kokrs: str, gjahr: int, by: Literal["kndnr", "land1", "brsch", "kukla"] = "kndnr",
    perio_from: int = 1, perio_to: int = 16, mandt: str = Query(default=None), s: Session = Depends(get_session),
) -> dict:
    return _run_or_422(lambda: copa.contribution(s, _m(mandt), kokrs, gjahr, by=by,
                                                 perio_from=perio_from, perio_to=perio_to))
