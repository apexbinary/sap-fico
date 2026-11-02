"""Internal order settlement (KO88).

An order's settlement rule (COBRA) has distribution rules (COBRB) that send a
percentage of the order's costs to a receiver:

  * KS cost center: CO posting — credit the order, debit the cost center with
    the internal settlement cost element (category 21);
  * SK G/L account: external settlement — the order is credited in CO with
    the settlement cost element (category 22, a G/L account) and an FI
    document debits the receiver account against that settlement account.

Settlement takes the order's balance cumulated up to the settlement period,
so settled costs are not settled again and a repeated run posts nothing new.
Percentages below 100 leave the rest on the order. One CO document (business
transaction KOAO) per settlement, plus one FI document if there are G/L
receivers.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.controlling import InternalOrder, SettlementDistribution
from app.services import controlling
from app.services.fiscal import PostingError, company_code

ZERO = Decimal("0")
_CENT = Decimal("0.01")
INTERNAL_ELEMENT = "950000"  # category 21: internal settlement
EXTERNAL_ELEMENT = "960000"  # category 22: external settlement (G/L account)


def _rules(session, mandt, objnr, gjahr, perio) -> list[SettlementDistribution]:
    rules = session.scalars(select(SettlementDistribution).where(
        SettlementDistribution.mandt == mandt, SettlementDistribution.objnr == objnr,
    ).order_by(SettlementDistribution.bureg, SettlementDistribution.lfdnr)).all()
    return [r for r in rules if (r.gabja or 0, r.gabpe or 0) <= (gjahr, perio)]


def settle_order(
    session: Session, mandt: str, kokrs: str, aufnr: str, gjahr: int, perio: int, *,
    test: bool = False, usnam: str = "SYSTEM",
) -> dict:
    from app.services.posting import DocumentRequest, LineRequest, post_document

    order = session.get(InternalOrder, (mandt, aufnr.zfill(12)))
    if order is None:
        raise PostingError(f"Order {aufnr} does not exist")
    if not order.phas1 or order.loekz:
        raise PostingError(f"Order {order.aufnr} is not released for settlement")
    objnr = controlling.order_objnr(order.aufnr)
    rules = _rules(session, mandt, objnr, gjahr, perio)
    if not rules:
        raise PostingError(f"Order {order.aufnr} has no settlement rule valid in {perio}/{gjahr}")
    if sum((r.prozs for r in rules), ZERO) > 100:
        raise PostingError(f"The settlement percentages of order {order.aufnr} exceed 100%")

    balance = sum(controlling.object_balance(session, mandt, kokrs, objnr, gjahr, 1, perio).values(), ZERO)
    lines = []
    for r in rules:
        amount = (balance * r.prozs / 100).quantize(_CENT, ROUND_HALF_UP)
        if not amount:
            continue
        receiver = r.kostl if r.konty == "KS" else r.hkont
        if r.konty not in ("KS", "SK") or not receiver:
            raise PostingError(f"Distribution rule {r.bureg} of order {order.aufnr} has no valid receiver")
        lines.append({"konty": r.konty, "receiver": receiver, "prozs": r.prozs, "amount": amount,
                      "kstar": INTERNAL_ELEMENT if r.konty == "KS" else EXTERNAL_ELEMENT})

    result = {"aufnr": order.aufnr, "gjahr": gjahr, "perio": perio, "balance": balance, "lines": lines,
              "settled": sum((l["amount"] for l in lines), ZERO), "co_document": None, "fi_document": None}
    if test or not lines:
        return result

    month = min(perio, 12)
    budat = date(gjahr, month, calendar.monthrange(gjahr, month)[1])
    co = controlling.open_document(session, mandt, kokrs, gjahr=gjahr, perab=perio, vrgng="KOAO", budat=budat,
                                   bltxt=f"Settlement order {order.aufnr}", usnam=usnam)
    for l in lines:
        controlling.add_line(session, co, kstar=l["kstar"], objnr=objnr, amount=-l["amount"],
                             aufnr=order.aufnr, bukrs=order.bukrs)
        if l["konty"] == "KS":
            controlling.add_line(session, co, kstar=l["kstar"], amount=l["amount"], kostl=l["receiver"],
                                 objnr=controlling.cost_center_objnr(kokrs, l["receiver"]), bukrs=order.bukrs)
    external = [l for l in lines if l["konty"] == "SK"]
    if external:
        cc = company_code(session, mandt, order.bukrs)
        total = sum((l["amount"] for l in external), ZERO)
        fi = post_document(session, DocumentRequest(
            mandt=mandt, bukrs=order.bukrs, blart="SA", bldat=budat, budat=budat, waers=cc.waers,
            bktxt=f"Settlement {order.aufnr}"[:25], usnam=usnam, tcode="KO88", lines=[
                *(LineRequest(bschl="40", account=l["receiver"], wrbtr=l["amount"], sgtxt=f"Order {order.aufnr}")
                  for l in external),
                LineRequest(bschl="50", account=EXTERNAL_ELEMENT, wrbtr=total, sgtxt=f"Order {order.aufnr}"),
            ]), commit=False)
        co.refbn, co.refgj, co.refbk, co.awtyp = fi.belnr, fi.gjahr, order.bukrs, "BKPF"
        result["fi_document"] = fi.belnr
    session.commit()
    result["co_document"] = co.belnr
    return result


def reverse_settlement(session: Session, mandt: str, kokrs: str, aufnr: str, gjahr: int, perio: int,
                       *, usnam: str = "SYSTEM") -> dict:
    """Reverse the last settlement of an order for a period (CO document and its FI document)."""
    from app.models.controlling import CODocumentHeader
    from app.services.reversal import reverse_document

    order_no = aufnr.zfill(12)
    doc = session.scalars(select(CODocumentHeader).where(
        CODocumentHeader.mandt == mandt, CODocumentHeader.kokrs == kokrs, CODocumentHeader.vrgng == "KOAO",
        CODocumentHeader.gjahr == gjahr, CODocumentHeader.perab == perio,
        CODocumentHeader.bltxt == f"Settlement order {order_no}",
        CODocumentHeader.stokz.is_(False), CODocumentHeader.stflg.is_(False),
    ).order_by(CODocumentHeader.belnr.desc())).first()
    if doc is None:
        raise PostingError(f"Order {order_no} has no settlement in {perio}/{gjahr} to reverse")
    fi = None
    if doc.refbn:
        fi = reverse_document(session, mandt, doc.refbk, doc.refbn, doc.refgj, usnam=usnam, commit=False)
    rev = controlling.reverse_document(session, mandt, kokrs, doc.belnr, usnam=usnam, commit=False)
    session.commit()
    return {"aufnr": order_no, "reversed": doc.belnr, "reversal": rev.belnr, "fi_reversal": fi.belnr if fi else None}


def rules_of(session: Session, mandt: str, aufnr: str) -> list[dict]:
    objnr = controlling.order_objnr(aufnr.zfill(12))
    rows = session.scalars(select(SettlementDistribution).where(
        SettlementDistribution.mandt == mandt, SettlementDistribution.objnr == objnr,
    ).order_by(SettlementDistribution.bureg)).all()
    return [{"bureg": r.bureg, "konty": r.konty, "receiver": r.kostl or r.hkont, "prozs": r.prozs,
             "perbz": r.perbz, "valid_from": f"{r.gabpe or 1}/{r.gabja}" if r.gabja else None} for r in rows]
