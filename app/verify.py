"""End-to-end smoke test: post real documents and print the resulting reports.

Run:  python -m app.verify   (run app.seed first)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.services import reporting
from app.services.posting import DocumentRequest, LineRequest, post_document

BUKRS = "1000"


def _print_doc(title, header):
    print(f"\n{title}: {header.blart} {header.belnr}/{header.gjahr}  period {header.monat}")
    for it in header.items:
        side = "DR" if it.shkzg == "S" else "CR"
        acct = it.kunnr or it.lifnr or it.hkont
        print(f"   {it.buzei:>3} {side} PK{it.bschl} {acct:<12} {it.wrbtr:>12} {header.waers}"
              + (f"  tax={it.mwskz}" if it.mwskz else "")
              + (f"  CC={it.kostl}" if it.kostl else ""))


def main() -> None:
    s = SessionLocal()
    try:
        # 1) Customer invoice with output tax (FB70 style)
        inv = post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="DR", bldat=date(2026, 3, 15), budat=date(2026, 3, 15),
            waers="EUR", bktxt="Sales invoice", tcode="FB70",
            lines=[
                LineRequest(bschl="01", account="0000010000", wrbtr=Decimal("1190.00"),
                            sgtxt="Customer receivable", zuonr="INV-001"),
                LineRequest(bschl="50", account="800000", wrbtr=Decimal("1000.00"),
                            mwskz="A1", calculate_tax=True, sgtxt="Revenue"),
            ],
        ))
        _print_doc("Customer invoice", inv)

        # 2) Vendor invoice with input tax + cost center (FB60 style, FI->CO)
        vinv = post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="KR", bldat=date(2026, 3, 20), budat=date(2026, 3, 20),
            waers="EUR", bktxt="Supplier invoice", tcode="FB60", kokrs="1000",
            lines=[
                LineRequest(bschl="31", account="0000020000", wrbtr=Decimal("595.00"),
                            sgtxt="Vendor payable", zuonr="PO-7788"),
                LineRequest(bschl="40", account="476000", wrbtr=Decimal("500.00"),
                            mwskz="V1", calculate_tax=True, kostl="0000001000",
                            sgtxt="Office supplies"),
            ],
        ))
        _print_doc("Vendor invoice", vinv)

        # 3) G/L document: capital contribution to bank (FB01 style)
        gl = post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="SA", bldat=date(2026, 1, 1), budat=date(2026, 1, 1),
            waers="EUR", bktxt="Opening capital",
            lines=[
                LineRequest(bschl="40", account="113100", wrbtr=Decimal("10000.00"), sgtxt="Bank"),
                LineRequest(bschl="50", account="100000", wrbtr=Decimal("10000.00"), sgtxt="Capital"),
            ],
        ))
        _print_doc("G/L document", gl)

        # 4) two lines on the same account in a year without totals yet (one GLT0 row per account/side)
        split = post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="SA", bldat=date(2028, 1, 15), budat=date(2028, 1, 15),
            waers="EUR", bktxt="Split expense", lines=[
                LineRequest(bschl="40", account="476000", wrbtr=Decimal("10.00")),
                LineRequest(bschl="40", account="476000", wrbtr=Decimal("5.00")),
                LineRequest(bschl="50", account="113100", wrbtr=Decimal("15.00")),
            ],
        ))
        _print_doc("Split G/L document", split)
        assert reporting.trial_balance(s, "100", BUKRS, 2028)["balanced"]

        # --- Trial balance ---
        tb = reporting.trial_balance(s, "100", BUKRS, 2026)
        print("\nTRIAL BALANCE  company code", BUKRS, "FY", tb["gjahr"])
        print(f"   {'Account':<10}{'Name':<32}{'Debit':>14}{'Credit':>14}")
        for ln in tb["lines"]:
            print(f"   {ln['saknr']:<10}{(ln['name'] or ''):<32}{ln['debit']:>14}{ln['credit']:>14}")
        print(f"   {'':<42}{tb['total_debit']:>14}{tb['total_credit']:>14}")
        print("   BALANCED:", tb["balanced"])

        # --- Open items ---
        print("\nOPEN ITEMS  customer 0000010000:")
        for oi in reporting.open_items(s, "100", BUKRS, "D", "0000010000"):
            print(f"   {oi['belnr']}/{oi['gjahr']}  {oi['amount']:>12} {oi['waers']}  {oi['sgtxt']}")
        print("OPEN ITEMS  vendor 0000020000:")
        for oi in reporting.open_items(s, "100", BUKRS, "K", "0000020000"):
            print(f"   {oi['belnr']}/{oi['gjahr']}  {oi['amount']:>12} {oi['waers']}  {oi['sgtxt']}")

        assert tb["balanced"], "Trial balance is not balanced!"
        print("\nOK - all documents posted and the ledger balances.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
