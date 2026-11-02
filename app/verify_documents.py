"""End-to-end check for the document lifecycle: park, change parked (FBV2), post
parked, delete parked, reverse (FB08), reset clearing (FBRA), asset reversal
(AB08) and mass reversal (F.80).

Run after app.seed:  python -m app.verify_documents
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.controlling import COLineItem
from app.models.assets import AssetValues
from app.models.documents import AccountingDocumentHeader
from app.services import reporting
from app.services.clearing import PaymentRequest, post_payment
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, LineRequest, delete_parked, post_document, post_parked
from app.services import asset_accounting as aa
from app.services.reversal import mass_reverse, reset_clearing, reverse_document

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

        # 5) change a parked document (FBV2): same number, new lines
        draft = post_document(s, _vendor_invoice(bstat="V"))
        changed = _vendor_invoice(bstat="V")
        changed.belnr = draft.belnr
        changed.lines[0].wrbtr = D("1190.00")
        changed.lines[1].wrbtr, changed.lines[1].kostl = D("1000.00"), "0000002000"
        changed = post_document(s, changed)
        print(f"5 Changed parked {changed.belnr}: lines {[(i.bschl, str(i.wrbtr), i.kostl) for i in changed.items]}")
        assert changed.belnr == draft.belnr and changed.bstat == "V" and len(changed.items) == 3
        assert changed.items[1].wrbtr == D("1000.00") and changed.items[1].kostl == "0000002000"
        assert changed.items[2].wrbtr == D("190.00"), "auto tax recalculated"
        expense = _balance(s, "476000")
        post_parked(s, MANDT, BUKRS, changed.belnr, changed.gjahr)
        assert _balance(s, "476000") == expense + D("1000.00")

        # 6) asset reversal (AB08): depreciation and acquisition are taken back out of ANLC
        anln1 = datetime.now().strftime("%m%d%H%M%S").zfill(12)
        aa.create_asset(s, MANDT, BUKRS, anln1, "00003000", "Test press", useful_life_years=5, kostl="0000001000")
        acq = aa.post_acquisition(s, MANDT, BUKRS, anln1, D("12000.00"), date(2026, 1, 10),
                                  offset_account=VEND, offset_is_vendor=True)
        dep = next(d for d in aa.run_depreciation(s, MANDT, BUKRS, 2026, 1)["posted"] if d["anln1"] == anln1)
        val = lambda: s.get(AssetValues, (MANDT, BUKRS, anln1, "0000", 2026, "01"))  # noqa: E731
        print(f"6 Asset {anln1}: APC {val().answl}, depreciation {val().nafag}")
        assert val().answl == D("12000.00") and val().nafag == D("200.00")
        reverse_document(s, MANDT, BUKRS, dep["belnr"], 2026)
        s.expire_all()
        assert val().nafag == 0, "reversed depreciation leaves the asset"
        reverse_document(s, MANDT, BUKRS, acq["belnr"], acq["gjahr"])
        s.expire_all()
        print(f"  After AB08: APC {val().answl}, retirements {val().abgan}, depreciation {val().nafag}")
        assert val().answl == 0 and (val().abgan or 0) == 0

        # 7) mass reversal (F.80): failures are reported per document
        docs = [post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="SA", bldat=date(2026, 7, 5), budat=date(2026, 7, 5), waers="EUR",
            bktxt=f"Mass test {n}", lines=[
                LineRequest(bschl="40", account="476000", wrbtr=D("10.00")),
                LineRequest(bschl="50", account="113100", wrbtr=D("10.00")),
            ])) for n in (1, 2)]
        result = mass_reverse(s, MANDT, BUKRS, [(d.belnr, d.gjahr) for d in docs] + [(orig.belnr, orig.gjahr)])
        print(f"7 Mass reversal: {[(r['belnr'], r['reversal'] or r['error'][:30]) for r in result]}")
        assert [bool(r["reversal"]) for r in result] == [True, True, False]

        tb = reporting.trial_balance(s, MANDT, BUKRS, 2026)
        print(f"Trial balance: debit {tb['total_debit']}  credit {tb['total_credit']}  balanced={tb['balanced']}")
        assert tb["balanced"]
        print("\nOK - park / post / delete, reversal and reset clearing behave as in SAP; the ledger balances.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
