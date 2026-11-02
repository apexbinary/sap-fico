"""REST endpoints: payment wizard."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.banking import PaymentRun
from app.services import paywiz

router = APIRouter()


def _run_out(r: PaymentRun, items: bool = False) -> dict:
    tot = paywiz.totals(r)
    out = {"id_entry": r.id_entry, "wizard_name": r.wizard_name, "pmnt_date": r.pmnt_date, "pay_type": r.pay_type,
           "pay_means": r.pay_means, "bank_acct": r.bank_acct, "due_date_to": r.due_date_to, "take_disc": r.take_disc == "Y",
           "status": r.status, "first_check": r.first_check, "items_count": len(r.items),
           "total": sum((v for v in tot.values() if v > 0), 0), "partners": {k: v for k, v in tot.items()}}
    if items:
        out["items"] = [{k: getattr(i, k) for k in ("line_num", "card_code", "trans_id", "line_id", "trans_type", "doc_num",
                                                     "due_date", "open_amount", "direction", "discount", "pay_entry")}
                        | {"selected": i.selected == "Y"} for i in r.items]
    return out


class RunIn(BaseModel):
    pmnt_date: date
    due_date_to: date
    bank_acct: str
    pay_type: str = Field("V", pattern="^[VC]$")
    pay_means: str = Field("T", pattern="^[TC]$")
    card_codes: list[str] | None = None
    take_disc: bool = True
    first_check: int | None = Field(None, gt=0)
    name: str | None = Field(None, max_length=50)


@router.post("/payment-wizard", tags=["Banking"], summary="Create a payment run (recommendation)")
def create(body: RunIn, s: Session = Depends(get_session)) -> dict:
    return _run_out(run(lambda: paywiz.create_run(s, paywiz.RunRequest(**body.model_dump()))), items=True)


@router.get("/payment-wizard", tags=["Banking"], summary="Payment runs (OPWZ)")
def runs(s: Session = Depends(get_session)) -> list[dict]:
    return [_run_out(r) for r in s.scalars(select(PaymentRun).order_by(PaymentRun.id_entry.desc()).limit(100))]


@router.get("/payment-wizard/{id_entry}", tags=["Banking"])
def get_run(id_entry: int, s: Session = Depends(get_session)) -> dict:
    r = s.get(PaymentRun, id_entry)
    if r is None:
        raise HTTPException(status_code=404, detail="Payment run not found")
    return _run_out(r, items=True)


class SelectIn(BaseModel):
    line_nums: list[int]
    selected: bool


@router.post("/payment-wizard/{id_entry}/select", tags=["Banking"], summary="Select / deselect items of a saved run")
def select_items(id_entry: int, body: SelectIn, s: Session = Depends(get_session)) -> dict:
    return _run_out(run(lambda: paywiz.select_items(s, id_entry, body.line_nums, body.selected)), items=True)


@router.post("/payment-wizard/{id_entry}/execute", tags=["Banking"], summary="Execute: one payment per business partner")
def execute(id_entry: int, s: Session = Depends(get_session)) -> dict:
    return _run_out(run(lambda: paywiz.execute(s, id_entry)), items=True)


@router.post("/payment-wizard/{id_entry}/cancel", tags=["Banking"], summary="Cancel a saved run")
def cancel(id_entry: int, s: Session = Depends(get_session)) -> dict:
    return _run_out(run(lambda: paywiz.cancel(s, id_entry)), items=True)
