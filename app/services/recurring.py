"""Recurring entries: original documents (FBD1) and the recurring entry run (F.14).

A recurring entry original is a document with status BKPF-BSTAT 'D', numbered
from interval X1, that updates nothing. Its BKDF schedule says when to post
it: first and last run date, interval in months and run day (clamped to the
month's last day). The run posts one copy per due run date up to the
settlement date, links it to the original (BKPF-DBBLG) and advances the next
run date (BKDF-DBATR), so running it again never posts a date twice.
"""

from __future__ import annotations

import calendar
from dataclasses import replace
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.documents import AccountingDocumentHeader, RecurringEntrySchedule
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, line_from_item, post_document


def _run_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _advance(current: date, months: int, day: int) -> date:
    index = current.year * 12 + current.month - 1 + months
    return _run_date(index // 12, index % 12 + 1, day)


def create_recurring(
    session: Session, req: DocumentRequest, *, dbbdt: date, dbedt: date, dbmon: int = 1,
    dbtag: int | None = None,
) -> AccountingDocumentHeader:
    """Store a recurring entry original with its run schedule (FBD1)."""
    if dbedt < dbbdt:
        raise PostingError("The last run date must not be before the first run date")
    if not 1 <= dbmon <= 12:
        raise PostingError("The interval must be between 1 and 12 months")
    day = dbtag or dbbdt.day
    if not 1 <= day <= 31:
        raise PostingError("The run day must be between 1 and 31")
    if any(ln.calculate_tax for ln in req.lines):
        raise PostingError("Enter tax lines explicitly in a recurring entry (no automatic tax)")
    original = post_document(session, replace(req, bstat="D", budat=dbbdt, bldat=dbbdt, tcode=req.tcode or "FBD1"),
                             commit=False)
    session.add(RecurringEntrySchedule(
        mandt=original.mandt, bukrs=original.bukrs, belnr=original.belnr, gjahr=original.gjahr,
        dbbdt=dbbdt, dbedt=dbedt, dbmon=dbmon, dbtag=day, dbatr=_run_date(dbbdt.year, dbbdt.month, day),
    ))
    session.commit()
    session.refresh(original)
    return original


def run_recurring(
    session: Session, mandt: str, bukrs: str, settle_to: date, *, usnam: str = "SYSTEM",
) -> list[dict]:
    """Post every recurring entry due up to ``settle_to`` (F.14); returns the posted documents."""
    schedules = session.scalars(select(RecurringEntrySchedule).where(
        RecurringEntrySchedule.mandt == mandt, RecurringEntrySchedule.bukrs == bukrs,
        RecurringEntrySchedule.dbatr.is_not(None), RecurringEntrySchedule.dbatr <= settle_to,
    ).order_by(RecurringEntrySchedule.dbatr)).all()

    posted = []
    for sched in schedules:
        original = session.get(AccountingDocumentHeader, (mandt, bukrs, sched.belnr, sched.gjahr))
        if original is None or original.bstat != "D":
            continue  # deleted original
        while sched.dbatr is not None and sched.dbatr <= settle_to:
            run_on = sched.dbatr
            lines = []
            for item in original.items:
                line = line_from_item(item)
                line.zfbdt = None  # baseline date from the copy's posting date
                lines.append(line)
            doc = post_document(session, DocumentRequest(
                mandt=mandt, bukrs=bukrs, blart=original.blart, bldat=run_on, budat=run_on,
                waers=original.waers, kursf=None, xblnr=original.xblnr,  # rate of the run date bktxt=original.bktxt,
                usnam=usnam, tcode="F.14", kokrs=original.kokrs, dbblg=original.belnr, lines=lines,
            ), commit=False)
            nxt = _advance(run_on, sched.dbmon, sched.dbtag)
            sched.dbatr = nxt if nxt <= sched.dbedt else None
            session.commit()
            posted.append({"belnr": doc.belnr, "gjahr": doc.gjahr, "budat": run_on,
                           "recurring": original.belnr, "bktxt": original.bktxt})
    return posted


def delete_recurring(session: Session, mandt: str, bukrs: str, belnr: str, gjahr: int) -> None:
    """Flag a recurring entry original as deleted (no further runs)."""
    original = session.get(AccountingDocumentHeader, (mandt, bukrs, belnr.zfill(10), gjahr))
    if original is None or original.bstat != "D":
        raise PostingError(f"Document {belnr}/{gjahr} is not a recurring entry original")
    original.bstat = "Z"
    for item in original.items:
        item.bstat = "Z"
    sched = session.get(RecurringEntrySchedule, (mandt, bukrs, original.belnr, gjahr))
    if sched is not None:
        sched.dbatr = None
    session.commit()


def list_recurring(session: Session, mandt: str, bukrs: str) -> list[dict]:
    out = []
    for sched in session.scalars(select(RecurringEntrySchedule).where(
            RecurringEntrySchedule.mandt == mandt, RecurringEntrySchedule.bukrs == bukrs)
            .order_by(RecurringEntrySchedule.belnr)):
        original = session.get(AccountingDocumentHeader, (mandt, bukrs, sched.belnr, sched.gjahr))
        runs = session.scalar(select(func.count()).select_from(AccountingDocumentHeader).where(
            AccountingDocumentHeader.mandt == mandt, AccountingDocumentHeader.bukrs == bukrs,
            AccountingDocumentHeader.dbblg == sched.belnr))
        out.append({
            "belnr": sched.belnr, "gjahr": sched.gjahr, "blart": original.blart, "bktxt": original.bktxt,
            "amount": sum((i.wrbtr for i in original.items if i.shkzg == "S"), 0), "waers": original.waers,
            "dbbdt": sched.dbbdt, "dbedt": sched.dbedt, "dbmon": sched.dbmon, "dbtag": sched.dbtag,
            "dbatr": sched.dbatr, "runs": runs, "deleted": original.bstat == "Z",
        })
    return out
