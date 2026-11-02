"""End-to-end check for bank statements and external (bank) reconciliation.

On a new bank G/L account: opening deposit, a customer payment and a rent payment booked; a
statement with those plus bank charges, interest and a customer receipt not yet booked;
automatic reconciliation by amount / date / reference, processing of the other rows (journal
entries, incoming payment for an invoice); a CSV statement with a cheque the auto match cannot
pair, reconciled manually (unbalanced selection rejected, cancel and redo); statement balance
checks; the bank reconciliation report agrees at every step.

Run after app.seed (rerunnable, uses a new bank account each run):  python -m app.verify_bankrec
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.finance import Account, JournalLine
from app.services import bankrec, banking, journal
from app.services import documents as docs
from app.services.admin import B1Error
from app.services.bankrec import ProcessRequest, RowRequest, StatementRequest
from app.services.banking import AccountLine, PaidItem, PaymentRequest
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR
from app.services.journal import JournalLineRequest as L
from app.services.journal import JournalRequest

D = Decimal
D0, D1, D2, D3 = date(2027, 3, 1), date(2027, 3, 5), date(2027, 3, 10), date(2027, 3, 31)


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def _item(s, doc) -> PaidItem:
    line = s.scalars(select(JournalLine).where(JournalLine.trans_id == doc.trans_id,
                                               JournalLine.short_name == doc.card_code)).one()
    return PaidItem(line.trans_id, line.line_id, line.bal_due_deb or line.bal_due_cred)


def main() -> None:
    s = SessionLocal()
    try:
        n = (s.scalar(select(func.count()).select_from(Account).where(Account.acct_code.like("1129%"))) or 0) + 1
        bank = f"1129{n:02d}"
        s.add(Account(acct_code=bank, acct_name=f"Verify bank {n}", group_mask=1, father_num="11", levels=3,
                      postable="Y", act_type="N", loc_man_tran="N", finanse="Y"))
        s.commit()

        # books: opening deposit, customer payment (UTR123), rent paid by cheque (CHQ-501)
        journal.post_entry(s, JournalRequest(ref_date=D0, memo="Opening deposit", ref1="OPEN", lines=[
            L(account=bank, debit=D(100000)), L(account="311000", credit=D(100000))]))
        inv = docs.create_document(s, DR(obj="13", doc_date=D0, card_code="C10000", doc_type="S", disc_prcnt=D(0),
                                         lines=[DL(dscription="Consulting", acct_code="412000", price=D(10000), vat_group="OCS18")]))
        banking.create_payment(s, PaymentRequest(obj="24", doc_date=D1, card_code="C10000", trsfr_acct=bank,
                                                 trsfr_sum=D(11800), trsfr_ref="UTR123", items=[_item(s, inv)]))
        banking.create_payment(s, PaymentRequest(obj="46", doc_date=D2, doc_type="A", trsfr_acct=bank, trsfr_sum=D(25000),
                                                 trsfr_ref="CHQ-501", accounts=[AccountLine("612000", D(25000), "Rent March")]))
        inv2 = docs.create_document(s, DR(obj="13", doc_date=D0, card_code="C20000", doc_type="S", disc_prcnt=D(0),
                                          lines=[DL(dscription="Support", acct_code="412000", price=D(5000), vat_group="OCS18")]))

        # 1) statement: balance checks, then the real one
        rows = [RowRequest(D0, amount_in=D(100000), ref="OPEN", memo="Initial deposit"),
                RowRequest(D1, amount_in=D(11800), ref="UTR123", memo="NEFT Maxi Teq"),
                RowRequest(date(2027, 3, 11), amount_out=D(25000), ref="CHQ-501", memo="Cheque 501"),
                RowRequest(D3, amount_out=D(236), memo="Bank charges incl. GST"),
                RowRequest(D3, amount_in=D(450), memo="Interest credit"),
                RowRequest(D3, amount_in=D(5900), ref="UTR987", memo="RTGS Earthshaker")]
        _rejects(lambda: bankrec.create_statement(s, StatementRequest(bank, D3, D(1), rows)), "closing balance does not add up")
        _rejects(lambda: bankrec.create_statement(s, StatementRequest(bank, D3, D(1), [RowRequest(D3, D(1), D(1))])),
                 "row with money in and out")
        st1 = bankrec.create_statement(s, StatementRequest(bank, D3, D(92914), rows))
        print(f"1 Statement {st1.statem_no}: opening {st1.start_bal}, closing {st1.end_bal}, {len(st1.rows)} rows")

        # 2) automatic reconciliation: opening, UTR123 and the cheque (one day later)
        auto = bankrec.auto_reconcile(s, bank)
        print(f"2 Automatic reconciliation: {len(auto)} matches; open rows {len(bankrec.open_rows(s, bank))}")
        assert len(auto) == 3 and len(bankrec.open_rows(s, bank)) == 3 and not bankrec.open_lines(s, bank)

        # 3) process the rows that are not in the books
        seq = {r.memo: r.sequence for r in bankrec.open_rows(s, bank)}
        bankrec.process_row(s, seq["Bank charges incl. GST"], ProcessRequest("journal", acct_code="613000"))
        bankrec.process_row(s, seq["Interest credit"], ProcessRequest("journal", acct_code="721000"))
        _rejects(lambda: bankrec.process_row(s, seq["RTGS Earthshaker"], ProcessRequest("outgoing", card_code="C20000")),
                 "outgoing payment for money in")
        bankrec.process_row(s, seq["RTGS Earthshaker"], ProcessRequest("incoming", card_code="C20000", items=[_item(s, inv2)]))
        rep = bankrec.reconciliation_report(s, bank, D3)
        print(f"3 Processed charges, interest and the receipt (invoice {inv2.doc_num} {inv2.doc_status}); "
              f"books {rep['balance_per_books']} = bank {rep['balance_per_bank']}, difference {rep['difference']}")
        assert inv2.doc_status == "C" and rep["difference"] == 0 and rep["balance_per_books"] == D(92914)
        assert not bankrec.open_rows(s, bank) and not bankrec.open_lines(s, bank)

        # 4) a cheque issued in April is outstanding until the April statement (CSV, Indian format)
        p = banking.create_payment(s, PaymentRequest(obj="46", doc_date=date(2027, 4, 2), doc_type="A", trsfr_acct=bank,
                                                     trsfr_sum=D(1500), trsfr_ref="CHQ-502",
                                                     accounts=[AccountLine("611000", D(1500), "Stationery")]))
        rep = bankrec.reconciliation_report(s, bank, date(2027, 4, 5))
        assert rep["outstanding_payments"] == D(1500) and rep["difference"] == 0
        csv = "Date,Narration,Ref No,Withdrawal,Deposit\n15/04/2027,CHQ 000502 cleared,000502,1500.00,\n"
        st2 = bankrec.create_statement(s, StatementRequest(bank, date(2027, 4, 30), D(91414), bankrec.parse_csv(csv),
                                                           data_source="I"))
        assert not bankrec.auto_reconcile(s, bank), "13 days apart and another reference: no automatic match"
        row = bankrec.open_rows(s, bank)[0]
        line = s.scalars(select(JournalLine).where(JournalLine.trans_id == p.trans_id, JournalLine.account == bank)).one()
        extra = journal.post_entry(s, JournalRequest(ref_date=date(2027, 4, 20), memo="Petty transfer", lines=[
            L(account=bank, credit=D(10)), L(account="111000", debit=D(10))]))
        extra_line = next(l for l in extra.lines if l.account == bank)
        _rejects(lambda: bankrec.reconcile(s, bank, [row.sequence], [(line.trans_id, line.line_id),
                                                                     (extra_line.trans_id, extra_line.line_id)]), "unbalanced selection")
        m = bankrec.reconcile(s, bank, [row.sequence], [(line.trans_id, line.line_id)], date(2027, 4, 30))
        bankrec.cancel_reconciliation(s, m.mth_num)
        assert row.bank_match is None and line.extr_match is None
        m = bankrec.reconcile(s, bank, [row.sequence], [(line.trans_id, line.line_id)], date(2027, 4, 30))
        rep = bankrec.reconciliation_report(s, bank, date(2027, 4, 30))
        print(f"4 CSV statement {st2.statem_no} (closing {st2.end_bal}): cheque 502 reconciled manually "
              f"(reconciliation {m.mth_num}); outstanding {rep['outstanding_payments']}, difference {rep['difference']}")
        assert rep["outstanding_payments"] == D(10) and rep["difference"] == 0
        _rejects(lambda: bankrec.create_statement(s, StatementRequest(bank, date(2027, 5, 31), D(0), [RowRequest(
            date(2027, 5, 2), amount_out=D(1))], start_bal=D(5))), "opening balance differs from the last closing balance")
        print("\nOK - bank statements, processing and external reconciliation are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
