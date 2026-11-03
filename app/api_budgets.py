"""REST endpoints: budget scenarios, account budgets, budget vs. actual report, budget check setting."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import budgets
from app.services.admin import B1Error, company

router = APIRouter()


@router.get("/budgets", tags=["Budgets"], summary="Budget vs. actual of a financial year")
def report(year: int, scenario_id: int | None = None, upto_month: int = 12, s: Session = Depends(get_session)) -> dict:
    return {**budgets.report(s, year, scenario_id, max(1, min(12, upto_month))), "scenarios": budgets.scenarios(s),
            "check": company(s).bgt_check}


class BudgetIn(BaseModel):
    acct_code: str = Field(..., max_length=15)
    year: int = Field(..., ge=2000, le=2100)
    annual: Decimal | None = None
    months: list[Decimal] | None = None
    scenario_id: int | None = None


@router.post("/budgets", tags=["Budgets"], summary="Set the budget of an account (annual split equally, or 12 months)")
def save_budget(body: BudgetIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: budgets.save(s, body.acct_code, body.year, body.annual, body.months, body.scenario_id))
    return budgets.report(s, body.year, body.scenario_id)


class ScenarioIn(BaseModel):
    name: str = Field(..., max_length=30)
    year: int = Field(..., ge=2000, le=2100)
    init_ratio: Decimal = Decimal("100")


@router.post("/budgets/scenarios", tags=["Budgets"], summary="Add a budget scenario (ratio of the main budget)")
def add_scenario(body: ScenarioIn, s: Session = Depends(get_session)) -> list[dict]:
    run(lambda: budgets.add_scenario(s, body.name, body.year, body.init_ratio))
    return budgets.scenarios(s)


class CheckIn(BaseModel):
    check: str = Field(..., pattern="^[NB]$")


@router.put("/admin/budget-check", tags=["Budgets"], summary="Budget check of postings: N none, B block")
def budget_check(body: CheckIn, s: Session = Depends(get_session)) -> dict:
    c = run(lambda: company(s))
    if body.check not in {"N", "B"}:
        raise B1Error("N or B")
    c.bgt_check = body.check
    s.commit()
    return {"check": c.bgt_check}
