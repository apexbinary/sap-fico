"""REST endpoints for periodic processing: recurring entries."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import _request
from app.config import settings
from app.database import get_session
from app.schemas import DocumentIn
from app.services import recurring
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
