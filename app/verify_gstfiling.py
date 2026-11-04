"""End-to-end check for the GST filing status, the lock of filed months and GSTR-1 amendments.

September 2027: invoices to a registered (B2B) and an unregistered (B2CS) customer, an A/P invoice;
GSTR-1 and GSTR-3B are marked as filed (snapshot kept). The month is locked: A/R / A/P postings, ITC
reversals and direct cancellations are refused; an A/P document is canceled with a date in October.
In October both invoices are amended (replacement + cancellation of the original): GSTR-1 reports B2BA
with the original number / date and B2CSA with revised = filed + change; the replacements are not in
B2B again; GSTR-3B of October changes by exactly the differences and still equals the journal; the
September return is unchanged. Undoing the filing unlocks the month.

Run after app.seed (rerunnable):  python -m app.verify_gstfiling
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import documents as docs
from app.services import gst_filing, gst_itc, reports
from app.services import gst_returns as gr
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
SEP, OCT = date(2027, 9, 15), date(2027, 10, 5)
KEYS = ("taxable", "igst", "cgst", "sgst", "cess")
PARTNERS = [("C95001", "Registered Retail Pvt Ltd", "C", 100, "29AABCR1234F1Z5", "R"), ("C95002", "Walk-in Mysuru", "C", 100, None, "U"),
            ("V95007", "Bengaluru Services LLP", "S", 102, "29AABCB1234F1Z5", "R")]


def _partners(s) -> None:
    for code, name, typ, group, gstin, gst_type in PARTNERS:
        if s.get(BusinessPartner, code) is None:
            s.add(BusinessPartner(card_code=code, card_name=name, card_type=typ, group_code=group, currency="##",
                                  deb_pay_acct="114000" if typ == "C" else "211000", group_num=1, list_num=1 if typ == "C" else 3,
                                  vat_group="OCS18" if typ == "C" else "ICS18", country="IN", lic_trad_num=gstin, balance=D(0), dnotes_bal=D(0),
                                  orders_bal=D(0), frozen_for="N", bill_to_def="Main", ship_to_def="Main", credit_line=D(0)))
            s.flush()
            for kind in ("B", "S"):
                s.add(PartnerAddress(card_code=code, adres_type=kind, address="Main", street="1 MG Road", city="Bengaluru", state="KA",
                                     country="IN", gst_regn_no=gstin, gst_type=gst_type))
            s.flush()
    s.commit()


def _refused(s, fn, text: str) -> None:
    try:
        fn()
    except B1Error as exc:
        assert text in str(exc), exc
        s.rollback()
        return
    raise AssertionError(f"expected refusal: {text}")


def _inv(s, card, qty, price, on=SEP, obj="13"):
    return docs.create_document(s, DR(obj=obj, doc_date=on, card_code=card, disc_prcnt=D(0), lines=[
        DL(item_code="S00001", quantity=D(qty), price=D(price), vat_group="OCS18")]))


def _req(card, qty, price, on=OCT, obj="13"):
    return DR(obj=obj, doc_date=on, card_code=card, disc_prcnt=D(0), lines=[DL(item_code="S00001", quantity=D(qty), price=D(price), vat_group="OCS18")])


def _agrees(s, y, m) -> dict:
    r3 = gr.gstr3b(s, y, m)
    comp = {x["component"]: x for x in reports.tax_report(s, *gr.period(y, m))["summary"]}
    for head, code in (("igst", "IGST"), ("cgst", "CGST"), ("sgst", "SGST")):
        assert r3["liability"][head] == comp.get(code, {}).get("output", 0), (y, m, head, r3["liability"][head], comp.get(code))
        assert r3["itc"]["net"][head] == comp.get(code, {}).get("input", 0), (y, m, head, r3["itc"]["net"][head], comp.get(code))
    return r3


def main() -> None:
    with SessionLocal() as s:
        _partners(s)
        for ret in ("GSTR1", "GSTR3B"):  # a run that stopped half-way left September filed
            if gst_filing.get(s, ret, 2027, 9):
                gst_filing.unfile(s, ret, 2027, 9)
        b2b = _inv(s, "C95001", 2, 1500)
        b2c = _inv(s, "C95002", 1, 1500)
        keep = _inv(s, "C95001", 1, 1500)
        ap = docs.create_document(s, DR(obj="18", doc_date=SEP, card_code="V95007", doc_type="S", disc_prcnt=D(0), num_at_card="SV-9",
                                        lines=[DL(acct_code="611000", price=D(10000), vat_group="ICS18")]))
        oct_before = _agrees(s, 2027, 10)
        g1 = gr.gstr1(s, 2027, 9)
        f1 = gst_filing.file_return(s, "GSTR1", 2027, 9, date(2027, 10, 11), "AA2909270001234")
        f3 = gst_filing.file_return(s, "GSTR3B", 2027, 9, date(2027, 10, 20), "AA2909270005678")
        _refused(s, lambda: gst_filing.file_return(s, "GSTR1", 2027, 9), "already marked as filed")
        assert gst_filing.status(s, "GSTR1", 2027, 9)["arn"] == "AA2909270001234" and gst_filing.snapshot(s, "GSTR1", 2027, 9)["documents"] == g1["documents"]
        print(f"1 September: invoices {b2b.doc_num} (B2B) / {b2c.doc_num} (B2CS) / {keep.doc_num}, A/P invoice {ap.doc_num}; "
              f"GSTR-1 filed (ARN {f1.arn}), GSTR-3B filed (ARN {f3.arn}); filing twice refused")

        _refused(s, lambda: _inv(s, "C95001", 1, 100), "GSTR-1 for 09/2027 is filed")
        _refused(s, lambda: docs.create_document(s, DR(obj="18", doc_date=SEP, card_code="V95007", doc_type="S",
                                                       lines=[DL(acct_code="611000", price=D(100), vat_group="ICS18")])), "GSTR-3B for 09/2027 is filed")
        _refused(s, lambda: gst_itc.post(s, "B1", SEP, {"cgst": 1}), "GSTR-3B for 09/2027 is filed")
        _refused(s, lambda: docs.cancel_document(s, "13", b2b.doc_entry, OCT), "amend the document")
        _refused(s, lambda: docs.cancel_document(s, "18", ap.doc_entry), "cancellation date in an open month")
        _refused(s, lambda: docs.cancel_document(s, "18", ap.doc_entry, date(2027, 9, 30)), "cancellation date in an open month")
        _refused(s, lambda: gst_filing.amend(s, "13", keep.doc_entry, _req("C95002", 1, 1500)), "same document type for the same business partner")
        _refused(s, lambda: gst_filing.amend(s, "13", keep.doc_entry, _req("C95001", 1, 1500, on=date(2027, 9, 1))), "on or after")
        print("2 Locked: A/R and A/P postings, ITC reversals in September refused; invoices are amended, not canceled; "
              "the A/P invoice needs a cancellation date in an open month")

        def csa_change() -> D:  # change of September POS 29 / intra / 18 % already amended in October (earlier runs)
            x = next((x for x in gr.gstr1(s, 2027, 10)["amendments"]["b2csa"] if x["omon"] == "092027" and x["pos"] == "29" and x["rate"] == 18), None)
            return x["change"]["taxable"] if x else D(0)

        csa_before = csa_change()
        new_b2b = gst_filing.amend(s, "13", b2b.doc_entry, _req("C95001", 3, 1500))
        new_b2c = gst_filing.amend(s, "13", b2c.doc_entry, _req("C95002", 1, 2000))
        docs.cancel_document(s, "18", ap.doc_entry, date(2027, 10, 6))
        s.refresh(b2b)
        assert b2b.canceled == "Y" and b2b.cancel_date == OCT and new_b2b.amnd_entry == b2b.doc_entry
        open_inv = _inv(s, "C95001", 1, 100, on=date(2027, 10, 7))
        _refused(s, lambda: gst_filing.amend(s, "13", open_inv.doc_entry, _req("C95001", 1, 200)), "is not filed")
        print(f"3 Invoice {b2b.doc_num} amended by {new_b2b.doc_num} (3 instead of 2 units), {b2c.doc_num} by {new_b2c.doc_num} (2,000 instead of 1,500), "
              f"both originals canceled on {OCT}; A/P invoice canceled on 06.10.2027; an invoice of an open month is not amended")

        r1 = gr.gstr1(s, 2027, 10)
        a = r1["amendments"]
        row = next(x for x in a["b2ba"] if x["doc_entry"] == new_b2b.doc_entry)
        assert row["original_num"] == b2b.doc_num and row["original_date"] == SEP and gr._sum(row["items"])["taxable"] == 4500
        assert not any(x["doc_entry"] in (new_b2b.doc_entry, new_b2c.doc_entry) for x in r1["b2b"])
        snap = gst_filing.snapshot(s, "GSTR1", 2027, 9)
        filed = next(x for x in snap["b2cs"] if x["pos"] == "29" and x["supply"] == "INTRA" and D(str(x["rate"])) == 18)
        csa = next(x for x in a["b2csa"] if x["omon"] == "092027" and x["pos"] == "29" and x["rate"] == 18)
        assert csa["change"]["taxable"] - csa_before == 500 and csa["taxable"] == D(str(filed["taxable"])) + csa["change"]["taxable"]
        j1 = gr.gstr1_json(s, 2027, 10)
        assert any(i["oinum"] == str(b2b.doc_num) and i["inum"] == str(new_b2b.doc_num) for c in j1["b2ba"] for i in c["inv"])
        assert any(x["omon"] == "092027" for x in j1["b2csa"])
        inv_issue = next(x for x in r1["doc_issue"] if x["nature"].startswith("Invoices"))
        assert inv_issue["to"] >= new_b2c.doc_num
        print(f"4 GSTR-1 October: B2BA {b2b.doc_num} -> {new_b2b.doc_num} taxable 4,500; B2CSA 09/2027 POS 29 18 %: revised = filed {filed['taxable']} + change (+500); "
              "replacements not in B2B; JSON b2ba / b2csa; replacements counted in documents issued")

        oct_after = _agrees(s, 2027, 10)
        da = {k: oct_after["outward"]["a_taxable"][k] - oct_before["outward"]["a_taxable"][k] for k in KEYS}
        assert da == {"taxable": 2100, "igst": 0, "cgst": 189, "sgst": 189, "cess": 0}, da
        di = {k: oct_after["itc"]["net"][k] - oct_before["itc"]["net"][k] for k in ("igst", "cgst", "sgst")}
        assert di == {"igst": 0, "cgst": -900, "sgst": -900}, di
        sep_live, sep_snap = gr.gstr1(s, 2027, 9), gst_filing.snapshot(s, "GSTR1", 2027, 9)
        assert all(abs(sep_live["total"][k] - D(str(sep_snap["total"][k]))) <= D("0.01") for k in KEYS)
        _agrees(s, 2027, 9)
        print("5 GSTR-3B October: 3.1(a) +2,100 (amendments +2,000 and a new invoice +100; CGST / SGST +189), ITC -900 / -900 "
              "(A/P invoice canceled); = journal; September still equals what was filed")

        gst_filing.unfile(s, "GSTR3B", 2027, 9)
        gst_filing.unfile(s, "GSTR1", 2027, 9)
        _refused(s, lambda: gst_filing.unfile(s, "GSTR1", 2027, 9), "is not filed")
        late = _inv(s, "C95001", 1, 100)
        docs.cancel_document(s, "13", late.doc_entry)
        print("6 Undo filing: September is open again (an invoice can be posted and canceled)")
    print("\nOK - GST filing status, period lock and GSTR-1 amendments work.")


if __name__ == "__main__":
    main()
