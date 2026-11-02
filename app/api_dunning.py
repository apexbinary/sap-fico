"""REST endpoints: dunning terms and the dunning wizard."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.admin import DunningLevel, DunningTerm
from app.models.banking import DunningRun
from app.services import dunning

router = APIRouter()


def _term_out(s: Session, t: DunningTerm) -> dict:
    return {"code": t.code, "name": t.name, "interest": t.interest, "highest": t.highest == "Y", "days_between": t.days_between,
            "levels": [{"level": l.level, "days": l.days, "fee": l.fee, "min_balance": l.min_balance, "letter_text": l.letter_text}
                       for l in s.scalars(select(DunningLevel).where(DunningLevel.term_code == t.code).order_by(DunningLevel.level))]}


@router.get("/dunning/terms", tags=["Dunning"], summary="Dunning terms (ODUT) with their levels (DUT1)")
def terms(s: Session = Depends(get_session)) -> list[dict]:
    return [_term_out(s, t) for t in s.scalars(select(DunningTerm).order_by(DunningTerm.code))]


class LevelIn(BaseModel):
    days: int = Field(..., ge=0)
    fee: Decimal = Field(Decimal("0"), ge=0)
    min_balance: Decimal = Field(Decimal("0"), ge=0)
    letter_text: str | None = Field(None, max_length=1000)


class TermIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=8)
    name: str = Field(..., max_length=50)
    interest: Decimal = Field(Decimal("0"), ge=0, lt=100)
    highest: bool = False
    days_between: int = Field(7, ge=0)
    levels: list[LevelIn]


@router.post("/dunning/terms", tags=["Dunning"], summary="Add / change a dunning term")
def save_term(body: TermIn, s: Session = Depends(get_session)) -> dict:
    t = run(lambda: dunning.save_term(s, body.code, body.name, body.interest, body.highest,
                                      [l.model_dump() for l in body.levels], body.days_between))
    return _term_out(s, t)


@router.get("/dunning/preview", tags=["Dunning"], summary="Dunning letters a run on a date would produce")
def preview(on: date, card_codes: str | None = None, highest: bool | None = None, s: Session = Depends(get_session)) -> list[dict]:
    codes = [c.strip() for c in card_codes.split(",")] if card_codes else None
    return run(lambda: dunning.preview(s, on, codes, highest))


class RunIn(BaseModel):
    dun_date: date
    card_codes: list[str] | None = None
    highest: bool | None = None
    post_fees: bool = False
    name: str | None = Field(None, max_length=50)


def _run_out(r: DunningRun, letters: bool = False) -> dict:
    out = {"abs_entry": r.abs_entry, "wizard_name": r.wizard_name, "dun_date": r.dun_date, "highest": r.highest == "Y",
           "post_fees": r.post_fees == "Y", "letters_count": len(r.letters),
           "total_interest": sum((l.interest for l in r.letters), Decimal("0")),
           "total_fee": sum((l.fee for l in r.letters), Decimal("0"))}
    if letters:
        out["letters"] = [{"letter_num": l.letter_num, "card_code": l.card_code, "card_name": l.card_name, "level": l.level,
                           "total_open": l.total_open, "interest": l.interest, "fee": l.fee, "trans_id": l.trans_id,
                           "letter_text": l.letter_text,
                           "items": [{k: getattr(i, k) for k in ("trans_id", "line_id", "trans_type", "doc_num", "due_date",
                                                                  "days_overdue", "open_amount", "old_level", "new_level",
                                                                  "interest")} for i in l.items]} for l in r.letters]
    return out


@router.post("/dunning/runs", tags=["Dunning"], summary="Execute the dunning wizard")
def execute(body: RunIn, s: Session = Depends(get_session)) -> dict:
    return _run_out(run(lambda: dunning.run(s, body.dun_date, body.card_codes, body.highest, body.post_fees, body.name)),
                    letters=True)


@router.get("/dunning/runs", tags=["Dunning"], summary="Dunning runs (ODWZ)")
def runs(s: Session = Depends(get_session)) -> list[dict]:
    return [_run_out(r) for r in s.scalars(select(DunningRun).order_by(DunningRun.abs_entry.desc()).limit(100))]


@router.get("/dunning/runs/{abs_entry}", tags=["Dunning"], summary="A dunning run with its letters")
def get_run(abs_entry: int, s: Session = Depends(get_session)) -> dict:
    r = s.get(DunningRun, abs_entry)
    if r is None:
        raise HTTPException(status_code=404, detail="Dunning run not found")
    return _run_out(r, letters=True)
