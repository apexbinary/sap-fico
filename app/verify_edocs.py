"""End-to-end check for India e-documents (e-invoice IRN, e-way bill).

IRN formula and financial year; INV-01 payload of an intra-state B2B invoice (seller / buyer
PIN and state codes, HSN, values that add up); B2C and disabled e-invoicing refused; test-mode
IRN with QR code; a document with an active IRN / e-way bill cannot be canceled; IRN cancel
only with a reason, a remark and within 24 hours; live mode imports the IRP response only when
its IRN belongs to the document; e-way bill validity (1 day per 200 km, ends 23:59:59), Part A
only until the vehicle is entered, transport checks; export payload (URP, POS 96); delivery
challan; settings restored at the end.

Run after app.seed (rerunnable):  python -m app.verify_edocs
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.database import SessionLocal
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import documents as docs
from app.services import edocs, printing
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 6, 7)
EXTRA = [("C90011", "Walk-in Mysuru", "KA", "IN", "570001"), ("C90013", "Initech LLC (USA)", None, "US", None)]


def _refused(fn, text: str) -> None:
    try:
        fn()
    except B1Error as exc:
        assert text in str(exc), exc
        return
    raise AssertionError(f"expected refusal: {text}")


def _customers(s) -> None:
    for code, name, state, country, pin in EXTRA:
        if s.get(BusinessPartner, code) is None:
            s.add(BusinessPartner(card_code=code, card_name=name, card_type="C", group_code=100, currency="##",
                                  deb_pay_acct="114000", group_num=1, list_num=1, vat_group="OCS18", country=country,
                                  balance=D(0), dnotes_bal=D(0), orders_bal=D(0), frozen_for="N", bill_to_def="Main",
                                  ship_to_def="Main", credit_line=D(0)))
            s.flush()
            for kind in ("B", "S"):
                s.add(PartnerAddress(card_code=code, adres_type=kind, address="Main", street="1 Main Street", city=name,
                                     zip_code=pin, state=state, country=country, gst_type="U"))
            s.flush()
    s.commit()


def _doc(s, obj: str, card: str, item: str, qty: int, price: int, vat: str | None = None):
    return docs.create_document(s, DR(obj=obj, doc_date=DAY, card_code=card, disc_prcnt=D(0), lines=[
        DL(item_code=item, quantity=D(qty), price=D(price), vat_group=vat)]))


def main() -> None:
    assert edocs.financial_year(date(2027, 3, 31)) == "2026-27" and edocs.financial_year(date(2027, 4, 1)) == "2027-28"
    import hashlib

    assert edocs.irn_hash("29AAACD1234E1Z5", "2027-28", "INV", "15") == hashlib.sha256(b"29AAACD1234E1Z52027-28INV15").hexdigest()
    start = datetime(2027, 6, 7, 10, 30)
    assert edocs.validity(850, "R", start) == datetime(2027, 6, 12, 23, 59, 59)  # 5 days
    assert edocs.validity(150, "R", start) == datetime(2027, 6, 8, 23, 59, 59)  # 1 day ends at midnight of the next day
    assert edocs.validity(45, "O", start) == datetime(2027, 6, 10, 23, 59, 59)  # over-dimensional: 20 km a day
    print("1 IRN = SHA-256(GSTIN + FY + type + no.); FY 2027-28 from 1 April; validity 850 km = 5 days, 150 km = 1 day "
          "(until 23:59:59 of the next day), ODC 45 km = 3 days")

    s = SessionLocal()
    before = edocs.settings(s)
    try:
        _customers(s)
        edocs.save_settings(s, {"e_invoice": False, "e_way_bill": False, "mode": "T"})
        inv = _doc(s, "13", "C10000", "S00001", 2, 1500)
        _refused(lambda: edocs.generate_irn(s, "13", inv.doc_entry), "not active")
        edocs.save_settings(s, {"e_invoice": True, "e_way_bill": True})
        p, issues = edocs.einvoice_payload(s, "13", inv.doc_entry)
        assert not issues, issues
        assert p["TranDtls"]["SupTyp"] == "B2B" and p["DocDtls"] == {"Typ": "INV", "No": str(inv.doc_num), "Dt": "07/06/2027"}
        assert p["SellerDtls"]["Pin"] == 560001 and p["SellerDtls"]["Stcd"] == "29" and p["BuyerDtls"]["Gstin"] == "29AABCM1234F1Z1"
        assert p["BuyerDtls"]["Pos"] == "29" and p["BuyerDtls"]["Pin"] == 560025
        it = p["ItemList"][0]
        assert it["HsnCd"] == "998713" and it["IsServc"] == "Y" and it["AssAmt"] == 3000 and it["CgstAmt"] == 270 and it["SgstAmt"] == 270
        v = p["ValDtls"]
        assert v["AssVal"] + v["CgstVal"] + v["SgstVal"] + v["IgstVal"] + v["CesVal"] + v["RndOffAmt"] == v["TotInvVal"] == 3540
        print(f"2 INV-01 of invoice {inv.doc_num}: B2B, seller PIN 560001 / state 29, buyer 29AABCM1234F1Z1 POS 29, "
              "SAC 998713 service, 3,000 + CGST 270 + SGST 270 = 3,540")

        b2c = _doc(s, "13", "C90011", "S00001", 1, 1500)
        _refused(lambda: edocs.generate_irn(s, "13", b2c.doc_entry), "not GST-registered")
        assert not edocs.status(s, "13", b2c.doc_entry)["einvoice_applicable"]

        e = edocs.generate_irn(s, "13", inv.doc_entry)
        assert e.irn == edocs.irn_hash("29AAACD1234E1Z5", "2027-28", "INV", str(inv.doc_num)) and len(e.ack_no) == 15
        st = edocs.status(s, "13", inv.doc_entry)
        assert st["irn"]["cancelable"] and st["qr_svg"].startswith("<svg")
        pr = printing.print_data(s, "13", inv.doc_entry)["edoc"]
        assert pr["irn"] == e.irn and pr["test"] and pr["qr_svg"].startswith("<svg")
        _refused(lambda: edocs.generate_irn(s, "13", inv.doc_entry), "already has an active IRN")
        _refused(lambda: docs.cancel_document(s, "13", inv.doc_entry, DAY), "active IRN")
        _refused(lambda: edocs.cancel_irn(s, "13", inv.doc_entry, "9", "x"), "Cancel reason")
        _refused(lambda: edocs.cancel_irn(s, "13", inv.doc_entry, "2", ""), "remark")
        _refused(lambda: edocs.cancel_irn(s, "13", inv.doc_entry, "2", "wrong rate", e.ack_date + timedelta(hours=25)), "24 hours")
        edocs.cancel_irn(s, "13", inv.doc_entry, "2", "wrong rate", e.ack_date + timedelta(hours=23))
        docs.cancel_document(s, "13", inv.doc_entry, DAY)
        print(f"3 Test IRN {e.irn[:16]}... ack {e.ack_no}, QR on the print; B2C / inactive / second IRN refused; document cancel "
              "blocked; IRN cancel needs reason + remark, refused after 24 h, done at 23 h; then the invoice is canceled")

        # live mode: import the IRP response
        edocs.save_settings(s, {"mode": "L"})
        live = _doc(s, "13", "C20000", "S00001", 1, 1500)
        _refused(lambda: edocs.generate_irn(s, "13", live.doc_entry), "Live mode")
        good = edocs.irn_hash("29AAACD1234E1Z5", "2027-28", "INV", str(live.doc_num))
        _refused(lambda: edocs.import_irn(s, "13", live.doc_entry, {"Irn": good}), "needs Irn, AckNo and SignedQRCode")
        _refused(lambda: edocs.import_irn(s, "13", live.doc_entry, {"Irn": "ab" * 32, "AckNo": 112710000000001, "SignedQRCode": "x.y.z"}),
                 "does not belong")
        resp = {"AckNo": 112710000000777, "AckDt": "2027-06-07 11:15:00", "Irn": good, "SignedQRCode": "eyJhbGciOiJSUzI1NiJ9.eyJkYXRhIjoie30ifQ.c2ln",
                "Status": "ACT"}
        li = edocs.import_irn(s, "13", live.doc_entry, resp)
        assert li.mode == "L" and li.ack_no == "112710000000777" and li.ack_date == datetime(2027, 6, 7, 11, 15)
        print(f"4 Live mode: IRN generation refused; IRP response with a foreign IRN refused; response for invoice {live.doc_num} imported")
        edocs.save_settings(s, {"mode": "T"})

        # e-way bill: goods above 50,000
        docs.create_document(s, DR(obj="20", doc_date=DAY, card_code="V10000", lines=[DL(item_code="A00001", quantity=D(4), price=D(30000))]))
        goods = _doc(s, "13", "C20000", "A00001", 2, 45000)
        assert edocs.ewb_required(s, "13", goods.doc_entry) and not edocs.ewb_required(s, "13", live.doc_entry)
        _refused(lambda: edocs.generate_ewb(s, "13", goods.doc_entry, {"distance": 850}), "vehicle number or the transporter ID")
        _refused(lambda: edocs.generate_ewb(s, "13", goods.doc_entry, {"distance": 0, "vehicle_no": "KA01AB1234"}), "1 to 4000")
        _refused(lambda: edocs.generate_ewb(s, "13", goods.doc_entry, {"distance": 850, "vehicle_no": "12345"}), "registration number")
        _refused(lambda: edocs.generate_ewb(s, "13", goods.doc_entry, {"trans_mode": "2", "distance": 850}), "transport document number")
        _refused(lambda: edocs.generate_ewb(s, "13", live.doc_entry, {"distance": 10, "vehicle_no": "KA01AB1234"}), "only services")
        w = edocs.generate_ewb(s, "13", goods.doc_entry, {"distance": 850, "transporter_id": "29AAECA3456J1Z2", "transporter_name": "Acme"})
        assert w.valid_until is None and len(w.ewb_no) == 12
        moved = w.ewb_date + timedelta(hours=2)
        w = edocs.update_vehicle(s, "13", goods.doc_entry, {"vehicle_no": "ka-01-ab-1234"}, moved)
        assert w.vehicle_no == "KA01AB1234" and w.valid_until == datetime.combine(moved.date() + timedelta(days=5), time(23, 59, 59))
        payload = __import__("json").loads(w.payload)
        assert payload["docType"] == "INV" and payload["toStateCode"] == 27 and payload["igstValue"] == 16200 and payload["totInvValue"] == 106200
        _refused(lambda: docs.cancel_document(s, "13", goods.doc_entry, DAY), "active e-way bill")
        print(f"5 E-way bill {w.ewb_no} for invoice {goods.doc_num} (1,06,200 > 50,000): Part A with transporter, valid after the "
              f"vehicle KA01AB1234 was entered: until {w.valid_until:%d-%m-%Y %H:%M}; bad distance / vehicle / rail without RR refused")

        irn = edocs.generate_irn(s, "13", goods.doc_entry)
        _refused(lambda: edocs.cancel_irn(s, "13", goods.doc_entry, "3", "order canceled", irn.ack_date), "e-way bill of the document first")
        edocs.cancel_ewb(s, "13", goods.doc_entry, "3", "order canceled", w.ewb_date + timedelta(hours=3))
        edocs.cancel_irn(s, "13", goods.doc_entry, "3", "order canceled", irn.ack_date + timedelta(hours=3))
        docs.cancel_document(s, "13", goods.doc_entry, DAY)
        print("6 IRN cancel waits for the e-way bill; e-way bill, IRN and invoice canceled in that order")

        exp = _doc(s, "13", "C90013", "S00001", 1, 1500, vat="ONIL")
        pe, issues = edocs.einvoice_payload(s, "13", exp.doc_entry)
        assert not issues and pe["TranDtls"]["SupTyp"] == "EXPWOP" and pe["BuyerDtls"]["Gstin"] == "URP" and pe["BuyerDtls"]["Pos"] == "96"
        so = docs.create_document(s, DR(obj="17", doc_date=DAY, card_code="C10000", lines=[DL(item_code="A00001", quantity=D(1), price=D(60000))]))
        dn = docs.create_document(s, DR(obj="15", doc_date=DAY, card_code="C10000", lines=[DL(base_type="17", base_entry=so.doc_entry, base_line=0)]))
        pd, issues = edocs.ewb_payload(s, "15", dn.doc_entry, edocs._transport({"distance": 12, "vehicle_no": "KA05MN4321"}))
        assert not issues and pd["docType"] == "CHL" and pd["cgstValue"] == 5400 and pd["toPincode"] == 560025
        print("7 Export e-invoice EXPWOP to URP / POS 96; delivery challan e-way bill (CHL, CGST 5,400, to PIN 560025)")
        print("\nOK - e-invoices and e-way bills follow the GST rules.")
    finally:
        s.rollback()
        edocs.save_settings(s, {k: before[k] for k in ("e_invoice", "e_way_bill", "mode")})
        s.close()


if __name__ == "__main__":
    main()
