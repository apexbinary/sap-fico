"""REST endpoints: batch and serial numbers (OBTN / OSRN with OBTQ / OSRQ) and their transactions."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import batches

router = APIRouter()


@router.get("/batches", tags=["Inventory"], summary="Batches / serial numbers with their quantity per warehouse")
def numbers(item_code: str | None = None, all: bool = False, s: Session = Depends(get_session)) -> list[dict]:
    return batches.numbers(s, item_code, with_stock=not all)


@router.get("/batches/history", tags=["Inventory"], summary="Transactions of a batch / serial number")
def history(item_code: str, number: str, s: Session = Depends(get_session)) -> list[dict]:
    return run(lambda: batches.history(s, item_code, number))
