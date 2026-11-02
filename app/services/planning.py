"""CO planning (KP06), plan/actual comparison (S_ALR_87013611) and activity prices (KP26).

Plan values are kept per CO object, cost element, version and period in COSP
with value type 01; actual values come from the CO line items (COEP, value
type 04). Activity prices are kept per cost center / activity type object
(LT<area><cost center><activity type>) and period in COST.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.controlling import ActivityPrice, ActivityType, COTotals
from app.models.organizational import ControllingArea
from app.services import controlling
from app.services.fiscal import PostingError

ZERO = Decimal("0")
_CENT = Decimal("0.01")


def activity_objnr(kokrs: str, kostl: str, lstar: str) -> str:
    return f"LT{kokrs}{kostl}{lstar}"


def spread(annual: Decimal, periods: int = 12) -> list[Decimal]:
    """Equal amounts for periods 1..n; the last period takes the rounding remainder."""
    share = (annual / periods).quantize(_CENT, ROUND_HALF_UP)
    values = [share] * periods
    values[-1] = annual - share * (periods - 1)
    return values + [ZERO] * (16 - periods)


def set_plan(session: Session, mandt: str, kokrs: str, objnr: str, kstar: str, gjahr: int,
             values: list[Decimal], *, versn: str = "000") -> COTotals:
    """Replace the plan of one object / cost element / year (16 period values)."""
    if len(values) != 16:
        raise PostingError("Enter 16 period values (12 periods and 4 special periods)")
    area = session.get(ControllingArea, (mandt, kokrs))
    if area is None:
        raise PostingError(f"Controlling area {kokrs} does not exist")
    row = session.get(COTotals, (mandt, objnr, gjahr, "01", versn, kstar))
    if row is None:
        row = COTotals(mandt=mandt, objnr=objnr, gjahr=gjahr, wrttp="01", versn=versn, kstar=kstar,
                       kokrs=kokrs, twaer=area.waers)
        session.add(row)
    for p, value in enumerate(values, start=1):
        setattr(row, f"wkg{p:03d}", Decimal(value))
    session.commit()
    return row


def plan_actual(session: Session, mandt: str, kokrs: str, gjahr: int, *, kind: str = "KS",
                perio_from: int = 1, perio_to: int = 16, versn: str = "000") -> list[dict]:
    """Actual, plan and variance per object and cost element."""
    actual = controlling.actuals(session, mandt, kokrs, gjahr, kind=kind, perio_from=perio_from, perio_to=perio_to)
    prefix = f"KS{kokrs}" if kind == "KS" else "OR"
    plan: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for row in session.scalars(select(COTotals).where(
            COTotals.mandt == mandt, COTotals.kokrs == kokrs, COTotals.gjahr == gjahr, COTotals.wrttp == "01",
            COTotals.versn == versn, COTotals.objnr.like(f"{prefix}%"))):
        total = sum((getattr(row, f"wkg{p:03d}") or ZERO for p in range(perio_from, perio_to + 1)), ZERO)
        if total:
            plan[row.objnr][row.kstar] = total
    out = []
    for obj in actual:
        planned = plan.get(obj["objnr"], {})
        elements = {e["kstar"]: {**e, "plan": ZERO} for e in obj["elements"]}
        for kstar, value in planned.items():
            elements.setdefault(kstar, {"kstar": kstar, "text": None, "katyp": None, "amount": ZERO})["plan"] = value
        rows = []
        for e in sorted(elements.values(), key=lambda x: x["kstar"]):
            variance = e["amount"] - e["plan"]
            rows.append({**e, "actual": e["amount"], "variance": variance,
                         "pct": ((variance / e["plan"]) * 100).quantize(Decimal("0.1")) if e["plan"] else None})
        plan_total = sum((r["plan"] for r in rows), ZERO)
        out.append({**obj, "elements": rows, "plan": plan_total, "actual": obj["total"],
                    "variance": obj["total"] - plan_total})
    return out


def set_price(session: Session, mandt: str, kokrs: str, kostl: str, lstar: str, gjahr: int, price: Decimal,
              *, periods: range = range(1, 17), versn: str = "000") -> ActivityPrice:
    if not session.scalars(select(ActivityType).where(
            ActivityType.mandt == mandt, ActivityType.kokrs == kokrs, ActivityType.lstar == lstar)).first():
        raise PostingError(f"Activity type {lstar} does not exist in controlling area {kokrs}")
    objnr = activity_objnr(kokrs, kostl, lstar)
    row = session.get(ActivityPrice, (mandt, objnr, gjahr, "01", versn))
    if row is None:
        row = ActivityPrice(mandt=mandt, objnr=objnr, gjahr=gjahr, wrttp="01", versn=versn, kokrs=kokrs)
        session.add(row)
    for p in periods:
        setattr(row, f"tkg{p:03d}", Decimal(price))
    session.commit()
    return row


def price_of(session: Session, mandt: str, kokrs: str, kostl: str, lstar: str, gjahr: int, perio: int,
             versn: str = "000") -> Decimal | None:
    row = session.get(ActivityPrice, (mandt, activity_objnr(kokrs, kostl, lstar), gjahr, "01", versn))
    price = getattr(row, f"tkg{perio:03d}") if row else None
    return price or None
