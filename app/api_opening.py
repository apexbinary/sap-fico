"""REST endpoints: opening balances of G/L accounts, business partners and items."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import opening

router = APIRouter()
KINDS = {"accounts": opening.post_accounts, "partners": opening.post_partners, "items": opening.post_stock}


@router.get("/opening-balances", tags=["Opening balances"], summary="Posted opening balances and the difference left on the opening balance account")
def listing(s: Session = Depends(get_session)) -> dict:
    return opening.listing(s)


@router.post("/opening-balances/{kind}", tags=["Opening balances"], summary="Post opening balances (accounts / partners / items)")
def post(kind: str, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    if kind not in KINDS:
        raise HTTPException(status_code=404, detail="Opening balances of accounts, partners or items")
    r = run(lambda: KINDS[kind](s, body))
    return {"kind": kind, "number": getattr(r, "number", None) or r.doc_num, "trans_id": r.trans_id,
            "doc_entry": getattr(r, "doc_entry", None)}


@router.post("/opening-balances/{kind}/{key}/cancel", tags=["Opening balances"], summary="Cancel opening balances (reverse / cancel the goods receipt)")
def cancel(kind: str, key: int, s: Session = Depends(get_session)) -> dict:
    if kind not in KINDS:
        raise HTTPException(status_code=404, detail="Opening balances of accounts, partners or items")
    run(lambda: opening.cancel(s, kind, key))
    return {"ok": True}
