"""GST return filing status (OGSR), the lock of filed months and GSTR-1 amendments.

Marking GSTR-1 / GSTR-3B of a month as filed stores the return as filed (Snapshot). Afterwards:
  - no A/R invoice / credit memo may be posted in a month whose GSTR-1 or GSTR-3B is filed, and no
    A/P invoice / credit memo or ITC reversal in a month whose GSTR-3B is filed;
  - an A/R invoice / credit memo of a GSTR-1-filed month is not canceled directly: it is amended — a
    replacement document is posted in an open month (AmndEntry = the original) and the original is
    canceled on the replacement's date (CancelDate). GSTR-1 of that month reports the replacement in
    B2BA / CDNRA / B2CLA / B2CSA with the original details; GSTR-3B takes the replacement and, negative,
    the canceled original, so liability still equals the journal of the month;
  - an A/P document of a GSTR-3B-filed month is canceled with a cancellation date in an open month (its
    ITC is reduced in that month).
Undoing a filing (e.g. filed by mistake) unlocks the month again.
"""

from __future__ import annotations

import json
from datetime import date

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.edocs import GstReturnFiling
from app.services.admin import B1Error

RETURNS = {"GSTR1": "GSTR-1", "GSTR3B": "GSTR-3B"}
SALES, PURCHASING = {"13", "14"}, {"18", "19"}


def _period(on: date) -> str:
    return f"{on.month:02d}{on.year}"


def get(session: Session, ret: str, year: int, month: int) -> GstReturnFiling | None:
    return session.scalar(select(GstReturnFiling).where(GstReturnFiling.ret_type == ret, GstReturnFiling.period == f"{month:02d}{year}"))


def status(session: Session, ret: str, year: int, month: int) -> dict | None:
    f = get(session, ret, year, month)
    return {"ret_type": f.ret_type, "period": f.period, "filed_date": f.filed_date, "arn": f.arn, "user_sign": f.user_sign} if f else None


def snapshot(session: Session, ret: str, year: int, month: int) -> dict | None:
    f = get(session, ret, year, month)
    return json.loads(f.snapshot) if f else None


def filed_for(session: Session, obj: str, on: date) -> str | None:
    """The filed return that locks a posting of this object type on this date, else None."""
    if obj not in SALES | PURCHASING:
        return None
    rets = ("GSTR1", "GSTR3B") if obj in SALES else ("GSTR3B",)
    for ret in rets:
        if get(session, ret, on.year, on.month) is not None:
            return ret
    return None


def check_posting(session: Session, obj: str, on: date) -> None:
    ret = filed_for(session, obj, on)
    if ret:
        raise B1Error(f"{RETURNS[ret]} for {on.month:02d}/{on.year} is filed; post the document in an open month")


def check_cancel(session: Session, obj: str, doc, cancel_date: date | None, amendment: bool = False) -> None:
    ret = filed_for(session, obj, doc.doc_date)
    if not ret:
        return
    if obj in SALES and get(session, "GSTR1", doc.doc_date.year, doc.doc_date.month) is not None and not amendment:
        raise B1Error(f"GSTR-1 for {doc.doc_date.month:02d}/{doc.doc_date.year} is filed: amend the document (replacement in an open month) "
                      f"or issue a credit memo instead of canceling it")
    if cancel_date is None or filed_for(session, obj, cancel_date) or cancel_date < doc.doc_date:
        raise B1Error(f"{RETURNS[ret]} for {doc.doc_date.month:02d}/{doc.doc_date.year} is filed; enter a cancellation date in an open month")


def check_journal(session: Session, on: date) -> None:
    """ITC reversals / reclaims change GSTR-3B of their month."""
    if get(session, "GSTR3B", on.year, on.month) is not None:
        raise B1Error(f"GSTR-3B for {on.month:02d}/{on.year} is filed; post in an open month")


def file_return(session: Session, ret: str, year: int, month: int, filed_date: date | None = None, arn: str | None = None) -> GstReturnFiling:
    from app.context import current_user_code
    from app.services import gst_returns

    if ret not in RETURNS:
        raise B1Error("Return: GSTR1 or GSTR3B")
    gst_returns.period(year, month)
    if get(session, ret, year, month) is not None:
        raise B1Error(f"{RETURNS[ret]} for {month:02d}/{year} is already marked as filed")
    data = gst_returns.gstr1(session, year, month) if ret == "GSTR1" else gst_returns.gstr3b(session, year, month)
    f = GstReturnFiling(abs_entry=(session.scalar(select(GstReturnFiling.abs_entry).order_by(GstReturnFiling.abs_entry.desc()).limit(1)) or 0) + 1,
                        ret_type=ret, period=f"{month:02d}{year}", filed_date=filed_date or date.today(), arn=(arn or "").strip()[:20] or None,
                        snapshot=json.dumps(jsonable_encoder(data)), user_sign=current_user_code.get())
    session.add(f)
    session.commit()
    return f


def unfile(session: Session, ret: str, year: int, month: int) -> None:
    f = get(session, ret, year, month)
    if f is None:
        raise B1Error(f"{RETURNS.get(ret, ret)} for {month:02d}/{year} is not filed")
    session.delete(f)
    session.commit()


def amend(session: Session, obj: str, doc_entry: int, req):
    """Replace an A/R invoice / credit memo of a GSTR-1-filed month: post the replacement (req) in an open
    month and cancel the original on its date, in one transaction."""
    from app.services import documents

    if obj not in SALES:
        raise B1Error("Only A/R invoices and A/R credit memos are amended")
    orig = documents.get_document(session, obj, doc_entry)
    if orig.canceled == "Y":
        raise B1Error(f"Document {orig.doc_num} is canceled")
    if orig.amnd_entry is None and get(session, "GSTR1", orig.doc_date.year, orig.doc_date.month) is None:
        raise B1Error(f"GSTR-1 for {orig.doc_date.month:02d}/{orig.doc_date.year} is not filed: cancel or change the document instead")
    if req.obj != obj or req.card_code != orig.card_code:
        raise B1Error("The replacement must be the same document type for the same business partner")
    if req.doc_date < orig.doc_date:
        raise B1Error(f"Post the replacement on or after {orig.doc_date} (the original's date), in an open month")
    if any(l.base_type for l in req.lines):
        raise B1Error("The replacement lines are entered again (not copied from base documents)")
    try:
        new = documents.create_document(session, req, commit=False)
        new.amnd_entry = orig.doc_entry
        documents._cancel(session, obj, doc_entry, new.doc_date, amendment=True)
        session.commit()
        return new
    except Exception:
        session.rollback()
        raise
