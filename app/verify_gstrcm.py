"""End-to-end check for GST reverse charge and imports.

In July 2027: a goods transport agency bill under reverse charge (RCS5: the vendor charges no GST,
the company posts input CGST / SGST against its RCM liability), legal services from Delhi (RCS18 is
switched to RIG18 for the inter-state vendor), imported goods with a bill of entry (IMP18: IGST on
the bill of entry value, payable to customs, not part of the vendor total), an imported service
(RIG18, foreign vendor) and an RCM credit memo. GSTR-3B: 3.1(d) and ITC 4A(1) / 4A(2) / 4A(3) change by
exactly these documents, reverse charge is paid in cash, and liability / ITC still agree with the
journal (also after canceling a document). Wrong setups and bills of entry are refused.

Run after app.seed (rerunnable):  python -m app.verify_gstrcm
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models.finance import JournalLine
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import documents as docs
from app.services import gst_returns as gr
from app.services import reports, tax
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
Y, M = 2027, 7
DAY = date(2027, 7, 14)
HEADS = ("igst", "cgst", "sgst")

# vendors: unregistered transporter (Karnataka = intra), advocates (Delhi = inter), foreign suppliers
VENDORS = [("V95001", "Speedy Transport (GTA)", "KA", "IN"), ("V95002", "Lex Advocates Delhi", "DL", "IN"),
           ("V95003", "Shenzhen Parts Co (China)", None, "CN"), ("V95004", "CloudSoft Inc (USA)", None, "US")]


def _vendors(s) -> None:
    for code, name, state, country in VENDORS:
        if s.get(BusinessPartner, code) is None:
            s.add(BusinessPartner(card_code=code, card_name=name, card_type="S", group_code=102, currency="##",
                                  deb_pay_acct="211000", group_num=1, list_num=3, vat_group="ICS18", country=country,
                                  balance=D(0), dnotes_bal=D(0), orders_bal=D(0), frozen_for="N", bill_to_def="Main",
                                  ship_to_def="Main", credit_line=D(0)))
            s.flush()
            for kind in ("B", "S"):
                s.add(PartnerAddress(card_code=code, adres_type=kind, address="Main", street="1 Main Street", city=name,
                                     state=state, country=country, gst_type="U"))
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


def _je(s, doc) -> dict:
    out = {}
    for l in s.scalars(select(JournalLine).where(JournalLine.trans_id == doc.trans_id)):
        key = l.short_name if l.short_name != l.account else l.account
        out[key] = out.get(key, D(0)) + l.debit - l.credit
    return out


def _svc(s, card, amount, vat, obj="18", **kw):
    return docs.create_document(s, DR(obj=obj, doc_date=DAY, card_code=card, doc_type="S", disc_prcnt=D(0), **kw,
                                      lines=[DL(acct_code="611000", price=D(amount), vat_group=vat)]))


def _d(a: dict, b: dict, keys=("taxable", *HEADS)) -> dict:
    return {k: b[k] - a[k] for k in keys}


def main() -> None:
    with SessionLocal() as s:
        _vendors(s)
        _refused(s, lambda: tax.save_tax_code(s, "XRC1", "bad", "O", [("IGST", D(18))], rev_charge="Y"), "input (purchasing)")
        _refused(s, lambda: tax.save_tax_code(s, "XRC2", "bad", "I", [], rate=D(5), account="116000", rev_charge="Y"), "needs tax components")
        print("1 Reverse charge codes must be input codes with components")

        before = gr.gstr3b(s, Y, M)
        gta = _svc(s, "V95001", 10000, "RCS5")
        assert gta.doc_total == 10000 and gta.vat_sum == 0
        j = _je(s, gta)
        assert j == {"611000": 10000, "116100": 250, "116200": 250, "216400": -250, "216500": -250, "V95001": -10000}, j
        print(f"2 GTA bill {gta.doc_num} (RCS5): vendor 10,000 without GST; input CGST / SGST 250 each against RCM liability 216400 / 216500")

        legal = _svc(s, "V95002", 50000, "RCS18")
        assert legal.lines[0].vat_group == "RIG18" and legal.doc_total == 50000
        j = _je(s, legal)
        assert j["116300"] == 9000 and j["216600"] == -9000 and j["V95002"] == -50000, j
        print(f"3 Legal services {legal.doc_num} from Delhi: RCS18 switched to RIG18, IGST 9,000 on reverse charge")

        _refused(s, lambda: docs.create_document(s, DR(obj="18", doc_date=DAY, card_code="V95003", boe_value=D(46000), lines=[
            DL(item_code="A00001", quantity=D(1), price=D(20000), vat_group="ICS18")])), "import tax code")
        _refused(s, lambda: docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", boe_num="X1", lines=[
            DL(item_code="A00001", quantity=D(1))])), "A/P invoice or A/P credit memo")
        imp = docs.create_document(s, DR(obj="18", doc_date=DAY, card_code="V95003", disc_prcnt=D(0), boe_num="1234567", boe_date=DAY,
                                         boe_value=D(46000), port_code="INMAA1", lines=[
            DL(item_code="A00001", quantity=D(1), price=D(15000), vat_group="IMP18"),
            DL(item_code="A00002", quantity=D(1), price=D(25000), vat_group="IMP18")]))
        assert imp.doc_total == 40000 and imp.vat_sum == 0 and imp.boe_num == "1234567" and imp.port_code == "INMAA1"
        j = _je(s, imp)
        assert j["116300"] == 8280 and j["218000"] == -8280 and j["V95003"] == -40000, j
        assert s.scalar(select(JournalLine.vat_group).where(JournalLine.trans_id == imp.trans_id, JournalLine.account == "218000")) is None
        print(f"4 Import {imp.doc_num}: bill of entry 1234567 value 46,000 -> IGST 8,280 (17,250 / 28,750 per line) payable to customs 218000; "
              "vendor 40,000; bill of entry without import codes / on a sales document refused")

        saas = _svc(s, "V95004", 30000, "RIG18")
        assert _je(s, saas)["216600"] == -5400
        cm = _svc(s, "V95001", 4000, "RCS5", obj="19")
        assert _je(s, cm) == {"611000": -4000, "116100": -100, "116200": -100, "216400": 100, "216500": 100, "V95001": 4000}
        print(f"5 Imported service {saas.doc_num} (RIG18) IGST 5,400; RCM credit memo {cm.doc_num} reverses CGST / SGST 100 each")

        after = gr.gstr3b(s, Y, M)
        d31 = _d(before["outward"]["d_reverse_charge"], after["outward"]["d_reverse_charge"])
        assert d31 == {"taxable": 86000, "igst": 14400, "cgst": 150, "sgst": 150}, d31
        itc, itcb = after["itc"], before["itc"]
        assert _d(itcb["import_goods"], itc["import_goods"], HEADS) == {"igst": 8280, "cgst": 0, "sgst": 0}
        assert _d(itcb["import_services"], itc["import_services"], HEADS) == {"igst": 5400, "cgst": 0, "sgst": 0}
        assert _d(itcb["reverse_charge"], itc["reverse_charge"], HEADS) == {"igst": 9000, "cgst": 150, "sgst": 150}
        assert all(after["payment"]["reverse_charge_cash"][h] == max(after["outward"]["d_reverse_charge"][h], 0) for h in HEADS)
        print("6 GSTR-3B: 3.1(d) +86,000 (IGST 14,400, CGST 150, SGST 150); ITC 4A(1) import of goods IGST +8,280, "
              "4A(2) import of services +5,400, 4A(3) reverse charge IGST +9,000 / CGST +150 / SGST +150; RCM tax paid in cash")

        def agrees() -> dict:
            r3 = gr.gstr3b(s, Y, M)
            comp = {x["component"]: x for x in reports.tax_report(s, *gr.period(Y, M))["summary"]}
            for head, code in (("igst", "IGST"), ("cgst", "CGST"), ("sgst", "SGST")):
                assert r3["liability"][head] == comp.get(code, {}).get("output", 0), (head, r3["liability"][head], comp.get(code))
                assert r3["itc"]["net"][head] == comp.get(code, {}).get("input", 0), (head, r3["itc"]["net"][head], comp.get(code))
                pay = r3["payment"]
                assert pay["cash"][head] + sum(u["amount"] for u in pay["used"] if u["against"] == head) == max(r3["liability"][head], 0)
            return r3

        agrees()
        docs.cancel_document(s, "18", saas.doc_entry)
        r3 = agrees()
        assert _d(itcb["import_services"], r3["itc"]["import_services"], HEADS)["igst"] == 0
        j3 = gr.gstr3b_json(s, Y, M)
        impg = next(x for x in j3["itc_elg"]["itc_avl"] if x["ty"] == "IMPG")
        assert impg["iamt"] == float(r3["itc"]["import_goods"]["igst"]) and j3["sup_details"]["isup_rev"]["iamt"] == float(r3["outward"]["d_reverse_charge"]["igst"])
        print("7 Liability (incl. reverse charge) = output tax of the journal, ITC = input tax; canceling the imported service "
              "takes it out again; JSON IMPG / isup_rev filled")
    print("\nOK - GST reverse charge and imports post and report like B1 India.")


if __name__ == "__main__":
    main()
