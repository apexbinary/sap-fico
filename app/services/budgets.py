"""Budgets: scenarios (OBGS), account budgets (OBGT) with monthly amounts (BGT1), the budget report
(budget vs. actual) and the budget check of postings.

The financial year is the period category (calendar year); months 1-12. A budget is entered as an
annual amount split equally (the last month takes the rounding) or as 12 monthly amounts, on the
debit side for asset / expense accounts and the credit side for liability / revenue accounts. A
scenario other than the main budget holds InitRatio % of the main budget when it is created.
Budget check (OADM BgtCheck B): a posting that raises the year's actual of an expense account
above its main budget for the year is refused.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.budgets import Budget, BudgetMonth, BudgetScenario
from app.models.finance import Account, JournalLine
from app.services.admin import B1Error, company

ZERO = Decimal("0")
CENT = Decimal("0.01")
CREDIT_DRAWERS = {2, 3, 4, 7}  # liabilities, capital, turnover, non-operating income: budgets on the credit side


def _credit_side(a: Account) -> bool:
    return a.act_type == "I" or (a.act_type != "E" and getattr(a, "group_mask", None) in CREDIT_DRAWERS)


def scenario(session: Session, year: int, create: bool = False) -> BudgetScenario | None:
    s = session.scalar(select(BudgetScenario).where(BudgetScenario.financ_year == year, BudgetScenario.main_budget == "Y"))
    if s is None and create:
        s = BudgetScenario(abs_id=(session.scalar(select(func.max(BudgetScenario.abs_id))) or 0) + 1, name="Main Budget",
                           financ_year=year, init_ratio=Decimal(100), main_budget="Y")
        session.add(s)
        session.flush()
    return s


def scenarios(session: Session) -> list[dict]:
    return [{"abs_id": s.abs_id, "name": s.name, "financ_year": s.financ_year, "init_ratio": s.init_ratio, "main": s.main_budget == "Y"}
            for s in session.scalars(select(BudgetScenario).order_by(BudgetScenario.financ_year.desc(), BudgetScenario.abs_id))]


def add_scenario(session: Session, name: str, year: int, ratio: Decimal) -> BudgetScenario:
    """A further scenario of a year: InitRatio % of every main budget of that year."""
    if not (name or "").strip():
        raise B1Error("Enter the scenario name")
    ratio = Decimal(str(ratio))
    if ratio <= 0:
        raise B1Error("The ratio must be positive")
    main = scenario(session, year, create=True)
    sc = BudgetScenario(abs_id=(session.scalar(select(func.max(BudgetScenario.abs_id))) or 0) + 1, name=name.strip()[:30],
                        financ_year=year, init_ratio=ratio, main_budget="N")
    session.add(sc)
    session.flush()
    for b in session.scalars(select(Budget).where(Budget.instance == main.abs_id)).all():
        _store(session, sc, session.get(Account, b.acct_code),
               [((m.deb_l_total or m.crd_l_total) * ratio / 100).quantize(CENT) for m in b.months])
    session.commit()
    return sc


def _store(session: Session, sc: BudgetScenario, acct: Account, months: list[Decimal]) -> Budget:
    b = session.scalar(select(Budget).where(Budget.acct_code == acct.acct_code, Budget.instance == sc.abs_id))
    if b is None:
        b = Budget(abs_id=(session.scalar(select(func.max(Budget.abs_id))) or 0) + 1, acct_code=acct.acct_code, instance=sc.abs_id,
                   financ_year=sc.financ_year)
        session.add(b)
    credit = _credit_side(acct)
    b.months = [BudgetMonth(line_id=n + 1, deb_l_total=ZERO if credit else m, crd_l_total=m if credit else ZERO) for n, m in enumerate(months)]
    total = sum(months, ZERO)
    b.deb_l_total, b.crd_l_total = (ZERO, total) if credit else (total, ZERO)
    session.flush()
    return b


def save(session: Session, acct_code: str, year: int, annual: Decimal | None = None, months: list | None = None,
         scenario_id: int | None = None) -> Budget:
    """Budget of an account: annual amount split equally, or 12 monthly amounts (positive)."""
    acct = session.get(Account, acct_code)
    if acct is None or acct.postable != "Y":
        raise B1Error(f"Account {acct_code} does not exist or is a title account")
    sc = session.get(BudgetScenario, scenario_id) if scenario_id else scenario(session, year, create=True)
    if sc is None or sc.financ_year != year:
        raise B1Error(f"Scenario {scenario_id} is not a budget scenario of {year}")
    if months is not None:
        if len(months) != 12:
            raise B1Error("Enter 12 monthly amounts")
        amounts = [Decimal(str(m or 0)).quantize(CENT) for m in months]
    elif annual is not None:
        total = Decimal(str(annual)).quantize(CENT)
        part = (total / 12).quantize(CENT)
        amounts = [part] * 11 + [total - part * 11]
    else:
        raise B1Error("Enter an annual amount or the monthly amounts")
    if any(a < 0 for a in amounts):
        raise B1Error("Budget amounts cannot be negative")
    b = _store(session, sc, acct, amounts)
    session.commit()
    return b


def _actuals(session: Session, year: int, accounts: list[str] | None = None) -> dict[str, list[Decimal]]:
    """Net amount per account and month (debit - credit)."""
    month = func.extract("month", JournalLine.ref_date)
    q = select(JournalLine.account, month, func.sum(JournalLine.debit - JournalLine.credit)).where(
        JournalLine.ref_date >= date(year, 1, 1), JournalLine.ref_date <= date(year, 12, 31)).group_by(JournalLine.account, month)
    if accounts is not None:
        q = q.where(JournalLine.account.in_(accounts))
    out: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO] * 12)
    for acct, m, net in session.execute(q):
        out[acct][int(m) - 1] = Decimal(net or 0)
    return out


def report(session: Session, year: int, scenario_id: int | None = None, upto_month: int = 12) -> dict:
    """Budget vs. actual per account (in the account's budget direction), by month, total and deviation."""
    sc = session.get(BudgetScenario, scenario_id) if scenario_id else scenario(session, year)
    if sc is None:
        return {"year": year, "scenario": None, "accounts": [], "total_budget": ZERO, "total_actual": ZERO}
    budgets = session.scalars(select(Budget).where(Budget.instance == sc.abs_id).order_by(Budget.acct_code)).all()
    actual = _actuals(session, year, [b.acct_code for b in budgets])
    rows = []
    for b in budgets:
        acct = session.get(Account, b.acct_code)
        credit = _credit_side(acct)
        months_b = [(m.crd_l_total if credit else m.deb_l_total) for m in b.months]
        months_a = [(-a if credit else a) for a in actual.get(b.acct_code, [ZERO] * 12)]
        bud, act_ = sum(months_b[:upto_month], ZERO), sum(months_a[:upto_month], ZERO)
        rows.append({"acct_code": b.acct_code, "acct_name": acct.acct_name, "side": "credit" if credit else "debit",
                     "months": [{"month": n + 1, "budget": months_b[n], "actual": months_a[n]} for n in range(12)],
                     "budget": bud, "actual": act_, "deviation": act_ - bud,
                     "pct": (act_ / bud * 100).quantize(Decimal("0.1")) if bud else None, "annual_budget": sum(months_b, ZERO)})
    return {"year": year, "upto_month": upto_month, "scenario": {"abs_id": sc.abs_id, "name": sc.name, "init_ratio": sc.init_ratio},
            "accounts": rows, "total_budget": sum((r["budget"] for r in rows), ZERO), "total_actual": sum((r["actual"] for r in rows), ZERO)}


def check_posting(session: Session, ref_date: date, lines: list[tuple[str, Decimal]], trans_id: int | None = None) -> None:
    """Budget check of a new journal entry: [(account, debit - credit)]; refuse an expense account going over
    its main budget of the year (OADM BgtCheck B)."""
    c = company(session)
    if c.bgt_check != "B":
        return
    sc = scenario(session, ref_date.year)
    if sc is None:
        return
    increase: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for acct, net in lines:
        increase[acct] += net
    for acct, net in increase.items():
        if net <= 0:
            continue
        a = session.get(Account, acct)
        if a is None or a.act_type != "E":
            continue
        b = session.scalar(select(Budget).where(Budget.acct_code == acct, Budget.instance == sc.abs_id))
        if b is None:
            continue
        spent = session.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
            JournalLine.account == acct, JournalLine.trans_id != (trans_id or -1),
            JournalLine.ref_date >= date(ref_date.year, 1, 1), JournalLine.ref_date <= date(ref_date.year, 12, 31)))
        if Decimal(spent) + net > b.deb_l_total:
            raise B1Error(f"Budget of account {acct} ({a.acct_name}) for {ref_date.year} exceeded: {Decimal(spent) + net:,.2f} "
                          f"> budget {b.deb_l_total:,.2f}")
