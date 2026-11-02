"""Account-based profitability analysis (CO-PA).

A controlling area assigned to an operating concern (TKA01-ERKRS, TKEB) sends
revenue and sales deduction lines (cost element categories 11 / 12) to
profitability segments. The segment is derived from the document's customer:
customer number, country, industry and customer classification (KNA1). Equal
characteristics reuse the same segment number (PAOBJNR, CO object EO<nr>).
The contribution report groups the segments' CO lines by a characteristic.

Costing-based CO-PA runs in parallel: every CO line on a segment also writes a
CE1IDEA line item whose value fields come from the cost element category
(11 revenue -> VV010, 12 sales deductions -> VV020, 42/43 assessed overhead ->
VV030). ``contribution(ledger="costing")`` reports from those value fields.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.controlling import COLineItem, CostElementCO, CostingBasedPALineItem, ProfitabilitySegment
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


def _categories(session: Session, mandt: str, kokrs: str) -> dict[str, str]:
    return {c.kstar: c.katyp for c in session.scalars(select(CostElementCO).where(
        CostElementCO.mandt == mandt, CostElementCO.kokrs == kokrs))}


def record_costing(session: Session, doc, line) -> None:
    """Write the costing-based line item (CE1IDEA) for a CO line on a profitability segment."""
    category = _categories(session, doc.mandt, doc.kokrs).get(line.kstar)
    item = CostingBasedPALineItem(
        mandt=doc.mandt, belnr=doc.belnr, posnr=line.buzei, kokrs=doc.kokrs, paobjnr=int(line.objnr[2:]),
        gjahr=doc.gjahr, perde=doc.perab, budat=doc.budat, vrgar="F" if doc.awtyp == "BKPF" else "D",
        kstar=line.kstar, vv010=ZERO, vv020=ZERO, vv030=ZERO,
    )
    if category == "11":
        item.vv010 = -line.wkgbtr  # revenue is a credit in CO
    elif category == "12":
        item.vv020 = line.wkgbtr
    else:
        item.vv030 = line.wkgbtr
    session.add(item)


def revenue_shares(session: Session, mandt: str, kokrs: str, gjahr: int, perio: int) -> dict[int, Decimal]:
    """Net revenue (revenue - sales deductions) per profitability segment in one period."""
    categories = _categories(session, mandt, kokrs)
    shares: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for objnr, kstar, total in session.execute(select(COLineItem.objnr, COLineItem.kstar, func.sum(COLineItem.wkgbtr)).where(
            COLineItem.mandt == mandt, COLineItem.kokrs == kokrs, COLineItem.wrttp == "04", COLineItem.gjahr == gjahr,
            COLineItem.perio == perio, COLineItem.objnr.like("EO%")).group_by(COLineItem.objnr, COLineItem.kstar)):
        if categories.get(kstar) in ("11", "12") and total:
            shares[int(objnr[2:])] -= total
    return {k: v for k, v in shares.items() if v > 0}


def contribution(
    session: Session, mandt: str, kokrs: str, gjahr: int, *, by: str = "kndnr",
    perio_from: int = 1, perio_to: int = 16, ledger: str = "account",
) -> dict:
    """Revenue, sales deductions, net revenue, overhead and contribution per characteristic value.

    ``ledger="account"`` reads the CO line items of the segments (account-based
    CO-PA), ``ledger="costing"`` the value fields of CE1IDEA (costing-based).
    """
    if by not in CHARACTERISTICS:
        raise PostingError(f"Unknown characteristic {by}; use one of {', '.join(CHARACTERISTICS)}")
    if ledger not in ("account", "costing"):
        raise PostingError("ledger must be 'account' or 'costing'")
    segments = {s.paobjnr: s for s in session.scalars(select(ProfitabilitySegment).where(
        ProfitabilitySegment.mandt == mandt, ProfitabilitySegment.kokrs == kokrs))}
    groups: dict[str | None, dict] = defaultdict(lambda: {"revenue": ZERO, "deductions": ZERO, "overhead": ZERO})
    if ledger == "account":
        categories = _categories(session, mandt, kokrs)
        rows = session.execute(select(COLineItem.objnr, COLineItem.kstar, func.sum(COLineItem.wkgbtr)).where(
            COLineItem.mandt == mandt, COLineItem.kokrs == kokrs, COLineItem.wrttp == "04",
            COLineItem.gjahr == gjahr, COLineItem.perio >= perio_from, COLineItem.perio <= perio_to,
            COLineItem.objnr.like("EO%"),
        ).group_by(COLineItem.objnr, COLineItem.kstar)).all()
        for objnr, kstar, total in rows:
            seg = segments.get(int(objnr[2:]))
            if seg is None or not total:
                continue
            g = groups[getattr(seg, by)]
            category = categories.get(kstar)
            if category == "11":
                g["revenue"] -= total  # CO stores revenue as a credit (negative); report it positive
            elif category == "12":
                g["deductions"] += total
            else:
                g["overhead"] += total
    else:
        rows = session.execute(select(CostingBasedPALineItem.paobjnr, func.sum(CostingBasedPALineItem.vv010),
                                      func.sum(CostingBasedPALineItem.vv020), func.sum(CostingBasedPALineItem.vv030)).where(
            CostingBasedPALineItem.mandt == mandt, CostingBasedPALineItem.kokrs == kokrs,
            CostingBasedPALineItem.gjahr == gjahr, CostingBasedPALineItem.perde >= perio_from,
            CostingBasedPALineItem.perde <= perio_to).group_by(CostingBasedPALineItem.paobjnr)).all()
        for paobjnr, vv010, vv020, vv030 in rows:
            seg = segments.get(paobjnr)
            if seg is None:
                continue
            g = groups[getattr(seg, by)]
            g["revenue"] += vv010 or ZERO
            g["deductions"] += vv020 or ZERO
            g["overhead"] += vv030 or ZERO

    names = {}
    if by == "kndnr":
        names = {c.kunnr: c.name1 for c in session.scalars(select(Customer).where(Customer.mandt == mandt))}
    lines = [{
        "value": key, "name": names.get(key), "revenue": g["revenue"], "deductions": g["deductions"],
        "net": g["revenue"] - g["deductions"], "overhead": g["overhead"],
        "contribution": g["revenue"] - g["deductions"] - g["overhead"],
    } for key, g in sorted(groups.items(), key=lambda kv: -(kv[1]["revenue"] - kv[1]["deductions"]))]
    return {
        "by": by, "label": CHARACTERISTICS[by], "ledger": ledger, "gjahr": gjahr,
        "perio_from": perio_from, "perio_to": perio_to, "lines": lines,
        **{k: sum((l[k] for l in lines), ZERO) for k in ("revenue", "deductions", "net", "overhead", "contribution")},
    }
