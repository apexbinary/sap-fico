"""Assessment (KSU5) and distribution (KSV5) cycles.

A cycle (T811C) has segments (T811S). Each segment names sender cost centers,
the range of cost elements they send, and receivers with tracing factors
(T811K). For a period, a sender sends its actual costs of the period in that
range:

  * assessment credits the sender and debits the receivers with the secondary
    assessment cost element of the segment (category 42), one total per sender;
  * distribution keeps the original primary cost elements, element by element;
  * CO-PA assessment (KEU5, cycle type P) assesses like an assessment, but the
    receivers are the profitability segments with net revenue in the period,
    weighted by that revenue.

Receivers get shares in proportion to their factors; the last receiver takes
the rounding remainder. A run posts one CO document (business transaction
RKIU for assessment, RKIV for distribution) that carries the cycle. A cycle
runs once per period: reverse the run to repeat it.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.controlling import (
    AllocationCycle,
    AllocationReceiver,
    AllocationSegment,
    CODocumentHeader,
    COLineItem,
    CostCenter,
)
from app.services import controlling
from app.services.fiscal import PostingError

ZERO = Decimal("0")
_CENT = Decimal("0.01")
_VRGNG = {"A": "RKIU", "D": "RKIV", "P": "RKEU"}


def _period_end(gjahr: int, perio: int) -> date:
    month = min(perio, 12)
    return date(gjahr, month, calendar.monthrange(gjahr, month)[1])


def _cycle(session: Session, mandt: str, kokrs: str, cycle: str, on: date) -> AllocationCycle:
    cyc = session.scalars(select(AllocationCycle).where(
        AllocationCycle.mandt == mandt, AllocationCycle.kokrs == kokrs, AllocationCycle.cycle == cycle,
        AllocationCycle.sdate <= on, AllocationCycle.edate >= on)).first()
    if cyc is None:
        raise PostingError(f"Cycle {cycle} is not defined for {on.isoformat()} in controlling area {kokrs}")
    return cyc


def _existing_run(session, mandt, kokrs, cycle, gjahr, perio) -> CODocumentHeader | None:
    return session.scalars(select(CODocumentHeader).where(
        CODocumentHeader.mandt == mandt, CODocumentHeader.kokrs == kokrs, CODocumentHeader.kscyc == cycle,
        CODocumentHeader.gjahr == gjahr, CODocumentHeader.perab == perio,
        CODocumentHeader.stflg.is_(False), CODocumentHeader.stokz.is_(False))).first()


def _split(amount: Decimal, receivers: list[AllocationReceiver]) -> list[tuple[str, Decimal]]:
    total = sum((r.faktor for r in receivers), ZERO)
    shares, given = [], ZERO
    for i, r in enumerate(receivers):
        share = amount - given if i == len(receivers) - 1 else (amount * r.faktor / total).quantize(_CENT, ROUND_HALF_UP)
        given += share
        shares.append((r.kostl, share))
    return shares


def run_cycle(
    session: Session, mandt: str, kokrs: str, cycle: str, gjahr: int, perio: int, *,
    test: bool = False, usnam: str = "SYSTEM",
) -> dict:
    """Execute (or simulate) an assessment / distribution cycle for one period."""
    budat = _period_end(gjahr, perio)
    cyc = _cycle(session, mandt, kokrs, cycle, budat)
    if not test:
        done = _existing_run(session, mandt, kokrs, cycle, gjahr, perio)
        if done is not None:
            raise PostingError(f"Cycle {cycle} already ran for {perio}/{gjahr} (CO document {done.belnr}); reverse it first")

    segments = session.scalars(select(AllocationSegment).where(
        AllocationSegment.mandt == mandt, AllocationSegment.kokrs == kokrs, AllocationSegment.cycle == cycle,
        AllocationSegment.sdate == cyc.sdate).order_by(AllocationSegment.seg)).all()
    if not segments:
        raise PostingError(f"Cycle {cycle} has no segments")

    plan = []
    shares = None
    if cyc.ttype == "P":
        from app.services import copa

        shares = copa.revenue_shares(session, mandt, kokrs, gjahr, perio)
        if not shares:
            raise PostingError(f"No net revenue in profitability segments in {perio}/{gjahr} to assess {cycle} to")
    for seg in segments:
        if cyc.ttype == "P":
            receivers = [AllocationReceiver(kostl=str(paobjnr), faktor=net) for paobjnr, net in sorted(shares.items())]
        else:
            receivers = session.scalars(select(AllocationReceiver).where(
            AllocationReceiver.mandt == mandt, AllocationReceiver.kokrs == kokrs, AllocationReceiver.cycle == cycle,
            AllocationReceiver.sdate == cyc.sdate, AllocationReceiver.seg == seg.seg,
            ).order_by(AllocationReceiver.kostl)).all()
        if not receivers or sum((r.faktor for r in receivers), ZERO) <= 0:
            raise PostingError(f"Segment {seg.seg} of cycle {cycle} has no receivers with a positive factor")
        if cyc.ttype in ("A", "P") and not seg.askst:
            raise PostingError(f"Segment {seg.seg} of assessment cycle {cycle} has no assessment cost element")
        senders = session.scalars(select(CostCenter).where(
            CostCenter.mandt == mandt, CostCenter.kokrs == kokrs,
            CostCenter.kostl >= seg.kostl_von, CostCenter.kostl <= seg.kostl_bis).order_by(CostCenter.kostl)).all()
        for sender in senders:
            if any(r.kostl == sender.kostl for r in receivers):
                raise PostingError(f"Cost center {sender.kostl} is sender and receiver in segment {seg.seg} of {cycle}")
            balances = controlling.object_balance(
                session, mandt, kokrs, controlling.cost_center_objnr(kokrs, sender.kostl), gjahr, perio, perio)
            sent = {k: v for k, v in balances.items() if seg.kstar_von <= k <= seg.kstar_bis and v}
            amounts = {seg.askst: sum(sent.values(), ZERO)} if cyc.ttype in ("A", "P") else sent
            for kstar, amount in sorted(amounts.items()):
                if not amount:
                    continue
                plan.append({"seg": seg.seg, "kostl": sender.kostl, "role": "sender", "kstar": kstar, "amount": -amount})
                for rcv, share in _split(amount, receivers):
                    plan.append({"seg": seg.seg, "kostl": rcv, "role": "receiver", "kstar": kstar, "amount": share})

    result = {"cycle": cycle, "ttype": cyc.ttype, "txt": cyc.txt, "gjahr": gjahr, "perio": perio,
              "lines": plan, "sent": -sum((l["amount"] for l in plan if l["role"] == "sender"), ZERO),
              "document": None}
    if test or not plan:
        return result
    kind = {"A": "Assessment", "D": "Distribution", "P": "CO-PA assessment"}[cyc.ttype]
    doc = controlling.open_document(
        session, mandt, kokrs, gjahr=gjahr, perab=perio, vrgng=_VRGNG[cyc.ttype], budat=budat,
        bltxt=f"{kind} {cycle} {perio:02d}/{gjahr}", usnam=usnam, kscyc=cycle)
    for line in plan:
        if cyc.ttype == "P" and line["role"] == "receiver":
            from app.services import copa

            controlling.add_line(session, doc, kstar=line["kstar"], amount=line["amount"],
                                 objnr=copa.segment_objnr(int(line["kostl"])))
        else:
            controlling.add_line(session, doc, kstar=line["kstar"], amount=line["amount"], kostl=line["kostl"],
                                 objnr=controlling.cost_center_objnr(kokrs, line["kostl"]))
    session.commit()
    result["document"] = doc.belnr
    return result


def reverse_run(session: Session, mandt: str, kokrs: str, cycle: str, gjahr: int, perio: int,
                *, usnam: str = "SYSTEM") -> dict:
    """Reverse the active run of a cycle for a period (new CO document with opposite values)."""
    orig = _existing_run(session, mandt, kokrs, cycle, gjahr, perio)
    if orig is None:
        raise PostingError(f"Cycle {cycle} has no active run for {perio}/{gjahr}")
    lines = session.scalars(select(COLineItem).where(
        COLineItem.mandt == mandt, COLineItem.kokrs == kokrs, COLineItem.belnr == orig.belnr)
        .order_by(COLineItem.buzei)).all()
    rev = controlling.open_document(
        session, mandt, kokrs, gjahr=gjahr, perab=perio, vrgng=orig.vrgng, budat=orig.budat,
        bltxt=f"Reversal of {orig.belnr}", usnam=usnam, kscyc=cycle)
    rev.stflg, rev.refbn, rev.refgj, rev.awtyp = True, orig.belnr, orig.gjahr, "COBK"
    for line in lines:
        controlling.add_line(session, rev, kstar=line.kstar, objnr=line.objnr, amount=-line.wkgbtr,
                             kostl=line.kostl, aufnr=line.aufnr)
    orig.stokz = True
    session.commit()
    return {"cycle": cycle, "gjahr": gjahr, "perio": perio, "reversed": orig.belnr, "reversal": rev.belnr}


def list_cycles(session: Session, mandt: str, kokrs: str) -> list[dict]:
    out = []
    for cyc in session.scalars(select(AllocationCycle).where(
            AllocationCycle.mandt == mandt, AllocationCycle.kokrs == kokrs).order_by(AllocationCycle.cycle)):
        segments = []
        for seg in session.scalars(select(AllocationSegment).where(
                AllocationSegment.mandt == mandt, AllocationSegment.kokrs == kokrs,
                AllocationSegment.cycle == cyc.cycle, AllocationSegment.sdate == cyc.sdate).order_by(AllocationSegment.seg)):
            receivers = session.scalars(select(AllocationReceiver).where(
                AllocationReceiver.mandt == mandt, AllocationReceiver.kokrs == kokrs,
                AllocationReceiver.cycle == cyc.cycle, AllocationReceiver.sdate == cyc.sdate,
                AllocationReceiver.seg == seg.seg)).all()
            segments.append({
                "seg": seg.seg, "txt": seg.txt, "senders": f"{seg.kostl_von}–{seg.kostl_bis}",
                "elements": f"{seg.kstar_von}–{seg.kstar_bis}", "askst": seg.askst,
                "receivers": [{"kostl": r.kostl, "faktor": r.faktor} for r in receivers],
            })
        runs = session.scalars(select(CODocumentHeader).where(
            CODocumentHeader.mandt == mandt, CODocumentHeader.kokrs == kokrs, CODocumentHeader.kscyc == cyc.cycle,
            CODocumentHeader.stflg.is_(False)).order_by(CODocumentHeader.gjahr, CODocumentHeader.perab)).all()
        out.append({
            "cycle": cyc.cycle, "sdate": cyc.sdate, "edate": cyc.edate, "txt": cyc.txt, "ttype": cyc.ttype,
            "segments": segments,
            "runs": [{"gjahr": r.gjahr, "perio": r.perab, "belnr": r.belnr, "reversed": r.stokz} for r in runs],
        })
    return out
