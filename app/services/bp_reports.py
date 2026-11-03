"""Business partner and cash reports: aging (customers / vendors), account statement, cash flow.

Aging: every open partner line (BalDue) by days overdue on a date — not yet due, 1-30, 31-60, 61-90,
91-120, over 120 — netted per partner (credit notes and payments on account reduce what is owed).
Statement: opening balance, every partner line in the period with a running balance, closing
balance (= OCRD Balance at the end) and the open items. Cash flow (direct): opening and closing
balance of the cash and bank accounts (OACT Finanse Y), receipts and payments of the period by
origin (incoming / outgoing payments, deposits, journal entries, ...).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import Account, JournalLine
from app.models.partners import BusinessPartner
from app.services.admin import B1Error

ZERO = Decimal("0")
BUCKETS = ["current", "1-30", "31-60", "61-90", "91-120", "120+"]
ORIGINS = {"24": "Incoming payments", "46": "Outgoing payments", "25": "Deposits", "30": "Journal entries", "13": "A/R invoices",
           "14": "A/R credit memos", "18": "A/P invoices", "19": "A/P credit memos", "-3": "Period-end closing"}


def _bucket(days: int) -> str:
    return "current" if days <= 0 else "1-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 \
        else "91-120" if days <= 120 else "120+"


def aging(session: Session, on: date, card_type: str = "C") -> dict:
    if card_type not in {"C", "S"}:
        raise B1Error("Aging of customers (C) or vendors (S)")
    sign = 1 if card_type == "C" else -1  # customers owe debits, vendors are owed credits
    partners = {b.card_code: b for b in session.scalars(select(BusinessPartner).where(BusinessPartner.card_type == card_type))}
    rows: dict[str, dict] = {}
    for l in session.scalars(select(JournalLine).where(JournalLine.short_name.in_(list(partners)), JournalLine.short_name != JournalLine.account,
                                                       (JournalLine.bal_due_deb > 0) | (JournalLine.bal_due_cred > 0), JournalLine.ref_date <= on)
                             .order_by(JournalLine.due_date)):
        amount = sign * (l.bal_due_deb - l.bal_due_cred)
        key = _bucket((on - l.due_date).days)
        r = rows.setdefault(l.short_name, {"card_code": l.short_name, "card_name": partners[l.short_name].card_name,
                                           **{b: ZERO for b in BUCKETS}, "total": ZERO, "items": []})
        r[key] += amount
        r["total"] += amount
        r["items"].append({"trans_type": l.trans_type, "doc_entry": l.created_by, "base_ref": l.base_ref, "ref_date": l.ref_date,
                           "due_date": l.due_date, "days": (on - l.due_date).days, "bucket": key, "open": amount})
    out = sorted((r for r in rows.values() if r["total"] or r["items"]), key=lambda r: -r["total"])
    return {"on": on, "card_type": card_type, "buckets": BUCKETS, "partners": out,
            "totals": {b: sum((r[b] for r in out), ZERO) for b in BUCKETS + ["total"]}}


def statement(session: Session, card_code: str, date_from: date, date_to: date) -> dict:
    bp = session.get(BusinessPartner, card_code)
    if bp is None:
        raise B1Error(f"Business partner {card_code} does not exist")
    base = select(JournalLine).where(JournalLine.short_name == card_code, JournalLine.short_name != JournalLine.account)
    opening = session.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
        JournalLine.short_name == card_code, JournalLine.short_name != JournalLine.account, JournalLine.ref_date < date_from))
    balance = Decimal(opening)
    lines = []
    for l in session.scalars(base.where(JournalLine.ref_date >= date_from, JournalLine.ref_date <= date_to)
                             .order_by(JournalLine.ref_date, JournalLine.trans_id, JournalLine.line_id)):
        balance += l.debit - l.credit
        lines.append({"ref_date": l.ref_date, "due_date": l.due_date, "trans_type": l.trans_type, "origin": ORIGINS.get(l.trans_type, l.trans_type),
                      "doc_entry": l.created_by, "base_ref": l.base_ref, "memo": l.line_memo, "debit": l.debit, "credit": l.credit,
                      "balance": balance, "open": l.bal_due_deb - l.bal_due_cred, "trans_id": l.trans_id})
    open_items = [{"ref_date": l.ref_date, "due_date": l.due_date, "trans_type": l.trans_type, "base_ref": l.base_ref, "doc_entry": l.created_by,
                   "open": l.bal_due_deb - l.bal_due_cred, "days": (date_to - l.due_date).days}
                  for l in session.scalars(base.where((JournalLine.bal_due_deb > 0) | (JournalLine.bal_due_cred > 0), JournalLine.ref_date <= date_to)
                                           .order_by(JournalLine.due_date))]
    return {"card_code": bp.card_code, "card_name": bp.card_name, "card_type": bp.card_type, "address": bp.address, "city": bp.city,
            "date_from": date_from, "date_to": date_to, "opening": Decimal(opening), "lines": lines, "closing": balance,
            "debits": sum((l["debit"] for l in lines), ZERO), "credits": sum((l["credit"] for l in lines), ZERO), "open_items": open_items}


def cash_flow(session: Session, date_from: date, date_to: date) -> dict:
    cash = [a.acct_code for a in session.scalars(select(Account).where(Account.finanse == "Y", Account.postable == "Y"))]
    if not cash:
        raise B1Error("No cash / bank accounts (OACT Finanse)")
    opening = Decimal(session.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
        JournalLine.account.in_(cash), JournalLine.ref_date < date_from)))
    flows: dict[str, dict] = defaultdict(lambda: {"in": ZERO, "out": ZERO})
    per_acct: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for l in session.scalars(select(JournalLine).where(JournalLine.account.in_(cash), JournalLine.ref_date >= date_from, JournalLine.ref_date <= date_to)):
        origin = ORIGINS.get(l.trans_type, f"Type {l.trans_type}")
        flows[origin]["in"] += l.debit
        flows[origin]["out"] += l.credit
        per_acct[l.account] += l.debit - l.credit
    rows = [{"origin": k, "in": v["in"], "out": v["out"], "net": v["in"] - v["out"]} for k, v in sorted(flows.items())]
    total_in, total_out = sum((r["in"] for r in rows), ZERO), sum((r["out"] for r in rows), ZERO)
    names = {a.acct_code: a.acct_name for a in session.scalars(select(Account).where(Account.acct_code.in_(cash)))}
    return {"date_from": date_from, "date_to": date_to, "opening": opening, "flows": rows, "total_in": total_in, "total_out": total_out,
            "closing": opening + total_in - total_out,
            "accounts": [{"acct_code": a, "acct_name": names[a], "movement": per_acct.get(a, ZERO)} for a in sorted(cash)]}
