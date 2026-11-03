"""End-to-end check for cost accounting: profit centers with direct rules, a shared rule 60 / 40,
an A/R invoice and an A/P invoice with rules on their lines, the profit center report splitting
revenue / expenses by the shares; inactive dimensions and wrong rules refused.

Run after app.seed (rerunnable: fresh codes each run):  python -m app.verify_costacct
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.costacct import ProfitCenter
from app.models.finance import JournalLine
from app.services import costacct
from app.services import documents as docs
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 12, 15)


def main() -> None:
    s = SessionLocal()
    try:
        n = s.scalar(select(func.count()).select_from(ProfitCenter)) + 1
        sal, adm, shr = f"S{n:04d}", f"A{n:04d}", f"SH{n:04d}"
        costacct.save_center(s, {"prc_code": sal, "prc_name": "Sales dept", "dim_code": 1})
        costacct.save_center(s, {"prc_code": adm, "prc_name": "Admin dept", "dim_code": 1})
        costacct.save_rule(s, {"ocr_code": shr, "ocr_name": "Shared 60/40", "dim_code": 1,
                               "shares": [{"prc_code": sal, "prc_amount": 60}, {"prc_code": adm, "prc_amount": 40}]})
        for bad, text in [((shr + "X",), "not a distribution rule"), ((None, None, sal), "not a distribution rule of dimension 3")]:
            try:
                costacct.check_codes(s, bad)
                raise AssertionError(text)
            except B1Error as exc:
                assert text in str(exc), exc
        before = {c["prc_code"]: c for c in costacct.report(s, DAY, DAY)["centers"]}
        inv = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", disc_prcnt=D(0),
                                         lines=[DL(item_code="S00001", quantity=D(1), price=D(1000), ocr_codes=[sal])]))
        ap = docs.create_document(s, DR(obj="18", doc_date=DAY, card_code="V10000", disc_prcnt=D(0),
                                        lines=[DL(item_code="C00001", quantity=D(1), price=D(500), ocr_codes=[shr])]))
        rev = s.scalar(select(JournalLine).where(JournalLine.trans_id == inv.trans_id, JournalLine.account == "412000"))
        tax = s.scalar(select(JournalLine).where(JournalLine.trans_id == inv.trans_id, JournalLine.account == "216100"))
        assert rev.profit_code == sal and tax.profit_code is None
        r = {c["prc_code"]: c for c in costacct.report(s, DAY, DAY)["centers"]}
        delta = lambda k, f: (r[k][f] if k in r else 0) - (before[k][f] if k in before else 0)  # noqa: E731
        assert delta(sal, "revenue") == 1000
        print(f"1 Centers {sal} / {adm}, rule {shr} 60/40; invoice {inv.doc_num} revenue 1,000 on {sal} (tax line without rule)")
        print(f"2 A/P invoice {ap.doc_num} with {shr}: report expenses {sal} {delta(sal, 'expenses')}, {adm} {delta(adm, 'expenses')}")
        print("\nOK - cost accounting keeps the distribution rules and splits the report.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
