"""Bank statements and external (bank) reconciliation.

A bank statement (OBNH + rows OBNK) belongs to a G/L bank account: opening balance = closing
balance of the previous statement, closing balance = opening + money in - money out.

External reconciliation (OMTH / MTH1) matches statement rows with the journal lines of the
same G/L bank account (JDT1 ExtrMatch / OBNK BankMatch): the rows' money in - out must equal
the lines' debit - credit. Rows not in the books yet are processed into an incoming payment,
an outgoing payment or a journal entry (bank charges, interest) and reconciled at once.
Automatic reconciliation pairs one row with one line of the same amount within a few days,
preferring a matching reference.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.banking import (BankStatement, BankStatementRow, ExternalReconciliation, ExternalReconciliationLine,
                                HouseBankAccount)
from app.models.finance import Account, JournalLine
from app.services import banking, journal
from app.services.admin import B1Error, company
from app.services.journal import JournalLineRequest, JournalRequest, money

ZERO = Decimal("0")


def bank_account(session: Session, code: str) -> Account:
    acct = session.get(Account, code) if code else None
    if acct is None or acct.postable != "Y" or acct.finanse != "Y" or acct.loc_man_tran == "Y":
        raise B1Error(f"G/L account {code} is not an active cash / bank account")
    return acct


# ------------------------------------------------------------- statements
@dataclass
class RowRequest:
    due_date: date
    amount_in: Decimal = ZERO
    amount_out: Decimal = ZERO
    ref: str | None = None
    memo: str | None = None
    extern_code: str | None = None
    card_code: str | None = None


@dataclass
class StatementRequest:
    acct_code: str
    stat_date: date
    end_bal: Decimal
    rows: list[RowRequest] = field(default_factory=list)
    start_bal: Decimal | None = None  # default: closing balance of the previous statement (0 for the first)
    statem_no: int | None = None
    house_bank: int | None = None
    data_source: str = "M"


def last_statement(session: Session, acct_code: str) -> BankStatement | None:
    return session.scalars(select(BankStatement).where(BankStatement.acct_code == acct_code)
                           .order_by(BankStatement.statem_no.desc())).first()


def create_statement(session: Session, req: StatementRequest) -> BankStatement:
    try:
        bank_account(session, req.acct_code)
        if req.house_bank is not None:
            hb = session.get(HouseBankAccount, req.house_bank)
            if hb is None or hb.gl_account != req.acct_code:
                raise B1Error(f"House bank account {req.house_bank} does not belong to G/L account {req.acct_code}")
        prev = last_statement(session, req.acct_code)
        start = money(req.start_bal) if req.start_bal is not None else (prev.end_bal if prev else ZERO)
        if prev is not None and start != prev.end_bal:
            raise B1Error(f"The opening balance {start} differs from the closing balance {prev.end_bal} of "
                          f"statement {prev.statem_no}")
        if prev is not None and req.stat_date < prev.stat_date:
            raise B1Error(f"The statement date is before statement {prev.statem_no} ({prev.stat_date})")
        if not req.rows:
            raise B1Error("Enter at least one statement row")
        total_in = total_out = ZERO
        for n, r in enumerate(req.rows):
            a_in, a_out = money(r.amount_in or 0), money(r.amount_out or 0)
            if a_in < 0 or a_out < 0 or bool(a_in) == bool(a_out):
                raise B1Error(f"Row {n + 1}: enter either money in or money out (positive)")
            total_in += a_in
            total_out += a_out
        end = money(req.end_bal)
        if start + total_in - total_out != end:
            raise B1Error(f"The closing balance {end} differs from opening {start} + in {total_in} - out {total_out} "
                          f"= {start + total_in - total_out}")
        number = req.statem_no or ((prev.statem_no + 1) if prev else 1)
        if session.scalar(select(BankStatement).where(BankStatement.acct_code == req.acct_code,
                                                      BankStatement.statem_no == number)) is not None:
            raise B1Error(f"Statement {number} of account {req.acct_code} already exists")
        st = BankStatement(abs_entry=(session.scalar(select(func.max(BankStatement.abs_entry))) or 0) + 1,
                           acct_code=req.acct_code, house_bank=req.house_bank, statem_no=number, stat_date=req.stat_date,
                           start_bal=start, end_bal=end, currency=company(session).main_curncy,
                           data_source=req.data_source)
        seq = session.scalar(select(func.max(BankStatementRow.sequence))) or 0
        for n, r in enumerate(req.rows):
            seq += 1
            st.rows.append(BankStatementRow(
                sequence=seq, acct_code=req.acct_code, statem_no=number, vis_order=n, due_date=r.due_date,
                ref=r.ref, memo=r.memo, deb_amount=money(r.amount_out or 0), cred_amnt=money(r.amount_in or 0),
                extern_code=r.extern_code, card_code=r.card_code))
        session.add(st)
        session.commit()
        return st
    except Exception:
        session.rollback()
        raise


def _parse_date(text: str) -> date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    raise B1Error(f"Unknown date format: {text!r} (use YYYY-MM-DD or DD/MM/YYYY)")


def _amount(text: str | None) -> Decimal:
    text = (text or "").strip().replace(",", "")
    if not text:
        return ZERO
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise B1Error(f"Not an amount: {text!r}") from exc


def parse_csv(text: str) -> list[RowRequest]:
    """Bank export with a header row: date, reference, description and either amount (+ in, - out)
    or separate deposit / withdrawal (credit / debit) columns."""
    reader = csv.DictReader(io.StringIO(text.strip()))
    if not reader.fieldnames:
        raise B1Error("The file is empty")
    cols = {c.strip().lower(): c for c in reader.fieldnames}

    def col(*names):
        return next((cols[n] for n in names if n in cols), None)

    c_date = col("date", "value date", "txn date", "transaction date")
    c_ref = col("reference", "ref", "ref no", "cheque no", "chq no")
    c_memo = col("description", "narration", "memo", "details")
    c_amt = col("amount")
    c_in = col("deposit", "credit", "deposit amount", "money in")
    c_out = col("withdrawal", "debit", "withdrawal amount", "money out")
    if c_date is None or (c_amt is None and (c_in is None or c_out is None)):
        raise B1Error("The file needs a date column and an amount column (or deposit and withdrawal columns)")
    rows = []
    for n, rec in enumerate(reader, start=2):
        if not any((v or "").strip() for v in rec.values()):
            continue
        if c_amt is not None:
            amt = _amount(rec.get(c_amt))
            a_in, a_out = (amt, ZERO) if amt > 0 else (ZERO, -amt)
        else:
            a_in, a_out = _amount(rec.get(c_in)), _amount(rec.get(c_out))
        if not a_in and not a_out:
            raise B1Error(f"Line {n}: no amount")
        rows.append(RowRequest(due_date=_parse_date(rec[c_date]), amount_in=a_in, amount_out=a_out,
                               ref=(rec.get(c_ref) or "").strip() or None if c_ref else None,
                               memo=(rec.get(c_memo) or "").strip() or None if c_memo else None))
    if not rows:
        raise B1Error("The file has no statement rows")
    return rows


# ------------------------------------------------------------- open items of the reconciliation
def open_lines(session: Session, acct_code: str) -> list[JournalLine]:
    return session.scalars(select(JournalLine).where(JournalLine.account == acct_code, JournalLine.extr_match.is_(None))
                           .order_by(JournalLine.ref_date, JournalLine.trans_id, JournalLine.line_id)).all()


def open_rows(session: Session, acct_code: str) -> list[BankStatementRow]:
    return session.scalars(select(BankStatementRow).where(BankStatementRow.acct_code == acct_code,
                                                          BankStatementRow.bank_match.is_(None))
                           .order_by(BankStatementRow.due_date, BankStatementRow.sequence)).all()


def _new_number(session: Session) -> int:
    return (session.scalar(select(func.max(ExternalReconciliation.mth_num))) or 0) + 1


def _reconcile(session: Session, acct_code: str, rows: list[BankStatementRow], lines: list[JournalLine], on: date,
               auto: bool = False) -> ExternalReconciliation:
    rows_sum = sum((r.cred_amnt - r.deb_amount for r in rows), ZERO)
    lines_sum = sum((l.debit - l.credit for l in lines), ZERO)
    if not rows and not lines:
        raise B1Error("Select statement rows and / or journal lines to reconcile")
    if rows and lines and rows_sum != lines_sum:
        raise B1Error(f"The selection does not balance: statement rows {rows_sum}, journal lines {lines_sum}")
    if not rows and lines_sum != 0:
        raise B1Error(f"Journal lines alone must net to zero (they net to {lines_sum})")
    if not lines and rows_sum != 0:
        raise B1Error(f"Statement rows alone must net to zero (they net to {rows_sum})")
    m = ExternalReconciliation(mth_num=_new_number(session), mth_date=on, acct_code=acct_code,
                               total=abs(rows_sum if rows else lines_sum) or sum((r.cred_amnt for r in rows), ZERO)
                               or sum((l.debit for l in lines), ZERO), auto="Y" if auto else "N", canceled="N")
    n = 0
    for r in rows:
        if r.acct_code != acct_code or r.bank_match is not None:
            raise B1Error(f"Statement row {r.sequence} is not open on account {acct_code}")
        r.bank_match = m.mth_num
        m.lines.append(ExternalReconciliationLine(line_num=n, bank_seq=r.sequence, recon_sum=r.cred_amnt - r.deb_amount))
        n += 1
    for l in lines:
        if l.account != acct_code or l.extr_match is not None:
            raise B1Error(f"Journal line {l.trans_id}/{l.line_id} is not open on account {acct_code}")
        l.extr_match, l.mth_date = m.mth_num, on
        m.lines.append(ExternalReconciliationLine(line_num=n, trans_id=l.trans_id, trans_row_id=l.line_id,
                                                  recon_sum=l.debit - l.credit))
        n += 1
    session.add(m)
    session.flush()
    return m


def reconcile(session: Session, acct_code: str, row_seqs: list[int], line_keys: list[tuple[int, int]],
              on: date | None = None) -> ExternalReconciliation:
    try:
        bank_account(session, acct_code)
        rows = [session.get(BankStatementRow, s) for s in dict.fromkeys(row_seqs)]
        lines = [session.get(JournalLine, k) for k in dict.fromkeys(tuple(k) for k in line_keys)]
        if None in rows or None in lines:
            raise B1Error("A selected statement row or journal line does not exist")
        m = _reconcile(session, acct_code, rows, lines, on or date.today())
        session.commit()
        return m
    except Exception:
        session.rollback()
        raise


def auto_reconcile(session: Session, acct_code: str, days: int = 3, on: date | None = None) -> list[ExternalReconciliation]:
    """Pair each open row with one open line of the same amount and direction within `days`; a
    matching reference decides between candidates."""
    try:
        bank_account(session, acct_code)
        lines = open_lines(session, acct_code)
        done = []
        for r in open_rows(session, acct_code):
            amount = r.cred_amnt - r.deb_amount
            window = [l for l in lines if l.extr_match is None and l.debit - l.credit == amount
                      and abs((l.ref_date - r.due_date).days) <= days]
            if not window:
                continue
            ref = (r.ref or "").strip().lower()
            by_ref = [l for l in window if ref and any(ref == (v or "").strip().lower() for v in (l.ref1, l.ref2, l.line_memo))
                      or ref and ref in (l.line_memo or "").lower()]
            pick = by_ref[0] if by_ref else (window[0] if len(window) == 1 else None)
            if pick is None:
                continue  # several candidates and no reference: leave it to the user
            done.append(_reconcile(session, acct_code, [r], [pick], on or date.today(), auto=True))
        session.commit()
        return done
    except Exception:
        session.rollback()
        raise


def cancel_reconciliation(session: Session, mth_num: int) -> ExternalReconciliation:
    m = session.get(ExternalReconciliation, mth_num)
    if m is None:
        raise B1Error(f"External reconciliation {mth_num} does not exist")
    if m.canceled == "Y":
        raise B1Error(f"External reconciliation {mth_num} is already canceled")
    for x in m.lines:
        if x.bank_seq is not None:
            session.get(BankStatementRow, x.bank_seq).bank_match = None
        else:
            l = session.get(JournalLine, (x.trans_id, x.trans_row_id))
            l.extr_match, l.mth_date = None, None
    m.canceled = "Y"
    session.commit()
    return m


# ------------------------------------------------------------- processing a row
@dataclass
class ProcessRequest:
    kind: str  # incoming, outgoing (payments), journal (G/L account: bank charges, interest)
    card_code: str | None = None
    items: list = field(default_factory=list)  # banking.PaidItem
    acct_code: str | None = None  # journal: offset G/L account
    memo: str | None = None


def process_row(session: Session, sequence: int, req: ProcessRequest):
    """Post the row as a payment or journal entry and reconcile it with the bank line of that posting."""
    row = session.get(BankStatementRow, sequence)
    if row is None:
        raise B1Error(f"Statement row {sequence} does not exist")
    if row.bank_match is not None or row.doc_num is not None:
        raise B1Error(f"Statement row {sequence} is already reconciled or processed")
    money_in = row.cred_amnt > 0
    amount = row.cred_amnt or row.deb_amount
    if req.kind in {"incoming", "outgoing"}:
        if (req.kind == "incoming") != money_in:
            raise B1Error(f"Money {'in' if money_in else 'out'}: use an {'incoming' if money_in else 'outgoing'} payment")
        bp_type = None
        from app.models.partners import BusinessPartner

        bp = session.get(BusinessPartner, req.card_code or "")
        if bp is None:
            raise B1Error("Enter the business partner of the payment")
        bp_type = bp.card_type
        pay = banking.create_payment(session, banking.PaymentRequest(
            obj="24" if money_in else "46", doc_date=row.due_date, doc_type=bp_type, card_code=bp.card_code,
            trsfr_acct=row.acct_code, trsfr_sum=amount, trsfr_date=row.due_date, trsfr_ref=(row.ref or "")[:27] or None,
            items=req.items, pay_no_doc=not req.items, jrnl_memo=(req.memo or row.memo or None) and (req.memo or row.memo)[:50]),
            commit=False)
        trans_id, obj, entry = pay.trans_id, pay.obj_type, pay.doc_entry
    elif req.kind == "journal":
        acct = session.get(Account, req.acct_code or "")
        if acct is None or acct.postable != "Y" or acct.loc_man_tran == "Y":
            raise B1Error("Enter the offset G/L account (e.g. bank charges, interest income)")
        memo = (req.memo or row.memo or "Bank statement")[:50]
        je = journal.post_entry(session, JournalRequest(ref_date=row.due_date, memo=memo, ref1=(row.ref or None),
                                                        ref2=f"Statement {row.statem_no}", manual=False, lines=[
            JournalLineRequest(account=row.acct_code, debit=amount if money_in else ZERO, credit=ZERO if money_in else amount),
            JournalLineRequest(account=acct.acct_code, debit=ZERO if money_in else amount, credit=amount if money_in else ZERO)]),
            commit=False)
        trans_id, obj, entry = je.trans_id, "30", je.trans_id
    else:
        raise B1Error("Process a row as incoming, outgoing or journal")
    try:
        bank_line = session.scalars(select(JournalLine).where(JournalLine.trans_id == trans_id,
                                                              JournalLine.account == row.acct_code)).one()
        row.doc_num_type, row.doc_num = obj, entry
        m = _reconcile(session, row.acct_code, [row], [bank_line], row.due_date, auto=True)
        session.commit()
        return m
    except Exception:
        session.rollback()
        raise


# ------------------------------------------------------------- bank reconciliation report
def reconciliation_report(session: Session, acct_code: str, as_of: date | None = None) -> dict:
    """Balance per books and per bank with the items reconciling them (bank reconciliation statement)."""
    bank_account(session, acct_code)
    as_of = as_of or date.today()
    book = session.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
        JournalLine.account == acct_code, JournalLine.ref_date <= as_of)) or ZERO
    st = session.scalars(select(BankStatement).where(BankStatement.acct_code == acct_code,
                                                     BankStatement.stat_date <= as_of)
                         .order_by(BankStatement.statem_no.desc())).first()
    bank = st.end_bal if st else ZERO
    lines = [l for l in open_lines(session, acct_code) if l.ref_date <= as_of]
    rows = [r for r in open_rows(session, acct_code) if r.due_date <= as_of and (st is None or r.statem_no <= st.statem_no)]
    in_transit = sum((l.debit for l in lines), ZERO)  # booked receipts not yet on the statement
    outstanding = sum((l.credit for l in lines), ZERO)  # booked payments not yet on the statement
    bank_in = sum((r.cred_amnt for r in rows), ZERO)  # bank credits not booked
    bank_out = sum((r.deb_amount for r in rows), ZERO)  # bank debits not booked
    adjusted_bank = Decimal(bank) + in_transit - outstanding
    adjusted_book = Decimal(book) + bank_in - bank_out
    return {"acct_code": acct_code, "as_of": as_of, "statement": st.statem_no if st else None,
            "balance_per_bank": bank, "balance_per_books": book,
            "deposits_in_transit": in_transit, "outstanding_payments": outstanding,
            "bank_credits_not_booked": bank_in, "bank_debits_not_booked": bank_out,
            "adjusted_bank": adjusted_bank, "adjusted_books": adjusted_book,
            "difference": adjusted_bank - adjusted_book,
            "open_lines": [{"trans_id": l.trans_id, "line_id": l.line_id, "ref_date": l.ref_date, "trans_type": l.trans_type,
                            "base_ref": l.base_ref, "ref1": l.ref1, "line_memo": l.line_memo,
                            "amount": l.debit - l.credit} for l in lines],
            "open_rows": [{"sequence": r.sequence, "statem_no": r.statem_no, "due_date": r.due_date, "ref": r.ref,
                           "memo": r.memo, "amount": r.cred_amnt - r.deb_amount} for r in rows]}
