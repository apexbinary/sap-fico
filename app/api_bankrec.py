"""REST endpoints: house banks, bank statements, external (bank) reconciliation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.banking import Bank, BankStatement, ExternalReconciliation, HouseBankAccount
from app.services import bankrec, banking

router = APIRouter()


# ------------------------------------------------------------- house banks
@router.get("/house-banks", tags=["Bank reconciliation"], summary="Banks (ODSC) and house bank accounts (DSC1)")
def house_banks(s: Session = Depends(get_session)) -> dict:
    return {"banks": [{"abs_entry": b.abs_entry, "bank_code": b.bank_code, "bank_name": b.bank_name,
                       "country_cod": b.country_cod, "swift_num": b.swift_num}
                      for b in s.scalars(select(Bank).order_by(Bank.bank_code))],
            "accounts": [{"abs_entry": a.abs_entry, "bank_code": a.bank_code, "account": a.account, "branch": a.branch,
                          "iban": a.iban, "gl_account": a.gl_account, "acct_name": a.acct_name, "country": a.country,
                          "currency": a.currency} for a in s.scalars(select(HouseBankAccount).order_by(HouseBankAccount.abs_entry))]}


class BankIn(BaseModel):
    bank_code: str = Field(..., min_length=1, max_length=30)
    bank_name: str = Field(..., max_length=250)
    country_cod: str | None = Field(None, max_length=3)
    swift_num: str | None = Field(None, max_length=50)


@router.post("/banks", tags=["Bank reconciliation"], summary="Add a bank (ODSC)")
def add_bank(body: BankIn, s: Session = Depends(get_session)) -> dict:
    if s.scalar(select(Bank).where(Bank.bank_code == body.bank_code)) is not None:
        raise HTTPException(status_code=422, detail=f"Bank {body.bank_code} already exists")
    b = Bank(abs_entry=(s.scalar(select(func.max(Bank.abs_entry))) or 0) + 1, **body.model_dump())
    s.add(b)
    s.commit()
    return {"abs_entry": b.abs_entry, **body.model_dump()}


class HouseBankAccountIn(BaseModel):
    bank_code: str
    account: str = Field(..., min_length=1, max_length=50)
    branch: str | None = Field(None, max_length=50)
    iban: str | None = Field(None, max_length=50)
    gl_account: str
    acct_name: str | None = Field(None, max_length=250)
    country: str | None = Field(None, max_length=3)
    currency: str | None = Field(None, max_length=3)


@router.post("/house-bank-accounts", tags=["Bank reconciliation"], summary="Add a house bank account (DSC1)")
def add_house_bank_account(body: HouseBankAccountIn, s: Session = Depends(get_session)) -> dict:
    if s.scalar(select(Bank).where(Bank.bank_code == body.bank_code)) is None:
        raise HTTPException(status_code=422, detail=f"Bank {body.bank_code} does not exist")
    run(lambda: bankrec.bank_account(s, body.gl_account))
    a = HouseBankAccount(abs_entry=(s.scalar(select(func.max(HouseBankAccount.abs_entry))) or 0) + 1, **body.model_dump())
    s.add(a)
    s.commit()
    return {"abs_entry": a.abs_entry, **body.model_dump()}


# ------------------------------------------------------------- statements
def _statement_out(st: BankStatement, rows: bool = False) -> dict:
    out = {"abs_entry": st.abs_entry, "acct_code": st.acct_code, "house_bank": st.house_bank, "statem_no": st.statem_no,
           "stat_date": st.stat_date, "start_bal": st.start_bal, "end_bal": st.end_bal, "currency": st.currency,
           "data_source": st.data_source, "rows_total": len(st.rows),
           "rows_open": sum(1 for r in st.rows if r.bank_match is None)}
    if rows:
        out["rows"] = [{"sequence": r.sequence, "vis_order": r.vis_order, "due_date": r.due_date, "ref": r.ref,
                        "memo": r.memo, "amount_in": r.cred_amnt, "amount_out": r.deb_amount,
                        "extern_code": r.extern_code, "card_code": r.card_code, "bank_match": r.bank_match,
                        "doc_num_type": r.doc_num_type, "doc_num": r.doc_num} for r in st.rows]
    return out


@router.get("/bank-statements", tags=["Bank reconciliation"], summary="Bank statements (OBNH / OBNK)")
def statements(acct_code: str | None = None, s: Session = Depends(get_session)) -> list[dict]:
    q = select(BankStatement).order_by(BankStatement.acct_code, BankStatement.statem_no.desc())
    if acct_code:
        q = q.where(BankStatement.acct_code == acct_code)
    return [_statement_out(st) for st in s.scalars(q)]


@router.get("/bank-statements/next", tags=["Bank reconciliation"], summary="Number and opening balance of the next statement")
def next_statement(acct_code: str, s: Session = Depends(get_session)) -> dict:
    prev = bankrec.last_statement(s, acct_code)
    return {"statem_no": (prev.statem_no + 1) if prev else 1, "start_bal": prev.end_bal if prev else Decimal("0"),
            "first": prev is None}


@router.get("/bank-statements/{abs_entry}", tags=["Bank reconciliation"])
def get_statement(abs_entry: int, s: Session = Depends(get_session)) -> dict:
    st = s.get(BankStatement, abs_entry)
    if st is None:
        raise HTTPException(status_code=404, detail="Bank statement not found")
    return _statement_out(st, rows=True)


class RowIn(BaseModel):
    due_date: date
    amount_in: Decimal = Field(Decimal("0"), ge=0)
    amount_out: Decimal = Field(Decimal("0"), ge=0)
    ref: str | None = Field(None, max_length=100)
    memo: str | None = Field(None, max_length=254)
    extern_code: str | None = Field(None, max_length=20)
    card_code: str | None = Field(None, max_length=15)


class StatementIn(BaseModel):
    acct_code: str
    stat_date: date
    end_bal: Decimal
    start_bal: Decimal | None = None
    house_bank: int | None = None
    rows: list[RowIn] = []
    csv: str | None = None  # bank export instead of rows


@router.post("/bank-statements", tags=["Bank reconciliation"], summary="Enter or import (CSV) a bank statement")
def create_statement(body: StatementIn, s: Session = Depends(get_session)) -> dict:
    rows = run(lambda: bankrec.parse_csv(body.csv)) if body.csv else [bankrec.RowRequest(**r.model_dump()) for r in body.rows]
    st = run(lambda: bankrec.create_statement(s, bankrec.StatementRequest(
        acct_code=body.acct_code, stat_date=body.stat_date, end_bal=body.end_bal, start_bal=body.start_bal,
        house_bank=body.house_bank, rows=rows, data_source="I" if body.csv else "M")))
    return _statement_out(st, rows=True)


class ParseIn(BaseModel):
    csv: str


@router.post("/bank-statements/parse", tags=["Bank reconciliation"], summary="Preview a CSV bank export")
def parse(body: ParseIn) -> list[dict]:
    return [r.__dict__ for r in run(lambda: bankrec.parse_csv(body.csv))]


class ProcessIn(BaseModel):
    kind: str = Field(..., pattern="^(incoming|outgoing|journal)$")
    card_code: str | None = None
    acct_code: str | None = None
    memo: str | None = Field(None, max_length=50)
    items: list[dict] = []  # [{trans_id, line_id, sum_applied}]


@router.post("/bank-statements/rows/{sequence}/process", tags=["Bank reconciliation"],
             summary="Post a statement row as payment or journal entry and reconcile it")
def process_row(sequence: int, body: ProcessIn, s: Session = Depends(get_session)) -> dict:
    items = [banking.PaidItem(trans_id=i["trans_id"], line_id=i["line_id"], sum_applied=Decimal(str(i["sum_applied"])))
             for i in body.items]
    m = run(lambda: bankrec.process_row(s, sequence, bankrec.ProcessRequest(
        kind=body.kind, card_code=body.card_code, acct_code=body.acct_code, memo=body.memo, items=items)))
    return _recon_out(m)


# ------------------------------------------------------------- reconciliation
def _recon_out(m: ExternalReconciliation) -> dict:
    return {"mth_num": m.mth_num, "mth_date": m.mth_date, "acct_code": m.acct_code, "total": m.total,
            "auto": m.auto == "Y", "canceled": m.canceled == "Y",
            "lines": [{"line_num": x.line_num, "trans_id": x.trans_id, "trans_row_id": x.trans_row_id,
                       "bank_seq": x.bank_seq, "recon_sum": x.recon_sum} for x in m.lines]}


@router.get("/bank-reconciliation/open", tags=["Bank reconciliation"], summary="Unreconciled statement rows and journal lines")
def open_items(acct_code: str, s: Session = Depends(get_session)) -> dict:
    run(lambda: bankrec.bank_account(s, acct_code))
    return {"rows": [{"sequence": r.sequence, "statem_no": r.statem_no, "due_date": r.due_date, "ref": r.ref,
                      "memo": r.memo, "amount": r.cred_amnt - r.deb_amount} for r in bankrec.open_rows(s, acct_code)],
            "lines": [{"trans_id": l.trans_id, "line_id": l.line_id, "ref_date": l.ref_date, "trans_type": l.trans_type,
                       "base_ref": l.base_ref, "created_by": l.created_by, "ref1": l.ref1, "line_memo": l.line_memo,
                       "amount": l.debit - l.credit} for l in bankrec.open_lines(s, acct_code)]}


class ReconcileIn(BaseModel):
    acct_code: str
    rows: list[int] = []
    lines: list[tuple[int, int]] = []
    mth_date: date | None = None


@router.post("/bank-reconciliation", tags=["Bank reconciliation"], summary="Reconcile selected rows and journal lines")
def reconcile(body: ReconcileIn, s: Session = Depends(get_session)) -> dict:
    return _recon_out(run(lambda: bankrec.reconcile(s, body.acct_code, body.rows, body.lines, body.mth_date)))


class AutoIn(BaseModel):
    acct_code: str
    days: int = Field(3, ge=0, le=31)


@router.post("/bank-reconciliation/auto", tags=["Bank reconciliation"], summary="Automatic reconciliation")
def auto(body: AutoIn, s: Session = Depends(get_session)) -> list[dict]:
    return [_recon_out(m) for m in run(lambda: bankrec.auto_reconcile(s, body.acct_code, body.days))]


@router.get("/bank-reconciliation/history", tags=["Bank reconciliation"], summary="External reconciliations (OMTH)")
def history(acct_code: str, s: Session = Depends(get_session)) -> list[dict]:
    return [_recon_out(m) for m in s.scalars(select(ExternalReconciliation).where(
        ExternalReconciliation.acct_code == acct_code).order_by(ExternalReconciliation.mth_num.desc()).limit(100))]


@router.post("/bank-reconciliation/{mth_num}/cancel", tags=["Bank reconciliation"], summary="Cancel an external reconciliation")
def cancel(mth_num: int, s: Session = Depends(get_session)) -> dict:
    return _recon_out(run(lambda: bankrec.cancel_reconciliation(s, mth_num)))


@router.get("/reports/bank-reconciliation", tags=["Financial reports"], summary="Bank reconciliation statement")
def report(acct_code: str, as_of: date | None = None, s: Session = Depends(get_session)) -> dict:
    return run(lambda: bankrec.reconciliation_report(s, acct_code, as_of))
