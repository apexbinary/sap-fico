"""End-to-end check for payments & clearing (F-28 / F-53 / F-32 / F-44 / F-03).

Covers: payment with cash discount (and its tax adjustment), partial payment,
residual item, header-only clearing of a residual against a credit memo, vendor
payment with discount received, tolerances, F-03 G/L clearing, and the
error paths. Run after app.seed:  python -m app.verify_payments
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.models.documents import AccountingDocumentHeader, AccountingDocumentItem
from app.services import reporting
from app.services.clearing import PaymentRequest, post_payment, proposal
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, LineRequest, post_document

MANDT, BUKRS = "100", "1000"
CUST, VEND, BANK = "0000010000", "0000020000", "113100"
D = Decimal


def _partner_line(header, koart):
    it = next(i for i in header.items if i.koart == koart)
    return (it.belnr, it.gjahr, it.buzei)


def _item(s, key):
    return s.get(AccountingDocumentItem, (MANDT, BUKRS, *key))


def _customer_invoice(s, budat, gross, net, zterm=None, ref=None):
    return post_document(s, DocumentRequest(
        bukrs=BUKRS, blart="DR", bldat=budat, budat=budat, waers="EUR", bktxt="Sales invoice",
        lines=[
            LineRequest(bschl="01", account=CUST, wrbtr=D(gross), zterm=zterm, zuonr=ref),
            LineRequest(bschl="50", account="800000", wrbtr=D(net), mwskz="A1", calculate_tax=True),
        ]))


def _show(title, res):
    print(f"{title}: doc {res['belnr']}/{res['gjahr']} ({res['blart']}, {res['mode']})  paid {res['amount']}"
          f"  discount {res['discount']}  residual {res['residual']}  cleared {len(res['cleared'])} item(s)")


def main() -> None:
    s = SessionLocal()
    try:
        # 1) F-28 incoming payment inside the 14-day / 3% discount period
        inv1 = _customer_invoice(s, date(2026, 4, 1), "1190.00", "1000.00", zterm="ZB01", ref="PAY-1")
        k1 = _partner_line(inv1, "D")
        prop = next(p for p in proposal(s, MANDT, BUKRS, "D", CUST, date(2026, 4, 10)) if p["belnr"] == k1[0])
        assert prop["discount"] == D("35.70") and prop["net"] == D("1154.30"), prop
        res = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 4, 10),
                                             amount=D("1154.30"), hkont=BANK, items=[k1]))
        _show("1 Payment with cash discount", res)
        assert res["discount"] == D("35.70") and _item(s, k1).augbl == res["belnr"]
        # 19% of the gross discount is output tax: 35.70 * 190 / 1190 = 5.70 corrects 175000
        assert res["tax_adjustment"] == D("5.70"), res
        pay1 = s.get(AccountingDocumentHeader, (MANDT, BUKRS, res["belnr"], res["gjahr"]))
        assert any(i.hkont == "175000" and i.shkzg == "S" and i.wrbtr == D("5.70") for i in pay1.items)
        assert any(i.hkont == "880000" and i.wrbtr == D("30.00") for i in pay1.items)

        # 2) partial payment, then the rest clears invoice + partial payment together
        inv2 = _customer_invoice(s, date(2026, 4, 2), "2380.00", "2000.00", ref="PAY-2")
        k2 = _partner_line(inv2, "D")
        part = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 4, 15),
                                              amount=D("1000.00"), hkont=BANK, items=[k2], mode="partial"))
        _show("2a Partial payment", part)
        pay_doc = s.get(AccountingDocumentHeader, (MANDT, BUKRS, part["belnr"], part["gjahr"]))
        pay_line = next(i for i in pay_doc.items if i.koart == "D")
        assert _item(s, k2).augbl is None and pay_line.rebzg == k2[0] and pay_line.augbl is None
        rest = post_payment(s, PaymentRequest(
            bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 4, 30), amount=D("1380.00"), hkont=BANK,
            items=[k2, (pay_line.belnr, pay_line.gjahr, pay_line.buzei)]))
        _show("2b Final payment", rest)
        assert _item(s, k2).augbl == rest["belnr"] and pay_line.augbl == rest["belnr"]

        # 3) residual item, then F-32 clears the residual against a credit memo
        inv3 = _customer_invoice(s, date(2026, 4, 3), "595.00", "500.00", ref="PAY-3")
        k3 = _partner_line(inv3, "D")
        resi = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 4, 20),
                                              amount=D("545.00"), hkont=BANK, items=[k3], mode="residual"))
        _show("3a Payment with residual", resi)
        assert resi["residual"] == D("50.00") and _item(s, k3).augbl == resi["belnr"]
        resid_line = next(p for p in proposal(s, MANDT, BUKRS, "D", CUST, date(2026, 4, 25))
                          if p["belnr"] == resi["belnr"])
        assert resid_line["open"] == D("50.00") and resid_line["rebzg"] == k3[0]
        memo = post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="DR", bldat=date(2026, 4, 25), budat=date(2026, 4, 25), waers="EUR",
            bktxt="Credit memo", lines=[
                LineRequest(bschl="11", account=CUST, wrbtr=D("50.00")),
                LineRequest(bschl="40", account="800000", wrbtr=D("50.00")),
            ]))
        km = _partner_line(memo, "D")
        clr = post_payment(s, PaymentRequest(
            bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 4, 25),
            items=[(resid_line["belnr"], resid_line["gjahr"], resid_line["buzei"]), km]))
        _show("3b F-32 clearing", clr)
        assert clr["blart"] == "AB" and _item(s, km).augbl == clr["belnr"]
        clr_doc = s.get(AccountingDocumentHeader, (MANDT, BUKRS, clr["belnr"], clr["gjahr"]))
        assert clr_doc.items == [], "a zero-balance clearing is a header without line items"

        # 4) F-53 vendor payment on ZB01 (vendor master) inside the 30-day / 2% period
        vinv = post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="KR", bldat=date(2026, 5, 1), budat=date(2026, 5, 1), waers="EUR",
            bktxt="Vendor invoice", kokrs="1000", lines=[
                LineRequest(bschl="31", account=VEND, wrbtr=D("1000.00"), zuonr="PAY-4"),
                LineRequest(bschl="40", account="476000", wrbtr=D("1000.00"), kostl="0000001000"),
            ]))
        kv = _partner_line(vinv, "K")
        assert _item(s, kv).zterm == "ZB01" and _item(s, kv).zbd2p == D("2")
        vpay = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="K", account=VEND, budat=date(2026, 5, 20),
                                              amount=D("980.00"), hkont=BANK, items=[kv]))
        _show("4 Vendor payment with discount", vpay)
        assert vpay["discount"] == D("20.00") and _item(s, kv).augbl == vpay["belnr"]

        # 6) payment differences within the tolerance (2.00 EUR / 1%) are posted to ZDI
        inv6 = _customer_invoice(s, date(2026, 5, 5), "595.00", "500.00", ref="PAY-6")
        under = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 5, 6),
                                               amount=D("594.00"), hkont=BANK, items=[_partner_line(inv6, "D")]))
        _show("6a Underpayment within tolerance", under)
        assert under["difference"] == D("1.00")
        inv7 = _customer_invoice(s, date(2026, 5, 5), "238.00", "200.00", ref="PAY-7")
        over = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 5, 6),
                                              amount=D("239.50"), hkont=BANK, items=[_partner_line(inv7, "D")]))
        _show("6b Overpayment within tolerance", over)
        assert over["difference"] == D("-1.50")
        diff_docs = [s.get(AccountingDocumentHeader, (MANDT, BUKRS, r["belnr"], r["gjahr"])) for r in (under, over)]
        assert any(i.hkont == "880100" and i.shkzg == "S" for i in diff_docs[0].items)  # loss
        assert any(i.hkont == "880200" and i.shkzg == "H" for i in diff_docs[1].items)  # gain

        # 7) F-03: clear open items of an open-item-managed G/L account (header-only document)
        for debit, credit in [("113109", "113100"), ("476000", "113109")]:
            post_document(s, DocumentRequest(
                bukrs=BUKRS, blart="SA", bldat=date(2026, 5, 7), budat=date(2026, 5, 7), waers="EUR",
                bktxt="Clearing account test", lines=[
                    LineRequest(bschl="40", account=debit, wrbtr=D("300.00"), zuonr="F03-TEST"),
                    LineRequest(bschl="50", account=credit, wrbtr=D("300.00"), zuonr="F03-TEST"),
                ]))
        gl_items = [p for p in proposal(s, MANDT, BUKRS, "S", "113109", date(2026, 5, 8)) if p["zuonr"] == "F03-TEST"]
        assert len(gl_items) == 2 and sum(p["open"] for p in gl_items) == 0, gl_items
        f03 = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="S", account="113109", budat=date(2026, 5, 8),
                                             items=[(p["belnr"], p["gjahr"], p["buzei"]) for p in gl_items]))
        _show("7 F-03 G/L clearing", f03)
        assert all(_item(s, (p["belnr"], p["gjahr"], p["buzei"])).augbl == f03["belnr"] for p in gl_items)
        try:
            post_payment(s, PaymentRequest(bukrs=BUKRS, koart="S", account="113100", budat=date(2026, 5, 8),
                                           items=[(p["belnr"], p["gjahr"], p["buzei"]) for p in gl_items]))
        except PostingError as exc:
            print("7 rejected (not open-item managed):", exc)
        else:
            raise AssertionError("113100 is not managed on an open item basis")

        # 8) employee tolerances (T043T): JDOE is in group JUNI (1000 EUR per document, 1.00 difference)
        def jdoe_doc(amount):
            return DocumentRequest(bukrs=BUKRS, blart="SA", bldat=date(2026, 5, 9), budat=date(2026, 5, 9),
                                   waers="EUR", usnam="JDOE", bktxt="Tolerance test", lines=[
                                       LineRequest(bschl="40", account="476000", wrbtr=D(amount)),
                                       LineRequest(bschl="50", account="113100", wrbtr=D(amount))])
        try:
            post_document(s, jdoe_doc("1500.00"))
        except PostingError as exc:
            print("8 rejected (user limit):", exc)
        else:
            raise AssertionError("JDOE may not post 1500 EUR")
        post_document(s, jdoe_doc("900.00"))
        inv8 = _customer_invoice(s, date(2026, 5, 10), "595.00", "500.00", ref="PAY-8")
        k8 = _partner_line(inv8, "D")
        try:
            post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 5, 11),
                                           amount=D("593.50"), hkont=BANK, items=[k8], usnam="JDOE"))
        except PostingError as exc:
            print("8 rejected (JDOE difference 1.50 > 1.00):", str(exc)[:70])
        else:
            raise AssertionError("JDOE may only write off 1.00")

        # 9) reason codes (T053R): 01 is charged off to bank charges 479000; 02 goes to the residual item
        bank_fees = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 5, 11),
                                                   amount=D("593.50"), hkont=BANK, items=[k8], rstgr="01"))
        fee_doc = s.get(AccountingDocumentHeader, (MANDT, BUKRS, bank_fees["belnr"], bank_fees["gjahr"]))
        fee = next(i for i in fee_doc.items if i.rstgr == "01")
        print(f"9 Difference {bank_fees['difference']} with reason 01 -> {fee.hkont} ({fee.sgtxt})")
        assert fee.hkont == "479000" and fee.wrbtr == D("1.50")
        inv9 = _customer_invoice(s, date(2026, 5, 10), "238.00", "200.00", ref="PAY-9")
        res9 = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 5, 11),
                                              amount=D("200.00"), hkont=BANK, items=[_partner_line(inv9, "D")],
                                              mode="residual", rstgr="02"))
        res_doc = s.get(AccountingDocumentHeader, (MANDT, BUKRS, res9["belnr"], res9["gjahr"]))
        assert any(i.rstgr == "02" and i.wrbtr == D("38.00") for i in res_doc.items), "residual carries the reason"

        # 5) error paths
        inv5 = _customer_invoice(s, date(2026, 5, 2), "119.00", "100.00", ref="PAY-5")
        k5 = _partner_line(inv5, "D")
        for bad, why in [
            (PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 5, 3),
                            amount=D("100.00"), hkont=BANK, items=[k5]), "difference remains"),
            (PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 5, 3),
                            amount=D("100.00"), hkont=BANK, items=[k1]), "already cleared"),
            (PaymentRequest(bukrs=BUKRS, koart="K", account=VEND, budat=date(2026, 5, 3),
                            amount=D("119.00"), hkont=BANK, items=[k5]), "wrong partner"),
        ]:
            try:
                post_payment(s, bad)
            except PostingError as exc:
                print(f"5 rejected ({why}): {exc}")
            else:
                raise AssertionError(f"expected rejection: {why}")
        assert _item(s, k5).augbl is None
        post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 5, 3),
                                       amount=D("119.00"), hkont=BANK, items=[k5]))

        tb = reporting.trial_balance(s, MANDT, BUKRS, 2026)
        print("\nCash discount granted 880000:", reporting.account_balance(s, MANDT, BUKRS, 2026, "880000")["balance"])
        print("Cash discount received 276000:", reporting.account_balance(s, MANDT, BUKRS, 2026, "276000")["balance"])
        print(f"Trial balance: debit {tb['total_debit']}  credit {tb['total_credit']}  balanced={tb['balanced']}")
        assert tb["balanced"], "Trial balance not balanced!"
        print("\nOK - payments, discounts, partial/residual items and clearing posted; the ledger balances.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
