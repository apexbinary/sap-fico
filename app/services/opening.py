"""Opening balances (Administration -> Opening Balances), as in B1:

  G/L accounts       one journal entry (TransType -2): each account's debit / credit against the opening
                     balance account (OACP OpenBalAcct, 313000); control accounts take BP opening balances
  business partners  one journal entry (TransType -2): an open item per row on the partner's control account
                     (due date, reference) against the opening balance account; paid like any open item
  items              one goods receipt (59) whose lines are offset on the opening balance account; moving
                     average cost from the entered price; batches / serial numbers as on any receipt

When everything is entered, the opening balance account is 0 (assets = liabilities + capital). An opening
balance is canceled by reversing its journal entry / canceling its goods receipt (refused once used).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import Account, AccountDetermination, JournalEntry, JournalLine
from app.models.inventory import Item
from app.models.partners import BusinessPartner
from app.services import journal
from app.services.admin import B1Error

ZERO = Decimal("0")
OPENING = "-2"  # B1 TransType of opening balances
STOCK_REF = "OPENING"  # goods receipts of opening stock (Ref2)


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def _date(v) -> date:
    if not v:
        raise B1Error("Enter the posting date of the opening balances")
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _det(session: Session, on: date) -> AccountDetermination:
    det = session.get(AccountDetermination, str(on.year))
    if det is None or not det.opening_bal:
        raise B1Error(f"No opening balance account in the G/L account determination for {on.year}")
    return det


def _amounts(n: int, row: dict) -> tuple[Decimal, Decimal]:
    debit, credit = _money(row.get("debit")), _money(row.get("credit"))
    if debit < 0 or credit < 0 or (debit and credit) or not (debit or credit):
        raise B1Error(f"Row {n}: enter either a debit or a credit amount (positive)")
    return debit, credit


def post_accounts(session: Session, data: dict) -> JournalEntry:
    """G/L account opening balances: [{account, debit | credit}] against the opening balance account."""
    on = _date(data.get("ref_date"))
    det = _det(session, on)
    lines, seen = [], set()
    for n, r in enumerate(data.get("rows") or [], 1):
        acct = session.get(Account, (r.get("account") or "").strip())
        if acct is None or acct.postable != "Y":
            raise B1Error(f"Row {n}: choose an active account (not a title account)")
        if acct.loc_man_tran == "Y":
            raise B1Error(f"Row {n}: {acct.acct_code} is a control account: enter business partner opening balances instead")
        if acct.acct_code == det.opening_bal:
            raise B1Error(f"Row {n}: {acct.acct_code} is the opening balance account itself")
        if acct.acct_code in seen:
            raise B1Error(f"Row {n}: account {acct.acct_code} is entered twice")
        seen.add(acct.acct_code)
        debit, credit = _amounts(n, r)
        lines.append(journal.JournalLineRequest(account=acct.acct_code, debit=debit, credit=credit, line_memo="Opening balance"))
    if not lines:
        raise B1Error("Enter at least one account")
    diff = sum((l.debit - l.credit for l in lines), ZERO)
    if diff:
        lines.append(journal.JournalLineRequest(account=det.opening_bal, debit=-diff if diff < 0 else ZERO, credit=diff if diff > 0 else ZERO,
                                                line_memo="Opening balance offset"))
    return journal.post_entry(session, journal.JournalRequest(ref_date=on, tax_date=on, due_date=on, lines=lines, trans_type=OPENING,
                                                              memo=(data.get("memo") or "Opening balances G/L accounts")[:50],
                                                              ref3="OB:GL", manual=False))


def post_partners(session: Session, data: dict) -> JournalEntry:
    """Business partner opening balances: [{card_code, debit | credit, due_date, ref}] as open items."""
    on = _date(data.get("ref_date"))
    det = _det(session, on)
    lines = []
    for n, r in enumerate(data.get("rows") or [], 1):
        bp = session.get(BusinessPartner, (r.get("card_code") or "").strip())
        if bp is None:
            raise B1Error(f"Row {n}: choose a business partner")
        if bp.card_type == "L":
            raise B1Error(f"Row {n}: {bp.card_code} is a lead (no balance)")
        debit, credit = _amounts(n, r)
        due = _date(r.get("due_date")) if r.get("due_date") else on
        if due < on and (on - due).days > 3650:
            raise B1Error(f"Row {n}: the due date is too far in the past")
        lines.append(journal.JournalLineRequest(card_code=bp.card_code, debit=debit, credit=credit, due_date=due,
                                                ref1=(r.get("ref") or None), line_memo=(r.get("ref") or "Opening balance")[:50]))
    if not lines:
        raise B1Error("Enter at least one business partner")
    diff = sum((l.debit - l.credit for l in lines), ZERO)
    if diff:
        lines.append(journal.JournalLineRequest(account=det.opening_bal, debit=-diff if diff < 0 else ZERO, credit=diff if diff > 0 else ZERO,
                                                line_memo="Opening balance offset"))
    return journal.post_entry(session, journal.JournalRequest(ref_date=on, tax_date=on, due_date=on, lines=lines, trans_type=OPENING,
                                                              memo=(data.get("memo") or "Opening balances business partners")[:50],
                                                              ref3="OB:BP", manual=False))


def post_stock(session: Session, data: dict):
    """Opening stock: [{item_code, whs_code, quantity, price, batches | serials}] as one goods receipt against
    the opening balance account."""
    from app.services import documents

    on = _date(data.get("ref_date"))
    det = _det(session, on)
    lines = []
    for n, r in enumerate(data.get("rows") or [], 1):
        item = session.get(Item, (r.get("item_code") or "").strip())
        if item is None or item.invnt_item != "Y":
            raise B1Error(f"Row {n}: choose an inventory item")
        qty, price = _money(r.get("quantity")), _money(r.get("price"))
        if qty <= 0 or price < 0:
            raise B1Error(f"Row {n}: enter a positive quantity and a price (cost per unit, not negative)")
        lines.append(documents.DocLineRequest(item_code=item.item_code, quantity=qty, price=price, whs_code=r.get("whs_code") or None,
                                              acct_code=det.opening_bal, batches=r.get("batches") or None, serials=r.get("serials") or None))
    if not lines:
        raise B1Error("Enter at least one item")
    return documents.create_document(session, documents.DocumentRequest(obj="59", doc_date=on, ref2=STOCK_REF, lines=lines,
                                                                         comments=data.get("memo") or "Opening stock",
                                                                         jrnl_memo="Opening balances items"))


def listing(session: Session) -> dict:
    from app.models.documents import DOCUMENT_CLASSES

    entries = []
    for je in session.scalars(select(JournalEntry).where(JournalEntry.trans_type == OPENING).order_by(JournalEntry.trans_id.desc())):
        if je.storno_to_tr and je.storno_to_tr < je.trans_id:
            continue  # the reversal of a canceled opening balance
        lines = session.scalars(select(JournalLine).where(JournalLine.trans_id == je.trans_id)).all()
        entries.append({"kind": "partners" if je.ref3 == "OB:BP" else "accounts", "trans_id": je.trans_id, "number": je.number,
                        "ref_date": je.ref_date, "memo": je.memo, "canceled": bool(je.storno_to_tr), "rows": len(lines) - 1,
                        "total": sum((l.debit for l in lines), ZERO)})
    hcls = DOCUMENT_CLASSES["59"][0]
    for d in session.scalars(select(hcls).where(hcls.ref2 == STOCK_REF).order_by(hcls.doc_entry.desc())):
        entries.append({"kind": "items", "doc_entry": d.doc_entry, "number": d.doc_num, "ref_date": d.doc_date, "memo": d.comments,
                        "canceled": d.canceled == "Y", "rows": len(d.lines), "total": d.doc_total, "trans_id": d.trans_id})
    det = session.scalars(select(AccountDetermination).order_by(AccountDetermination.period_cat.desc())).first()
    acct = session.get(Account, det.opening_bal) if det is not None else None
    balance = session.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
        JournalLine.account == acct.acct_code)) if acct else ZERO
    return {"entries": sorted(entries, key=lambda e: (str(e["ref_date"]), e["number"]), reverse=True),
            "opening_account": acct.acct_code if acct else None, "opening_account_name": acct.acct_name if acct else None,
            "difference": Decimal(balance)}


def cancel(session: Session, kind: str, key: int):
    from app.services import documents

    if kind == "items":
        return documents.cancel_document(session, "59", key)
    je = session.get(JournalEntry, key)
    if je is None or je.trans_type != OPENING:
        raise B1Error(f"Journal entry {key} is no opening balance")
    return journal.reverse_entry(session, key, ref_date=je.ref_date)
