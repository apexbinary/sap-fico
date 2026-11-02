"""End-to-end check for the document lifecycle: park, post parked, delete parked,
reverse (FB08) and reset clearing (FBRA).

Run after app.seed:  python -m app.verify_documents
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.controlling import COLineItem
from app.models.documents import AccountingDocumentHeader
from app.services import reporting
from app.services.clearing import PaymentRequest, post_payment
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, LineRequest, delete_parked, post_document, post_parked
from app.services.reversal import reset_clearing, reverse_document

MANDT, BUKRS = "100", "1000"
CUST, VEND = "0000010000", "0000020000"
D = Decimal


def _balance(s, saknr):
    return reporting.account_balance(s, MANDT, BUKRS, 2026, saknr)["balance"]


def _co_total(s, belnr):
    return s.scalar(select(func.coalesce(func.sum(COLineItem.wkgbtr), 0)).where(
        COLineItem.mandt == MANDT, COLineItem.refbn == belnr)) or D("0")


def _open(s, koart, account, belnr):
    return [o for o in reporting.open_items(s, MANDT, BUKRS, koart, account) if o["belnr"] == belnr]


def _expect_error(fn, why):
    try:
        fn()
    except PostingError as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def _vendor_invoice(bstat=" "):
    return DocumentRequest(
        bukrs=BUKRS, blart="KR", bldat=date(2026, 7, 1), budat=date(2026, 7, 1), waers="EUR",
        bktxt="Office supplies", kokrs="1000", bstat=bstat, lines=[
            LineRequest(bschl="31", account=VEND, wrbtr=D("595.00"), sgtxt="DOC-TEST"),
            LineRequest(bschl="40", account="476000", wrbtr=D("500.00"), mwskz="V1", calculate_tax=True,
                        kostl="0000001000"),
        ])


def main() -> None:
    s = SessionLocal()
    try:
        # 1) park: numbered and stored, but no totals, CO or open items
        expense = _balance(s, "476000")
        parked = post_document(s, _vendor_invoice(bstat="V"))
        print(f"1 Parked {parked.belnr}/{parked.gjahr} (status {parked.bstat!r})")
        assert parked.bstat == "V" and _balance(s, "476000") == expense
        assert not _open(s, "K", VEND, parked.belnr) and _co_total(s, parked.belnr) == 0

        posted = post_parked(s, MANDT, BUKRS, parked.belnr, parked.gjahr)
        print(f"  Posted parked {posted.belnr}: expense +{_balance(s, '476000') - expense}, CO {_co_total(s, posted.belnr)}")
        assert posted.bstat == " " and posted.belnr == parked.belnr, "posting keeps the parked number"
        assert _balance(s, "476000") == expense + D("500.00") and _co_total(s, posted.belnr) == D("500.00")
        assert len(_open(s, "K", VEND, posted.belnr)) == 1
        _expect_error(lambda: post_parked(s, MANDT, BUKRS, posted.belnr, posted.gjahr), "already posted")

        # 2) park and delete
        dropped = post_document(s, _vendor_invoice(bstat="V"))
        delete_parked(s, MANDT, BUKRS, dropped.belnr, dropped.gjahr)
        dropped = s.get(AccountingDocumentHeader, (MANDT, BUKRS, dropped.belnr, dropped.gjahr))
        print(f"2 Deleted parked {dropped.belnr} (status {dropped.bstat!r})")
        assert dropped.bstat == "Z"
        _expect_error(lambda: post_parked(s, MANDT, BUKRS, dropped.belnr, dropped.gjahr), "deleted")

        # 3) reverse the posted vendor invoice: totals, CO and open items net to zero
        rev = reverse_document(s, MANDT, BUKRS, posted.belnr, posted.gjahr)
        orig = s.get(AccountingDocumentHeader, (MANDT, BUKRS, posted.belnr, posted.gjahr))
        print(f"3 Reversed {orig.belnr} by {rev.belnr}: keys {[i.bschl for i in orig.items]} -> {[i.bschl for i in rev.items]}")
        assert [i.bschl for i in rev.items] == ["22", "50", "50"]
        assert orig.stblg == rev.belnr and rev.stblg == orig.belnr and rev.stgrd == "01"
        assert _balance(s, "476000") == expense and _co_total(s, orig.belnr) + _co_total(s, rev.belnr) == 0
        assert not _open(s, "K", VEND, orig.belnr) and not _open(s, "K", VEND, rev.belnr), "items clear each other"
        _expect_error(lambda: reverse_document(s, MANDT, BUKRS, orig.belnr, orig.gjahr), "already reversed")

        # 4) a paid invoice: reversal blocked until FBRA resets (and reverses) the payment
        inv = post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="DR", bldat=date(2026, 7, 2), budat=date(2026, 7, 2), waers="EUR",
            bktxt="Sales invoice", lines=[
                LineRequest(bschl="01", account=CUST, wrbtr=D("1190.00"), sgtxt="DOC-TEST"),
                LineRequest(bschl="50", account="800000", wrbtr=D("1000.00"), mwskz="A1", calculate_tax=True),
            ]))
        key = next((i.belnr, i.gjahr, i.buzei) for i in inv.items if i.koart == "D")
        pay = post_payment(s, PaymentRequest(bukrs=BUKRS, koart="D", account=CUST, budat=date(2026, 7, 3),
                                             amount=D("1190.00"), hkont="113100", items=[key]))
        print(f"4 Invoice {inv.belnr} paid by {pay['belnr']}")
        _expect_error(lambda: reverse_document(s, MANDT, BUKRS, inv.belnr, inv.gjahr), "invoice is cleared")
        reset = reset_clearing(s, MANDT, BUKRS, pay["belnr"], pay["gjahr"], reverse=True)
        print(f"  FBRA reset {reset['reset_items']} item(s), payment reversed by {reset['reversal']['belnr']}")
        assert reset["reset_items"] == 2 and len(_open(s, "D", CUST, inv.belnr)) == 1
        inv_rev = reverse_document(s, MANDT, BUKRS, inv.belnr, inv.gjahr, budat=date(2026, 7, 4), stgrd="02")
        print(f"  Invoice reversed by {inv_rev.belnr} on {inv_rev.budat} (reason {inv_rev.stgrd})")
        assert not _open(s, "D", CUST, inv.belnr)
        assert any(i.hkont == "175000" and i.shkzg == "S" and i.wrbtr == D("190.00") for i in inv_rev.items)

        tb = reporting.trial_balance(s, MANDT, BUKRS, 2026)
        print(f"Trial balance: debit {tb['total_debit']}  credit {tb['total_credit']}  balanced={tb['balanced']}")
        assert tb["balanced"]
        print("\nOK - park / post / delete, reversal and reset clearing behave as in SAP; the ledger balances.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
