"""REST endpoints: cost accounting setup (ODIM, OPRC, OOCR / OCR1) and the profit center report."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import costacct

router = APIRouter()


@router.get("/cost-accounting", tags=["Cost accounting"], summary="Dimensions, profit centers, distribution rules")
def setup(s: Session = Depends(get_session)) -> dict:
    return costacct.setup(s)


@router.patch("/cost-accounting/dimensions/{code}", tags=["Cost accounting"], summary="Rename / activate a dimension")
def dimension(code: int, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: costacct.save_dimension(s, code, body))
    return costacct.setup(s)


@router.post("/cost-accounting/centers", tags=["Cost accounting"], summary="Add a profit center (with its direct rule)")
def add_center(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: costacct.save_center(s, body))
    return costacct.setup(s)


@router.patch("/cost-accounting/centers/{code}", tags=["Cost accounting"], summary="Change a profit center")
def change_center(code: str, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: costacct.save_center(s, body, code))
    return costacct.setup(s)


@router.patch("/cost-accounting/rules/{code}", tags=["Cost accounting"], summary="Change a distribution rule")
def change_rule(code: str, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: costacct.save_rule(s, body, code))
    return costacct.setup(s)


@router.post("/cost-accounting/rules", tags=["Cost accounting"], summary="Add a distribution rule")
def add_rule(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: costacct.save_rule(s, body))
    return costacct.setup(s)


@router.get("/reports/profit-centers", tags=["Financial reports"], summary="Profit center report")
def report(date_from: date, date_to: date, dim: int = 1, s: Session = Depends(get_session)) -> dict:
    return run(lambda: costacct.report(s, date_from, date_to, dim))
