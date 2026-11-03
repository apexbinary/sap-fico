"""REST endpoints: approval stages / templates, approval requests and decisions, alerts."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import alerts, approvals

router = APIRouter()


def _me(s: Session):
    from app.context import current_user_id
    from app.models.users import User

    uid = current_user_id.get()
    u = s.get(User, uid) if uid else None
    return (u.user_id, u.superuser == "Y") if u else (None, True)


@router.get("/approvals/setup", tags=["Approvals"], summary="Approval stages and templates")
def setup(s: Session = Depends(get_session)) -> dict:
    return approvals.setup(s)


@router.post("/approvals/stages", tags=["Approvals"], summary="Add an approval stage")
def add_stage(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: approvals.save_stage(s, body))
    return approvals.setup(s)


@router.patch("/approvals/stages/{code}", tags=["Approvals"], summary="Change an approval stage")
def change_stage(code: int, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: approvals.save_stage(s, body, code))
    return approvals.setup(s)


@router.post("/approvals/templates", tags=["Approvals"], summary="Add an approval template")
def add_template(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: approvals.save_template(s, body))
    return approvals.setup(s)


@router.patch("/approvals/templates/{code}", tags=["Approvals"], summary="Change an approval template")
def change_template(code: int, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: approvals.save_template(s, body, code))
    return approvals.setup(s)


@router.get("/approval-requests", tags=["Approvals"], summary="My approval requests and the requests waiting for my decision")
def my_requests(s: Session = Depends(get_session)) -> dict:
    uid, sup = _me(s)
    return approvals.requests_for(s, uid, sup)


class DecisionIn(BaseModel):
    approve: bool
    remarks: str | None = Field(None, max_length=254)


@router.post("/approval-requests/{code}/decide", tags=["Approvals"], summary="Approve or reject a request")
def decide(code: int, body: DecisionIn, s: Session = Depends(get_session)) -> dict:
    uid, _ = _me(s)
    return approvals.out(s, run(lambda: approvals.decide(s, code, uid, body.approve, body.remarks)))


@router.post("/approval-requests/{code}/add", tags=["Approvals"], summary="Add the document of an approved request")
def add_document(code: int, s: Session = Depends(get_session)) -> dict:
    from app.api_documents import build_request
    from app.models.approvals import ApprovalRequest

    uid, sup = _me(s)
    req = s.get(ApprovalRequest, code)
    entry = run(lambda: approvals.generate(s, code, uid, sup, lambda p: build_request(req.obj_type, p)))
    return {"obj": req.obj_type, "doc_entry": entry}


@router.get("/alerts", tags=["Alerts"], summary="My alerts (evaluated now)")
def my_alerts(s: Session = Depends(get_session)) -> dict:
    uid, sup = _me(s)
    return alerts.for_user(s, uid)


@router.get("/alerts/setup", tags=["Alerts"], summary="Alert definitions")
def alert_setup(s: Session = Depends(get_session)) -> dict:
    return alerts.setup(s)


@router.patch("/alerts/setup/{code}", tags=["Alerts"], summary="Activate / change an alert and its recipients")
def alert_change(code: int, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: alerts.save(s, code, body))
    return alerts.setup(s)
