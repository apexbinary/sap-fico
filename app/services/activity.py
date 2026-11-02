"""Direct internal activity allocation (KB21N) and its reversal (KB24N).

A sender cost center provides a quantity of an activity type (CSLA) to a
receiver cost center or internal order. The value is quantity x the activity
price of the sender for the period (COST); the CO document (business
transaction RKL) credits the sender and debits the receiver with the activity
type's allocation cost element (category 43), quantities included.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.controlling import ActivityType, CostCenter, InternalOrder
from app.services import controlling, planning
from app.services.fiscal import PostingError

_CENT = Decimal("0.01")


def allocate(
    session: Session, mandt: str, kokrs: str, *, sender_kostl: str, lstar: str, quantity: Decimal, gjahr: int,
    perio: int, receiver_kostl: str | None = None, receiver_aufnr: str | None = None, usnam: str = "SYSTEM",
) -> dict:
    if bool(receiver_kostl) == bool(receiver_aufnr):
        raise PostingError("Enter either a receiver cost center or a receiver order")
    if quantity <= 0:
        raise PostingError("The quantity must be positive")
    month = min(perio, 12)
    budat = date(gjahr, month, calendar.monthrange(gjahr, month)[1])
    activity = session.scalars(select(ActivityType).where(
        ActivityType.mandt == mandt, ActivityType.kokrs == kokrs, ActivityType.lstar == lstar,
        ActivityType.datab <= budat, ActivityType.datbi >= budat)).first()
    if activity is None:
        raise PostingError(f"Activity type {lstar} is not valid on {budat.isoformat()}")
    if not session.scalars(select(CostCenter).where(
            CostCenter.mandt == mandt, CostCenter.kokrs == kokrs, CostCenter.kostl == sender_kostl)).first():
        raise PostingError(f"Sender cost center {sender_kostl} does not exist")
    if receiver_kostl:
        if receiver_kostl == sender_kostl:
            raise PostingError("Sender and receiver must differ")
        receiver = controlling.cost_center_objnr(kokrs, receiver_kostl)
    else:
        order = session.get(InternalOrder, (mandt, receiver_aufnr.zfill(12)))
        if order is None or not order.phas1:
            raise PostingError(f"Order {receiver_aufnr} does not exist or is not released")
        receiver = controlling.order_objnr(order.aufnr)
    price = planning.price_of(session, mandt, kokrs, sender_kostl, lstar, gjahr, perio)
    if price is None:
        raise PostingError(f"No price for activity type {lstar} of cost center {sender_kostl} in {perio}/{gjahr} (KP26)")
    value = (quantity * price).quantize(_CENT, ROUND_HALF_UP)

    doc = controlling.open_document(session, mandt, kokrs, gjahr=gjahr, perab=perio, vrgng="RKL", budat=budat,
                                    bltxt=f"Activity {lstar}: {quantity} {activity.leinh} from {sender_kostl}", usnam=usnam)
    controlling.add_line(session, doc, kstar=activity.vksta, objnr=controlling.cost_center_objnr(kokrs, sender_kostl),
                         amount=-value, kostl=sender_kostl, megbtr=-quantity, meinb=activity.leinh)
    controlling.add_line(session, doc, kstar=activity.vksta, objnr=receiver, amount=value,
                         kostl=receiver_kostl, aufnr=receiver_aufnr.zfill(12) if receiver_aufnr else None,
                         megbtr=quantity, meinb=activity.leinh)
    session.commit()
    return {"belnr": doc.belnr, "lstar": lstar, "quantity": quantity, "unit": activity.leinh, "price": price,
            "value": value, "sender": sender_kostl, "receiver": receiver_kostl or receiver_aufnr}
