"""End-to-end check for the GST returns (GSTR-1, GSTR-3B).

In May 2027: B2B intra- and inter-state invoices, a B2CL invoice (unregistered, inter-state,
above 1 lakh), B2CS invoices (unregistered, inter and intra), a credit note to a registered
customer (CDNR), a nil-rated invoice (Table 8 only), an export (EXP, zero-rated), a canceled
invoice (documents issued), and A/P invoices / a credit memo (ITC). Each section changes by
exactly these documents; GSTR-3B output tax and ITC agree with the tax accounts of the
journal; the ITC set-off follows the IGST-first rule; the JSON has the GSTN layout.

Run after app.seed (rerunnable):  python -m app.verify_gstreturns
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import documents as docs
from app.services import gst_returns as gr
from app.services import reports
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
Y, M = 2027, 5
DAY = date(2027, 5, 12)
KEYS = ("taxable", "igst", "cgst", "sgst", "cess")

# extra customers: unregistered (Tamil Nadu = inter, Karnataka = intra) and an export customer (USA)
CUSTOMERS = [("C90001", "Walk-in Chennai", "TN", "IN", None, "U"), ("C90002", "Walk-in Bengaluru", "KA", "IN", None, "U"),
             ("C90003", "Globex Corp (USA)", None, "US", None, "U")]


def _customers(s) -> None:
    for code, name, state, country, gstin, gst_type in CUSTOMERS:
        if s.get(BusinessPartner, code) is None:
            s.add(BusinessPartner(card_code=code, card_name=name, card_type="C", group_code=100, currency="##",
                                  deb_pay_acct="114000", group_num=1, list_num=1, vat_group="OCS18", country=country,
                                  balance=D(0), dnotes_bal=D(0), orders_bal=D(0), frozen_for="N", bill_to_def="Main",
                                  ship_to_def="Main", credit_line=D(0)))
            s.flush()
            for kind in ("B", "S"):
                s.add(PartnerAddress(card_code=code, adres_type=kind, address="Main", street="1 Main Street", city=name,
                                     state=state, country=country, gst_regn_no=gstin, gst_type=gst_type))
            s.flush()
    s.commit()


def _sec(r: dict, name: str) -> dict:
    return r["totals"][name]


def _delta(a: dict, b: dict) -> dict:
    return {k: b[k] - a[k] for k in KEYS if k in a}


def _b2cs(r: dict, pos: str, supply: str) -> dict:
    row = next((x for x in r["b2cs"] if x["pos"] == pos and x["supply"] == supply and x["rate"] == 18), None)
    return {k: row[k] if row else D(0) for k in KEYS}


def _unreg(r: dict, pos: str) -> dict:
    row = next((x for x in r["inter_state_unregistered"] if x["pos"] == pos), None)
    return {"taxable": row["taxable"] if row else D(0), "igst": row["igst"] if row else D(0)}


def _inv(s, card: str, qty: int, vat: str | None = None, obj: str = "13", item: str = "S00001", price: D = D(1500)):
    return docs.create_document(s, DR(obj=obj, doc_date=DAY, card_code=card, disc_prcnt=D(0), lines=[
        DL(item_code=item, quantity=D(qty), vat_group=vat, price=price)]))


def main() -> None:
    # set-off rule (no data needed)
    p = gr.set_off({"igst": D(100), "cgst": D(50), "sgst": D(50), "cess": D(0)},
                   {"igst": D(120), "cgst": D(10), "sgst": D(60), "cess": D(0)})
    used = {(u["credit"], u["against"]): u["amount"] for u in p["used"]}
    assert used == {("igst", "igst"): 100, ("igst", "cgst"): 20, ("cgst", "cgst"): 10, ("sgst", "sgst"): 50}, used
    assert p["cash"] == {"igst": 0, "cgst": 20, "sgst": 0, "cess": 0} and p["credit_left"]["sgst"] == 10
    print("1 Set-off: IGST credit 120 -> IGST 100 + CGST 20; CGST 10 -> CGST; SGST 60 -> SGST 50 (10 left, never "
          "against CGST); cash CGST 20")

    s = SessionLocal()
    try:
        _customers(s)
        r1a, r3a = gr.gstr1(s, Y, M), gr.gstr3b(s, Y, M)
        b2b1 = _inv(s, "C10000", 2)             # intra, registered: 3000, CGST 270 + SGST 270
        _inv(s, "C20000", 1)                    # inter, registered: 1500, IGST 270
        b2cl = _inv(s, "C90001", 100)           # inter, unregistered, 1,77,000 > 1 lakh: B2CL
        _inv(s, "C90001", 2)                    # inter, unregistered, small: B2CS INTER 33
        _inv(s, "C90002", 1)                    # intra, unregistered: B2CS INTRA 29
        _inv(s, "C10000", 1, obj="14")          # credit note to registered: CDNR 1500
        _inv(s, "C10000", 1, vat="ONIL")        # nil-rated: Table 8 only
        exp = _inv(s, "C90003", 4, vat="ONIL")  # export without payment of tax: EXP WOPAY 6000
        cancel = _inv(s, "C10000", 1)
        docs.cancel_document(s, "13", cancel.doc_entry, DAY)
        _inv(s, "V10000", 2, obj="18", item="C00001", price=D(1000))   # ITC intra: CGST 180 + SGST 180
        _inv(s, "V20000", 1, obj="18", item="C00001", price=D(1000))   # ITC inter: IGST 180
        _inv(s, "V10000", 1, obj="19", item="C00001", price=D(1000))   # A/P credit memo: ITC -90 / -90
        _inv(s, "V10000", 1, obj="18", item="C00001", vat="INIL", price=D(500))  # exempt inward (intra) 500
        r1, r3 = gr.gstr1(s, Y, M), gr.gstr3b(s, Y, M)

        assert len(r1["b2b"]) - len(r1a["b2b"]) == 2, "nil-only invoice and canceled invoice are not B2B"
        assert _delta(_sec(r1a, "b2b"), _sec(r1, "b2b")) == {"taxable": 4500, "igst": 270, "cgst": 270, "sgst": 270, "cess": 0}
        row = next(x for x in r1["b2b"] if x["doc_entry"] == b2b1.doc_entry)
        assert row["gstin"] == "29AABCM1234F1Z1" and row["pos"] == "29" and row["invoice_type"] == "R"
        print(f"2 B2B: +2 invoices (taxable 4,500, IGST 270, CGST 270, SGST 270); invoice {row['doc_num']} to {row['gstin']}, POS {row['pos']}")

        cl = next(x for x in r1["b2cl"] if x["doc_entry"] == b2cl.doc_entry)
        assert cl["pos"] == "33" and cl["value"] == D(177000) and cl["items"][0]["igst"] == D(27000)
        assert _delta(_b2cs(r1a, "33", "INTER"), _b2cs(r1, "33", "INTER")) == {"taxable": 3000, "igst": 540, "cgst": 0, "sgst": 0, "cess": 0}
        assert _delta(_b2cs(r1a, "29", "INTRA"), _b2cs(r1, "29", "INTRA")) == {"taxable": 1500, "igst": 0, "cgst": 135, "sgst": 135, "cess": 0}
        print("3 B2CL: invoice 1,77,000 to an unregistered buyer in Tamil Nadu (POS 33, IGST 27,000); "
              "B2CS: POS 33 inter +3,000 / IGST 540, POS 29 intra +1,500 / CGST + SGST 135 each")

        assert _delta(_sec(r1a, "cdnr"), _sec(r1, "cdnr")) == {"taxable": 1500, "igst": 0, "cgst": 135, "sgst": 135, "cess": 0}
        nil = lambda r: next(x for x in r["nil"] if x["supply"] == "Intra-state to registered")["nil"]  # noqa: E731
        assert nil(r1) - nil(r1a) == 1500
        ex = next(x for x in r1["exp"] if x["doc_entry"] == exp.doc_entry)
        assert ex["type"] == "WOPAY" and ex["pos"] == "96" and ex["items"][0]["taxable"] == 6000 and ex["items"][0]["rate"] == 0
        di = next(x for x in r1["doc_issue"] if x["nature"].startswith("Invoices"))
        di_a = next((x for x in r1a["doc_issue"] if x["nature"].startswith("Invoices")), {"canceled": 0, "total": 0})
        assert di["canceled"] - di_a["canceled"] == 1 and di["total"] - di_a["total"] == 8
        print(f"4 CDNR +1,500; nil-rated intra-state to registered +1,500; export {ex['doc_num']} WOPAY 6,000 at 0 %; "
              f"documents issued {di['from']}-{di['to']}, {di['canceled']} canceled")

        hsn = gr._sum(r1["hsn"]["b2b"] + r1["hsn"]["b2c"])
        assert all(abs(hsn[k] - r1["total"][k]) <= D("0.01") for k in KEYS) and not [i for i in r1["issues"] if "HSN summary" in i]
        assert any(h["hsn"] == "998713" and h["uqc"] == "NA" for h in r1["hsn"]["b2b"])
        print(f"5 HSN summary (B2B {len(r1['hsn']['b2b'])} / B2C {len(r1['hsn']['b2c'])} rows) = document totals; services with UQC NA")

        o, oa = r3["outward"], r3a["outward"]
        assert _delta(oa["a_taxable"], o["a_taxable"]) == {"taxable": 157500, "igst": 27810, "cgst": 270, "sgst": 270, "cess": 0}
        assert o["b_zero_rated"]["taxable"] - oa["b_zero_rated"]["taxable"] == 6000
        assert o["c_nil_exempt"]["taxable"] - oa["c_nil_exempt"]["taxable"] == 1500
        assert _delta(_unreg(r3a, "33") | {"cess": 0, "cgst": 0, "sgst": 0}, _unreg(r3, "33") | {"cess": 0, "cgst": 0, "sgst": 0}) \
            == {"taxable": 153000, "igst": 27540, "cgst": 0, "sgst": 0, "cess": 0}
        itc, itca = r3["itc"]["available_other"], r3a["itc"]["available_other"]
        assert {k: itc[k] - itca[k] for k in gr.HEADS} == {"igst": 180, "cgst": 90, "sgst": 90, "cess": 0}
        assert r3["exempt_inward"]["intra"] - r3a["exempt_inward"]["intra"] == 500
        print("6 GSTR-3B: 3.1(a) +1,57,500 (IGST 27,810, CGST 270, SGST 270), 3.1(b) +6,000, 3.1(c) +1,500; "
              "3.2 POS 33 +1,53,000 / IGST 27,540; ITC IGST +180, CGST +90, SGST +90; exempt inward +500")

        # the whole month agrees with the tax accounts of the journal
        tr = reports.tax_report(s, *gr.period(Y, M))
        comp = {x["component"]: x for x in tr["summary"]}
        for head, code in (("igst", "IGST"), ("cgst", "CGST"), ("sgst", "SGST")):
            assert r3["liability"][head] == comp.get(code, {}).get("output", 0), (head, r3["liability"][head], comp.get(code))
            assert r3["itc"]["net"][head] == comp.get(code, {}).get("input", 0), (head, r3["itc"]["net"][head], comp.get(code))
        pay = r3["payment"]
        for head in ("igst", "cgst", "sgst"):
            assert pay["cash"][head] + sum(u["amount"] for u in pay["used"] if u["against"] == head) == max(r3["liability"][head], 0)
        print(f"7 Liability = output tax of the journal, ITC = input tax; cash to pay IGST {pay['cash']['igst']}, "
              f"CGST {pay['cash']['cgst']}, SGST {pay['cash']['sgst']}")

        j1, j3 = gr.gstr1_json(s, Y, M), gr.gstr3b_json(s, Y, M)
        assert j1["fp"] == "052027" and j1["gstin"] == "29AAACD1234E1Z5"
        ctin = next(x for x in j1["b2b"] if x["ctin"] == "29AABCM1234F1Z1")
        inv = next(i for i in ctin["inv"] if i["inum"] == str(b2b1.doc_num))
        assert inv["idt"] == "12-05-2027" and inv["itms"][0]["itm_det"] == {"rt": 18.0, "txval": 3000.0, "iamt": 0.0, "csamt": 0.0,
                                                                          "camt": 270.0, "samt": 270.0}
        assert j3["ret_period"] == "052027" and j3["sup_details"]["osup_det"]["txval"] == float(o["a_taxable"]["taxable"])
        assert any(x["exp_typ"] == "WOPAY" for x in j1["exp"]) and any(x["pos"] == "33" for x in j1["b2cl"])
        print("8 JSON: GSTR-1 (fp 052027, b2b / b2cl / b2cs / exp / cdnr / nil / hsn / doc_issue) and GSTR-3B (ret_period, "
              "sup_details, inter_sup, itc_elg, inward_sup)")
        print("\nOK - GSTR-1 and GSTR-3B agree with the documents and the journal.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
