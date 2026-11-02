"""REST endpoints: exchange rate differences (revaluation of open foreign-currency items)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.finance import ExchangeRateRun
from app.services import fxreval

router = APIRouter()


@router.get("/exchange-rate-differences/preview", tags=["Financials"],
            summary="Open FC items (B) or FC G/L accounts (G) revalued at the rate of a date")
def preview(on: date, category: str = "B", currencies: str | None = None, s: Session = Depends(get_session)) -> list[dict]:
    curr = [c.strip().upper() for c in currencies.split(",")] if currencies else None
    return run(lambda: fxreval.preview(s, on, category, curr))


class RunIn(BaseModel):
    run_date: date
    category: str = Field("B", pattern="^[BG]$")
    storno_date: date | None = None
    currencies: list[str] | None = None


def _run_out(r: ExchangeRateRun, lines: bool = False) -> dict:
    out = {"abs_entry": r.abs_entry, "run_date": r.run_date, "category": r.category, "storno_date": r.storno_date,
           "trans_id": r.trans_id, "total_gain": r.total_gain, "total_loss": r.total_loss, "lines_count": len(r.lines)}
    if lines:
        out["lines"] = [{k: getattr(x, k) for k in ("line_num", "short_name", "account", "trans_id", "line_id", "currency",
                                                     "open_fc", "open_lc", "rate", "new_lc", "difference")} for x in r.lines]
    return out


@router.post("/exchange-rate-differences", tags=["Financials"], summary="Execute an exchange rate differences run")
def execute(body: RunIn, s: Session = Depends(get_session)) -> dict:
    return _run_out(run(lambda: fxreval.run(s, body.run_date, body.category, body.storno_date, body.currencies)), lines=True)


@router.get("/exchange-rate-differences", tags=["Financials"], summary="Exchange rate differences runs")
def runs(s: Session = Depends(get_session)) -> list[dict]:
    return [_run_out(r) for r in s.scalars(select(ExchangeRateRun).order_by(ExchangeRateRun.abs_entry.desc()).limit(100))]
