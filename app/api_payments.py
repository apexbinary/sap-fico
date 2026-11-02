"""REST endpoints for payments and open-item clearing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.models.bank import HouseBankAccount
from app.models.payments import PaymentDifferenceReason
from app.services import clearing
from app.services.fiscal import PostingError

router = APIRouter(tags=["Payments & Clearing"])


def _m(mandt: str | None) -> str:
    return mandt or settings.default_client


class OpenItemRef(BaseModel):
    belnr: str
    gjahr: int
    buzei: int


class PaymentIn(BaseModel):
    bukrs: str
    koart: Literal["D", "K"] = Field(..., description="D = customer (incoming), K = vendor (outgoing)")
    account: str = Field(..., description="Customer or vendor number")
    budat: date
    bldat: date | None = None
    amount: Decimal = Field(..., gt=0, description="Amount paid")
    hbkid: str = Field(..., description="House bank")
    hktid: str = Field(..., description="House bank account ID")
    items: list[OpenItemRef] = []
    mode: Literal["clear", "residual", "partial", "on_account"] = "clear"
    apply_discount: bool = True
    rstgr: str | None = Field(None, description="Reason code for a payment difference / residual item")
    usnam: str = "SYSTEM"
    xblnr: str | None = None
    bktxt: str | None = None
    sgtxt: str | None = None


def _acct(koart: str, account: str) -> str:
    """Partner numbers are zero-padded; G/L account numbers are used as entered."""
    return account if koart == "S" else account.zfill(10)


class ClearingIn(BaseModel):
    bukrs: str
    koart: Literal["D", "K", "S"] = Field(..., description="D customer (F-32), K vendor (F-44), S G/L account (F-03)")
    account: str
    budat: date
    items: list[OpenItemRef]
    mode: Literal["clear", "residual"] = "clear"
    rstgr: str | None = None
    usnam: str = "SYSTEM"
    bktxt: str | None = None


@router.get("/payments/open-items", summary="Open items with due date and cash discount (payment proposal)")
def open_items(
    bukrs: str, koart: Literal["D", "K", "S"], account: str, budat: date | None = None,
    mandt: str = Query(default=None), s: Session = Depends(get_session),
) -> list[dict]:
    try:
        return clearing.proposal(s, _m(mandt), bukrs, koart, _acct(koart, account), budat or date.today())
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/payments/tolerance", summary="Permitted payment differences for a partner (T043G)")
def tolerance(
    bukrs: str, koart: Literal["D", "K"], account: str,
    mandt: str = Query(default=None), s: Session = Depends(get_session),
) -> dict:
    return clearing.tolerance_limits(s, _m(mandt), bukrs, koart, account.zfill(10))


@router.post("/payments", summary="Incoming / outgoing payment with clearing (F-28 / F-53)")
def post_payment(body: PaymentIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    m = _m(mandt)
    acct = s.get(HouseBankAccount, (m, body.bukrs, body.hbkid, body.hktid))
    if acct is None:
        raise HTTPException(status_code=422, detail=f"House bank account {body.hbkid}/{body.hktid} not defined")
    try:
        return clearing.post_payment(s, clearing.PaymentRequest(
            mandt=m, bukrs=body.bukrs, koart=body.koart, account=body.account.zfill(10),
            budat=body.budat, bldat=body.bldat, amount=body.amount, hkont=acct.hkont,
            items=[(i.belnr, i.gjahr, i.buzei) for i in body.items], mode=body.mode,
            apply_discount=body.apply_discount, xblnr=body.xblnr, bktxt=body.bktxt, sgtxt=body.sgtxt,
            rstgr=body.rstgr, usnam=body.usnam,
        ))
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/clearing", summary="Clear open items against each other (F-32 / F-44 / F-03)")
def post_clearing(body: ClearingIn, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> dict:
    try:
        return clearing.post_payment(s, clearing.PaymentRequest(
            mandt=_m(mandt), bukrs=body.bukrs, koart=body.koart, account=_acct(body.koart, body.account),
            budat=body.budat, items=[(i.belnr, i.gjahr, i.buzei) for i in body.items],
            mode=body.mode, apply_discount=False, bktxt=body.bktxt, rstgr=body.rstgr, usnam=body.usnam,
        ))
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/payments/reasons", summary="Reason codes for payment differences (T053R)")
def reasons(bukrs: str, mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    rows = s.scalars(select(PaymentDifferenceReason).where(
        PaymentDifferenceReason.mandt == _m(mandt), PaymentDifferenceReason.bukrs == bukrs)
        .order_by(PaymentDifferenceReason.rstgr)).all()
    return [{"rstgr": r.rstgr, "txt40": r.txt40, "xausb": r.xausb} for r in rows]
