"""End-to-end check for foreign currency: translation, rounding, valuation, realized differences.

USD rates (seed): 0.90 from 2026-06-01, 0.95 from 2026-09-01, 0.88 from 2026-12-01.
Run after app.seed:  python -m app.verify_fx  (rerunnable: an already valuated
key date is reported, not posted twice)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.models.documents import AccountingDocumentHeader
from app.services import fx, reporting
from app.services.clearing import PaymentRequest, post_payment
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, LineRequest, post_document

MANDT, BUKRS, CUST, VEND = "100", "1000", "0000010000", "0000020000"
D = Decimal


def main() -> None:
    s = SessionLocal()
    try:
        # 1) a USD invoice is translated at the posting-date rate (0.90)
        inv = post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="DR", bldat=date(2026, 6, 15), budat=date(2026, 6, 15), waers="USD",
            xblnr="FX-1", bktxt="Export invoice", lines=[
                LineRequest(bschl="01", account=CUST, wrbtr=D("1190.00"), sgtxt="FX-1"),
                LineRequest(bschl="50", account="800000", wrbtr=D("1000.00"), mwskz="A1", calculate_tax=True),
            ]))
        item = next(i for i in inv.items if i.koart == "D")
        print(f"1 USD invoice {inv.belnr}: rate {inv.kursf}, 1190.00 USD = {item.dmbtr} EUR")
        assert inv.kursf == D("0.90000") and item.dmbtr == D("1071.00") and inv.wwert == date(2026, 6, 15)

        # 2) cent differences of translating several lines are absorbed (rate 0.92 in January)
        odd = post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="KR", bldat=date(2026, 1, 20), budat=date(2026, 1, 20), waers="USD",
            bktxt="Split costs", lines=[
                LineRequest(bschl="31", account=VEND, wrbtr=D("100.00")),
                LineRequest(bschl="40", account="476000", wrbtr=D("33.33")),
                LineRequest(bschl="40", account="476000", wrbtr=D("33.33")),
                LineRequest(bschl="40", account="476000", wrbtr=D("33.34")),
            ]))
        debit = sum(i.dmbtr for i in odd.items if i.shkzg == "S")
        print(f"2 Rounding: vendor {odd.items[0].dmbtr} EUR, expenses {[str(i.dmbtr) for i in odd.items[1:]]}")
        assert debit == odd.items[0].dmbtr == D("92.00")

        # 3) valuation at 2026-09-30 (rate 0.95): +59.50 EUR on the invoice, reversed on 2026-10-01
        test = fx.valuate(s, MANDT, BUKRS, date(2026, 9, 30))
        line = next(l for l in test["items"] if l["belnr"] == inv.belnr)
        print(f"3 Valuation test run: {inv.belnr} {line['local_before']} -> {line['local_after']} EUR "
              f"(diff {line['difference']}); total {test['total']}")
        assert line["difference"] == D("59.50") and test["document"] is None
        try:
            posted = fx.valuate(s, MANDT, BUKRS, date(2026, 9, 30), post=True)
            print(f"  Posted {posted['document']['belnr']}, reversed by {posted['reversal']['belnr']} "
                  f"on {posted['reversal']['budat']}")
            doc = s.get(AccountingDocumentHeader, (MANDT, BUKRS, posted["document"]["belnr"], posted["document"]["gjahr"]))
            assert doc.stblg == posted["reversal"]["belnr"]
            accounts = {i.hkont for i in doc.items}
            assert {"140099", "280010"} <= accounts or {"230010"} & accounts
        except PostingError as exc:
            print(f"  (already valuated: {exc})")
        try:
            fx.valuate(s, MANDT, BUKRS, date(2026, 9, 30), post=True)
        except PostingError as exc:
            print(f"  Second valuation rejected: {exc}")
        else:
            raise AssertionError("a key date must not be valuated twice")

        # 4) payment at 0.88: the item clears at its historical 1071.00 EUR, the bank gets 1047.20 EUR,
        #    and the 23.80 EUR difference is a realized exchange rate loss
        pay = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 12, 15),
                                             amount=D("1190.00"), hkont="113100",
                                             items=[(item.belnr, item.gjahr, item.buzei)]))
        print(f"4 Payment {pay['belnr']} in {pay['waers']} at {pay['kursf']}: realized {pay['realized_fx']} EUR")
        assert pay["waers"] == "USD" and pay["realized_fx"] == D("-23.80")
        pdoc = s.get(AccountingDocumentHeader, (MANDT, BUKRS, pay["belnr"], pay["gjahr"]))
        assert any(i.hkont == "230000" and i.shkzg == "S" and i.dmbtr == D("23.80") for i in pdoc.items)
        assert any(i.hkont == "113100" and i.dmbtr == D("1047.20") for i in pdoc.items)
        assert s.get(type(item), (MANDT, BUKRS, item.belnr, item.gjahr, item.buzei)).augbl == pay["belnr"]

        tb = reporting.trial_balance(s, MANDT, BUKRS, 2026)
        print(f"Trial balance balanced={tb['balanced']}")
        assert tb["balanced"]
        print("\nOK - translation, rounding, valuation with reversal and realized FX differences are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
