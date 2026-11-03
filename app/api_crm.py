"""REST endpoints: CRM — sales stages, opportunities, activities, calendar, pipeline."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.crm import Opportunity
from app.services import crm

router = APIRouter()


@router.get("/crm/stages", tags=["CRM"], summary="Sales stages")
def list_stages(s: Session = Depends(get_session)) -> list[dict]:
    return [{"num": x.num, "descript": x.descript, "clo_prcnt": x.clo_prcnt, "step_id": x.step_id} for x in crm.stages(s)]


@router.post("/crm/stages", tags=["CRM"], summary="Add a sales stage")
def add_stage(body: dict = Body(...), s: Session = Depends(get_session)) -> list[dict]:
    run(lambda: crm.save_stage(s, body))
    return list_stages(s)


@router.get("/crm/opportunities", tags=["CRM"], summary="Sales opportunities")
def list_opportunities(status: str | None = None, card_code: str | None = None, s: Session = Depends(get_session)) -> list[dict]:
    q = select(Opportunity).order_by(Opportunity.oppr_id.desc())
    if status:
        q = q.where(Opportunity.status == status)
    if card_code:
        q = q.where(Opportunity.card_code == card_code)
    return [crm.opportunity_out(s, o) for o in s.scalars(q)]


@router.post("/crm/opportunities", tags=["CRM"], summary="Add a sales opportunity")
def add_opportunity(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return crm.opportunity_out(s, run(lambda: crm.create_opportunity(s, body)))


@router.get("/crm/opportunities/{oid}", tags=["CRM"], summary="A sales opportunity")
def get_opportunity(oid: int, s: Session = Depends(get_session)) -> dict:
    return crm.opportunity_out(s, run(lambda: crm.get(s, oid)))


class StageIn(BaseModel):
    stage: int
    amount: Decimal | None = None
    on: date | None = None
    memo: str | None = Field(None, max_length=254)
    obj_type: str | None = None
    doc_entry: int | None = None


@router.post("/crm/opportunities/{oid}/stage", tags=["CRM"], summary="Move an opportunity to a stage")
def advance(oid: int, body: StageIn, s: Session = Depends(get_session)) -> dict:
    return crm.opportunity_out(s, run(lambda: crm.advance(s, oid, body.stage, body.amount, body.on, body.memo, body.obj_type, body.doc_entry)))


class CloseIn(BaseModel):
    won: bool
    on: date | None = None
    reason: str | None = Field(None, max_length=100)
    obj_type: str | None = None
    doc_entry: int | None = None


@router.post("/crm/opportunities/{oid}/close", tags=["CRM"], summary="Close an opportunity as won or lost")
def close(oid: int, body: CloseIn, s: Session = Depends(get_session)) -> dict:
    return crm.opportunity_out(s, run(lambda: crm.close(s, oid, body.won, body.on, body.reason, body.obj_type, body.doc_entry)))


@router.get("/crm/pipeline", tags=["CRM"], summary="Open opportunities by stage and sales employee, won / lost")
def pipeline(slp_code: int | None = None, s: Session = Depends(get_session)) -> dict:
    return crm.pipeline(s, slp_code)


@router.get("/crm/activities", tags=["CRM"], summary="Activities (filter by dates, user, partner, open)")
def list_activities(date_from: date | None = None, date_to: date | None = None, user_id: int | None = None, card_code: str | None = None,
                    open_only: bool = False, s: Session = Depends(get_session)) -> dict:
    rows = crm.activities(s, date_from, date_to, user_id, card_code, open_only)
    return {"activities": [crm.activity_out(s, a) for a in rows], "actions": crm.ACTIONS, "priorities": crm.PRIORITIES}


@router.post("/crm/activities", tags=["CRM"], summary="Add an activity")
def add_activity(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return crm.activity_out(s, run(lambda: crm.save_activity(s, body)))


@router.patch("/crm/activities/{code}", tags=["CRM"], summary="Change / close an activity")
def change_activity(code: int, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return crm.activity_out(s, run(lambda: crm.save_activity(s, body, code)))
