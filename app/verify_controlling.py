"""End-to-end check for Controlling: CO documents from FI, actual cost reports,
assessment and distribution cycles.

Run after app.seed (rerunnable):  python -m app.verify_controlling
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models.controlling import CODocumentHeader, COLineItem
from app.services import allocation, controlling
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, LineRequest, post_document
from app.services.reversal import reverse_document

MANDT, BUKRS, KOKRS = "100", "1000", "1000"
ADMIN, SALES, PROD, ORDER = "0000001000", "0000002000", "0000003000", "000000400001"
D = Decimal


def _co_docs_for(s, belnr, gjahr):
    return s.scalars(select(CODocumentHeader).where(
        CODocumentHeader.mandt == MANDT, CODocumentHeader.refbn == belnr, CODocumentHeader.refgj == gjahr)).all()


def _balance(s, objnr, year=2026, perio=(1, 16)):
    return sum(controlling.object_balance(s, MANDT, KOKRS, objnr, year, *perio).values(), D("0"))


def main() -> None:
    s = SessionLocal()
    try:
        admin = controlling.cost_center_objnr(KOKRS, ADMIN)
        order = controlling.order_objnr(ORDER)
        admin_before, order_before = _balance(s, admin), _balance(s, order)

        # 1) FI posting with a cost center and an order line -> one CO document (COIN) referencing FI
        fi = post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="KR", bldat=date(2026, 10, 5), budat=date(2026, 10, 5), waers="EUR",
            bktxt="Fair stand and supplies", lines=[
                LineRequest(bschl="31", account="0000020000", wrbtr=D("800.00")),
                LineRequest(bschl="40", account="476000", wrbtr=D("500.00"), kostl=ADMIN),
                LineRequest(bschl="40", account="476000", wrbtr=D("300.00"), aufnr=ORDER),
            ]))
        cos = _co_docs_for(s, fi.belnr, fi.gjahr)
        assert len(cos) == 1, cos
        co = cos[0]
        lines = s.scalars(select(COLineItem).where(COLineItem.mandt == MANDT, COLineItem.kokrs == KOKRS,
                                                   COLineItem.belnr == co.belnr).order_by(COLineItem.buzei)).all()
        print(f"1 FI {fi.belnr} -> CO {co.belnr} ({co.vrgng}, period {co.perab}): "
              + ", ".join(f"{l.objnr} {l.wkgbtr}" for l in lines))
        assert co.belnr.startswith("2") and co.vrgng == "COIN" and co.awtyp == "BKPF"
        assert [(l.objnr, l.wkgbtr) for l in lines] == [(admin, D("500.00")), (order, D("300.00"))]
        assert _balance(s, admin) == admin_before + D("500.00") and _balance(s, order) == order_before + D("300.00")

        report = {r["object"]: r for r in controlling.actuals(s, MANDT, KOKRS, 2026, kind="KS")}
        assert {ADMIN, SALES, PROD} <= set(report), "every cost center is listed"
        assert report[ADMIN]["total"] == _balance(s, admin)

        # 2) reversing the FI document writes a second CO document with the opposite values
        rev = reverse_document(s, MANDT, BUKRS, fi.belnr, fi.gjahr)
        rev_co = _co_docs_for(s, rev.belnr, rev.gjahr)
        print(f"2 Reversal {rev.belnr} -> CO {rev_co[0].belnr}")
        assert len(rev_co) == 1 and _balance(s, admin) == admin_before and _balance(s, order) == order_before

        # 3) assessment ADMIN-ASM and distribution SALES-DST for period 11/2026
        sales, prod = controlling.cost_center_objnr(KOKRS, SALES), controlling.cost_center_objnr(KOKRS, PROD)
        post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="SA", bldat=date(2026, 11, 10), budat=date(2026, 11, 10), waers="EUR",
            bktxt="November costs", lines=[
                LineRequest(bschl="40", account="476000", wrbtr=D("1000.00"), kostl=ADMIN),
                LineRequest(bschl="40", account="476000", wrbtr=D("200.00"), kostl=SALES),
                LineRequest(bschl="50", account="113100", wrbtr=D("1200.00")),
            ]))
        for cycle in ("SALES-DST", "ADMIN-ASM"):  # rerunnable: undo a previous run of this period
            try:
                allocation.reverse_run(s, MANDT, KOKRS, cycle, 2026, 11)
            except PostingError:
                pass
        nov = (11, 11)
        sent = sum(v for k, v in controlling.object_balance(s, MANDT, KOKRS, admin, 2026, 11, 11).items()
                   if "400000" <= k <= "499999")
        test = allocation.run_cycle(s, MANDT, KOKRS, "ADMIN-ASM", 2026, 11, test=True)
        shares = {l["kostl"]: l["amount"] for l in test["lines"] if l["role"] == "receiver"}
        print(f"3 ADMIN-ASM test run: admin sends {test['sent']} -> sales {shares[SALES]}, production {shares[PROD]}")
        assert test["document"] is None and test["sent"] == sent
        assert shares[SALES] == (sent * D("0.6")).quantize(D("0.01")) and shares[SALES] + shares[PROD] == sent
        sales_before, prod_before = _balance(s, sales, perio=nov), _balance(s, prod, perio=nov)
        run = allocation.run_cycle(s, MANDT, KOKRS, "ADMIN-ASM", 2026, 11)
        print(f"  Posted CO document {run['document']} (RKIU)")
        assert _balance(s, admin, perio=nov) == 0, "the admin cost center is fully assessed"
        assert _balance(s, sales, perio=nov) == sales_before + shares[SALES]
        try:
            allocation.run_cycle(s, MANDT, KOKRS, "ADMIN-ASM", 2026, 11)
        except PostingError as exc:
            print(f"  Second run rejected: {exc}")
        else:
            raise AssertionError("a cycle must not run twice for a period")

        office = controlling.object_balance(s, MANDT, KOKRS, sales, 2026, 11, 11).get("476000", D("0"))
        dist = allocation.run_cycle(s, MANDT, KOKRS, "SALES-DST", 2026, 11)
        print(f"  SALES-DST distributed {dist['sent']} on 476000 to production (CO {dist['document']}, RKIV)")
        assert dist["sent"] == office
        assert not controlling.object_balance(s, MANDT, KOKRS, sales, 2026, 11, 11).get("476000")
        assert all(l["kstar"] == "476000" for l in dist["lines"]), "distribution keeps the primary cost element"
        assert _balance(s, prod, perio=nov) == prod_before + shares[PROD] + office

        rev = allocation.reverse_run(s, MANDT, KOKRS, "ADMIN-ASM", 2026, 11)
        print(f"  Reversed {rev['reversed']} by {rev['reversal']}; admin carries its costs again")
        assert _balance(s, admin, perio=nov) == sent
        again = allocation.run_cycle(s, MANDT, KOKRS, "ADMIN-ASM", 2026, 11)
        assert again["document"] and _balance(s, admin, perio=nov) == 0
        print("\nOK - CO documents, cost reports, assessment, distribution and cycle reversal are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
