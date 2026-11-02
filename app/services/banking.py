"""Incoming / outgoing payments and deposits.

A payment (ORCT 24 / OVPM 46) has payment means (cash, bank transfer with bank
charges, checks) in the payment currency and pays open items in local currency:
any open partner line of the business partner (invoices, credit memos, journal
entries, payments on account). Postings, incoming (outgoing is the mirror image):

    Dr cash / bank (transfer - bank charges) / checks received, Dr bank charges
    Cr business partner (control account)      -- or Cr G/L accounts (DocType A)
    (+/- exchange differences when foreign-currency means do not match the items)

Applied amounts reduce the items' open amounts (JDT1 BalDueDeb / BalDueCred) and the
PaidToDate of their documents; what is not applied stays open on the payment's own
partner line (payment on account, OpenBal). A payment with items but no means
reconciles the items against each other (e.g. an invoice with a payment on account).
Incoming checks go to the checks register (OCHH) and are deposited to the bank (ODPS).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.banking import PAYMENT_CLASSES, CheckForReceipt, Deposit
from app.models.documents import DOCUMENT_CLASSES
from app.models.finance import Account, AccountDetermination, JournalLine
from app.models.partners import BusinessPartner
from app.services import journal
from app.services.admin import (B1Error, check_project, company, default_series, exchange_rate, next_number,
                                posting_period)
from app.services.journal import JournalLineRequest, JournalRequest, money

ZERO = Decimal("0")
NAMES = {"24": "Incoming Payment", "46": "Outgoing Payment"}
INVOICE_TYPES = {"13", "14", "18", "19"}  # documents with PaidToDate
FX_TOLERANCE = Decimal("0.005")  # foreign-currency means may differ from the items by 0.5 % (exchange difference)


@dataclass
class CheckRequest:
    check_num: int
    check_sum: Decimal  # payment currency
    due_date: date | None = None
    bank_code: str | None = None
    branch: str | None = None
    acct_num: str | None = None
    country_cod: str | None = None
    trnsfrable: bool = False


@dataclass
class PaidItem:
    trans_id: int  # journal entry of the open item
    line_id: int  # its partner line
    sum_applied: Decimal  # LC, positive: the amount of the item's open amount that is paid


@dataclass
class AccountLine:
    acct_code: str
    sum_applied: Decimal  # payment currency
    descrip: str | None = None
    prj_code: str | None = None


@dataclass
class PaymentRequest:
    obj: str  # 24 incoming, 46 outgoing
    doc_date: date
    doc_type: str = "C"  # C customer, S vendor, A account
    card_code: str | None = None
    doc_due_date: date | None = None
    tax_date: date | None = None
    doc_curr: str | None = None  # payment currency (default: local currency)
    cash_acct: str | None = None
    cash_sum: Decimal = ZERO
    trsfr_acct: str | None = None
    trsfr_sum: Decimal = ZERO
    trsfr_date: date | None = None
    trsfr_ref: str | None = None
    bank_chrg: Decimal = ZERO  # LC
    check_acct: str | None = None
    checks: list[CheckRequest] = field(default_factory=list)
    items: list[PaidItem] = field(default_factory=list)
    accounts: list[AccountLine] = field(default_factory=list)
    pay_no_doc: bool = False  # payment on account
    cntct_code: int | None = None
    counter_ref: str | None = None
    ref2: str | None = None
    prj_code: str | None = None
    comments: str | None = None
    jrnl_memo: str | None = None


def _determination(session: Session, on: date) -> AccountDetermination:
    det = session.get(AccountDetermination, str(on.year))
    if det is None:
        raise B1Error(f"No G/L account determination for {on.year}")
    return det


def _gl(session: Session, code: str | None, what: str) -> Account:
    acct = session.get(Account, code) if code else None
    if acct is None or acct.postable != "Y" or acct.frozen == "Y" or acct.loc_man_tran == "Y":
        raise B1Error(f"Enter an active {what} G/L account (not a control account)")
    return acct


def get_payment(session: Session, obj: str, doc_entry: int):
    if obj not in PAYMENT_CLASSES:
        raise B1Error(f"Unknown payment type {obj}")
    pay = session.get(PAYMENT_CLASSES[obj][0], doc_entry)
    if pay is None:
        raise B1Error(f"{NAMES[obj]} {doc_entry} does not exist")
    return pay


# ------------------------------------------------------------- open items
def open_items(session: Session, card_code: str) -> list[dict]:
    """Open partner lines of a business partner (what a payment can pay), oldest due first."""
    lines = session.scalars(select(JournalLine).where(
        JournalLine.short_name == card_code,
        (JournalLine.bal_due_deb != 0) | (JournalLine.bal_due_cred != 0)).order_by(JournalLine.due_date, JournalLine.trans_id)).all()
    out = []
    for l in lines:
        doc_total = paid = None
        if l.trans_type in INVOICE_TYPES and l.created_by:
            doc = session.get(DOCUMENT_CLASSES[l.trans_type][0], l.created_by)
            doc_total, paid = doc.doc_total, doc.paid_to_date
        out.append({"trans_id": l.trans_id, "line_id": l.line_id, "inv_type": l.trans_type,
                    "doc_entry": l.created_by or l.trans_id, "doc_num": l.base_ref or str(l.trans_id),
                    "ref_date": l.ref_date, "due_date": l.due_date, "memo": l.line_memo,
                    "side": "D" if l.bal_due_deb else "C", "amount": l.debit or l.credit,
                    "open": l.bal_due_deb or l.bal_due_cred, "doc_total": doc_total, "paid_to_date": paid,
                    "overdue_days": None})
    return out


def _apply_to_item(session: Session, line: JournalLine, amount: Decimal) -> None:
    """Reduce (amount > 0) or restore (amount < 0) the open amount of an item and of its document."""
    if line.bal_due_deb or (line.debit and not line.bal_due_cred and amount < 0):
        line.bal_due_deb -= amount
    else:
        line.bal_due_cred -= amount
    if line.trans_type in INVOICE_TYPES and line.created_by:
        doc = session.get(DOCUMENT_CLASSES[line.trans_type][0], line.created_by)
        doc.paid_to_date += amount
        if doc.canceled == "N":
            doc.doc_status = "C" if doc.paid_to_date >= doc.doc_total else "O"
    elif line.trans_type in PAYMENT_CLASSES and line.created_by:
        pay = session.get(PAYMENT_CLASSES[line.trans_type][0], line.created_by)
        pay.open_bal -= amount


# ------------------------------------------------------------- add a payment
def create_payment(session: Session, req: PaymentRequest, *, commit: bool = True):
    try:
        pay = _create(session, req)
        if commit:
            session.commit()
        else:
            session.flush()
        return pay
    except Exception:
        session.rollback()
        raise


def _create(session: Session, req: PaymentRequest):
    if req.obj not in PAYMENT_CLASSES:
        raise B1Error(f"Unknown payment type {req.obj}")
    header_cls, check_cls, inv_cls, acct_cls = PAYMENT_CLASSES[req.obj]
    incoming = req.obj == "24"
    posting_period(session, req.doc_date, req.doc_due_date, req.tax_date)
    det = _determination(session, req.doc_date)
    main = company(session).main_curncy
    curr = (req.doc_curr or main).upper()
    rate = exchange_rate(session, curr, req.doc_date)
    lc = lambda fc: money(Decimal(fc) * rate)  # noqa: E731
    check_project(session, req.prj_code, req.doc_date)

    if req.doc_type not in {"C", "S", "A"}:
        raise B1Error("Payment type must be C (customer), S (vendor) or A (account)")
    bp = None
    if req.doc_type == "A":
        if req.items or req.card_code:
            raise B1Error("An account payment has G/L account lines, no business partner")
        if not req.accounts:
            raise B1Error("Enter at least one G/L account line")
    else:
        if req.accounts:
            raise B1Error("G/L account lines belong to account payments (type A)")
        bp = session.get(BusinessPartner, req.card_code) if req.card_code else None
        if bp is None:
            raise B1Error("Enter a business partner")
        if bp.card_type != req.doc_type:
            raise B1Error(f"{bp.card_code} is not a {'customer' if req.doc_type == 'C' else 'vendor'}")
        if bp.frozen_for == "Y":
            raise B1Error(f"Business partner {bp.card_code} is inactive")
        if bp.currency not in ("##", main, curr):
            raise B1Error(f"{bp.card_code} is paid in {bp.currency} or {main}")
        if req.cntct_code is not None:
            from app.models.partners import ContactPerson

            cp = session.get(ContactPerson, req.cntct_code)
            if cp is None or cp.card_code != bp.card_code:
                raise B1Error(f"Contact person {req.cntct_code} does not belong to {bp.card_code}")

    # payment means (payment currency -> local currency)
    for label, amount in (("cash", req.cash_sum), ("transfer", req.trsfr_sum), ("bank charges", req.bank_chrg)):
        if Decimal(amount) < 0:
            raise B1Error(f"The {label} amount cannot be negative")
    cash_fc, trsfr_fc = money(req.cash_sum), money(req.trsfr_sum)
    cash_lc, trsfr_lc, chrg = lc(cash_fc), lc(trsfr_fc), money(req.bank_chrg)
    if cash_fc:
        _gl(session, req.cash_acct, "cash")
    if trsfr_fc:
        _gl(session, req.trsfr_acct, "bank transfer")
    if chrg and (not trsfr_fc or chrg >= trsfr_lc):
        raise B1Error("Bank charges belong to a bank transfer and must be lower than it")
    check_acct = req.check_acct or (det.checks_received if incoming else None)
    checks_fc = ZERO
    for n, c in enumerate(req.checks):
        if Decimal(c.check_sum) <= 0 or int(c.check_num) <= 0:
            raise B1Error(f"Check {n + 1}: enter a check number and a positive amount")
        checks_fc += money(c.check_sum)
    if req.checks:
        _gl(session, check_acct, "checks received" if incoming else "check (bank)")
    checks_lc = lc(checks_fc)
    means_lc = cash_lc + trsfr_lc + checks_lc

    # paid items (LC) -> signed applied amounts: positive increases the payment
    applied, items, seen = ZERO, [], set()
    for it in req.items:
        line = session.get(JournalLine, (it.trans_id, it.line_id))
        if line is None or line.short_name != bp.card_code or line.short_name == line.account:
            raise B1Error(f"Item {it.trans_id}/{it.line_id} is not an open item of {bp.card_code}")
        if (it.trans_id, it.line_id) in seen:
            raise B1Error(f"Item {it.trans_id}/{it.line_id} is selected twice")
        seen.add((it.trans_id, it.line_id))
        amount = money(it.sum_applied)
        open_amt = line.bal_due_deb or line.bal_due_cred
        if amount <= 0 or amount > open_amt:
            raise B1Error(f"Item {line.base_ref or line.trans_id}: the amount to pay must be between 0 and the open "
                          f"amount {open_amt.normalize()}")
        debit_item = bool(line.bal_due_deb)
        sign = 1 if debit_item == incoming else -1
        applied += sign * amount
        items.append((line, amount, sign * amount))

    accounts = []
    for n, a in enumerate(req.accounts):
        _gl(session, a.acct_code, "")
        if Decimal(a.sum_applied) <= 0:
            raise B1Error(f"Account line {n + 1}: enter a positive amount")
        check_project(session, a.prj_code, req.doc_date)
        accounts.append((a, money(a.sum_applied), lc(money(a.sum_applied))))

    # what the partner (or the accounts) are posted with, payment on account, exchange difference
    exch = ZERO
    if req.doc_type == "A":
        target = sum((x[2] for x in accounts), ZERO)
        if curr == main and target != means_lc:
            raise B1Error(f"The payment means ({means_lc}) differ from the account lines ({target})")
        exch = means_lc - target
        on_account = ZERO
    else:
        target = means_lc
        on_account = means_lc - applied
        if not items and means_lc > 0:
            on_account, req.pay_no_doc = means_lc, True  # nothing selected: the whole payment is on account
        if on_account < 0 or (on_account > 0 and not req.pay_no_doc):
            if curr != main and items and abs(on_account) <= abs(applied) * FX_TOLERANCE:
                exch, target, on_account = on_account, applied, ZERO
            elif on_account < 0:
                raise B1Error(f"The payment means ({means_lc}) are lower than the amount to pay ({applied})")
            else:
                raise B1Error(f"The payment means exceed the amount to pay by {on_account}; select payment on account")
        if means_lc == 0 and applied != 0:
            raise B1Error(f"The selected items do not balance (difference {applied}); add payment means")
        if means_lc == 0 and not items:
            raise B1Error("Enter payment means or select items to reconcile")
    if req.doc_type == "A" and abs(exch) > target * FX_TOLERANCE:
        raise B1Error(f"The payment means ({means_lc}) differ from the account lines ({target})")

    entry = (session.scalar(select(func.max(header_cls.doc_entry))) or 0) + 1
    name = NAMES[req.obj]
    pay = header_cls(
        doc_entry=entry, doc_num=next_number(session, req.obj), doc_type=req.doc_type, canceled="N", obj_type=req.obj,
        series=default_series(session, req.obj), doc_date=req.doc_date, doc_due_date=req.doc_due_date or req.doc_date,
        tax_date=req.tax_date or req.doc_date, card_code=bp.card_code if bp else None,
        card_name=bp.card_name if bp else None, cntct_code=req.cntct_code,
        address=", ".join(filter(None, [bp.address, bp.zip_code, bp.city])) if bp else None,
        doc_curr=curr, doc_rate=rate, cash_acct=req.cash_acct if cash_fc else None, cash_sum=cash_lc, cash_sum_fc=cash_fc if curr != main else ZERO,
        trsfr_acct=req.trsfr_acct if trsfr_fc else None, trsfr_sum=trsfr_lc, trsfr_sum_fc=trsfr_fc if curr != main else ZERO,
        trsfr_date=(req.trsfr_date or req.doc_date) if trsfr_fc else None, trsfr_ref=req.trsfr_ref, bank_chrg=chrg,
        check_acct=check_acct if req.checks else None, check_sum=checks_lc, check_sum_fc=checks_fc if curr != main else ZERO,
        doc_total=means_lc, doc_total_fc=(cash_fc + trsfr_fc + checks_fc) if curr != main else ZERO,
        pay_no_doc="Y" if on_account else "N", no_doc_sum=on_account, open_bal=on_account,
        counter_ref=req.counter_ref, ref2=req.ref2, prj_code=req.prj_code, comments=req.comments,
        jrnl_memo=(req.jrnl_memo or (f"{name} - {bp.card_code}" if bp else name))[:50],
    )
    for n, c in enumerate(req.checks):
        pay.checks.append(check_cls(line_id=n, due_date=c.due_date or req.doc_date, check_num=int(c.check_num),
                                    bank_code=c.bank_code, branch=c.branch, acct_num=c.acct_num,
                                    country_cod=c.country_cod, check_sum=money(c.check_sum),
                                    trnsfrable="Y" if c.trnsfrable else "N", check_act=check_acct))
    for n, (line, amount, signed) in enumerate(items):
        pay.invoices.append(inv_cls(invoice_id=n, doc_entry=line.created_by or line.trans_id, inv_type=line.trans_type,
                                    doc_trans_id=line.trans_id, doc_line=line.line_id, sum_applied=signed,
                                    applied_fc=money(signed / rate) if curr != main else ZERO))
    for n, (a, fc, amount_lc) in enumerate(accounts):
        pay.accounts.append(acct_cls(line_id=n, acct_code=a.acct_code, sum_applied=amount_lc,
                                     applied_fc=fc if curr != main else ZERO, descrip=a.descrip, prj_code=a.prj_code))
    session.add(pay)
    session.flush()

    # journal entry
    sign = 1 if incoming else -1  # incoming: means debit, partner credit
    fc = curr != main
    lines: list[JournalLineRequest] = []

    def add(account=None, card=None, amount=ZERO, amount_fc=ZERO, memo=None, due=None, project=None):
        amount = sign * amount
        if not amount:
            return
        debit, credit = (amount, ZERO) if amount > 0 else (ZERO, -amount)
        fcd, fcc = ((abs(amount_fc), ZERO) if amount > 0 else (ZERO, abs(amount_fc))) if fc and amount_fc else (ZERO, ZERO)
        lines.append(JournalLineRequest(account=account, card_code=card, debit=debit, credit=credit, fc_debit=fcd,
                                        fc_credit=fcc, fc_currency=curr if fc and amount_fc else None, line_memo=memo,
                                        due_date=due, project=project))

    add(req.cash_acct, amount=cash_lc, amount_fc=cash_fc, memo="Cash")
    add(req.trsfr_acct, amount=trsfr_lc - sign * chrg if incoming else trsfr_lc + chrg, amount_fc=trsfr_fc, memo=req.trsfr_ref or "Bank transfer")
    if chrg:
        add(det.bank_charges, amount=sign * chrg, memo="Bank charges")
    add(check_acct, amount=checks_lc, amount_fc=checks_fc, memo="Checks")
    if bp:
        add(card=bp.card_code, amount=-target, due=pay.doc_due_date)
    for a, a_fc, amount_lc in accounts:
        add(a.acct_code, amount=-amount_lc, amount_fc=a_fc, memo=a.descrip, project=a.prj_code)
    if exch:
        gain = exch > 0 if incoming else exch < 0
        add(det.exch_gain if gain else det.exch_loss, amount=-exch, memo="Exchange rate difference")
    if lines:
        je = journal.post_entry(session, JournalRequest(
            ref_date=req.doc_date, due_date=pay.doc_due_date, tax_date=pay.tax_date, memo=pay.jrnl_memo,
            ref1=str(pay.doc_num), ref2=req.counter_ref or req.ref2, trans_type=req.obj, base_ref=str(pay.doc_num),
            created_by=pay.doc_entry, project=req.prj_code, manual=False, trans_curr=curr if fc else None, lines=lines),
            commit=False)
        pay.trans_id = je.trans_id
        own = _own_line(session, pay)
        if own is not None:  # only the amount on account stays open on the payment
            own.bal_due_deb = own.bal_due_cred = ZERO
            if incoming:
                own.bal_due_cred = on_account
            else:
                own.bal_due_deb = on_account

    for line, amount, _signed in items:
        _apply_to_item(session, line, amount)

    if incoming:  # checks received wait in the checks register until they are deposited
        key = session.scalar(select(func.max(CheckForReceipt.check_key))) or 0
        for c in pay.checks:
            key += 1
            c.check_abs = key
            session.add(CheckForReceipt(check_key=key, check_num=c.check_num, bank_code=c.bank_code, branch=c.branch,
                                        acct_num=c.acct_num, check_date=c.due_date, check_sum=lc(c.check_sum),
                                        currency=curr, check_act=check_acct, card_code=pay.card_code,
                                        rcpt_num=pay.doc_entry, deposited="N", canceled="N"))
    session.flush()
    return pay


def _own_line(session: Session, pay) -> JournalLine | None:
    if not pay.trans_id or not pay.card_code:
        return None
    return session.scalars(select(JournalLine).where(JournalLine.trans_id == pay.trans_id,
                                                     JournalLine.short_name == pay.card_code)).first()


# ------------------------------------------------------------- cancel a payment
def cancel_payment(session: Session, obj: str, doc_entry: int, cancel_date: date | None = None):
    try:
        pay = get_payment(session, obj, doc_entry)
        if pay.canceled == "Y":
            raise B1Error(f"{NAMES[obj]} {pay.doc_num} is already canceled")
        if pay.open_bal != pay.no_doc_sum:
            raise B1Error(f"The amount on account of {NAMES[obj]} {pay.doc_num} was used by another payment; "
                          f"cancel that payment first")
        if obj == "24":
            checks = session.scalars(select(CheckForReceipt).where(CheckForReceipt.rcpt_num == pay.doc_entry)).all()
            if any(c.deposited != "N" for c in checks):
                raise B1Error(f"A check of {NAMES[obj]} {pay.doc_num} is deposited; cancel the deposit first")
            for c in checks:
                c.canceled = "Y"
        for inv in pay.invoices:  # reopen the paid items
            line = session.get(JournalLine, (inv.doc_trans_id, inv.doc_line))
            _apply_to_item(session, line, -abs(inv.sum_applied))
        if pay.trans_id:
            own = _own_line(session, pay)
            if own is not None:
                own.bal_due_deb, own.bal_due_cred = own.debit, own.credit
            journal.reverse_entry(session, pay.trans_id, ref_date=cancel_date or pay.doc_date, commit=False)
        pay.canceled, pay.open_bal = "Y", ZERO
        session.commit()
        return pay
    except Exception:
        session.rollback()
        raise


# ------------------------------------------------------------- deposits
def _post_deposit(session: Session, dep: Deposit, credit_lines: list[tuple[str, Decimal]]) -> None:
    lines = [JournalLineRequest(account=dep.banck_acct, debit=dep.loc_total, line_memo="Deposit")]
    lines += [JournalLineRequest(account=acct, credit=amount, line_memo="Deposit") for acct, amount in credit_lines]
    je = journal.post_entry(session, JournalRequest(
        ref_date=dep.depos_date, memo=(dep.memo or f"Deposit {dep.depos_num}")[:50], ref1=str(dep.depos_num),
        trans_type="25", base_ref=str(dep.depos_num), created_by=dep.depos_id, project=dep.project, manual=False,
        lines=lines), commit=False)
    dep.trans_abs = je.trans_id


def _new_deposit(session: Session, kind: str, on: date, bank_acct: str, memo: str | None, project: str | None,
                 bank_acc_num: str | None) -> Deposit:
    posting_period(session, on)
    _gl(session, bank_acct, "bank")
    check_project(session, project, on)
    dep_id = (session.scalar(select(func.max(Deposit.depos_id))) or 0) + 1
    return Deposit(depos_id=dep_id, depos_num=next_number(session, "25"), depos_type=kind, depos_date=on,
                   depos_curr=company(session).main_curncy, banck_acct=bank_acct, loc_total=ZERO, memo=memo,
                   project=project, bank_acc_num=bank_acc_num, canceled="N")


def deposit_checks(session: Session, on: date, bank_acct: str, check_keys: list[int], memo: str | None = None,
                   project: str | None = None, bank_acc_num: str | None = None) -> Deposit:
    try:
        if not check_keys:
            raise B1Error("Select the checks to deposit")
        dep = _new_deposit(session, "K", on, bank_acct, memo, project, bank_acc_num)
        by_account: dict[str, Decimal] = {}
        for key in dict.fromkeys(check_keys):
            chk = session.get(CheckForReceipt, key)
            if chk is None or chk.deposited != "N" or chk.canceled == "Y":
                raise B1Error(f"Check {key} is not available for deposit")
            chk.deposited, chk.dpst_abs = "C", dep.depos_id
            by_account[chk.check_act] = by_account.get(chk.check_act, ZERO) + chk.check_sum
            dep.loc_total += chk.check_sum
        session.add(dep)
        session.flush()
        _post_deposit(session, dep, list(by_account.items()))
        session.commit()
        return dep
    except Exception:
        session.rollback()
        raise


def deposit_cash(session: Session, on: date, bank_acct: str, cash_acct: str, amount: Decimal, memo: str | None = None,
                 project: str | None = None, bank_acc_num: str | None = None) -> Deposit:
    try:
        if money(amount) <= 0:
            raise B1Error("Enter a positive amount to deposit")
        _gl(session, cash_acct, "cash")
        if session.get(Account, cash_acct).finanse != "Y":
            raise B1Error(f"G/L account {cash_acct} is not a cash account")
        dep = _new_deposit(session, "C", on, bank_acct, memo, project, bank_acc_num)
        dep.alloc_acct, dep.loc_total = cash_acct, money(amount)
        session.add(dep)
        session.flush()
        _post_deposit(session, dep, [(cash_acct, dep.loc_total)])
        session.commit()
        return dep
    except Exception:
        session.rollback()
        raise


def cancel_deposit(session: Session, depos_id: int, cancel_date: date | None = None) -> Deposit:
    try:
        dep = session.get(Deposit, depos_id)
        if dep is None:
            raise B1Error(f"Deposit {depos_id} does not exist")
        if dep.canceled == "Y":
            raise B1Error(f"Deposit {dep.depos_num} is already canceled")
        journal.reverse_entry(session, dep.trans_abs, ref_date=cancel_date or dep.depos_date, commit=False)
        for chk in session.scalars(select(CheckForReceipt).where(CheckForReceipt.dpst_abs == dep.depos_id)):
            chk.deposited, chk.dpst_abs = "N", None
        dep.canceled = "Y"
        session.commit()
        return dep
    except Exception:
        session.rollback()
        raise
