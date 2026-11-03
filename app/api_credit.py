"""REST endpoints: credit limit / commitment limit check settings (General Settings -> BP)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import credit

router = APIRouter()


@router.get("/admin/credit-check", tags=["Administration"], summary="Credit / commitment limit check settings")
def get_settings(s: Session = Depends(get_session)) -> dict:
    return credit.settings(s)


class CreditIn(BaseModel):
    credit_check: str | None = Field(None, max_length=1)
    commitment_check: str | None = Field(None, max_length=1)
    documents: list[str] | None = None


@router.put("/admin/credit-check", tags=["Administration"], summary="Change the credit / commitment limit check")
def put_settings(body: CreditIn, s: Session = Depends(get_session)) -> dict:
    return run(lambda: credit.save_settings(s, body.model_dump(exclude_unset=True)))
