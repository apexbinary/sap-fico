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


def apply_changes(obj, data: dict) -> None:
    """PATCH semantics: set the given attributes; an empty value clears only nullable columns."""
    from sqlalchemy import inspect

    attrs = inspect(type(obj)).attrs
    for key, value in data.items():
        if value is None and key in attrs and not attrs[key].columns[0].nullable:
            continue
        setattr(obj, key, value)


def run(fn):
    try:
        return fn()
    except B1Error as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ------------------------------------------------------------- administration
def _company_out(c) -> dict:
    return {"company_name": c.company_name, "main_curncy": c.main_curncy, "sys_curncy": c.sys_curncy,
            "country": c.country, "tax_id": c.tax_id, "address": c.address, "phone": c.phone, "phone2": c.phone2,
            "fax": c.fax, "e_mail": c.e_mail, "manager": c.manager}


@router.get("/admin/company", tags=["Administration"], summary="Company details (OADM)")
def get_company(s: Session = Depends(get_session)) -> dict:
    return _company_out(run(lambda: company(s)))


class CompanyIn(BaseModel):
    company_name: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=3)
    tax_id: str | None = Field(None, max_length=32)
    address: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=20)
    phone2: str | None = Field(None, max_length=20)
    fax: str | None = Field(None, max_length=20)
    e_mail: str | None = Field(None, max_length=100)
    manager: str | None = Field(None, max_length=100)


@router.patch("/admin/company", tags=["Administration"], summary="Change company details (currencies are fixed)")
def update_company(body: CompanyIn, s: Session = Depends(get_session)) -> dict:
    from app.services.masterdata import check_country

    c = run(lambda: company(s))
    data = body.model_dump(exclude_unset=True)
    run(lambda: check_country(s, data.get("country")))
    apply_changes(c, data)
    s.commit()
    return _company_out(c)


@router.get("/admin/lookups", tags=["Administration"], summary="Currencies, tax groups, payment terms, periods")
def lookups(s: Session = Depends(get_session)) -> dict:
    return {
        "currencies": [{"code": c.curr_code, "name": c.curr_name} for c in s.scalars(select(Currency))],
        "tax_groups": [{"code": t.code, "name": t.name, "category": t.category, "rate": t.rate, "account": t.account}
                       for t in s.scalars(select(TaxGroup).order_by(TaxGroup.code))],
        "payment_terms": [_terms_out(p) for p in s.scalars(select(PaymentTerms).order_by(PaymentTerms.group_num))],
    }


def _terms_out(p: PaymentTerms) -> dict:
    return {"group_num": p.group_num, "name": p.pymnt_group, "bsline_date": p.bsline_date,
            "pay_du_month": p.pay_du_month, "extra_month": p.extra_month, "extra_days": p.extra_days,
            "tol_days": p.tol_days, "discount_pct": p.discount_pct, "list_num": p.list_num,
            "cred_limit": p.cred_limit, "oblig_limit": p.oblig_limit}


class PaymentTermsIn(BaseModel):
    name: str = Field(..., max_length=100)
    bsline_date: str = Field("P", pattern="^[PTS]$", description="Due date based on: P posting, T document, S system date")
    pay_du_month: str = Field("N", pattern="^[NSHE]$", description="Start from: N -, S month start, H half month, E month end")
    extra_month: int = Field(0, ge=0)
    extra_days: int = Field(0, ge=0)
    tol_days: int = Field(0, ge=0)
    discount_pct: Decimal = Field(Decimal("0"), ge=0, lt=100)
    list_num: int | None = None
    cred_limit: Decimal = Field(Decimal("0"), ge=0)
    oblig_limit: Decimal = Field(Decimal("0"), ge=0)


@router.post("/admin/payment-terms", tags=["Administration"], summary="Add payment terms (OCTG)")
def add_payment_terms(body: PaymentTermsIn, s: Session = Depends(get_session)) -> dict:
    from sqlalchemy import func

    num = max(s.scalar(select(func.max(PaymentTerms.group_num))) or 0, 0) + 1
    data = body.model_dump()
    p = PaymentTerms(group_num=num, pymnt_group=data.pop("name"), **data)
    s.add(p)
    s.commit()
    return _terms_out(p)


@router.put("/admin/payment-terms/{group_num}", tags=["Administration"], summary="Change payment terms")
def update_payment_terms(group_num: int, body: PaymentTermsIn, s: Session = Depends(get_session)) -> dict:
    p = s.get(PaymentTerms, group_num)
    if p is None:
        raise HTTPException(status_code=404, detail="Payment terms not found")
    data = body.model_dump()
    p.pymnt_group = data.pop("name")
    for key, value in data.items():
        setattr(p, key, value)
    s.commit()
    return _terms_out(p)


@router.get("/admin/periods", tags=["Administration"], summary="Posting periods (OFPR)")
def periods(s: Session = Depends(get_session)) -> list[dict]:
    return [{"abs_entry": p.abs_entry, "code": p.code, "name": p.name, "from": p.f_ref_date, "to": p.t_ref_date,
             "due_from": p.f_due_date, "due_to": p.t_due_date, "doc_from": p.f_tax_date, "doc_to": p.t_tax_date,
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
            "control": a.loc_man_tran == "Y", "cash": a.finanse == "Y", "balance": a.curr_total, "frozen": a.frozen == "Y",
            "act_curr": a.act_curr, "frgn_name": a.frgn_name, "details": a.details, "bloc_man_pos": a.bloc_man_pos == "Y",
            "project": a.project}


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
    act_type: str | None = Field(None, pattern="^[IEN]$", description="I sales, E expenditure, N other")
    act_curr: str = Field("##", max_length=3)
    frgn_name: str | None = Field(None, max_length=100)
    details: str | None = Field(None, max_length=254)
    bloc_man_pos: bool = False
    project: str | None = Field(None, max_length=20)


def _check_account_refs(s: Session, act_curr: str | None, project: str | None) -> None:
    from app.services.admin import check_project

    if act_curr not in (None, "##") and s.get(Currency, act_curr) is None:
        raise HTTPException(status_code=422, detail=f"Currency {act_curr} does not exist")
    run(lambda: check_project(s, project))


@router.post("/accounts", tags=["Financials"], summary="Create a G/L account under a title account")
def create_account(body: AccountIn, s: Session = Depends(get_session)) -> dict:
    parent = s.get(Account, body.father_num)
    if parent is None or parent.postable == "Y":
        raise HTTPException(status_code=422, detail="The parent must be a title account")
    if s.get(Account, body.acct_code) is not None:
        raise HTTPException(status_code=422, detail=f"Account {body.acct_code} already exists")
    _check_account_refs(s, body.act_curr, body.project)
    a = Account(acct_code=body.acct_code, acct_name=body.acct_name, group_mask=parent.group_mask,
                father_num=parent.acct_code, levels=parent.levels + 1, postable="Y" if body.postable else "N",
                act_type=body.act_type or parent.act_type, loc_man_tran="Y" if body.control else "N",
                finanse="Y" if body.cash else "N", act_curr=body.act_curr, frgn_name=body.frgn_name,
                details=body.details, bloc_man_pos="Y" if body.bloc_man_pos else "N", project=body.project)
    s.add(a)
    s.commit()
    return _account_out(a)


class AccountUpdate(BaseModel):
    acct_name: str | None = Field(None, max_length=100)
    frgn_name: str | None = Field(None, max_length=100)
    details: str | None = Field(None, max_length=254)
    act_type: str | None = Field(None, pattern="^[IEN]$")
    act_curr: str | None = Field(None, max_length=3)
    control: bool | None = None
    cash: bool | None = None
    bloc_man_pos: bool | None = None
    frozen: bool | None = None
    project: str | None = Field(None, max_length=20)


@router.patch("/accounts/{acct_code}", tags=["Financials"], summary="Change a G/L account")
def update_account(acct_code: str, body: AccountUpdate, s: Session = Depends(get_session)) -> dict:
    a = s.get(Account, acct_code)
    if a is None:
        raise HTTPException(status_code=404, detail="Account not found")
    data = body.model_dump(exclude_unset=True)
    _check_account_refs(s, data.get("act_curr"), data.get("project"))
    if a.curr_total and ("control" in data or "act_curr" in data):
        raise HTTPException(status_code=422, detail="Control account and currency cannot change on an account with a balance")
    for flag, attr in (("control", "loc_man_tran"), ("cash", "finanse"), ("bloc_man_pos", "bloc_man_pos"),
                       ("frozen", "frozen")):
        if flag in data:
            setattr(a, attr, "Y" if data.pop(flag) else "N")
    apply_changes(a, data)
    s.commit()
    return _account_out(a)


# ------------------------------------------------------------- journal entries
class JELineIn(BaseModel):
    account: str | None = None
    card_code: str | None = None
    debit: Decimal = Field(Decimal("0"), ge=0)
    credit: Decimal = Field(Decimal("0"), ge=0)
    line_memo: str | None = Field(None, max_length=50)
    due_date: date | None = None
    project: str | None = Field(None, max_length=20)
    ref1: str | None = Field(None, max_length=100)
    ref2: str | None = Field(None, max_length=100)
    ref3_line: str | None = Field(None, max_length=27)


class JournalEntryIn(BaseModel):
    ref_date: date
    tax_date: date | None = None
    due_date: date | None = None
    memo: str | None = Field(None, max_length=50)
    ref1: str | None = Field(None, max_length=100)
    ref2: str | None = Field(None, max_length=100)
    ref3: str | None = Field(None, max_length=27)
    trans_code: str | None = Field(None, max_length=4)
    project: str | None = Field(None, max_length=20)
    auto_storno: bool = False
    storno_date: date | None = None
    lines: list[JELineIn]


def _je_out(e: JournalEntry) -> dict:
    return {"trans_id": e.trans_id, "number": e.number, "series": e.series, "ref_date": e.ref_date,
            "tax_date": e.tax_date, "due_date": e.due_date, "memo": e.memo, "ref1": e.ref1, "ref2": e.ref2,
            "ref3": e.ref3, "trans_code": e.trans_code, "project": e.project, "storno_date": e.storno_date,
            "is_reversal": e.storno_to_tr is not None and e.storno_to_tr < e.trans_id, "trans_type": e.trans_type,
            "base_ref": e.base_ref, "created_by": e.created_by, "loc_total": e.loc_total, "storno_to_tr": e.storno_to_tr,
            "auto_storno": e.auto_storno == "Y",
            "lines": [{"line_id": l.line_id, "account": l.account, "short_name": l.short_name, "debit": l.debit,
                       "credit": l.credit, "bal_due_deb": l.bal_due_deb, "bal_due_cred": l.bal_due_cred,
                       "line_memo": l.line_memo, "contra_act": l.contra_act, "vat_group": l.vat_group,
                       "due_date": l.due_date, "project": l.project, "ref1": l.ref1, "ref2": l.ref2,
                       "ref3_line": l.ref3_line} for l in e.lines]}


@router.post("/journal-entries", tags=["Financials"], summary="Post a manual journal entry")
def post_journal_entry(body: JournalEntryIn, s: Session = Depends(get_session)) -> dict:
    entry = run(lambda: journal.post_entry(s, journal.JournalRequest(
        ref_date=body.ref_date, tax_date=body.tax_date, due_date=body.due_date, memo=body.memo,
        ref1=body.ref1, ref2=body.ref2, ref3=body.ref3, trans_code=body.trans_code or None, project=body.project or None,
        auto_storno=body.auto_storno, storno_date=body.storno_date,
        lines=[journal.JournalLineRequest(account=l.account or None, card_code=l.card_code or None, debit=l.debit,
                                          credit=l.credit, line_memo=l.line_memo, due_date=l.due_date,
                                          project=l.project or None, ref1=l.ref1, ref2=l.ref2, ref3_line=l.ref3_line)
               for l in body.lines])))
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
