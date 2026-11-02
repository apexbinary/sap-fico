"""Controlling: CO documents (COBK/COEP) and actual cost reports.

Every CO posting is a CO document: a COBK header numbered from interval 01
of number range object RK_BELEG for the controlling area, and COEP lines on
CO objects. Object numbers follow SAP: KS<kokrs><cost center> for cost
centers, OR<order> for internal orders, EO<segment> for profitability
segments. Real-time FI->CO (business transaction COIN) opens its CO document
from the posting engine; allocations and settlement open their own.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.controlling import (
    CODocumentHeader,
    COLineItem,
    CostCenter,
    CostElementCO,
    InternalOrder,
)
from app.models.documents import NumberRange
from app.models.gl_master import GLAccountText
from app.services.fiscal import PostingError

ZERO = Decimal("0")


def cost_center_objnr(kokrs: str, kostl: str) -> str:
    return f"KS{kokrs}{kostl}"


def order_objnr(aufnr: str) -> str:
    return f"OR{aufnr}"


def next_number(session: Session, mandt: str, kokrs: str) -> str:
    rng = session.get(NumberRange, (mandt, "RK_BELEG", kokrs, "01", 0))
    if rng is None:
        raise PostingError(f"No CO document number range (RK_BELEG) for controlling area {kokrs}")
    nxt = int(rng.nrlevel or "0") + 1
    if nxt > int(rng.tonumber):
        raise PostingError(f"CO document number range of controlling area {kokrs} is exhausted")
    rng.nrlevel = str(nxt)
    return str(nxt).zfill(10)


def open_document(
    session: Session, mandt: str, kokrs: str, *, gjahr: int, perab: int, vrgng: str, budat: date,
    bldat: date | None = None, bltxt: str | None = None, usnam: str = "SYSTEM", awtyp: str | None = None,
    refbk: str | None = None, refbn: str | None = None, refgj: int | None = None, kscyc: str | None = None,
) -> CODocumentHeader:
    doc = CODocumentHeader(
        mandt=mandt, kokrs=kokrs, belnr=next_number(session, mandt, kokrs), gjahr=gjahr, versn="000",
        vrgng=vrgng, perab=perab, bldat=bldat or budat, budat=budat, usnam=usnam, bltxt=bltxt,
        awtyp=awtyp, refbk=refbk, refbn=refbn, refgj=refgj, kscyc=kscyc,
    )
    session.add(doc)
    session.flush([doc])
    doc._next_buzei = 0  # running line counter for add_line
    return doc


def add_line(
    session: Session, doc: CODocumentHeader, *, kstar: str, objnr: str, amount: Decimal,
    bukrs: str | None = None, kostl: str | None = None, aufnr: str | None = None,
    prctr: str | None = None, owaer: str | None = None, twaer: str | None = None,
    refbz: int | None = None,
) -> COLineItem:
    """Add a CO line; ``amount`` is signed (debit positive) in controlling area currency."""
    if not hasattr(doc, "_next_buzei"):
        doc._next_buzei = session.scalar(select(func.count()).select_from(COLineItem).where(
            COLineItem.mandt == doc.mandt, COLineItem.kokrs == doc.kokrs, COLineItem.belnr == doc.belnr)) or 0
    doc._next_buzei += 1
    line = COLineItem(
        mandt=doc.mandt, kokrs=doc.kokrs, belnr=doc.belnr, buzei=doc._next_buzei, perio=doc.perab,
        gjahr=doc.gjahr, wrttp="04", versn=doc.versn, kstar=kstar, objnr=objnr, bukrs=bukrs,
        kostl=kostl, aufnr=aufnr, prctr=prctr, wkgbtr=amount, owaer=owaer, twaer=twaer,
        vrgng=doc.vrgng, refbn=doc.refbn, refbz=refbz, refgj=doc.refgj,
    )
    session.add(line)
    return line


def object_balance(
    session: Session, mandt: str, kokrs: str, objnr: str, gjahr: int, perio_from: int = 1,
    perio_to: int = 16, kstars: set[str] | None = None,
) -> dict[str, Decimal]:
    """Actual costs of a CO object by cost element for a period range."""
    stmt = select(COLineItem.kstar, func.sum(COLineItem.wkgbtr)).where(
        COLineItem.mandt == mandt, COLineItem.kokrs == kokrs, COLineItem.objnr == objnr,
        COLineItem.wrttp == "04", COLineItem.gjahr == gjahr,
        COLineItem.perio >= perio_from, COLineItem.perio <= perio_to,
    ).group_by(COLineItem.kstar)
    out = {kstar: total for kstar, total in session.execute(stmt) if total}
    if kstars is not None:
        out = {k: v for k, v in out.items() if k in kstars}
    return out


def _element_texts(session: Session, mandt: str, kokrs: str) -> dict[str, tuple[str | None, str]]:
    names = {}
    for ce in session.scalars(select(CostElementCO).where(CostElementCO.mandt == mandt, CostElementCO.kokrs == kokrs)):
        names[ce.kstar] = (ce.ktext, ce.katyp)
    for t in session.scalars(select(GLAccountText).where(GLAccountText.mandt == mandt)):
        if t.saknr in names and (not names[t.saknr][0] or names[t.saknr][0] == t.saknr):
            names[t.saknr] = (t.txt50, names[t.saknr][1])
    return names


def actuals(
    session: Session, mandt: str, kokrs: str, gjahr: int, *, kind: str = "KS",
    perio_from: int = 1, perio_to: int = 16,
) -> list[dict]:
    """Actual costs per cost center (KS) or internal order (OR), by cost element."""
    if kind == "KS":
        objects = {cost_center_objnr(kokrs, c.kostl): (c.kostl, c.ltext or c.ktext)
                   for c in session.scalars(select(CostCenter).where(
                       CostCenter.mandt == mandt, CostCenter.kokrs == kokrs).order_by(CostCenter.kostl))}
        prefix = f"KS{kokrs}"
    elif kind == "OR":
        objects = {order_objnr(o.aufnr): (o.aufnr, o.ktext)
                   for o in session.scalars(select(InternalOrder).where(
                       InternalOrder.mandt == mandt, InternalOrder.kokrs == kokrs).order_by(InternalOrder.aufnr))}
        prefix = "OR"
    else:
        raise PostingError("kind must be KS (cost centers) or OR (internal orders)")

    rows = session.execute(select(COLineItem.objnr, COLineItem.kstar, func.sum(COLineItem.wkgbtr)).where(
        COLineItem.mandt == mandt, COLineItem.kokrs == kokrs, COLineItem.wrttp == "04",
        COLineItem.gjahr == gjahr, COLineItem.perio >= perio_from, COLineItem.perio <= perio_to,
        COLineItem.objnr.like(f"{prefix}%"),
    ).group_by(COLineItem.objnr, COLineItem.kstar)).all()
    by_object: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for objnr, kstar, total in rows:
        if total:
            by_object[objnr][kstar] = total
    names = _element_texts(session, mandt, kokrs)
    out = []
    for objnr in list(objects) + sorted(set(by_object) - set(objects)):
        key, text = objects.get(objnr, (objnr[len(prefix):], None))
        elements = by_object.get(objnr, {})
        out.append({
            "objnr": objnr, "object": key, "text": text, "total": sum(elements.values(), ZERO),
            "elements": [{"kstar": k, "text": names.get(k, (None, None))[0], "katyp": names.get(k, (None, None))[1],
                          "amount": v} for k, v in sorted(elements.items())],
        })
    return out
