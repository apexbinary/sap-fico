"""REST endpoints: period-end closing of a financial year."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import closing

router = APIRouter()


@router.get("/period-end-closing", tags=["Period-end closing"], summary="Profit and loss balances of a year to close")
def preview(year: int, s: Session = Depends(get_session)) -> dict:
    return closing.preview(s, year)


class ClosingIn(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    closing_account: str = Field(..., max_length=15)
    lock: bool = True


@router.post("/period-end-closing", tags=["Period-end closing"], summary="Close a year (P&L to the closing account)")
def close_year(body: ClosingIn, s: Session = Depends(get_session)) -> dict:
    je = run(lambda: closing.run(s, body.year, body.closing_account, body.lock))
    return {**closing.preview(s, body.year), "trans_id": je.trans_id}


@router.post("/period-end-closing/{year}/cancel", tags=["Period-end closing"], summary="Cancel the closing of a year")
def cancel(year: int, s: Session = Depends(get_session)) -> dict:
    run(lambda: closing.cancel(s, year))
    return closing.preview(s, year)
