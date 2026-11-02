"""End-to-end check for the dunning program (F150).

Creates a fresh test customer (so the check is exact and rerunnable), posts
invoices and a credit memo, and runs three dunning runs: level 1, a run inside
the dunning interval, and level 2 with charges. Run after app.seed:
python -m app.verify_dunning
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.database import SessionLocal
from app.models.documents import AccountingDocumentItem
from app.models.partners import Customer, CustomerCompanyCode, CustomerDunningData
from app.services import dunning
from app.services.posting import DocumentRequest, LineRequest, post_document

MANDT, BUKRS = "100", "1000"
D = Decimal


def _invoice(s, kunnr, budat, gross, net, *, credit=False, ref=None):
    doc = post_document(s, DocumentRequest(
        bukrs=BUKRS, blart="DR", bldat=budat, budat=budat, waers="EUR", xblnr=ref,
        bktxt="Credit memo" if credit else "Sales invoice", lines=[
            LineRequest(bschl="11" if credit else "01", account=kunnr, wrbtr=D(gross), sgtxt=ref),
            LineRequest(bschl="40" if credit else "50", account="800000", wrbtr=D(net),
                        mwskz="A1", calculate_tax=True),
        ]))
    return next((i.belnr, i.gjahr, i.buzei) for i in doc.items if i.koart == "D")


def _run(s, kunnr, laufi, ausdt):
    run = dunning.create_proposal(s, MANDT, laufd=ausdt, laufi=laufi, ausdt=ausdt, bukrs=BUKRS,
                                  kunnr_low=kunnr, kunnr_high=kunnr)
    acct = next(a for a in dunning.run_summary(run)["accounts"])
    print(f"Run {ausdt} {laufi}: level {acct['mahns']} (was {acct['mahnv']}), overdue {acct['salhw']}, "
          f"charge {acct['mahng']}, notice={acct['xmflg']} {acct['reason'] or ''}")
    return run, acct


def main() -> None:
    s = SessionLocal()
    try:
        kunnr = datetime.now().strftime("%d%H%M%S").zfill(10)
        s.merge(Customer(mandt=MANDT, kunnr=kunnr, ktokd="KUNA", name1="Delta Test KG", land1="DE",
                         ort01="Cologne", pstlz="50667", stras="Domplatz 1", spras="E"))
        s.merge(CustomerCompanyCode(mandt=MANDT, kunnr=kunnr, bukrs=BUKRS, akont="140000", zterm="0001"))
        s.add(CustomerDunningData(mandt=MANDT, kunnr=kunnr, bukrs=BUKRS, maber="", mahna="0001"))
        s.commit()

        inv1 = _invoice(s, kunnr, date(2026, 8, 1), "1190.00", "1000.00", ref="DN-1")   # due 2026-08-01
        inv2 = _invoice(s, kunnr, date(2026, 9, 10), "595.00", "500.00", ref="DN-2")    # due 2026-09-10
        _invoice(s, kunnr, date(2026, 8, 15), "119.00", "100.00", credit=True, ref="CM-1")

        # 1) 31 days in arrears would reach level 3, but a level rises by one per run
        run1, a1 = _run(s, kunnr, f"D{kunnr[-4:]}1", date(2026, 9, 1))
        assert a1["xmflg"] and a1["mahns"] == 1 and a1["salhw"] == D("1071.00") and a1["mahng"] == 0
        assert all(i["belnr"] != inv2[0] for i in a1["items"]), "DN-2 is not due yet"
        html = dunning.notice_html(s, MANDT, run1.laufd, run1.laufi, kunnr)
        assert "Payment reminder" in html and "Delta Test KG" in html and "1,071.00" in html
        dunning.execute(s, MANDT, run1.laufd, run1.laufi)
        item1 = s.get(AccountingDocumentItem, (MANDT, BUKRS, *inv1))
        knb5 = s.get(CustomerDunningData, (MANDT, kunnr, BUKRS, ""))
        assert item1.manst == 1 and item1.madat == date(2026, 9, 1) and knb5.mahns == 1

        # 2) inside the 14-day interval: listed, no notice
        _, a2 = _run(s, kunnr, f"D{kunnr[-4:]}2", date(2026, 9, 10))
        assert not a2["xmflg"] and "next notice" in a2["reason"]

        # 3) DN-1 rises to level 2 (charge 5.00); DN-2 is 10 days overdue -> level 1
        run3, a3 = _run(s, kunnr, f"D{kunnr[-4:]}3", date(2026, 9, 20))
        levels = {i["belnr"]: i["mahnn"] for i in a3["items"]}
        assert a3["xmflg"] and a3["mahns"] == 2 and a3["mahng"] == D("5.00")
        assert levels[inv1[0]] == 2 and levels[inv2[0]] == 1 and a3["salhw"] == D("1666.00")
        dunning.execute(s, MANDT, run3.laufd, run3.laufi)
        assert "Second reminder" in dunning.notice_html(s, MANDT, run3.laufd, run3.laufi, kunnr)
        assert s.get(AccountingDocumentItem, (MANDT, BUKRS, *inv2)).manst == 1
        assert s.get(CustomerDunningData, (MANDT, kunnr, BUKRS, "")).mahns == 2
        print("\nOK - dunning levels, interval, credit offset, charges and notices behave as specified.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
