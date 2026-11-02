"""Dunning: raising the dunning level of overdue customer items and producing dunning letters.

Each open customer item (JDT1 partner line with an open debit) carries a dunning level
(DunnLevel, DunDate). For a run date, an item overdue by D days may reach the highest level of
the customer's dunning term (ODUT / DUT1) with Days <= D; a run raises it by one level (or
straight to that level when the term or the run says "highest"). Items whose level does not
rise are not dunned again. A letter is produced per customer whose overdue total reaches the
minimum balance of its letter level. Interest on arrears = open x rate x days / 365 for the
days since the last dunning (since the due date for the first letter; the customer's rate,
else the term's); items dunned within the term's minimum days between letters are skipped; the fee is the one of the letter's level. Optionally the
interest and fee are posted as a new open item of the customer.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.admin import DunningLevel, DunningTerm
from app.models.banking import DunningLetter, DunningLetterItem, DunningRun
from app.models.finance import AccountDetermination, JournalLine
from app.models.partners import BusinessPartner
from app.services import journal
from app.services.admin import B1Error
from app.services.journal import JournalLineRequest, JournalRequest, money

ZERO = Decimal("0")


def _levels(session: Session, term: str) -> list[DunningLevel]:
    return session.scalars(select(DunningLevel).where(DunningLevel.term_code == term).order_by(DunningLevel.level)).all()


def preview(session: Session, on: date, card_codes: list[str] | None = None, highest: bool | None = None) -> list[dict]:
    """Letters a run on `on` would produce: one per customer, with the items whose level rises."""
    q = select(BusinessPartner).where(BusinessPartner.card_type == "C", BusinessPartner.dun_term.is_not(None),
                                      BusinessPartner.frozen_for == "N")
    if card_codes:
        q = q.where(BusinessPartner.card_code.in_(card_codes))
    letters = []
    for bp in session.scalars(q.order_by(BusinessPartner.card_code)):
        term = session.get(DunningTerm, bp.dun_term)
        levels = _levels(session, bp.dun_term) if term else []
        if not levels:
            continue
        to_highest = term.highest == "Y" if highest is None else highest
        rate = bp.intrst_rate or term.interest or ZERO
        items, overdue_total = [], ZERO
        for l in session.scalars(select(JournalLine).where(
                JournalLine.short_name == bp.card_code, JournalLine.short_name != JournalLine.account,
                JournalLine.bal_due_deb > 0, JournalLine.due_date < on).order_by(JournalLine.due_date, JournalLine.trans_id)):
            days = (on - l.due_date).days
            overdue_total += l.bal_due_deb
            if l.dun_date is not None and (on - l.dun_date).days < (term.days_between or 0):
                continue  # dunned too recently
            reachable = max((lv.level for lv in levels if lv.days <= days), default=0)
            new = reachable if to_highest else min(l.dunn_level + 1, reachable)
            if new <= l.dunn_level:
                continue
            items.append({"trans_id": l.trans_id, "line_id": l.line_id, "trans_type": l.trans_type, "doc_num": l.base_ref,
                          "due_date": l.due_date, "days_overdue": days, "open_amount": l.bal_due_deb,
                          "old_level": l.dunn_level, "new_level": new,
                          # interest since the last dunning (the due date for the first letter): never charged twice
                          "interest": money(l.bal_due_deb * rate / 100 * (on - (l.dun_date or l.due_date)).days / 365)})
        if not items:
            continue
        level = max(i["new_level"] for i in items)
        lv = next(x for x in levels if x.level == level)
        if overdue_total < lv.min_balance:
            continue
        letters.append({"card_code": bp.card_code, "card_name": bp.card_name, "level": level,
                        "total_open": overdue_total, "interest": sum((i["interest"] for i in items), ZERO),
                        "fee": money(lv.fee), "letter_text": lv.letter_text, "interest_rate": rate, "items": items})
    return letters


def run(session: Session, on: date, card_codes: list[str] | None = None, highest: bool | None = None,
        post_fees: bool = False, name: str | None = None) -> DunningRun:
    try:
        letters = preview(session, on, card_codes, highest)
        if not letters:
            raise B1Error(f"Nothing to dun on {on.isoformat()}")
        det = session.get(AccountDetermination, str(on.year))
        if post_fees and det is None:
            raise B1Error(f"No G/L account determination for {on.year}")
        r = DunningRun(abs_entry=(session.scalar(select(func.max(DunningRun.abs_entry))) or 0) + 1,
                       wizard_name=(name or f"Dunning {on.isoformat()}")[:50], dun_date=on,
                       highest="Y" if highest else "N", post_fees="Y" if post_fees else "N")
        for n, x in enumerate(letters, start=1):
            letter = DunningLetter(letter_num=n, card_code=x["card_code"], card_name=x["card_name"], level=x["level"],
                                   total_open=x["total_open"], interest=x["interest"], fee=x["fee"],
                                   letter_text=x["letter_text"])
            for m, it in enumerate(x["items"]):
                line = session.get(JournalLine, (it["trans_id"], it["line_id"]))
                line.dunn_level, line.dun_date = it["new_level"], on
                letter.items.append(DunningLetterItem(abs_entry=r.abs_entry, letter_num=n, line_num=m, **{
                    k: it[k] for k in ("trans_id", "line_id", "trans_type", "doc_num", "due_date", "days_overdue",
                                       "open_amount", "old_level", "new_level", "interest")}))
            charge = x["interest"] + x["fee"]
            if post_fees and charge > 0:  # interest on arrears and dunning fee become an open item of the customer
                lines = [JournalLineRequest(card_code=x["card_code"], debit=charge, due_date=on,
                                            line_memo=f"Dunning level {x['level']}")]
                if x["interest"]:
                    lines.append(JournalLineRequest(account=det.dunning_interest, credit=x["interest"], line_memo="Interest on arrears"))
                if x["fee"]:
                    lines.append(JournalLineRequest(account=det.dunning_fee, credit=x["fee"], line_memo="Dunning fee"))
                je = journal.post_entry(session, JournalRequest(ref_date=on, due_date=on, memo=f"Dunning {x['card_code']} level {x['level']}"[:50],
                                                                ref1=f"DUN {r.abs_entry}", manual=False, lines=lines), commit=False)
                letter.trans_id = je.trans_id
            r.letters.append(letter)
        session.add(r)
        session.commit()
        return r
    except Exception:
        session.rollback()
        raise


def save_term(session: Session, code: str, name: str, interest: Decimal, highest: bool, levels: list[dict],
              days_between: int = 7) -> DunningTerm:
    """Add or change a dunning term with its levels (days overdue strictly rising)."""
    code = code.strip().upper()
    if not code:
        raise B1Error("Enter a dunning term code")
    if not levels:
        raise B1Error("Enter at least one dunning level")
    days = [int(l["days"]) for l in levels]
    if days != sorted(days) or len(set(days)) != len(days) or days[0] < 0:
        raise B1Error("The days overdue of the levels must rise from level to level")
    t = session.get(DunningTerm, code) or DunningTerm(code=code)
    t.name, t.interest, t.highest, t.days_between = name, Decimal(interest or 0), "Y" if highest else "N", int(days_between or 0)
    session.merge(t)
    session.flush()
    for row in session.scalars(select(DunningLevel).where(DunningLevel.term_code == code)):
        session.delete(row)
    session.flush()
    for n, l in enumerate(levels, start=1):
        session.add(DunningLevel(term_code=code, level=n, days=int(l["days"]), fee=Decimal(l.get("fee") or 0),
                                 min_balance=Decimal(l.get("min_balance") or 0), letter_text=l.get("letter_text")))
    session.commit()
    return session.get(DunningTerm, code)
