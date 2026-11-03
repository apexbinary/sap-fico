"""REST endpoints: inventory counting (OINC / INC1) and inventory posting (OIQR / IQR1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.counting import InventoryCounting
from app.services import counting

router = APIRouter()


@router.get("/inventory/counting", tags=["Inventory"], summary="Inventory countings")
def list_countings(s: Session = Depends(get_session)) -> list[dict]:
    rows = s.scalars(select(InventoryCounting).order_by(InventoryCounting.doc_entry.desc()))
    return [{"doc_entry": c.doc_entry, "doc_num": c.doc_num, "count_date": c.count_date, "status": c.status, "remarks": c.remarks,
             "lines": len(c.lines), "counted": sum(1 for l in c.lines if l.counted == "Y"),
             "differences": sum(1 for l in c.lines if l.counted == "Y" and l.difference)} for c in rows]


class CountLineIn(BaseModel):
    item_code: str
    whs_code: str


class CountingIn(BaseModel):
    count_date: date
    whs_code: str | None = None
    item_group: int | None = None
    lines: list[CountLineIn] | None = None
    remarks: str | None = Field(None, max_length=254)


@router.post("/inventory/counting", tags=["Inventory"], summary="New inventory counting (items or a whole warehouse)")
def create_counting(body: CountingIn, s: Session = Depends(get_session)) -> dict:
    c = run(lambda: counting.create(s, body.count_date, [l.model_dump() for l in body.lines] if body.lines else None,
                                    body.whs_code, body.item_group, body.remarks))
    return counting.out(s, c)


@router.get("/inventory/counting/{entry}", tags=["Inventory"], summary="An inventory counting")
def get_counting(entry: int, s: Session = Depends(get_session)) -> dict:
    return counting.out(s, run(lambda: counting.get(s, entry)))


class CountIn(BaseModel):
    line_num: int
    count_qty: Decimal | None = None
    batches: list[dict] | None = None
    remarks: str | None = Field(None, max_length=254)


@router.put("/inventory/counting/{entry}/counts", tags=["Inventory"], summary="Enter counted quantities")
def put_counts(entry: int, body: list[CountIn], s: Session = Depends(get_session)) -> dict:
    return counting.out(s, run(lambda: counting.record(s, entry, [c.model_dump(exclude_unset=True) for c in body])))


class PostIn(BaseModel):
    doc_date: date


@router.post("/inventory/counting/{entry}/post", tags=["Inventory"], summary="Inventory posting of the differences")
def post_counting(entry: int, body: PostIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: counting.post(s, entry, body.doc_date))
    return counting.out(s, counting.get(s, entry))


@router.post("/inventory/counting/{entry}/close", tags=["Inventory"], summary="Close a counting without posting")
def close_counting(entry: int, s: Session = Depends(get_session)) -> dict:
    return counting.out(s, run(lambda: counting.close(s, entry)))
