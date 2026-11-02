"""REST endpoints: incoming / outgoing payments, checks for receipt, deposits."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.banking import PAYMENT_CLASSES, CheckForReceipt, Deposit
from app.services import banking
from app.services.admin import B1Error

router = APIRouter()
KINDS = {"incoming": "24", "outgoing": "46"}


def _obj(kind: str) -> str:
    if kind not in KINDS:
        raise HTTPException(status_code=404, detail="Payment kind is incoming or outgoing")
    return KINDS[kind]


def _pay_out(p, detail: bool = False) -> dict:
    out = {"obj": p.obj_type, "doc_entry": p.doc_entry, "doc_num": p.doc_num, "doc_type": p.doc_type,
           "canceled": p.canceled == "Y", "series": p.series, "doc_date": p.doc_date, "doc_due_date": p.doc_due_date,
           "tax_date": p.tax_date, "card_code": p.card_code, "card_name": p.card_name, "doc_curr": p.doc_curr,
           "doc_rate": p.doc_rate, "doc_total": p.doc_total, "doc_total_fc": p.doc_total_fc,
           "pay_no_doc": p.pay_no_doc == "Y", "no_doc_sum": p.no_doc_sum, "open_bal": p.open_bal,
           "trans_id": p.trans_id, "counter_ref": p.counter_ref, "jrnl_memo": p.jrnl_memo}
    if detail:
        out.update(
            address=p.address, cntct_code=p.cntct_code, cash_acct=p.cash_acct, cash_sum=p.cash_sum,
            cash_sum_fc=p.cash_sum_fc, trsfr_acct=p.trsfr_acct, trsfr_sum=p.trsfr_sum, trsfr_sum_fc=p.trsfr_sum_fc,
            trsfr_date=p.trsfr_date, trsfr_ref=p.trsfr_ref, bank_chrg=p.bank_chrg, check_acct=p.check_acct,
            check_sum=p.check_sum, check_sum_fc=p.check_sum_fc, ref2=p.ref2, prj_code=p.prj_code, comments=p.comments,
            checks=[{"line_id": c.line_id, "due_date": c.due_date, "check_num": c.check_num, "bank_code": c.bank_code,
                     "branch": c.branch, "acct_num": c.acct_num, "country_cod": c.country_cod, "check_sum": c.check_sum,
                     "trnsfrable": c.trnsfrable == "Y", "check_act": c.check_act, "check_abs": c.check_abs} for c in p.checks],
            invoices=[{"invoice_id": i.invoice_id, "doc_entry": i.doc_entry, "inv_type": i.inv_type,
                       "doc_trans_id": i.doc_trans_id, "doc_line": i.doc_line, "sum_applied": i.sum_applied,
                       "applied_fc": i.applied_fc} for i in p.invoices],
            accounts=[{"line_id": a.line_id, "acct_code": a.acct_code, "sum_applied": a.sum_applied,
                       "applied_fc": a.applied_fc, "descrip": a.descrip, "prj_code": a.prj_code} for a in p.accounts])
    return out


@router.get("/payments/open-items", tags=["Banking"], summary="Open items of a business partner (what a payment can pay)")
def open_items(card_code: str, s: Session = Depends(get_session)) -> list[dict]:
    return banking.open_items(s, card_code)


@router.get("/payments/{kind}", tags=["Banking"], summary="Incoming (ORCT) or outgoing (OVPM) payments, newest first")
def list_payments(kind: str, card_code: str | None = None, limit: int = 100, s: Session = Depends(get_session)) -> list[dict]:
    header_cls = PAYMENT_CLASSES[_obj(kind)][0]
    q = select(header_cls).order_by(header_cls.doc_entry.desc()).limit(limit)
    if card_code:
        q = q.where(header_cls.card_code == card_code)
    return [_pay_out(p) for p in s.scalars(q)]


class CheckIn(BaseModel):
    check_num: int = Field(..., gt=0)
    check_sum: Decimal = Field(..., gt=0)
    due_date: date | None = None
    bank_code: str | None = Field(None, max_length=30)
    branch: str | None = Field(None, max_length=50)
    acct_num: str | None = Field(None, max_length=50)
    country_cod: str | None = Field(None, max_length=3)
    trnsfrable: bool = False


class ItemIn(BaseModel):
    trans_id: int
    line_id: int
    sum_applied: Decimal = Field(..., gt=0)


class AccountLineIn(BaseModel):
    acct_code: str
    sum_applied: Decimal = Field(..., gt=0)
    descrip: str | None = Field(None, max_length=254)
    prj_code: str | None = Field(None, max_length=20)


class PaymentIn(BaseModel):
    doc_date: date
    doc_type: str = Field("C", pattern="^[CSA]$")
    card_code: str | None = None
    doc_due_date: date | None = None
    tax_date: date | None = None
    doc_curr: str | None = Field(None, max_length=3)
    cash_acct: str | None = None
    cash_sum: Decimal = Field(Decimal("0"), ge=0)
    trsfr_acct: str | None = None
    trsfr_sum: Decimal = Field(Decimal("0"), ge=0)
    trsfr_date: date | None = None
    trsfr_ref: str | None = Field(None, max_length=27)
    bank_chrg: Decimal = Field(Decimal("0"), ge=0)
    check_acct: str | None = None
    checks: list[CheckIn] = []
    items: list[ItemIn] = []
    accounts: list[AccountLineIn] = []
    pay_no_doc: bool = False
    cntct_code: int | None = None
    counter_ref: str | None = Field(None, max_length=8)
    ref2: str | None = Field(None, max_length=11)
    prj_code: str | None = Field(None, max_length=20)
    comments: str | None = Field(None, max_length=254)
    jrnl_memo: str | None = Field(None, max_length=50)


@router.post("/payments/{kind}", tags=["Banking"], summary="Add an incoming or outgoing payment")
def create_payment(kind: str, body: PaymentIn, s: Session = Depends(get_session)) -> dict:
    obj = _obj(kind)
    data = body.model_dump()
    req = banking.PaymentRequest(
        obj=obj, **{k: v for k, v in data.items() if k not in ("checks", "items", "accounts")},
        checks=[banking.CheckRequest(**c) for c in data["checks"]],
        items=[banking.PaidItem(**i) for i in data["items"]],
        accounts=[banking.AccountLine(**a) for a in data["accounts"]])
    return _pay_out(run(lambda: banking.create_payment(s, req)), detail=True)


@router.get("/payments/{kind}/{doc_entry}", tags=["Banking"])
def get_payment(kind: str, doc_entry: int, s: Session = Depends(get_session)) -> dict:
    try:
        return _pay_out(banking.get_payment(s, _obj(kind), doc_entry), detail=True)
    except B1Error as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CancelIn(BaseModel):
    cancel_date: date | None = None


@router.post("/payments/{kind}/{doc_entry}/cancel", tags=["Banking"], summary="Cancel a payment (reopens the paid items)")
def cancel_payment(kind: str, doc_entry: int, body: CancelIn, s: Session = Depends(get_session)) -> dict:
    return _pay_out(run(lambda: banking.cancel_payment(s, _obj(kind), doc_entry, body.cancel_date)), detail=True)


# ------------------------------------------------------------- checks and deposits
def _check_out(c: CheckForReceipt) -> dict:
    return {"check_key": c.check_key, "check_num": c.check_num, "bank_code": c.bank_code, "branch": c.branch,
            "acct_num": c.acct_num, "check_date": c.check_date, "check_sum": c.check_sum, "currency": c.currency,
            "check_act": c.check_act, "card_code": c.card_code, "rcpt_num": c.rcpt_num,
            "deposited": c.deposited == "C", "dpst_abs": c.dpst_abs, "canceled": c.canceled == "Y"}


@router.get("/checks", tags=["Banking"], summary="Checks for receipt (OCHH)")
def checks(deposited: bool | None = None, s: Session = Depends(get_session)) -> list[dict]:
    q = select(CheckForReceipt).where(CheckForReceipt.canceled == "N").order_by(CheckForReceipt.check_date)
    if deposited is not None:
        q = q.where(CheckForReceipt.deposited == ("C" if deposited else "N"))
    return [_check_out(c) for c in s.scalars(q)]


def _dep_out(d: Deposit) -> dict:
    return {"depos_id": d.depos_id, "depos_num": d.depos_num, "depos_type": d.depos_type, "depos_date": d.depos_date,
            "depos_curr": d.depos_curr, "banck_acct": d.banck_acct, "alloc_acct": d.alloc_acct,
            "loc_total": d.loc_total, "bank_acc_num": d.bank_acc_num, "memo": d.memo, "trans_abs": d.trans_abs,
            "canceled": d.canceled == "Y", "project": d.project}


@router.get("/deposits", tags=["Banking"], summary="Deposits (ODPS)")
def deposits(s: Session = Depends(get_session)) -> list[dict]:
    return [_dep_out(d) for d in s.scalars(select(Deposit).order_by(Deposit.depos_id.desc()))]


class DepositIn(BaseModel):
    depos_type: str = Field(..., pattern="^[KC]$", description="K checks, C cash")
    depos_date: date
    banck_acct: str
    check_keys: list[int] = []
    alloc_acct: str | None = None  # cash account (cash deposit)
    amount: Decimal | None = Field(None, gt=0)
    bank_acc_num: str | None = Field(None, max_length=50)
    memo: str | None = Field(None, max_length=254)
    project: str | None = Field(None, max_length=20)


@router.post("/deposits", tags=["Banking"], summary="Deposit checks or cash to a bank account")
def create_deposit(body: DepositIn, s: Session = Depends(get_session)) -> dict:
    if body.depos_type == "K":
        dep = run(lambda: banking.deposit_checks(s, body.depos_date, body.banck_acct, body.check_keys, body.memo,
                                                 body.project, body.bank_acc_num))
    else:
        if not body.alloc_acct or body.amount is None:
            raise HTTPException(status_code=422, detail="A cash deposit needs the cash account and the amount")
        dep = run(lambda: banking.deposit_cash(s, body.depos_date, body.banck_acct, body.alloc_acct, body.amount,
                                               body.memo, body.project, body.bank_acc_num))
    return _dep_out(dep)


@router.post("/deposits/{depos_id}/cancel", tags=["Banking"], summary="Cancel a deposit (checks return to the register)")
def cancel_deposit(depos_id: int, body: CancelIn, s: Session = Depends(get_session)) -> dict:
    return _dep_out(run(lambda: banking.cancel_deposit(s, depos_id, body.cancel_date)))
