"""REST endpoints for Controlling (CO)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.models.controlling import ActivityPrice, ActivityType, CODocumentHeader, COLineItem
from app.services import activity, allocation, controlling, copa, planning, settlement
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
    ledger: Literal["account", "costing"] = "account",
    perio_from: int = 1, perio_to: int = 16, mandt: str = Query(default=None), s: Session = Depends(get_session),
) -> dict:
    return _run_or_422(lambda: copa.contribution(s, _m(mandt), kokrs, gjahr, by=by, ledger=ledger,
                                                 perio_from=perio_from, perio_to=perio_to))


@router.get("/plan-actual", summary="Plan / actual / variance by cost center or order (S_ALR_87013611)")
def plan_actual(
    kokrs: str, gjahr: int, kind: Literal["KS", "OR"] = "KS", perio_from: int = 1, perio_to: int = 16,
    mandt: str = Query(default=None), s: Session = Depends(get_session),
) -> list[dict]:
    return _run_or_422(lambda: planning.plan_actual(s, _m(mandt), kokrs, gjahr, kind=kind,
                                                    perio_from=perio_from, perio_to=perio_to))


class PlanIn(BaseModel):
    kokrs: str
    kind: Literal["KS", "OR"] = "KS"
    object: str = Field(..., description="Cost center or order")
    kstar: str
    gjahr: int
    annual: Decimal | None = Field(None, description="Annual amount, spread evenly over periods 1-12")
    periods: list[Decimal] | None = Field(None, description="16 period values")


@router.post("/plan", summary="Enter plan costs (KP06)")
def enter_plan(body: PlanIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    values = body.periods if body.periods is not None else planning.spread(body.annual or Decimal("0"))
    objnr = (controlling.cost_center_objnr(body.kokrs, body.object.zfill(10)) if body.kind == "KS"
             else controlling.order_objnr(body.object.zfill(12)))
    _run_or_422(lambda: planning.set_plan(s, _m(mandt), body.kokrs, objnr, body.kstar, body.gjahr, values))
    return {"objnr": objnr, "kstar": body.kstar, "total": sum(values, Decimal("0"))}


@router.get("/activity-types", summary="Activity types with prices of a year (KP26)")
def activity_types(kokrs: str, gjahr: int, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    m = _m(mandt)
    out = []
    for a in s.scalars(select(ActivityType).where(ActivityType.mandt == m, ActivityType.kokrs == kokrs)):
        prices = [{"kostl": p.objnr[2 + len(kokrs):-len(a.lstar)], "price": p.tkg001}
                  for p in s.scalars(select(ActivityPrice).where(
                      ActivityPrice.mandt == m, ActivityPrice.kokrs == kokrs, ActivityPrice.gjahr == gjahr,
                      ActivityPrice.objnr.like(f"LT{kokrs}%{a.lstar}")))]
        out.append({"lstar": a.lstar, "ktext": a.ktext, "leinh": a.leinh, "vksta": a.vksta, "prices": prices})
    return out


class PriceIn(BaseModel):
    kokrs: str
    kostl: str
    lstar: str
    gjahr: int
    price: Decimal = Field(..., ge=0)


@router.post("/activity-prices", summary="Plan activity price (KP26)")
def activity_price(body: PriceIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    _run_or_422(lambda: planning.set_price(s, _m(mandt), body.kokrs, body.kostl.zfill(10), body.lstar,
                                           body.gjahr, body.price))
    return body.model_dump()


class AllocationIn(BaseModel):
    kokrs: str
    sender_kostl: str
    lstar: str
    quantity: Decimal
    gjahr: int
    perio: int = Field(..., ge=1, le=16)
    receiver_kostl: str | None = None
    receiver_aufnr: str | None = None


@router.post("/activity-allocations", summary="Direct activity allocation (KB21N)")
def allocate_activity(body: AllocationIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    return _run_or_422(lambda: activity.allocate(
        s, _m(mandt), body.kokrs, sender_kostl=body.sender_kostl.zfill(10), lstar=body.lstar,
        quantity=body.quantity, gjahr=body.gjahr, perio=body.perio,
        receiver_kostl=body.receiver_kostl.zfill(10) if body.receiver_kostl else None,
        receiver_aufnr=body.receiver_aufnr or None))


class CODocRef(BaseModel):
    kokrs: str


@router.post("/documents/{belnr}/reverse", summary="Reverse a CO document (KB24N / KB14N)")
def reverse_co_document(belnr: str, body: CODocRef, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    rev = _run_or_422(lambda: controlling.reverse_document(s, _m(mandt), body.kokrs, belnr))
    return {"reversed": belnr.zfill(10), "reversal": rev.belnr}


@router.post("/orders/{aufnr}/settle/reverse", summary="Reverse an order settlement (KO88 reversal)")
def reverse_settlement(aufnr: str, body: SettleIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    return _run_or_422(lambda: settlement.reverse_settlement(s, _m(mandt), body.kokrs, aufnr, body.gjahr, body.perio))
