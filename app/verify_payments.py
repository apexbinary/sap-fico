"""End-to-end check for payments & clearing (F-28 / F-53 / F-32 / F-44).

Covers: payment with cash discount, partial payment, residual item, clearing a
residual against a credit memo, vendor payment with discount received, and the
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
