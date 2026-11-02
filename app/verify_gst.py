"""End-to-end check for India GST: CGST + SGST within the state, IGST between states.

Company in Karnataka. Sales to Karnataka (CGST 9 % + SGST 9 % on their own output accounts),
to Maharashtra (the line's intra-state code switches to IGST 18 %), to a Karnataka customer
shipping to Maharashtra (the ship-to state is the place of supply), a 12 % item, purchases
from Delhi (input IGST) and Karnataka (input CGST + SGST); the GST report of the period
matches the postings; GSTIN validation.

Run after app.seed (rerunnable, uses its own posting date):  python -m app.verify_gst
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models.finance import Account, JournalLine
from app.models.partners import PartnerAddress
from app.services import masterdata, reports
from app.services import documents as docs
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 1, 15)


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def _tax_lines(s, doc) -> dict[str, Decimal]:
    """Tax postings of a document by account (credit positive for output, debit positive for input)."""
    out = {}
    for l in s.scalars(select(JournalLine).where(JournalLine.trans_id == doc.trans_id, JournalLine.vat_group.is_not(None))):
        out[l.account] = out.get(l.account, D(0)) + (l.credit - l.debit if l.credit else l.debit - l.credit)
    return out


def main() -> None:
    s = SessionLocal()
    try:
        bal = lambda code: s.get(Account, code).curr_total  # noqa: E731
        before = reports.tax_report(s, DAY, DAY)

        # 1) intra-state sale (Karnataka -> Karnataka): CGST 9 % + SGST 9 %
        inv1 = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", disc_prcnt=D(0),
                                          lines=[DL(item_code="S00001", quantity=D(2))]))
        t1 = _tax_lines(s, inv1)
        print(f"1 A/R invoice {inv1.doc_num} to Karnataka: net {inv1.doc_total - inv1.vat_sum}, tax code {inv1.lines[0].vat_group}, "
              f"CGST {t1.get('216100')}, SGST {t1.get('216200')}, total {inv1.doc_total}")
        assert inv1.lines[0].vat_group == "OCS18" and t1 == {"216100": D(270), "216200": D(270)} and inv1.doc_total == D(3540)

        # 2) inter-state sale (Karnataka -> Maharashtra): the intra-state code becomes IGST 18 %
        inv2 = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C20000", disc_prcnt=D(0),
                                          lines=[DL(item_code="S00001", quantity=D(2), vat_group="OCS18")]))
        t2 = _tax_lines(s, inv2)
        print(f"2 A/R invoice {inv2.doc_num} to Maharashtra: tax code {inv2.lines[0].vat_group}, IGST {t2.get('216300')}")
        assert inv2.lines[0].vat_group == "OIG18" and t2 == {"216300": D("486")}  # wholesale 1350 x 2 = 2700 x 18 %

        # 3) place of supply is the ship-to state: Karnataka customer shipping to Maharashtra
        if s.get(PartnerAddress, ("C10000", "S", "Mumbai site")) is None:
            masterdata.save_address(s, "C10000", "S", "Mumbai site", {"street": "BKC 5", "city": "Mumbai", "zip_code": "400051",
                                                                      "state": "MH", "country": "IN"})
        inv3 = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", ship_to_code="Mumbai site",
                                          disc_prcnt=D(0), lines=[DL(item_code="S00001", quantity=D(1))]))
        print(f"3 A/R invoice {inv3.doc_num} shipped to Mumbai: tax code {inv3.lines[0].vat_group}")
        assert inv3.lines[0].vat_group == "OIG18"

        # 4) 12 % item, inter-state
        inv4 = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C20000", doc_type="S", disc_prcnt=D(0),
                                          lines=[DL(dscription="Paper supply", acct_code="411000", price=D(1000), vat_group="OCS12")]))
        assert inv4.lines[0].vat_group == "OIG12" and inv4.doc_total == D(1120)

        # 5) purchases: Delhi vendor -> input IGST; Karnataka vendor -> input CGST + SGST
        ap1 = docs.create_document(s, DR(obj="18", doc_date=DAY, card_code="V20000", doc_type="S", disc_prcnt=D(0),
                                         lines=[DL(dscription="Stationery", acct_code="611000", price=D(500), vat_group="ICS18")]))
        ap2 = docs.create_document(s, DR(obj="18", doc_date=DAY, card_code="V10000", doc_type="S", disc_prcnt=D(0),
                                         lines=[DL(dscription="Repairs", acct_code="611000", price=D(500), vat_group="ICS18")]))
        print(f"5 A/P invoices: Delhi {ap1.lines[0].vat_group} {_tax_lines(s, ap1)}, Karnataka {ap2.lines[0].vat_group} {_tax_lines(s, ap2)}")
        assert ap1.lines[0].vat_group == "IIG18" and _tax_lines(s, ap1) == {"116300": D(90)}
        assert ap2.lines[0].vat_group == "ICS18" and _tax_lines(s, ap2) == {"116100": D(45), "116200": D(45)}

        # 6) GST report of the day: what was added equals the postings above
        after = reports.tax_report(s, DAY, DAY)
        delta = {r["component"]: r for r in after["summary"]}
        prev = {r["component"]: r for r in before["summary"]}
        diff = lambda comp, k: delta[comp][k] - (prev[comp][k] if comp in prev else 0)  # noqa: E731
        print(f"6 GST report {DAY}: output CGST {diff('CGST', 'output')}, SGST {diff('SGST', 'output')}, IGST {diff('IGST', 'output')}; "
              f"input CGST {diff('CGST', 'input')}, SGST {diff('SGST', 'input')}, IGST {diff('IGST', 'input')}")
        assert (diff("CGST", "output"), diff("SGST", "output"), diff("IGST", "output")) == (D(270), D(270), D(486) + D(270) + D(120))
        assert (diff("CGST", "input"), diff("SGST", "input"), diff("IGST", "input")) == (D(45), D(45), D(90))
        assert after["net_payable"] == after["total_output"] - after["total_input"]
        assert bal("216300") <= 0 and bal("116300") >= 0  # output tax is a credit, input tax a debit balance

        # 7) GSTIN validation
        _rejects(lambda: masterdata.save_address(s, "C10000", "B", "Bad", {"state": "KA", "country": "IN",
                                                                          "gst_regn_no": "27AABCM1234F1Z1"}), "GSTIN of another state")
        _rejects(lambda: masterdata.save_address(s, "C10000", "B", "Bad", {"state": "KA", "country": "IN",
                                                                          "gst_regn_no": "29ABC"}), "malformed GSTIN")
        print("\nOK - GST components, place of supply and the GST report are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
