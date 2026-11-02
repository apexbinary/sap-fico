"""Journal entries (OJDT / JDT1) — the single posting engine of the system.

Manual journal entries (object type 30) and the automatic entries of sales,
purchasing, inventory and banking documents all go through ``post_entry``:

  * every line names a G/L account or a business partner; a partner line posts
    to the partner's control account (Account) and keeps the partner code in
    ShortName, with its full amount open (BalDueDeb / BalDueCred);
  * only active (postable), unfrozen accounts can be posted; manual entries may
    not post a control account directly (use the business partner instead);
  * the entry must balance in local currency and fall into an unlocked
    posting period;
  * account balances (OACT-CurrTotal) and partner balances (OCRD-Balance) are
    updated with the entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import Account, JournalEntry, JournalLine
from app.services.admin import B1Error, next_number, posting_period

ZERO = Decimal("0")
CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, ROUND_HALF_UP)


@dataclass
class JournalLineRequest:
    """One line: a G/L account or a business partner, debit or credit in local currency."""

    account: str | None = None  # G/L account (active account)
    card_code: str | None = None  # Business partner (posts to its control account)
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    fc_debit: Decimal = ZERO
    fc_credit: Decimal = ZERO
    fc_currency: str | None = None
    line_memo: str | None = None
    vat_group: str | None = None
    control_account: str | None = None  # Explicit control account for a partner line (else the partner's)
    due_date: date | None = None


@dataclass
class JournalRequest:
    ref_date: date  # Posting date
    lines: list[JournalLineRequest]
    tax_date: date | None = None  # Document date
    due_date: date | None = None
    memo: str | None = None
    ref1: str | None = None
    ref2: str | None = None
    trans_type: str = "30"  # 30 = manual journal entry
    base_ref: str | None = None  # Source document number
    created_by: int | None = None  # Source DocEntry
    trans_curr: str | None = None
    user_sign: str = "manager"
    manual: bool = True  # manual entries may not post control accounts directly
    extra: dict = field(default_factory=dict)


def _account(session: Session, code: str) -> Account:
    acct = session.get(Account, code)
    if acct is None:
        raise B1Error(f"G/L account {code} does not exist")
    if acct.postable != "Y":
        raise B1Error(f"G/L account {code} {acct.acct_name} is a title account and cannot be posted")
    if acct.frozen == "Y":
        raise B1Error(f"G/L account {code} {acct.acct_name} is inactive")
    return acct


def _partner(session: Session, card_code: str):
    from app.models.partners import BusinessPartner  # available from phase 2 on

    bp = session.get(BusinessPartner, card_code)
    if bp is None:
        raise B1Error(f"Business partner {card_code} does not exist")
    if bp.frozen_for == "Y":
        raise B1Error(f"Business partner {card_code} is inactive")
    return bp


def post_entry(session: Session, req: JournalRequest, *, commit: bool = True) -> JournalEntry:
    """Validate and post a journal entry; returns the OJDT header."""
    try:
        entry = _post(session, req)
        if commit:
            session.commit()
        else:
            session.flush()
        return entry
    except Exception:
        session.rollback()
        raise


def _post(session: Session, req: JournalRequest) -> JournalEntry:
    lines = [l for l in req.lines if money(l.debit) or money(l.credit) or l.fc_debit or l.fc_credit]
    if len(lines) < 2:
        raise B1Error("A journal entry needs at least two lines with amounts")
    for l in lines:
        if bool(l.account) == bool(l.card_code):
            raise B1Error("Each line needs either a G/L account or a business partner")
        if l.debit < 0 or l.credit < 0 or (money(l.debit) and money(l.credit)):
            raise B1Error("A line is either a debit or a credit, and not negative")
    debit = sum((money(l.debit) for l in lines), ZERO)
    credit = sum((money(l.credit) for l in lines), ZERO)
    if debit != credit:
        raise B1Error(f"The journal entry is not balanced: debit {debit}, credit {credit}")
    posting_period(session, req.ref_date)

    trans_id = (session.scalar(select(func.max(JournalEntry.trans_id))) or 0) + 1
    entry = JournalEntry(
        trans_id=trans_id, number=next_number(session, "30"), ref_date=req.ref_date,
        due_date=req.due_date or req.ref_date, tax_date=req.tax_date or req.ref_date, memo=req.memo,
        ref1=req.ref1, ref2=req.ref2, trans_type=req.trans_type, base_ref=req.base_ref,
        created_by=req.created_by, loc_total=debit, trans_curr=req.trans_curr, user_sign=req.user_sign,
        fc_total=sum((l.fc_debit for l in lines), ZERO),
    )
    session.add(entry)
    # contra account of a line: the first line on the other side
    first_debit = next(l.card_code or l.account for l in lines if money(l.debit))
    first_credit = next(l.card_code or l.account for l in lines if money(l.credit))

    for n, l in enumerate(lines):
        amount_d, amount_c = money(l.debit), money(l.credit)
        if l.card_code:
            bp = _partner(session, l.card_code)
            control = l.control_account or bp.deb_pay_acct
            acct = _account(session, control)
            bp.balance = (bp.balance or ZERO) + amount_d - amount_c
            short_name = bp.card_code
        else:
            acct = _account(session, l.account)
            if req.manual and acct.loc_man_tran == "Y":
                raise B1Error(f"G/L account {acct.acct_code} is a control account; post the business partner instead")
            short_name = acct.acct_code
        acct.curr_total = (acct.curr_total or ZERO) + amount_d - amount_c
        entry.lines.append(JournalLine(
            line_id=n, account=acct.acct_code, short_name=short_name,
            contra_act=first_credit if amount_d else first_debit, debit=amount_d, credit=amount_c,
            fc_debit=money(l.fc_debit), fc_credit=money(l.fc_credit), fc_currency=l.fc_currency,
            bal_due_deb=amount_d if l.card_code else ZERO, bal_due_cred=amount_c if l.card_code else ZERO,
            line_memo=(l.line_memo or req.memo), ref_date=req.ref_date, due_date=l.due_date or req.due_date or req.ref_date,
            trans_type=req.trans_type, created_by=req.created_by, base_ref=req.base_ref, vat_group=l.vat_group,
        ))
    session.flush()
    return entry


def reverse_entry(session: Session, trans_id: int, *, ref_date: date | None = None, commit: bool = True) -> JournalEntry:
    """Reverse a journal entry: opposite lines, linked through StornoToTr; open partner amounts close."""
    orig = session.get(JournalEntry, trans_id)
    if orig is None:
        raise B1Error(f"Journal entry {trans_id} does not exist")
    if orig.storno_to_tr:
        raise B1Error(f"Journal entry {orig.number} is already reversed or is a reversal")
    for line in orig.lines:
        if line.short_name != line.account and (line.bal_due_deb != line.debit or line.bal_due_cred != line.credit):
            raise B1Error(f"Journal entry {orig.number} is partly paid or reconciled and cannot be reversed")
    req = JournalRequest(
        ref_date=ref_date or orig.ref_date, memo=f"Reversal of JE {orig.number}"[:50], trans_type=orig.trans_type,
        ref1=orig.ref1, base_ref=orig.base_ref, created_by=orig.created_by, manual=False,
        lines=[JournalLineRequest(
            account=None if l.short_name != l.account else l.account,
            card_code=l.short_name if l.short_name != l.account else None,
            control_account=l.account if l.short_name != l.account else None,
            debit=l.credit, credit=l.debit, fc_debit=l.fc_credit, fc_credit=l.fc_debit, fc_currency=l.fc_currency,
            line_memo=l.line_memo, vat_group=l.vat_group,
        ) for l in orig.lines],
    )
    try:
        rev = _post(session, req)
        rev.storno_to_tr, rev.auto_storno = orig.trans_id, "Y"
        orig.storno_to_tr = rev.trans_id
        for o, r in zip(orig.lines, rev.lines):  # the reversal settles the open partner amounts
            if o.short_name != o.account:
                o.bal_due_deb = o.bal_due_cred = r.bal_due_deb = r.bal_due_cred = ZERO
        if commit:
            session.commit()
        return rev
    except Exception:
        session.rollback()
        raise
