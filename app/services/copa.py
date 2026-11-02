"""Account-based profitability analysis (CO-PA).

A controlling area assigned to an operating concern (TKA01-ERKRS, TKEB) sends
revenue and sales deduction lines (cost element categories 11 / 12) to
profitability segments. The segment is derived from the document's customer:
customer number, country, industry and customer classification (KNA1). Equal
characteristics reuse the same segment number (PAOBJNR, CO object EO<nr>).
The contribution report groups the segments' CO lines by a characteristic.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.controlling import COLineItem, CostElementCO, ProfitabilitySegment
from app.models.organizational import ControllingArea
from app.models.partners import Customer
from app.services.fiscal import PostingError

ZERO = Decimal("0")
CHARACTERISTICS = {"kndnr": "Customer", "land1": "Country", "brsch": "Industry", "kukla": "Customer class"}


def segment_objnr(paobjnr: int) -> str:
    return f"EO{paobjnr:010d}"


def derive_segment(session: Session, mandt: str, kokrs: str, bukrs: str, kunnr: str) -> int | None:
    """Profitability segment of a customer (None when the controlling area has no operating concern)."""
    area = session.get(ControllingArea, (mandt, kokrs))
    if area is None or not area.erkrs:
        return None
    cust = session.get(Customer, (mandt, kunnr))
    values = {
        "kokrs": kokrs, "bukrs": bukrs, "kndnr": kunnr,
        "land1": cust.land1 if cust else None, "brsch": cust.brsch if cust else None,
        "kukla": cust.kukla if cust else None,
    }
    stmt = select(ProfitabilitySegment).where(ProfitabilitySegment.mandt == mandt)
    for col, value in values.items():
        attr = getattr(ProfitabilitySegment, col)
        stmt = stmt.where(attr.is_(None) if value is None else attr == value)
    found = session.scalars(stmt).first()
    if found is not None:
        return found.paobjnr
    nxt = (session.scalar(select(func.max(ProfitabilitySegment.paobjnr)).where(
        ProfitabilitySegment.mandt == mandt)) or 0) + 1
    seg = ProfitabilitySegment(mandt=mandt, paobjnr=nxt, **values)
    session.add(seg)
    session.flush([seg])
    return nxt


def contribution(
    session: Session, mandt: str, kokrs: str, gjahr: int, *, by: str = "kndnr",
    perio_from: int = 1, perio_to: int = 16,
) -> dict:
    """Revenue, sales deductions and net revenue per characteristic value."""
    if by not in CHARACTERISTICS:
        raise PostingError(f"Unknown characteristic {by}; use one of {', '.join(CHARACTERISTICS)}")
    categories = {c.kstar: c.katyp for c in session.scalars(select(CostElementCO).where(
        CostElementCO.mandt == mandt, CostElementCO.kokrs == kokrs))}
    segments = {segment_objnr(s.paobjnr): s for s in session.scalars(select(ProfitabilitySegment).where(
        ProfitabilitySegment.mandt == mandt, ProfitabilitySegment.kokrs == kokrs))}
    rows = session.execute(select(COLineItem.objnr, COLineItem.kstar, func.sum(COLineItem.wkgbtr)).where(
        COLineItem.mandt == mandt, COLineItem.kokrs == kokrs, COLineItem.wrttp == "04",
        COLineItem.gjahr == gjahr, COLineItem.perio >= perio_from, COLineItem.perio <= perio_to,
        COLineItem.objnr.like("EO%"),
    ).group_by(COLineItem.objnr, COLineItem.kstar)).all()

    names = {}
    if by == "kndnr":
        names = {c.kunnr: c.name1 for c in session.scalars(select(Customer).where(Customer.mandt == mandt))}
    groups: dict[str | None, dict] = defaultdict(lambda: {"revenue": ZERO, "deductions": ZERO})
    for objnr, kstar, total in rows:
        seg = segments.get(objnr)
        if seg is None or not total:
            continue
        key = getattr(seg, by)
        # CO stores revenue as a credit (negative); report it positive
        if categories.get(kstar) == "12":
            groups[key]["deductions"] += total
        else:
            groups[key]["revenue"] -= total
    lines = [{
        "value": key, "name": names.get(key), "revenue": g["revenue"], "deductions": g["deductions"],
        "net": g["revenue"] - g["deductions"],
    } for key, g in sorted(groups.items(), key=lambda kv: -(kv[1]["revenue"] - kv[1]["deductions"]))]
    return {
        "by": by, "label": CHARACTERISTICS[by], "gjahr": gjahr, "perio_from": perio_from, "perio_to": perio_to,
        "lines": lines,
        "revenue": sum((l["revenue"] for l in lines), ZERO),
        "deductions": sum((l["deductions"] for l in lines), ZERO),
        "net": sum((l["net"] for l in lines), ZERO),
    }
