"""Recurring postings (ORCR / RCR1): templates that post a journal entry at a frequency.

Executing on a date posts every due instance up to that date (missed ones are caught up), each
dated on its due date, and moves NextDeu by the frequency (month ends stay month ends: a template
due 31 January is next due 28 / 29 February, then 31 March). A template ends after its number of
postings or at its valid-until date (it is then inactive). The journal entries keep the template
code in Ref3 ("RC:<code>"); they follow all posting rules (balanced, open periods, budgets).
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recurring import RecurringPosting, RecurringPostingLine
from app.services import journal
from app.services.admin import B1Error

ZERO = Decimal("0")
FREQUENCIES = {"D": "Daily", "W": "Weekly", "M": "Monthly", "Q": "Quarterly", "H": "Semiannually", "A": "Annually", "O": "One time"}
MONTHS = {"M": 1, "Q": 3, "H": 6, "A": 12}


def next_date(d: date, frequency: str, day: int | None = None) -> date | None:
    """Next due date; monthly frequencies post on the template's day (capped at the month's last day)."""
    if frequency == "O":
        return None
    if frequency == "D":
        return d + timedelta(days=1)
    if frequency == "W":
        return d + timedelta(days=7)
    m = d.month - 1 + MONTHS[frequency]
    year, month = d.year + m // 12, m % 12 + 1
    return date(year, month, min(day or d.day, calendar.monthrange(year, month)[1]))


def save(session: Session, data: dict, code: str | None = None) -> RecurringPosting:
    if code is None:
        code = (data.get("rcur_code") or "").strip().upper()
        if not re.match(r"^[A-Z0-9_-]{1,8}$", code):
            raise B1Error("A template code has 1-8 letters, digits, '_' or '-'")
        if session.get(RecurringPosting, code) is not None:
            raise B1Error(f"Recurring posting {code} already exists")
        rc = RecurringPosting(rcur_code=code, instance=0, active="Y")
        session.add(rc)
    else:
        rc = session.get(RecurringPosting, code)
        if rc is None:
            raise B1Error(f"Recurring posting {code} does not exist")
    for key in ("rcur_desc", "memo"):
        if key in data and data[key] is not None:
            setattr(rc, key, data[key].strip()[:50 if key == "rcur_desc" else 50])
    if not rc.rcur_desc:
        raise B1Error("Enter a description")
    if data.get("frequency"):
        if data["frequency"] not in FREQUENCIES:
            raise B1Error("Frequency: D, W, M, Q, H, A or O")
        rc.frequency = data["frequency"]
    if not rc.frequency:
        raise B1Error("Choose the frequency")
    for key in ("next_deu", "valid_until"):
        if key in data:
            v = data[key]
            setattr(rc, key, date.fromisoformat(v) if isinstance(v, str) and v else (v or None))
    if not rc.next_deu:
        raise B1Error("Enter the next due date")
    if "next_deu" in data or rc.day is None:
        rc.day = rc.next_deu.day
    if "limit_rtrns" in data:
        rc.limit_rtrns = int(data["limit_rtrns"]) if data["limit_rtrns"] else None
        if rc.limit_rtrns is not None and rc.limit_rtrns < 1:
            raise B1Error("The number of postings must be at least 1")
    if data.get("active") is not None:
        rc.active = "Y" if data["active"] else "N"
    if data.get("lines") is not None:
        lines = []
        for n, l in enumerate(data["lines"]):
            debit, credit = Decimal(str(l.get("debit") or 0)), Decimal(str(l.get("credit") or 0))
            if not (l.get("account") or l.get("card_code")):
                raise B1Error(f"Line {n + 1}: enter a G/L account or a business partner")
            if debit < 0 or credit < 0 or (debit and credit) or not (debit or credit):
                raise B1Error(f"Line {n + 1}: enter either a debit or a credit amount")
            codes = list(l.get("ocr_codes") or []) + [None, None]
            lines.append(RecurringPostingLine(line_id=n, account=l.get("account") or None, card_code=l.get("card_code") or None,
                                              debit=debit, credit=credit, line_memo=(l.get("line_memo") or None),
                                              ocr_code=codes[0] or None, ocr_code2=codes[1] or None))
        if len(lines) < 2 or sum((x.debit for x in lines), ZERO) != sum((x.credit for x in lines), ZERO):
            raise B1Error("The template must have at least two lines and debit = credit")
        rc.lines = lines
    if not rc.lines:
        raise B1Error("Enter the template lines")
    session.commit()
    return rc


def due(session: Session, on: date) -> list[dict]:
    """Active templates with at least one instance due up to a date."""
    out = []
    for rc in session.scalars(select(RecurringPosting).where(RecurringPosting.active == "Y", RecurringPosting.next_deu <= on)
                              .order_by(RecurringPosting.next_deu)):
        dates, d, count = [], rc.next_deu, rc.instance
        while d is not None and d <= on and (rc.valid_until is None or d <= rc.valid_until) and \
                (rc.limit_rtrns is None or count < rc.limit_rtrns) and len(dates) < 400:
            dates.append(d)
            count += 1
            d = next_date(d, rc.frequency, rc.day)
        if dates:
            out.append({"rcur_code": rc.rcur_code, "rcur_desc": rc.rcur_desc, "dates": dates,
                        "amount": sum((l.debit for l in rc.lines), ZERO)})
    return out


def execute(session: Session, code: str, on: date) -> list[int]:
    """Post the due instances of a template up to a date; returns the journal entry numbers."""
    rc = session.get(RecurringPosting, code)
    if rc is None:
        raise B1Error(f"Recurring posting {code} does not exist")
    if rc.active != "Y":
        raise B1Error(f"Recurring posting {code} is inactive")
    posted = []
    try:
        while rc.active == "Y" and rc.next_deu <= on:
            if (rc.valid_until and rc.next_deu > rc.valid_until) or (rc.limit_rtrns is not None and rc.instance >= rc.limit_rtrns):
                rc.active = "N"
                break
            je = journal.post_entry(session, journal.JournalRequest(
                ref_date=rc.next_deu, memo=(rc.memo or rc.rcur_desc)[:50], ref3=f"RC:{rc.rcur_code}", lines=[
                    journal.JournalLineRequest(account=l.account, card_code=l.card_code, debit=l.debit, credit=l.credit,
                                               line_memo=l.line_memo, ocr_codes=(l.ocr_code, l.ocr_code2) if l.ocr_code or l.ocr_code2 else None)
                    for l in rc.lines]), commit=False)
            posted.append(je.number)
            rc.instance += 1
            rc.last_date = rc.next_deu
            nxt = next_date(rc.next_deu, rc.frequency, rc.day)
            if nxt is None or (rc.limit_rtrns is not None and rc.instance >= rc.limit_rtrns) or (rc.valid_until and nxt > rc.valid_until):
                rc.active = "N"
                break
            rc.next_deu = nxt
        session.commit()
    except Exception:
        session.rollback()
        raise
    return posted


def out(rc: RecurringPosting) -> dict:
    return {"rcur_code": rc.rcur_code, "rcur_desc": rc.rcur_desc, "frequency": rc.frequency, "frequency_name": FREQUENCIES.get(rc.frequency),
            "next_deu": rc.next_deu, "day": rc.day, "last_date": rc.last_date, "valid_until": rc.valid_until, "limit_rtrns": rc.limit_rtrns,
            "instance": rc.instance, "memo": rc.memo, "active": rc.active == "Y",
            "lines": [{"account": l.account, "card_code": l.card_code, "debit": l.debit, "credit": l.credit, "line_memo": l.line_memo,
                       "ocr_codes": [l.ocr_code, l.ocr_code2, None, None, None]} for l in rc.lines]}
