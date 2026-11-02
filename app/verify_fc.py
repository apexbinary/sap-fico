"""End-to-end check for foreign-currency documents, journal entries and their payment.

USD A/R invoice (amounts in USD, LC at the document rate), paid in USD at a later rate
(realized exchange difference), partial FC payment, FC invoice paid in local currency,
credit memo copied from an FC invoice at another rate (exchange difference on the
reconciliation, undone on cancel), GBP purchase with stock valued in LC, manual journal
entry in FC; invariants: BP balance = open items (LC), open FC = document FC - paid FC,
trial balance balanced.

Run after app.seed (rerunnable):  python -m app.verify_fc
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.finance import Account, JournalLine
from app.models.inventory import Item
from app.models.partners import BusinessPartner
from app.services import banking, journal, masterdata, reports
from app.services import documents as docs
from app.services.admin import B1Error, exchange_rate
from app.services.banking import PaidItem, PaymentRequest
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR
from app.services.journal import JournalLineRequest as L
from app.services.journal import JournalRequest

D = Decimal
D1, D2, D3 = date(2026, 3, 2), date(2026, 9, 1), date(2026, 10, 1)


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


def _usd_invoice(s, amount: str, day: date, obj: str = "13", card: str = "C30000", base=None):
    lines = [DL(base_type=base.obj_type, base_entry=base.doc_entry, base_line=0)] if base else [
        DL(dscription="Consulting", acct_code="412000", price=D(amount), vat_group="OCS18")]
    return docs.create_document(s, DR(obj=obj, doc_date=day, card_code=card, doc_type="S", doc_cur="USD",
                                      disc_prcnt=D(0), lines=lines))


def main() -> None:
    s = SessionLocal()
    try:
        bal = lambda code: s.get(Account, code).curr_total  # noqa: E731
        r1, r2, r3 = (exchange_rate(s, "USD", d) for d in (D1, D2, D3))
        print(f"USD rates: {D1} {r1}, {D2} {r2}, {D3} {r3}")

        # 1) USD invoice: amounts in USD, LC at the document rate, partner line with its FC amount
        inv = _usd_invoice(s, "1000", D1)
        line = _bp_line(s, inv)
        lc = (D(1000) * r1).quantize(D("0.01")) + (D(180) * r1).quantize(D("0.01"))
        print(f"1 A/R invoice {inv.doc_num}: USD {inv.doc_total_fc} at {inv.doc_rate} = INR {inv.doc_total}; partner line "
              f"FC {line.fc_debit} {line.fc_currency}, open FC {line.bal_fc_deb}")
        assert inv.doc_cur == "USD" and inv.doc_total_fc == D(1180) and inv.doc_total == lc
        assert line.fc_debit == D(1180) and line.bal_fc_deb == D(1180) and line.fc_currency == "USD"
        assert inv.lines[0].total_frgn == D(1000) and inv.lines[0].price == D(1000)

        # 2) paid in USD at a later rate: partly (500), then the rest (690): realized exchange difference
        gain0, loss0 = bal("711000"), bal("712000")
        p1 = banking.create_payment(s, PaymentRequest(obj="24", doc_date=D2, card_code="C30000", doc_curr="USD",
                                                      trsfr_acct="112000", trsfr_sum=D(500),
                                                      items=[PaidItem(line.trans_id, line.line_id, D(500))]))
        assert inv.paid_fc == D(500) and line.bal_fc_deb == D(680) and inv.doc_status == "O"
        p2 = banking.create_payment(s, PaymentRequest(obj="24", doc_date=D2, card_code="C30000", doc_curr="USD",
                                                      trsfr_acct="112000", trsfr_sum=D(680),
                                                      items=[PaidItem(line.trans_id, line.line_id, D(680))]))
        realized = (bal("712000") - loss0) + (bal("711000") - gain0)  # net debit = loss
        expected = lc - (D(500) * r2).quantize(D("0.01")) - (D(680) * r2).quantize(D("0.01"))
        print(f"2 Payments {p1.doc_num} + {p2.doc_num}: USD 1180 at {r2} = INR {p1.doc_total + p2.doc_total}; invoice "
              f"closed, realized exchange {'loss' if realized > 0 else 'gain'} {abs(realized)}")
        assert inv.doc_status == "C" and inv.paid_fc == D(1180) and line.bal_due_deb == 0 and line.bal_fc_deb == 0
        assert realized == expected

        # 3) USD invoice paid in local currency: the FC open amount goes with it
        inv2 = _usd_invoice(s, "200", D1)
        l2 = _bp_line(s, inv2)
        banking.create_payment(s, PaymentRequest(obj="24", doc_date=D2, card_code="C30000", cash_acct="111000",
                                                 cash_sum=l2.bal_due_deb, items=[PaidItem(l2.trans_id, l2.line_id, l2.bal_due_deb)]))
        print(f"3 A/R invoice {inv2.doc_num} USD 236 paid in INR {inv2.paid_to_date}: open FC {l2.bal_fc_deb}")
        assert inv2.doc_status == "C" and l2.bal_fc_deb == 0 and inv2.paid_fc == D(236)

        # 4) credit memo copied from a USD invoice at another rate: exchange difference on the reconciliation
        inv3 = _usd_invoice(s, "400", D1)
        cust = s.get(BusinessPartner, "C30000")
        g0, lo0 = bal("711000"), bal("712000")
        cm = _usd_invoice(s, "", D3, obj="14", base=inv3)
        l3 = _bp_line(s, inv3)
        print(f"4 Credit memo {cm.doc_num} USD {cm.doc_total_fc} at {cm.doc_rate} = INR {cm.doc_total} against invoice "
              f"{inv3.doc_num} INR {inv3.doc_total}: invoice closed, exchange difference "
              f"{(bal('711000') - g0) + (bal('712000') - lo0)}")
        assert inv3.doc_status == "C" and l3.bal_due_deb == 0 and l3.bal_fc_deb == 0 and cm.paid_fc == D(472)
        docs.cancel_document(s, "14", cm.doc_entry)
        print(f"   credit memo canceled: invoice open again INR {l3.bal_due_deb} / USD {l3.bal_fc_deb}")
        assert l3.bal_due_deb == inv3.doc_total and l3.bal_fc_deb == D(472) and inv3.doc_status == "O"
        assert bal("711000") == g0 and bal("712000") == lo0

        # 5) GBP purchase: stock valued in local currency at the document rate
        code = f"VFC{(s.scalar(select(func.count()).select_from(Item)) or 0) + 1:04d}"
        masterdata.create_item(s, masterdata.ItemRequest(item_code=code, item_name="FC item", itms_grp_cod=101,
                                                         vat_gourp_sa="OCS18", vat_group_pu="ICS18", dflt_wh="01"))
        gbp = exchange_rate(s, "GBP", D1)
        grpo = docs.create_document(s, DR(obj="20", doc_date=D1, card_code="V20000", doc_cur="GBP",
                                          lines=[DL(item_code=code, quantity=D(10), price=D(20))]))
        item = s.get(Item, code)
        print(f"5 GRPO {grpo.doc_num} GBP 200 at {gbp}: stock value INR {item.stock_value}, item cost {item.avg_price}")
        assert item.stock_value == (D(200) * gbp).quantize(D("0.01")) and grpo.doc_total_fc == D(236)  # net 200 + IGST 18 % (Delhi vendor)
        _rejects(lambda: docs.create_document(s, DR(obj="18", doc_date=D1, card_code="V20000", doc_cur="USD",
                                                    lines=[DL(base_type="20", base_entry=grpo.doc_entry, base_line=0)])),
                 "copied in another currency")
        _rejects(lambda: docs.create_document(s, DR(obj="59", doc_date=D1, doc_cur="USD",
                                                    lines=[DL(item_code=code, quantity=D(1), price=D(1))])),
                 "inventory document in FC")

        # 6) manual journal entry in USD: local amounts at the posting date rate
        je = journal.post_entry(s, JournalRequest(ref_date=D1, memo="USD fee", lines=[
            L(card_code="C30000", fc_currency="USD", fc_debit=D(100)),
            L(account="412000", fc_currency="USD", fc_credit=D(100))]))
        print(f"6 JE {je.number}: USD 100 = INR {je.loc_total}, partner open USD {je.lines[0].bal_fc_deb}")
        assert je.loc_total == (D(100) * r1).quantize(D("0.01")) and je.trans_curr == "USD"
        assert je.lines[0].bal_fc_deb == D(100)

        # 7) a partner with a fixed currency takes documents only in that currency or LC
        fixed = s.get(BusinessPartner, "CVERIFY") or s.get(BusinessPartner, "C10000")
        old, fixed.currency = fixed.currency, "USD"
        s.commit()
        _rejects(lambda: docs.create_document(s, DR(obj="13", doc_date=D1, card_code=fixed.card_code, doc_type="S",
                                                    doc_cur="GBP", lines=[DL(acct_code="412000", price=D(1))])),
                 "currency other than the partner's")
        fixed.currency = old
        s.commit()

        # invariants
        s.flush()
        for bp in s.scalars(select(BusinessPartner)):
            open_sum = s.scalar(select(func.coalesce(func.sum(JournalLine.bal_due_deb - JournalLine.bal_due_cred), 0))
                                .where(JournalLine.short_name == bp.card_code, JournalLine.short_name != JournalLine.account))
            assert Decimal(open_sum) == bp.balance, f"{bp.card_code}: balance {bp.balance} != open items {open_sum}"
        for d in (inv, inv2, inv3):
            l = _bp_line(s, d)
            assert l.bal_fc_deb == d.doc_total_fc - d.paid_fc
        assert reports.trial_balance(s, date(2026, 1, 1), date(2026, 12, 31))["balanced"]
        print("Every BP balance equals its open items; open FC = document FC - paid FC; trial balance balanced")
        print("\nOK - foreign-currency documents, journal entries and payments are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
