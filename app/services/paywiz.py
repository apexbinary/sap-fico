"""Payment wizard: batch payment of due vendor items (or collection from customers).

A run (OPWZ) recommends the open partner lines due up to a date: vendors' open credits are
paid (+1), their open debits — credit memos, payments on account — offset them (-1); for
customers the other way round. The cash discount allowed on the payment date is taken when
the run says so. Items can be deselected; executing creates one payment per business partner
(bank transfer or check from the run's bank account) in one transaction and skips partners
whose net amount is not positive. An item paid elsewhere meanwhile makes the run outdated.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.banking import PaymentRun, PaymentRunItem
from app.models.finance import JournalLine
from app.models.partners import BusinessPartner
from app.services import banking
from app.services.admin import B1Error, posting_period
from app.services.bankrec import bank_account
from app.services.journal import money

ZERO = Decimal("0")


@dataclass
class RunRequest:
    pmnt_date: date
    due_date_to: date
    bank_acct: str
    pay_type: str = "V"  # V vendors (outgoing), C customers (incoming)
    pay_means: str = "T"  # T bank transfer, C check
    card_codes: list[str] | None = None
    take_disc: bool = True
    first_check: int | None = None
    name: str | None = None


def create_run(session: Session, req: RunRequest) -> PaymentRun:
    """Save the recommendation of a run."""
    try:
        if req.pay_type not in {"V", "C"} or req.pay_means not in {"T", "C"}:
            raise B1Error("Pay type V (vendors) / C (customers), means T (transfer) / C (check)")
        if req.pay_means == "C" and req.pay_type == "C":
            raise B1Error("Checks are issued to vendors; collect from customers by transfer")
        if req.pay_means == "C" and not req.first_check:
            raise B1Error("Enter the first check number")
        bank_account(session, req.bank_acct)
        posting_period(session, req.pmnt_date)
        q = select(BusinessPartner).where(BusinessPartner.card_type == ("S" if req.pay_type == "V" else "C"),
                                          BusinessPartner.frozen_for == "N")
        if req.card_codes:
            q = q.where(BusinessPartner.card_code.in_(req.card_codes))
        codes = [bp.card_code for bp in session.scalars(q.order_by(BusinessPartner.card_code))]
        run = PaymentRun(id_entry=(session.scalar(select(func.max(PaymentRun.id_entry))) or 0) + 1,
                         wizard_name=(req.name or f"Payment run {req.pmnt_date.isoformat()}")[:50], pmnt_date=req.pmnt_date,
                         pay_type=req.pay_type, pay_means=req.pay_means, bank_acct=req.bank_acct,
                         due_date_to=req.due_date_to, take_disc="Y" if req.take_disc else "N", status="S",
                         first_check=req.first_check)
        n = 0
        for code in codes:
            lines = session.scalars(select(JournalLine).where(
                JournalLine.short_name == code, JournalLine.short_name != JournalLine.account,
                (JournalLine.bal_due_deb != 0) | (JournalLine.bal_due_cred != 0),
                JournalLine.due_date <= req.due_date_to).order_by(JournalLine.due_date, JournalLine.trans_id)).all()
            for l in lines:
                pay = (l.bal_due_cred > 0) if req.pay_type == "V" else (l.bal_due_deb > 0)
                discount = banking.eligible_discount(session, l, req.pmnt_date)[1] if (pay and req.take_disc) else ZERO
                run.items.append(PaymentRunItem(line_num=n, card_code=code, trans_id=l.trans_id, line_id=l.line_id,
                                                trans_type=l.trans_type, doc_num=l.base_ref, due_date=l.due_date,
                                                open_amount=l.bal_due_deb or l.bal_due_cred, direction=1 if pay else -1,
                                                discount=discount, selected="Y"))
                n += 1
        if not run.items:
            raise B1Error(f"No open items due up to {req.due_date_to.isoformat()}")
        session.add(run)
        session.commit()
        return run
    except Exception:
        session.rollback()
        raise


def select_items(session: Session, id_entry: int, line_nums: list[int], selected: bool) -> PaymentRun:
    run = _saved(session, id_entry)
    for it in run.items:
        if it.line_num in line_nums:
            it.selected = "Y" if selected else "N"
    session.commit()
    return run


def _saved(session: Session, id_entry: int) -> PaymentRun:
    run = session.get(PaymentRun, id_entry)
    if run is None:
        raise B1Error(f"Payment run {id_entry} does not exist")
    if run.status != "S":
        raise B1Error(f"Payment run {id_entry} is already {'executed' if run.status == 'E' else 'canceled'}")
    return run


def totals(run: PaymentRun) -> dict[str, Decimal]:
    """Net amount per business partner of the selected items (paid minus offsets, after discount)."""
    out: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for it in run.items:
        if it.selected == "Y":
            out[it.card_code] += it.direction * (it.open_amount - it.discount)
    return dict(out)


def execute(session: Session, id_entry: int) -> PaymentRun:
    try:
        run = _saved(session, id_entry)
        obj = "46" if run.pay_type == "V" else "24"
        check_no = run.first_check
        created = 0
        for code, net in sorted(totals(run).items()):
            if net <= 0:
                continue  # nothing to pay after offsets
            items = [it for it in run.items if it.selected == "Y" and it.card_code == code]
            paid = []
            for it in items:
                line = session.get(JournalLine, (it.trans_id, it.line_id))
                if (line.bal_due_deb or line.bal_due_cred) != it.open_amount:
                    raise B1Error(f"Item {it.doc_num or it.trans_id} of {code} changed since the recommendation; "
                                  f"create a new payment run")
                paid.append(banking.PaidItem(it.trans_id, it.line_id, it.open_amount - it.discount, it.discount))
            means = dict(trsfr_acct=run.bank_acct, trsfr_sum=money(net), trsfr_date=run.pmnt_date,
                         trsfr_ref=f"PWZ {run.id_entry}") if run.pay_means == "T" else dict(
                check_acct=run.bank_acct, checks=[banking.CheckRequest(check_num=check_no, check_sum=money(net),
                                                                       due_date=run.pmnt_date)])
            pay = banking.create_payment(session, banking.PaymentRequest(
                obj=obj, doc_date=run.pmnt_date, doc_type="S" if run.pay_type == "V" else "C", card_code=code,
                items=paid, jrnl_memo=f"Payment wizard {run.id_entry} - {code}"[:50], **means), commit=False)
            for it in items:
                it.pay_entry = pay.doc_entry
            if run.pay_means == "C":
                check_no += 1
            created += 1
        if not created:
            raise B1Error("No business partner has a positive amount to pay")
        run.status = "E"
        session.commit()
        return run
    except Exception:
        session.rollback()
        raise


def cancel(session: Session, id_entry: int) -> PaymentRun:
    run = _saved(session, id_entry)
    run.status = "C"
    session.commit()
    return run
