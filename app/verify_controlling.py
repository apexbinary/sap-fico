"""End-to-end check for Controlling: CO documents from FI and actual cost reports.

Run after app.seed (rerunnable):  python -m app.verify_controlling
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models.controlling import CODocumentHeader, COLineItem
from app.services import controlling
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
        print("\nOK - CO documents (COBK/COEP) mirror FI postings and feed the actual cost reports.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
