"""End-to-end check for exchange rate differences (revaluation of open FC items).

A USD invoice and a USD vendor invoice revalued at a later rate: unrealized gain / loss on the
control accounts, reversed the next day; the partners' open items and balances stay at
historical LC; a second run on the same date is refused; the later payment still realizes the
whole difference. A USD bank G/L account is revalued permanently; a second run finds nothing.

Run after app.seed (rerunnable, uses its own dates and a new bank account):  python -m app.verify_fxreval
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.finance import Account, ExchangeRateRun, JournalEntry, JournalLine
from app.models.partners import BusinessPartner
from app.services import banking, fxreval, journal, reports
from app.services import documents as docs
from app.services.admin import B1Error, exchange_rate
from app.services.banking import PaidItem, PaymentRequest
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR
from app.services.journal import JournalLineRequest as L
from app.services.journal import JournalRequest

D = Decimal


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def _bp_line(s, doc) -> JournalLine:
    return s.scalars(select(JournalLine).where(JournalLine.trans_id == doc.trans_id,
                                               JournalLine.short_name == doc.card_code)).one()


def main() -> None:
    s = SessionLocal()
    try:
        # a fresh run date per execution (month ends of 2027, after the previous runs)
        runs = s.scalar(select(func.count()).select_from(ExchangeRateRun).where(ExchangeRateRun.category == "B")) or 0
        d_doc, run_on = date(2027, 1, 4), date(2027, 6, 30) + timedelta(days=runs)
        bal = lambda code: s.get(Account, code).curr_total  # noqa: E731
        r_doc, r_run = exchange_rate(s, "USD", d_doc), exchange_rate(s, "USD", run_on)

        # 1) open USD items: an A/R invoice (Chennai) and an A/P invoice (Delhi)
        ar = docs.create_document(s, DR(obj="13", doc_date=d_doc, card_code="C30000", doc_type="S", doc_cur="USD",
                                        disc_prcnt=D(0), lines=[DL(dscription="Consulting", acct_code="412000", price=D(1000), vat_group="OCS18")]))
        ap = docs.create_document(s, DR(obj="18", doc_date=d_doc, card_code="V20000", doc_type="S", doc_cur="USD",
                                        disc_prcnt=D(0), lines=[DL(dscription="Software", acct_code="611000", price=D(500), vat_group="ICS18")]))
        ar_line, ap_line = _bp_line(s, ar), _bp_line(s, ap)
        prev = {(x["trans_id"], x["line_id"]): x for x in fxreval.preview(s, run_on, "B")}
        x_ar, x_ap = prev[(ar_line.trans_id, ar_line.line_id)], prev[(ap_line.trans_id, ap_line.line_id)]
        print(f"1 Preview {run_on} (USD {r_doc} -> {r_run}): A/R USD {x_ar['open_fc']} INR {x_ar['open_lc']} -> {x_ar['new_lc']} "
              f"({x_ar['difference']}); A/P USD {x_ap['open_fc']} INR {x_ap['open_lc']} -> {x_ap['new_lc']} ({x_ap['difference']})")
        assert x_ar["open_fc"] == D(1180) and x_ar["new_lc"] == (D(1180) * r_run).quantize(D("0.01"))
        assert x_ap["open_fc"] == D(-590) and x_ap["difference"] < 0  # payable grew with the rate: a loss

        # 2) run: unrealized differences on the control accounts, reversed the next day
        cust, vend = s.get(BusinessPartner, "C30000"), s.get(BusinessPartner, "V20000")
        cbal, vbal, ar0, ap0 = cust.balance, vend.balance, bal("114000"), bal("211000")
        run = fxreval.run(s, run_on, "B")
        je = s.get(JournalEntry, run.trans_id)
        rev = s.get(JournalEntry, je.storno_to_tr)
        print(f"2 Run {run.abs_entry}: JE {je.number} gain {run.total_gain} / loss {run.total_loss}, reversed by JE "
              f"{rev.number} on {rev.ref_date}; customer balance unchanged {cust.balance == cbal}")
        assert rev.ref_date == run_on + timedelta(days=1) and cust.balance == cbal and vend.balance == vbal
        assert ar_line.bal_due_deb == ar.doc_total and ap_line.bal_due_cred == ap.doc_total  # open items untouched
        assert bal("114000") == ar0 and bal("211000") == ap0  # revaluation + reversal net to zero
        rev_lines = {l.account: l.debit - l.credit for l in je.lines}
        assert rev_lines["114000"] >= x_ar["difference"]  # includes the run's other open USD items
        _rejects(lambda: fxreval.run(s, run_on, "B"), "second run on the same date")

        # 3) the payment later realizes the whole difference against the historical rate
        loss0, gain0 = bal("712000"), bal("711000")
        pay_on = run_on + timedelta(days=5)
        banking.create_payment(s, PaymentRequest(obj="24", doc_date=pay_on, card_code="C30000", doc_curr="USD",
                                                 trsfr_acct="112000", trsfr_sum=D(1180),
                                                 items=[PaidItem(ar_line.trans_id, ar_line.line_id, D(1180))]))
        realized = -((bal("711000") - gain0) + (bal("712000") - loss0))  # credit = gain
        expected = (D(1180) * exchange_rate(s, "USD", pay_on)).quantize(D("0.01")) - ar.doc_total
        print(f"3 Payment on {pay_on}: realized gain {realized} (= INR value then - invoice INR {ar.doc_total})")
        assert realized == expected and ar.doc_status == "C"

        # 4) a USD bank G/L account is revalued permanently
        n = (s.scalar(select(func.count()).select_from(Account).where(Account.acct_code.like("1128%"))) or 0) + 1
        usd_bank = f"1128{n:02d}"
        s.add(Account(acct_code=usd_bank, acct_name=f"USD account {n}", group_mask=1, father_num="11", levels=3,
                      postable="Y", act_type="N", loc_man_tran="N", finanse="Y", act_curr="USD"))
        s.commit()
        journal.post_entry(s, JournalRequest(ref_date=d_doc, memo="USD funding", lines=[
            L(account=usd_bank, fc_currency="USD", fc_debit=D(2000)), L(account="311000", debit=D(0), credit=(D(2000) * r_doc).quantize(D("0.01")))]))
        g = fxreval.run(s, run_on, "G", currencies=["USD"])
        mine = next(x for x in g.lines if x.short_name == usd_bank)
        print(f"4 G/L run {g.abs_entry}: {usd_bank} USD 2000 INR {mine.open_lc} -> {mine.new_lc} (permanent, no reversal: "
              f"{s.get(JournalEntry, g.trans_id).storno_to_tr is None}); balance now {bal(usd_bank)}")
        assert bal(usd_bank) == (D(2000) * r_run).quantize(D("0.01")) and s.get(JournalEntry, g.trans_id).storno_to_tr is None
        again = [x for x in fxreval.preview(s, run_on, "G", ["USD"]) if x["short_name"] == usd_bank]
        assert again and again[0]["difference"] == 0

        assert reports.trial_balance(s, date(2027, 1, 1), date(2027, 12, 31))["balanced"]
        print("\nOK - exchange rate differences revalue, reverse and realize consistently.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
