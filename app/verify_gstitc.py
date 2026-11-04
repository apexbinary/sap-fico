"""End-to-end check for blocked ITC, ITC reversals / reclaims and the GSTR-2B reconciliation.

In August 2027: a bill with a blocked tax code (IBC18, section 17(5): the vendor charges the GST, it is
posted to 618000 instead of input tax and reported in GSTR-3B 4(A) and 4(B)(1)); a permanent reversal
(B1), a temporary reversal (B2) and a reclaim (D1, capped at what is still reversed); GSTR-3B 4(B)(1) /
4(B)(2) / 4(D)(1) / 4(C) and the JSON; liability / net ITC still agree with the journal, also after
canceling. GSTR-2B: a portal JSON with a matching invoice (other spelling of the number), an amount
mismatch, an invoice only on the portal and a credit note (CDNR); an A/P invoice missing on the
portal shows as "only in books". Wrong setups are refused.

Run after app.seed (rerunnable):  python -m app.verify_gstitc
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.documents import DOCUMENT_CLASSES
from app.models.finance import JournalLine
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import documents as docs
from app.services import gst_itc, reports, tax
from app.services import gst_returns as gr
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
Y, M = 2027, 8
DAY = date(2027, 8, 10)
HEADS = ("igst", "cgst", "sgst", "cess")
VENDORS = [("V95005", "Karnataka Office Supplies", "KA", "29AABCK1234F1Z5"), ("V95006", "Delhi Electronics Pvt Ltd", "DL", "07AABCD1234E1Z3")]


def _vendors(s) -> None:
    for code, name, state, gstin in VENDORS:
        if s.get(BusinessPartner, code) is None:
            s.add(BusinessPartner(card_code=code, card_name=name, card_type="S", group_code=102, currency="##", deb_pay_acct="211000",
                                  group_num=1, list_num=3, vat_group="ICS18", country="IN", lic_trad_num=gstin, balance=D(0), dnotes_bal=D(0),
                                  orders_bal=D(0), frozen_for="N", bill_to_def="Main", ship_to_def="Main", credit_line=D(0)))
            s.flush()
            for kind in ("B", "S"):
                s.add(PartnerAddress(card_code=code, adres_type=kind, address="Main", street="1 Main Road", city=name, state=state, country="IN",
                                     gst_regn_no=gstin, gst_type="R"))
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


def _bill(s, card, amount, vat, ref, obj="18"):
    return docs.create_document(s, DR(obj=obj, doc_date=DAY, card_code=card, doc_type="S", disc_prcnt=D(0), num_at_card=ref,
                                      lines=[DL(acct_code="611000", price=D(amount), vat_group=vat)]))


def _d(a: dict, b: dict) -> dict:
    return {h: b[h] - a[h] for h in HEADS}


def _agrees(s) -> dict:
    r3 = gr.gstr3b(s, Y, M)
    comp = {x["component"]: x for x in reports.tax_report(s, *gr.period(Y, M))["summary"]}
    for head, code in (("igst", "IGST"), ("cgst", "CGST"), ("sgst", "SGST")):
        assert r3["liability"][head] == comp.get(code, {}).get("output", 0), (head, r3["liability"][head], comp.get(code))
        assert r3["itc"]["net"][head] == comp.get(code, {}).get("input", 0), (head, r3["itc"]["net"][head], comp.get(code))
    for h in HEADS:
        assert r3["itc"]["net"][h] == r3["itc"]["available"][h] - r3["itc"]["reversed"][h]
    return r3


def main() -> None:
    with SessionLocal() as s:
        _vendors(s)
        _refused(s, lambda: tax.save_tax_code(s, "XND1", "bad", "O", [("IGST", D(18))], non_dedct=D(100), non_ded_acc="618000"), "Only input tax")
        _refused(s, lambda: tax.save_tax_code(s, "XND2", "bad", "I", [("IGST", D(18))], non_dedct=D(50)), "non-deductible tax")
        print("1 Non-deductible tax only on input codes and with an account")

        run = s.scalar(select(func.count()).select_from(DOCUMENT_CLASSES["18"][0]).where(DOCUMENT_CLASSES["18"][0].card_code == "V95005")) + 1
        before = _agrees(s)
        car = _bill(s, "V95005", 10000, "IBC18", None)
        assert car.doc_total == 11800 and car.vat_sum == 1800
        je = {}
        for l in s.scalars(select(JournalLine).where(JournalLine.trans_id == car.trans_id)):
            je[l.short_name] = je.get(l.short_name, D(0)) + l.debit - l.credit
        assert je == {"611000": 10000, "618000": 1800, "V95005": -11800}, je
        print(f"2 Blocked credit {car.doc_num} (IBC18): vendor 11,800 incl. GST; the GST 1,800 is posted to 618000, not to input tax")

        b1 = gst_itc.post(s, "B1", DAY, {"cgst": 200, "sgst": 200}, "Rule 42 common credit")
        b2 = gst_itc.post(s, "B2", DAY, {"igst": 1000}, "Rule 37: not paid in 180 days")
        left = gst_itc.still_reversed(s)["igst"]
        _refused(s, lambda: gst_itc.post(s, "D1", DAY, {"igst": left + 1}), "can be reclaimed")
        d1 = gst_itc.post(s, "D1", DAY, {"igst": 600}, "Paid: reclaim")
        _refused(s, lambda: gst_itc.post(s, "B1", DAY, {}), "Enter the IGST")
        after = _agrees(s)
        it, ib = after["itc"], before["itc"]
        assert _d(ib["reversed_rules"], it["reversed_rules"]) == {"igst": 0, "cgst": 1100, "sgst": 1100, "cess": 0}
        assert _d(ib["reversed_others"], it["reversed_others"]) == {"igst": 1000, "cgst": 0, "sgst": 0, "cess": 0}
        assert _d(ib["reclaimed"], it["reclaimed"]) == {"igst": 600, "cgst": 0, "sgst": 0, "cess": 0}
        assert _d(ib["available_other"], it["available_other"]) == {"igst": 600, "cgst": 900, "sgst": 900, "cess": 0}
        assert _d(ib["net"], it["net"]) == {"igst": -400, "cgst": -200, "sgst": -200, "cess": 0}
        j3 = gr.gstr3b_json(s, Y, M)
        rul = next(x for x in j3["itc_elg"]["itc_rev"] if x["ty"] == "RUL")
        assert rul["camt"] == float(it["reversed_rules"]["cgst"]) and j3["itc_elg"]["itc_net"]["iamt"] == float(it["net"]["igst"])
        print(f"3 JE {b1.number} B1 CGST / SGST 200, JE {b2.number} B2 IGST 1,000, JE {d1.number} D1 reclaim IGST 600 (more than reversed refused); "
              "GSTR-3B 4(B)(1) +1,100 / +1,100 (blocked + rule 42), 4(B)(2) IGST +1,000, 4(D)(1) +600, net = journal input tax")

        _refused(s, lambda: gst_itc.cancel(s, car.trans_id), "no ITC reversal")
        gst_itc.cancel(s, d1.trans_id)
        gst_itc.cancel(s, b2.trans_id)
        _refused(s, lambda: gst_itc.cancel(s, b2.trans_id), "already canceled")
        r3 = _agrees(s)
        assert _d(ib["reversed_others"], r3["itc"]["reversed_others"])["igst"] == 0 and _d(ib["reclaimed"], r3["itc"]["reclaimed"])["igst"] == 0
        rows = gst_itc.listing(s, DAY, DAY)["rows"]
        assert {r["trans_id"]: r["active"] for r in rows if r["trans_id"] in (b1.trans_id, b2.trans_id, d1.trans_id)} == \
            {b1.trans_id: True, b2.trans_id: False, d1.trans_id: False}
        print("4 Reclaim and temporary reversal canceled (journal reversed); 3B and the journal still agree; listing shows them canceled")

        ok = _bill(s, "V95005", 50000, "ICS18", f"AB/001-{run}")
        diff = _bill(s, "V95006", 20000, "ICS18", f"D-77-{run}")  # switched to IIG18 (Delhi)
        missing = _bill(s, "V95005", 1000, "ICS18", f"AB/002-{run}")
        cn = _bill(s, "V95005", 5000, "ICS18", f"CN-5-{run}", obj="19")
        assert diff.lines[0].vat_group == "IIG18"
        portal = {"data": {"gstin": "29AAACD1234E1Z5", "rtnprd": "082027", "docdata": {
            "b2b": [{"ctin": "29AABCK1234F1Z5", "trdnm": "Karnataka Office Supplies", "inv": [
                        {"inum": f"ab001{run}", "dt": "10-08-2027", "val": 59000, "pos": "29", "rev": "N", "itcavl": "Y",
                         "items": [{"rt": 18, "txval": 50000, "igst": 0, "cgst": 4500, "sgst": 4500, "cess": 0}]},
                        {"inum": f"X-999-{run}", "dt": "12-08-2027", "val": 1180, "pos": "29", "rev": "N", "itcavl": "Y",
                         "items": [{"rt": 18, "txval": 1000, "cgst": 90, "sgst": 90}]}]},
                    {"ctin": "07AABCD1234E1Z3", "trdnm": "Delhi Electronics", "inv": [
                        {"inum": f"D-77-{run}", "dt": "10-08-2027", "val": 23700, "pos": "29", "rev": "N", "itcavl": "Y",
                         "items": [{"rt": 18, "txval": 20000, "igst": 3700, "cgst": 0, "sgst": 0}]}]}],
            "cdnr": [{"ctin": "29AABCK1234F1Z5", "trdnm": "Karnataka Office Supplies", "nt": [
                        {"ntnum": f"CN-5-{run}", "typ": "C", "dt": "10-08-2027", "val": 5900, "items": [{"rt": 18, "txval": 5000, "cgst": 450, "sgst": 450}]}]}],
            "impg": [{"boenum": f"9{run:06d}", "boedt": "05-08-2027", "portcode": "INMAA1", "txval": 10000, "igst": 1800}]}}}
        res = gst_itc.reconcile(s, Y, M, portal)
        by = {(r["section"], str(r["number"])): r for r in res["rows"]}
        assert by[("B2B", f"ab001{run}")]["status"] == "matched" and by[("B2B", f"ab001{run}")]["doc_entry"] == ok.doc_entry
        m = by[("B2B", f"D-77-{run}")]
        assert m["status"] == "mismatch" and m["diff"]["igst"] == 100 and m["doc_entry"] == diff.doc_entry
        assert by[("B2B", f"X-999-{run}")]["status"] == "portal_only" and by[("IMPG", f"9{run:06d}")]["status"] == "portal_only"
        assert by[("CDNR", f"CN-5-{run}")]["status"] == "matched" and by[("CDNR", f"CN-5-{run}")]["doc_entry"] == cn.doc_entry
        assert by[("B2B", f"AB/002-{run}")]["status"] == "books_only" and by[("B2B", f"AB/002-{run}")]["doc_entry"] == missing.doc_entry
        assert res["summary"]["mismatch"]["count"] >= 1 and res["summary"]["matched"]["count"] >= 2
        _agrees(s)
        print(f"5 GSTR-2B: invoice AB/001-{run} matched as 'ab001{run}', D-77 IGST differs by 100, X-999 and a bill of entry only on the portal, "
              f"credit note CN-5 matched (CDNR), AB/002 only in books")
    print("\nOK - blocked ITC, ITC reversals / reclaims and the GSTR-2B reconciliation work.")


if __name__ == "__main__":
    main()
