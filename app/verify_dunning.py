"""End-to-end check for dunning.

Two overdue invoices of a customer on the standard dunning term (7 / 30 / 60 days, fees 0 / 250 /
500, interest 18 % p.a.): the first run raises both items one level (level 1, interest), a
second run the same day finds nothing, the next run raises to level 2 with the fee posted as
an open item, a run with "highest" goes straight to level 3; a customer below the minimum
balance gets no letter; paid items are not dunned.

Run after app.seed (rerunnable, new customers each run):  python -m app.verify_dunning
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.finance import Account, JournalLine
from app.models.partners import BusinessPartner
from app.services import dunning, masterdata, reports
from app.services import documents as docs
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
D0 = date(2027, 2, 1)


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def _customer(s, tag: str) -> BusinessPartner:
    n = (s.scalar(select(func.count()).select_from(BusinessPartner).where(BusinessPartner.card_code.like(f"{tag}%"))) or 0) + 1
    code = f"{tag}{n:03d}"
    masterdata.create_partner(s, masterdata.PartnerRequest(card_code=code, card_name=f"Verify {code}", card_type="C",
                                                           group_num=1, dun_term="STD", country="IN"))
    return s.get(BusinessPartner, code)


def _invoice(s, card: str, day: date, amount: str):
    return docs.create_document(s, DR(obj="13", doc_date=day, card_code=card, doc_type="S", disc_prcnt=D(0), lines=[
        DL(dscription="Service", acct_code="412000", price=D(amount), vat_group="OCS18")]))


def _line(s, doc) -> JournalLine:
    return s.scalars(select(JournalLine).where(JournalLine.trans_id == doc.trans_id, JournalLine.short_name == doc.card_code)).one()


def main() -> None:
    s = SessionLocal()
    try:
        bp = _customer(s, "CDUN")
        a = _invoice(s, bp.card_code, D0, "1000")                       # due D0 + 30
        b = _invoice(s, bp.card_code, D0 - timedelta(days=60), "1000")  # due D0 - 30
        la, lb = _line(s, a), _line(s, b)
        due_a = la.due_date

        # 1) first run: both items to level 1 (one step at a time), interest on arrears
        on1 = due_a + timedelta(days=10)
        prev = dunning.preview(s, on1, [bp.card_code])
        letter = prev[0]
        expected_interest = (D(1180) * 18 / 100 * 10 / 365).quantize(D("0.01")) + (D(1180) * 18 / 100 * 70 / 365).quantize(D("0.01"))
        print(f"1 Preview {on1}: level {letter['level']}, items "
              + ", ".join(f"{i['doc_num']} {i['days_overdue']}d {i['old_level']}->{i['new_level']}" for i in letter["items"])
              + f", interest {letter['interest']}, fee {letter['fee']}")
        assert letter["level"] == 1 and [i["new_level"] for i in letter["items"]] == [1, 1]
        assert letter["interest"] == expected_interest and letter["fee"] == 0
        r1 = dunning.run(s, on1, [bp.card_code])
        assert la.dunn_level == 1 and lb.dunn_level == 1 and la.dun_date == on1
        _rejects(lambda: dunning.run(s, on1, [bp.card_code]), "second run on the same day")

        # 2) next run: level 2, fee and interest posted as an open item
        bal0, fees0 = bp.balance, s.get(Account, "723000").curr_total
        on2 = due_a + timedelta(days=35)
        r2 = dunning.run(s, on2, [bp.card_code], post_fees=True)
        l2 = r2.letters[0]
        print(f"2 Run {r2.abs_entry} on {on2}: level {l2.level}, fee {l2.fee}, interest {l2.interest}, posted JE {l2.trans_id}; "
              f"customer balance +{bp.balance - bal0}")
        assert l2.level == 2 and l2.fee == D(250) and la.dunn_level == 2 and lb.dunn_level == 2
        assert bp.balance - bal0 == l2.fee + l2.interest and fees0 - s.get(Account, "723000").curr_total == D(250)

        # 3) "highest": straight to level 3
        on3 = due_a + timedelta(days=65)
        r3 = dunning.run(s, on3, [bp.card_code], highest=True)
        print(f"3 Run {r3.abs_entry} on {on3} (highest): level {r3.letters[0].level}, fee {r3.letters[0].fee}")
        assert r3.letters[0].level == 3 and la.dunn_level == 3 and lb.dunn_level == 3

        # 4) below the minimum balance: no letter; paid items are not dunned
        small = _customer(s, "CDUS")
        _invoice(s, small.card_code, D0 - timedelta(days=60), "50")  # 59 < minimum balance 100
        assert dunning.preview(s, on1, [small.card_code]) == []
        from app.services import banking

        fresh = _customer(s, "CDUP")
        inv = _invoice(s, fresh.card_code, D0 - timedelta(days=60), "1000")
        li = _line(s, inv)
        banking.create_payment(s, banking.PaymentRequest(obj="24", doc_date=D0, card_code=fresh.card_code, cash_acct="111000",
                                                         cash_sum=D(1180), items=[banking.PaidItem(li.trans_id, li.line_id, D(1180))]))
        assert dunning.preview(s, on1, [fresh.card_code]) == []
        print("4 Below minimum balance and paid items: no letters")

        assert reports.trial_balance(s, date(2027, 1, 1), date(2027, 12, 31))["balanced"]
        print(f"\nOK - dunning levels, letters, interest and fees are consistent (runs {r1.abs_entry}-{r3.abs_entry}).")
    finally:
        s.close()


if __name__ == "__main__":
    main()
