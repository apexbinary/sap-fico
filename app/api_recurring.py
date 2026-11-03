"""REST endpoints: recurring postings (ORCR / RCR1) and their execution."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.recurring import RecurringPosting
from app.services import recurring

router = APIRouter()


@router.get("/recurring-postings", tags=["Recurring postings"], summary="Templates and the instances due up to a date")
def list_templates(on: date | None = None, s: Session = Depends(get_session)) -> dict:
    on = on or date.today()
    return {"templates": [recurring.out(r) for r in s.scalars(select(RecurringPosting).order_by(RecurringPosting.rcur_code))],
            "due": recurring.due(s, on), "on": on, "frequencies": recurring.FREQUENCIES}


@router.post("/recurring-postings", tags=["Recurring postings"], summary="Add a template")
def add_template(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return recurring.out(run(lambda: recurring.save(s, body)))


@router.patch("/recurring-postings/{code}", tags=["Recurring postings"], summary="Change a template")
def change_template(code: str, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return recurring.out(run(lambda: recurring.save(s, body, code)))


class ExecuteIn(BaseModel):
    on: date
    codes: list[str]


@router.post("/recurring-postings/execute", tags=["Recurring postings"], summary="Post the due instances of templates")
def execute(body: ExecuteIn, s: Session = Depends(get_session)) -> dict:
    return {c: run(lambda c=c: recurring.execute(s, c, body.on)) for c in body.codes}
