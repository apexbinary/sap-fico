"""REST endpoints: bills of materials and production orders."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.production import BillOfMaterials, ProductionOrder
from app.services import production

router = APIRouter()


@router.get("/production/boms", tags=["Production"], summary="Bills of materials")
def boms(s: Session = Depends(get_session)) -> list[dict]:
    return [production.bom_out(s, b) for b in s.scalars(select(BillOfMaterials).order_by(BillOfMaterials.code))]


@router.put("/production/boms/{code}", tags=["Production"], summary="Add or change the bill of materials of an item")
def save_bom(code: str, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return production.bom_out(s, run(lambda: production.save_bom(s, code, body)))


@router.get("/production/orders", tags=["Production"], summary="Production orders")
def orders(s: Session = Depends(get_session)) -> list[dict]:
    return [production.out(s, p) for p in s.scalars(select(ProductionOrder).order_by(ProductionOrder.doc_entry.desc()))]


class OrderIn(BaseModel):
    item_code: str
    planned_qty: Decimal = Field(..., gt=0)
    post_date: date
    due_date: date | None = None
    warehouse: str | None = None
    card_code: str | None = None
    comments: str | None = Field(None, max_length=254)
    release: bool = False
    origin_num: int | None = None  # sales order no. (made to order)
    project: str | None = Field(None, max_length=20)
    ocr_code: str | None = Field(None, max_length=8)
    line_whs: dict[str, str] | None = None  # component line no. -> warehouse (default: the BOM line's, else the order's)


@router.post("/production/orders", tags=["Production"], summary="Add a production order (components from the BOM)")
def add_order(body: OrderIn, s: Session = Depends(get_session)) -> dict:
    return production.out(s, run(lambda: production.create_order(s, body.item_code, body.planned_qty, body.post_date, body.due_date,
                                                                 body.warehouse, body.card_code, body.comments, body.release,
                                                                 body.origin_num, body.project, body.ocr_code, body.line_whs)))


@router.get("/production/orders/{entry}", tags=["Production"], summary="A production order")
def get_order(entry: int, s: Session = Depends(get_session)) -> dict:
    return production.out(s, run(lambda: production.get(s, entry)))


@router.post("/production/orders/{entry}/release", tags=["Production"], summary="Release a planned order")
def release(entry: int, s: Session = Depends(get_session)) -> dict:
    return production.out(s, run(lambda: production.release(s, entry)))


class IssueIn(BaseModel):
    doc_date: date
    lines: list[dict] | None = None  # [{line_num, quantity, batches}] (empty: all remaining manual components)


@router.post("/production/orders/{entry}/issue", tags=["Production"], summary="Issue components for production")
def issue(entry: int, body: IssueIn, s: Session = Depends(get_session)) -> dict:
    return production.out(s, run(lambda: production.issue(s, entry, body.doc_date, body.lines)))


class ReceiptIn(BaseModel):
    doc_date: date
    quantity: Decimal = Field(..., gt=0)
    batches: list[dict] | None = None


@router.post("/production/orders/{entry}/receive", tags=["Production"], summary="Receipt from production (backflush)")
def receive(entry: int, body: ReceiptIn, s: Session = Depends(get_session)) -> dict:
    return production.out(s, run(lambda: production.receive(s, entry, body.doc_date, body.quantity, body.batches)))


class DateIn(BaseModel):
    doc_date: date


@router.post("/production/orders/{entry}/close", tags=["Production"], summary="Close (variance to the variance account)")
def close(entry: int, body: DateIn, s: Session = Depends(get_session)) -> dict:
    return production.out(s, run(lambda: production.close(s, entry, body.doc_date)))


@router.post("/production/orders/{entry}/cancel", tags=["Production"], summary="Cancel a production order without postings")
def cancel(entry: int, s: Session = Depends(get_session)) -> dict:
    return production.out(s, run(lambda: production.cancel(s, entry)))


@router.get("/production/mrp", tags=["Production"], summary="MRP: net requirements and order recommendations up to a horizon")
def mrp_run(horizon: date, s: Session = Depends(get_session)) -> dict:
    from app.services import mrp

    return run(lambda: mrp.run(s, horizon))


class MrpCreateIn(BaseModel):
    doc_date: date
    recommendations: list[dict]
    default_vendor: str | None = None


@router.post("/production/mrp/create", tags=["Production"], summary="Create purchase / production orders from recommendations")
def mrp_create(body: MrpCreateIn, s: Session = Depends(get_session)) -> dict:
    from app.services import mrp

    return run(lambda: mrp.create_documents(s, body.recommendations, body.doc_date, body.default_vendor))
