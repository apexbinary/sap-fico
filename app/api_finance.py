"""REST endpoints: administration and financials."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.admin import Currency, ExchangeRate, PaymentTerms, PostingPeriod, TaxGroup
from app.models.finance import DRAWERS, Account, JournalEntry
from app.services import journal, reports
from app.services.admin import B1Error, company

router = APIRouter()


def run(fn):
    try:
        return fn()
    except B1Error as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ------------------------------------------------------------- administration
@router.get("/admin/company", tags=["Administration"], summary="Company details (OADM)")
def get_company(s: Session = Depends(get_session)) -> dict:
    c = run(lambda: company(s))
    return {"company_name": c.company_name, "main_curncy": c.main_curncy, "sys_curncy": c.sys_curncy,
            "country": c.country, "tax_id": c.tax_id, "address": c.address, "phone": c.phone}


@router.get("/admin/lookups", tags=["Administration"], summary="Currencies, tax groups, payment terms, periods")
def lookups(s: Session = Depends(get_session)) -> dict:
    return {
        "currencies": [{"code": c.curr_code, "name": c.curr_name} for c in s.scalars(select(Currency))],
        "tax_groups": [{"code": t.code, "name": t.name, "category": t.category, "rate": t.rate, "account": t.account}
                       for t in s.scalars(select(TaxGroup).order_by(TaxGroup.code))],
        "payment_terms": [{"group_num": p.group_num, "name": p.pymnt_group, "extra_month": p.extra_month,
                           "extra_days": p.extra_days} for p in s.scalars(select(PaymentTerms).order_by(PaymentTerms.group_num))],
    }


@router.get("/admin/periods", tags=["Administration"], summary="Posting periods (OFPR)")
def periods(s: Session = Depends(get_session)) -> list[dict]:
    return [{"abs_entry": p.abs_entry, "code": p.code, "from": p.f_ref_date, "to": p.t_ref_date,
             "category": p.category, "status": p.period_stat} for p in s.scalars(select(PostingPeriod).order_by(PostingPeriod.f_ref_date))]


class PeriodStatusIn(BaseModel):
    status: str = Field(..., pattern="^[NYC]$", description="N unlocked, Y locked, C closing period")


@router.put("/admin/periods/{abs_entry}", tags=["Administration"], summary="Lock / unlock a posting period")
def set_period_status(abs_entry: int, body: PeriodStatusIn, s: Session = Depends(get_session)) -> dict:
    p = s.get(PostingPeriod, abs_entry)
    if p is None:
        raise HTTPException(status_code=404, detail="Posting period not found")
    p.period_stat = body.status
    s.commit()
    return {"code": p.code, "status": p.period_stat}


class RateIn(BaseModel):
    currency: str
    rate_date: date
    rate: Decimal = Field(..., gt=0)


@router.post("/admin/exchange-rates", tags=["Administration"], summary="Exchange rates (ORTT)")
def set_rate(body: RateIn, s: Session = Depends(get_session)) -> dict:
    s.merge(ExchangeRate(rate_date=body.rate_date, currency=body.currency.upper(), rate=body.rate))
    s.commit()
    return body.model_dump()


@router.get("/admin/exchange-rates", tags=["Administration"])
def get_rates(rate_date: date, s: Session = Depends(get_session)) -> list[dict]:
    return [{"currency": r.currency, "rate": r.rate} for r in s.scalars(select(ExchangeRate).where(ExchangeRate.rate_date == rate_date))]


# ------------------------------------------------------------- chart of accounts
def _account_out(a: Account) -> dict:
    return {"acct_code": a.acct_code, "acct_name": a.acct_name, "group_mask": a.group_mask, "drawer": DRAWERS[a.group_mask],
            "father_num": a.father_num, "levels": a.levels, "postable": a.postable, "act_type": a.act_type,
            "control": a.loc_man_tran == "Y", "cash": a.finanse == "Y", "balance": a.curr_total, "frozen": a.frozen == "Y"}


@router.get("/accounts", tags=["Financials"], summary="Chart of accounts (OACT)")
def accounts(s: Session = Depends(get_session)) -> list[dict]:
    return [_account_out(a) for a in s.scalars(select(Account).order_by(Account.group_mask, Account.acct_code))]


class AccountIn(BaseModel):
    acct_code: str = Field(..., max_length=15)
    acct_name: str = Field(..., max_length=100)
    father_num: str
    postable: bool = True
    control: bool = False
    cash: bool = False


@router.post("/accounts", tags=["Financials"], summary="Create a G/L account under a title account")
def create_account(body: AccountIn, s: Session = Depends(get_session)) -> dict:
    parent = s.get(Account, body.father_num)
    if parent is None or parent.postable == "Y":
        raise HTTPException(status_code=422, detail="The parent must be a title account")
    if s.get(Account, body.acct_code) is not None:
        raise HTTPException(status_code=422, detail=f"Account {body.acct_code} already exists")
    a = Account(acct_code=body.acct_code, acct_name=body.acct_name, group_mask=parent.group_mask,
                father_num=parent.acct_code, levels=parent.levels + 1, postable="Y" if body.postable else "N",
                act_type=parent.act_type, loc_man_tran="Y" if body.control else "N", finanse="Y" if body.cash else "N")
    s.add(a)
    s.commit()
    return _account_out(a)


# ------------------------------------------------------------- journal entries
class JELineIn(BaseModel):
    account: str | None = None
    card_code: str | None = None
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    line_memo: str | None = Field(None, max_length=50)


class JournalEntryIn(BaseModel):
    ref_date: date
    tax_date: date | None = None
    due_date: date | None = None
    memo: str | None = Field(None, max_length=50)
    ref1: str | None = None
    ref2: str | None = None
    lines: list[JELineIn]


def _je_out(e: JournalEntry) -> dict:
    return {"trans_id": e.trans_id, "number": e.number, "ref_date": e.ref_date, "tax_date": e.tax_date,
            "due_date": e.due_date, "memo": e.memo, "ref1": e.ref1, "ref2": e.ref2, "trans_type": e.trans_type,
            "base_ref": e.base_ref, "loc_total": e.loc_total, "storno_to_tr": e.storno_to_tr,
            "auto_storno": e.auto_storno == "Y",
            "lines": [{"line_id": l.line_id, "account": l.account, "short_name": l.short_name, "debit": l.debit,
                       "credit": l.credit, "bal_due_deb": l.bal_due_deb, "bal_due_cred": l.bal_due_cred,
                       "line_memo": l.line_memo, "contra_act": l.contra_act, "vat_group": l.vat_group} for l in e.lines]}


@router.post("/journal-entries", tags=["Financials"], summary="Post a manual journal entry")
def post_journal_entry(body: JournalEntryIn, s: Session = Depends(get_session)) -> dict:
    entry = run(lambda: journal.post_entry(s, journal.JournalRequest(
        ref_date=body.ref_date, tax_date=body.tax_date, due_date=body.due_date, memo=body.memo,
        ref1=body.ref1, ref2=body.ref2,
        lines=[journal.JournalLineRequest(account=l.account or None, card_code=l.card_code or None, debit=l.debit,
                                          credit=l.credit, line_memo=l.line_memo) for l in body.lines])))
    return _je_out(entry)


@router.get("/journal-entries", tags=["Financials"], summary="Journal entries (newest first)")
def list_journal_entries(limit: int = 50, s: Session = Depends(get_session)) -> list[dict]:
    rows = s.scalars(select(JournalEntry).order_by(JournalEntry.trans_id.desc()).limit(limit)).all()
    return [_je_out(e) for e in rows]


@router.get("/journal-entries/{trans_id}", tags=["Financials"])
def get_journal_entry(trans_id: int, s: Session = Depends(get_session)) -> dict:
    e = s.get(JournalEntry, trans_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return _je_out(e)


class ReverseIn(BaseModel):
    ref_date: date | None = None


@router.post("/journal-entries/{trans_id}/reverse", tags=["Financials"], summary="Reverse a journal entry")
def reverse_journal_entry(trans_id: int, body: ReverseIn, s: Session = Depends(get_session)) -> dict:
    return _je_out(run(lambda: journal.reverse_entry(s, trans_id, ref_date=body.ref_date)))


# ------------------------------------------------------------- reports
@router.get("/reports/trial-balance", tags=["Financial reports"])
def trial_balance(date_from: date, date_to: date, s: Session = Depends(get_session)) -> dict:
    return reports.trial_balance(s, date_from, date_to)


@router.get("/reports/profit-and-loss", tags=["Financial reports"])
def profit_and_loss(date_from: date, date_to: date, s: Session = Depends(get_session)) -> dict:
    return reports.profit_and_loss(s, date_from, date_to)


@router.get("/reports/balance-sheet", tags=["Financial reports"])
def balance_sheet(as_of: date, s: Session = Depends(get_session)) -> dict:
    return reports.balance_sheet(s, as_of, date(as_of.year, 1, 1))
