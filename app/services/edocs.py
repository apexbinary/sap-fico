"""India e-documents: e-invoice registration (IRN, signed QR code) and e-way bills.

The e-invoice JSON follows schema INV-01 (version 1.1) of the invoice registration portal (IRP);
the e-way bill JSON the layout of the e-way bill portal. The IRN is the SHA-256 hash of the
supplier GSTIN, financial year, document type and document number (the IRP computes it the same
way). Two modes (OADM EDocMode):
  T test  — IRN, acknowledgement and a QR code (unsigned, marked TEST) are made here;
  L live  — the JSON is sent through a GST Suvidha Provider; its response (Irn, AckNo, AckDt,
            SignedQRCode / ewayBillNo, ewayBillDate, validUpto) is imported and checked.
An IRN or an e-way bill can be canceled within 24 hours of its generation; a document with an
active IRN or e-way bill cannot be canceled (documents._cancel checks it).
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.admin import CompanyAddress, State, TaxGroup
from app.models.edocs import EDocument
from app.models.inventory import Item
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import tax
from app.services.admin import B1Error, company
from app.services.documents import get_document

CENT = Decimal("0.01")
EINV_OBJS = {"13": "INV", "14": "CRN"}  # A/R invoice, A/R credit memo (debit notes: not a B1 A/R object here)
EWB_OBJS = {"13": "INV", "15": "CHL"}  # A/R invoice, delivery (challan)
EWB_LIMIT = Decimal("50000")  # consignment value above which an e-way bill is needed
CANCEL_REASONS = {"1": "Duplicate", "2": "Data entry mistake", "3": "Order canceled", "4": "Others"}
TRANS_MODES = {"1": "Road", "2": "Rail", "3": "Air", "4": "Ship"}
VEHICLE_TYPES = {"R": "Regular", "O": "Over-dimensional cargo"}
GSTIN = re.compile(r"^[0-9]{2}[A-Z0-9]{10}[0-9A-Z]Z[0-9A-Z]$")
VEHICLE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{1,4}$|^TM[A-Z0-9]{6,14}$")  # registration no. or temporary no.
PIN = re.compile(r"^[1-9][0-9]{5}$")
CANCEL_WINDOW = timedelta(hours=24)


def _m(x) -> float:
    return float(Decimal(x).quantize(CENT))


def _now() -> datetime:
    """Local time of the company (B1_TIMEZONE, default India): acknowledgement times and the
    24-hour windows of the portals are in IST, whatever the server clock is set to."""
    import os
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(os.environ.get("B1_TIMEZONE", "Asia/Kolkata"))).replace(microsecond=0, tzinfo=None)


def financial_year(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def irn_hash(gstin: str, fy: str, doc_type: str, doc_no: str) -> str:
    """IRN: SHA-256 of supplier GSTIN + financial year + document type + document number."""
    return hashlib.sha256(f"{gstin}{fy}{doc_type}{doc_no}".upper().encode()).hexdigest()


def active(session: Session, obj: str, doc_entry: int, kind: str) -> EDocument | None:
    return session.scalar(select(EDocument).where(EDocument.obj_type == obj, EDocument.doc_entry == doc_entry,
                                                  EDocument.kind == kind, EDocument.status == "A"))


def blocks_cancel(session: Session, obj: str, doc_entry: int) -> str | None:
    """Reason why the document cannot be canceled (active IRN / e-way bill), else None."""
    for kind, what in (("I", "an active IRN"), ("E", "an active e-way bill")):
        if active(session, obj, doc_entry, kind) is not None:
            return f"the document has {what}; cancel it first (within 24 hours) or issue a credit memo"
    return None


# ------------------------------------------------------------- settings
def settings(session: Session) -> dict:
    c = company(session)
    a = session.get(CompanyAddress, 1)
    return {"e_invoice": c.e_invoice == "Y", "e_way_bill": c.e_way_bill == "Y", "mode": c.edoc_mode,
            "street": a.street if a else None, "city": a.city if a else None, "zip_code": a.zip_code if a else None}


def save_settings(session: Session, data: dict) -> dict:
    c = company(session)
    for key, col in (("e_invoice", "e_invoice"), ("e_way_bill", "e_way_bill")):
        if data.get(key) is not None:
            setattr(c, col, "Y" if data[key] else "N")
    if data.get("mode") is not None:
        if data["mode"] not in {"T", "L"}:
            raise B1Error("Mode is T (test) or L (live)")
        c.edoc_mode = data["mode"]
    a = session.get(CompanyAddress, 1)
    if a is None:
        a = CompanyAddress(code=1)
        session.add(a)
    for key in ("street", "city", "zip_code"):
        if key in data:
            setattr(a, key, (data[key] or "").strip() or None)
    if a.zip_code and not PIN.match(a.zip_code):
        raise B1Error("The PIN code has 6 digits and does not start with 0")
    session.commit()
    return settings(session)


# ------------------------------------------------------------- document data
def _seller(session: Session) -> tuple[dict, list[str]]:
    c = company(session)
    a = session.get(CompanyAddress, 1)
    st = session.get(State, (c.country or "IN", c.state)) if c.state else None
    issues = []
    if not c.tax_id or not GSTIN.match(c.tax_id):
        issues.append("company GSTIN missing or not in the GSTIN format (Administration -> Company details)")
    if not a or not a.city or not a.zip_code:
        issues.append("company city and PIN code missing (Administration -> E-Documents)")
    if not st or not st.gst_code:
        issues.append("company state missing")
    addr1 = ((a.street if a and a.street else None) or c.address or "")[:100]
    return {"Gstin": c.tax_id, "LglNm": c.company_name[:100], "Addr1": addr1 or "-", "Loc": (a.city if a else None) or "",
            "Pin": int(a.zip_code) if a and a.zip_code and PIN.match(a.zip_code) else 0, "Stcd": st.gst_code if st else "",
            **({"Ph": re.sub(r"\D", "", c.phone)[-12:]} if c.phone else {}), **({"Em": c.e_mail} if c.e_mail else {})}, issues


def _address(session: Session, bp: BusinessPartner, kind: str, code: str | None) -> PartnerAddress | None:
    return session.get(PartnerAddress, (bp.card_code, kind, code)) if code else None


def _lines(session: Session, doc, fc: bool, rate: Decimal) -> tuple[list[dict], list[str], dict]:
    items, issues = [], []
    totals = {"AssVal": Decimal(0), "CgstVal": Decimal(0), "SgstVal": Decimal(0), "IgstVal": Decimal(0), "CesVal": Decimal(0),
              "Discount": Decimal(0)}
    for n, l in enumerate(doc.lines, 1):
        tg = session.get(TaxGroup, l.vat_group) if l.vat_group else None
        gross_fc = l.total_frgn if fc else l.line_total
        net_fc = (gross_fc * (1 - doc.disc_prcnt / 100)).quantize(CENT)
        comps = {name: (amount * rate).quantize(CENT) for _, amount, name in tax.split(session, tg, net_fc)}
        item = session.get(Item, l.item_code) if l.item_code else None
        hsn = item.chapter_id if item else None
        if not hsn:
            issues.append(f"line {n}: no HSN / SAC code (item {l.item_code or '-'})")
        service = bool(hsn and hsn.startswith("99"))
        from app.services.gst_returns import _uqc

        uqc, _ = _uqc(l.unit_msr, hsn)
        tot = (gross_fc * rate).quantize(CENT)
        ass = (net_fc * rate).quantize(CENT)
        cgst, sgst, igst = comps.get("CGST", Decimal(0)), comps.get("SGST", Decimal(0)) + comps.get("UTGST", Decimal(0)), comps.get("IGST", Decimal(0))
        cess = sum((v for k, v in comps.items() if k not in {"CGST", "SGST", "UTGST", "IGST"}), Decimal(0))
        items.append({"SlNo": str(n), "PrdDesc": (l.dscription or (item.item_name if item else ""))[:300], "IsServc": "Y" if service else "N",
                      "HsnCd": hsn or "", "Qty": float(l.quantity), "Unit": "OTH" if uqc == "NA" else uqc,
                      "UnitPrice": _m(l.price_bef_di * (rate if fc else 1)), "TotAmt": _m(tot), "Discount": _m(tot - ass),
                      "AssAmt": _m(ass), "GstRt": float(tg.rate if tg else 0), "IgstAmt": _m(igst), "CgstAmt": _m(cgst),
                      "SgstAmt": _m(sgst), "CesRt": 0, "CesAmt": _m(cess), "TotItemVal": _m(ass + cgst + sgst + igst + cess)})
        totals["AssVal"] += ass
        totals["CgstVal"] += cgst
        totals["SgstVal"] += sgst
        totals["IgstVal"] += igst
        totals["CesVal"] += cess
    return items, issues, totals


def einvoice_payload(session: Session, obj: str, doc_entry: int) -> tuple[dict, list[str]]:
    """INV-01 JSON of an A/R invoice / credit memo and the problems that block its registration."""
    if obj not in EINV_OBJS:
        raise B1Error("E-invoices exist for A/R invoices and A/R credit memos")
    doc = get_document(session, obj, doc_entry)
    comp = company(session)
    seller, issues = _seller(session)
    bp = session.get(BusinessPartner, doc.card_code)
    bill = _address(session, bp, "B", doc.pay_to_code)
    ship = _address(session, bp, "S", doc.ship_to_code)
    country = (bill.country if bill and bill.country else None) or bp.country or comp.country
    export = country != (comp.country or "IN")
    gstin = ((bill.gst_regn_no if bill else None) or bp.lic_trad_num or "").strip().upper()
    gst_type = (bill.gst_type if bill else None) or ("R" if gstin else "U")
    if doc.canceled == "Y":
        issues.append("the document is canceled")
    if not export and (not gstin or gst_type == "U"):
        issues.append("the customer is not GST-registered: e-invoices are for B2B, SEZ and export supplies (B2C invoices need none)")
    elif not export and not GSTIN.match(gstin):
        issues.append(f"customer GSTIN {gstin} is not in the GSTIN format")
    kind, st_code = tax.supply(session, "S", bp, {"ship_to_code": doc.ship_to_code, "pay_to_code": doc.pay_to_code})
    pos = session.get(State, (comp.country or "IN", st_code)) if st_code else None
    bill_state = session.get(State, (bill.country or "IN", bill.state)) if bill and bill.state else None
    if not export and (not bill or not bill.zip_code or not PIN.match(bill.zip_code or "")):
        issues.append("customer bill-to PIN code missing or invalid")
    if not export and not pos:
        issues.append("place of supply unknown (no state on the ship-to / bill-to address)")
    fc = doc.doc_cur != comp.main_curncy
    rate = doc.doc_rate or Decimal(1)
    items, line_issues, tot = _lines(session, doc, fc, rate)
    issues += line_issues
    any_tax = any(i["IgstAmt"] or i["CgstAmt"] or i["SgstAmt"] for i in items)
    sup_typ = ("EXPWP" if any_tax else "EXPWOP") if export else ("SEZWP" if any_tax else "SEZWOP") if gst_type == "E" else "B2B"
    total = sum((Decimal(str(i["TotItemVal"])) for i in items), Decimal(0))
    doc_total = (doc.doc_total).quantize(CENT)
    payload = {
        "Version": "1.1",
        "TranDtls": {"TaxSch": "GST", "SupTyp": sup_typ, "RegRev": "N", "IgstOnIntra": "N"},
        "DocDtls": {"Typ": EINV_OBJS[obj], "No": str(doc.doc_num)[:16], "Dt": doc.doc_date.strftime("%d/%m/%Y")},
        "SellerDtls": seller,
        "BuyerDtls": {"Gstin": "URP" if export else gstin, "LglNm": (doc.card_name or bp.card_name)[:100],
                      "Pos": "96" if export else (pos.gst_code if pos else ""),
                      "Addr1": ((bill.street if bill else None) or bp.address or "-")[:100], "Loc": ((bill.city if bill else None) or bp.city or "")[:100],
                      "Pin": 999999 if export else (int(bill.zip_code) if bill and bill.zip_code and PIN.match(bill.zip_code) else 0),
                      "Stcd": "96" if export else (bill_state.gst_code if bill_state else "")},
        "ItemList": items,
        "ValDtls": {"AssVal": _m(tot["AssVal"]), "CgstVal": _m(tot["CgstVal"]), "SgstVal": _m(tot["SgstVal"]), "IgstVal": _m(tot["IgstVal"]),
                    "CesVal": _m(tot["CesVal"]), "StCesVal": 0, "Discount": 0, "OthChrg": 0, "RndOffAmt": _m(doc_total - total),
                    "TotInvVal": _m(doc_total)},
    }
    if ship and (ship.street != (bill.street if bill else None) or ship.state != (bill.state if bill else None)):
        ship_state = session.get(State, (ship.country or "IN", ship.state)) if ship.state else None
        payload["ShipDtls"] = {"Gstin": ship.gst_regn_no or gstin or "URP", "LglNm": (doc.card_name or "")[:100], "Addr1": (ship.street or "-")[:100],
                               "Loc": (ship.city or "")[:100], "Pin": int(ship.zip_code) if ship.zip_code and PIN.match(ship.zip_code) else 0,
                               "Stcd": ship_state.gst_code if ship_state else ""}
    if export:
        payload["ExpDtls"] = {"ForCur": doc.doc_cur, "CntCode": country[:2]}
    if kind == "intra" and tot["IgstVal"]:
        issues.append("IGST on an intra-state supply")
    return payload, issues


def _qr_token(payload: dict, irn: str, ack_date: datetime) -> str:
    """Test QR content: the fields of the IRP's signed QR code, as an unsigned token marked TEST."""
    items = payload["ItemList"]
    main_hsn = max(items, key=lambda i: i["AssAmt"])["HsnCd"] if items else ""
    data = {"data": json.dumps({"SellerGstin": payload["SellerDtls"]["Gstin"], "BuyerGstin": payload["BuyerDtls"]["Gstin"],
                                "DocNo": payload["DocDtls"]["No"], "DocTyp": payload["DocDtls"]["Typ"], "DocDt": payload["DocDtls"]["Dt"],
                                "TotInvVal": payload["ValDtls"]["TotInvVal"], "ItemCnt": len(items), "MainHsnCode": main_hsn,
                                "Irn": irn, "IrnDt": ack_date.strftime("%Y-%m-%d %H:%M:%S")}), "iss": "TEST - not registered with the IRP"}
    enc = lambda x: base64.urlsafe_b64encode(json.dumps(x).encode()).decode().rstrip("=")  # noqa: E731
    return f"{enc({'alg': 'none', 'typ': 'JWT'})}.{enc(data)}."


def _next_entry(session: Session) -> int:
    return (session.scalar(select(func.max(EDocument.abs_entry))) or 0) + 1


def _user() -> str | None:
    from app.context import current_user_code

    return current_user_code.get()


def generate_irn(session: Session, obj: str, doc_entry: int) -> EDocument:
    c = company(session)
    if c.e_invoice != "Y":
        raise B1Error("E-invoicing is not active (Administration -> E-Documents)")
    if active(session, obj, doc_entry, "I") is not None:
        raise B1Error("The document already has an active IRN")
    payload, issues = einvoice_payload(session, obj, doc_entry)
    if issues:
        raise B1Error("Cannot register the e-invoice: " + "; ".join(issues))
    if c.edoc_mode != "T":
        raise B1Error("Live mode: download the e-invoice JSON, register it through your GSP and import the IRP response")
    doc = get_document(session, obj, doc_entry)
    irn = irn_hash(c.tax_id, financial_year(doc.doc_date), EINV_OBJS[obj], str(doc.doc_num))
    if session.scalar(select(EDocument).where(EDocument.irn == irn, EDocument.kind == "I")) is not None:
        raise B1Error("This document number was already registered in this financial year (an IRN cannot be generated twice)")
    entry, now = _next_entry(session), _now()
    e = EDocument(abs_entry=entry, obj_type=obj, doc_entry=doc_entry, kind="I", status="A", mode="T", irn=irn,
                  ack_no=f"1{now.year % 100:02d}{entry:012d}", ack_date=now, signed_qr=_qr_token(payload, irn, now),
                  payload=json.dumps(payload), user_sign=_user(), created=now)
    session.add(e)
    session.commit()
    return e


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %I:%M:00 %p"):
        try:
            return datetime.strptime(v.strip(), fmt)
        except ValueError:
            continue
    raise B1Error(f"Unknown date / time format: {v}")


def import_irn(session: Session, obj: str, doc_entry: int, response: dict) -> EDocument:
    """Store the IRP response (Irn, AckNo, AckDt, SignedQRCode; optional EwbNo, EwbDt, EwbValidTill)."""
    c = company(session)
    data = response.get("data", response) if isinstance(response, dict) else {}
    if isinstance(data, str):
        data = json.loads(data)
    irn, ack_no, signed = data.get("Irn"), data.get("AckNo"), data.get("SignedQRCode")
    if not irn or not ack_no or not signed:
        raise B1Error("The response needs Irn, AckNo and SignedQRCode")
    if active(session, obj, doc_entry, "I") is not None:
        raise B1Error("The document already has an active IRN")
    payload, issues = einvoice_payload(session, obj, doc_entry)
    doc = get_document(session, obj, doc_entry)
    expected = irn_hash(c.tax_id, financial_year(doc.doc_date), EINV_OBJS[obj], str(doc.doc_num))
    if irn.lower() != expected:
        raise B1Error("The IRN of the response does not belong to this document (GSTIN, financial year, type or number differ)")
    entry, now = _next_entry(session), _now()
    e = EDocument(abs_entry=entry, obj_type=obj, doc_entry=doc_entry, kind="I", status="A", mode="L", irn=irn.lower(),
                  ack_no=str(ack_no), ack_date=_parse_dt(str(data.get("AckDt") or "")) or now, signed_qr=signed,
                  payload=json.dumps(payload), user_sign=_user(), created=now)
    session.add(e)
    if data.get("EwbNo"):
        session.flush()
        session.add(EDocument(abs_entry=entry + 1, obj_type=obj, doc_entry=doc_entry, kind="E", status="A", mode="L",
                              ewb_no=str(data["EwbNo"]), ewb_date=_parse_dt(str(data.get("EwbDt") or "")) or now,
                              valid_until=_parse_dt(str(data.get("EwbValidTill") or "")), user_sign=_user(), created=now))
    session.commit()
    return e


def _cancel(session: Session, e: EDocument | None, what: str, reason: str, remark: str | None, when: datetime | None) -> EDocument:
    if e is None:
        raise B1Error(f"The document has no active {what}")
    if reason not in CANCEL_REASONS:
        raise B1Error("Cancel reason: 1 duplicate, 2 data entry mistake, 3 order canceled, 4 others")
    if not (remark or "").strip():
        raise B1Error("Enter a cancel remark")
    now = when or _now()
    started = e.ack_date if e.kind == "I" else e.ewb_date
    if started and now - started > CANCEL_WINDOW:
        raise B1Error(f"The {what} can only be canceled within 24 hours of its generation ({started:%d-%m-%Y %H:%M}); "
                      "issue a credit memo instead" if e.kind == "I" else f"The {what} can only be canceled within 24 hours")
    e.status, e.cancel_reason, e.cancel_remark, e.cancel_date = "C", reason, remark.strip()[:100], now
    session.commit()
    return e


def cancel_irn(session: Session, obj: str, doc_entry: int, reason: str, remark: str | None, when: datetime | None = None) -> EDocument:
    if active(session, obj, doc_entry, "E") is not None:
        raise B1Error("Cancel the e-way bill of the document first")
    return _cancel(session, active(session, obj, doc_entry, "I"), "IRN", reason, remark, when)


# ------------------------------------------------------------- e-way bill
def validity(distance: int, vehicle_type: str, start: datetime) -> datetime:
    """1 day per 200 km (over-dimensional cargo: 20 km); a day ends at midnight of the following day
    (rule 138(10)), so n days run until 23:59:59 of the generation date + n."""
    days = max(1, math.ceil(distance / (20 if vehicle_type == "O" else 200)))
    return datetime.combine(start.date() + timedelta(days=days), time(23, 59, 59))


def _transport(data: dict) -> dict:
    mode = str(data.get("trans_mode") or "1")
    if mode not in TRANS_MODES:
        raise B1Error("Transport mode: 1 road, 2 rail, 3 air, 4 ship")
    try:
        distance = int(data.get("distance") or 0)
    except (TypeError, ValueError) as exc:
        raise B1Error("The distance is a whole number of kilometres") from exc
    if not 1 <= distance <= 4000:
        raise B1Error("The distance is 1 to 4000 km")
    vtype = data.get("vehicle_type") or "R"
    if vtype not in VEHICLE_TYPES:
        raise B1Error("Vehicle type: R regular, O over-dimensional cargo")
    vehicle = re.sub(r"[\s-]", "", (data.get("vehicle_no") or "")).upper() or None
    if vehicle and not VEHICLE.match(vehicle):
        raise B1Error(f"Vehicle number {vehicle} is not a registration number such as KA01AB1234")
    tid = (data.get("transporter_id") or "").strip().upper() or None
    if tid and not GSTIN.match(tid) and not re.match(r"^88[A-Z0-9]{13}$", tid):
        raise B1Error("The transporter ID is a GSTIN or an 88... transporter enrolment number")
    doc_no = (data.get("trans_doc_no") or "").strip() or None
    doc_dt = data.get("trans_doc_date")
    if isinstance(doc_dt, str) and doc_dt:
        doc_dt = date.fromisoformat(doc_dt)
    if mode != "1" and not doc_no:
        raise B1Error("Rail, air and ship need the transport document number (RR / airway bill / bill of lading)")
    if mode == "1" and not vehicle and not tid:
        raise B1Error("Road transport needs the vehicle number or the transporter ID")
    return {"trans_mode": mode, "distance": distance, "vehicle_type": vtype, "vehicle_no": vehicle, "transporter_id": tid,
            "transporter_name": (data.get("transporter_name") or "").strip()[:100] or None, "trans_doc_no": doc_no,
            "trans_doc_date": doc_dt or None}


def ewb_payload(session: Session, obj: str, doc_entry: int, transport: dict) -> tuple[dict, list[str]]:
    if obj not in EWB_OBJS:
        raise B1Error("E-way bills exist for A/R invoices and deliveries")
    doc = get_document(session, obj, doc_entry)
    comp = company(session)
    seller, issues = _seller(session)
    bp = session.get(BusinessPartner, doc.card_code)
    bill = _address(session, bp, "B", doc.pay_to_code)
    ship = _address(session, bp, "S", doc.ship_to_code) or bill
    gstin = ((bill.gst_regn_no if bill else None) or bp.lic_trad_num or "").strip().upper()
    fc = doc.doc_cur != comp.main_curncy
    items, line_issues, tot = _lines(session, doc, fc, doc.doc_rate or Decimal(1))
    issues += line_issues
    if all(i["IsServc"] == "Y" for i in items):
        issues.append("only services on the document: an e-way bill is for the movement of goods")
    if doc.canceled == "Y":
        issues.append("the document is canceled")
    to_state = session.get(State, (ship.country or "IN", ship.state)) if ship and ship.state else None
    bill_state = session.get(State, (bill.country or "IN", bill.state)) if bill and bill.state else None
    if not ship or not ship.zip_code or not PIN.match(ship.zip_code):
        issues.append("ship-to PIN code missing or invalid")
    value = Decimal(str(sum(i["TotItemVal"] for i in items if i["IsServc"] == "N")))
    goods = [i for i in items if i["IsServc"] == "N"]
    payload = {
        "supplyType": "O", "subSupplyType": "1" if obj == "13" else "4", "subSupplyDesc": "" if obj == "13" else "Job work / own use",
        "docType": EWB_OBJS[obj], "docNo": str(doc.doc_num), "docDate": doc.doc_date.strftime("%d/%m/%Y"),
        "fromGstin": seller["Gstin"], "fromTrdName": seller["LglNm"], "fromAddr1": seller["Addr1"], "fromPlace": seller["Loc"],
        "fromPincode": seller["Pin"], "fromStateCode": int(seller["Stcd"] or 0), "actFromStateCode": int(seller["Stcd"] or 0),
        "toGstin": gstin or "URP", "toTrdName": doc.card_name, "toAddr1": (ship.street if ship else "") or "", "toPlace": (ship.city if ship else "") or "",
        "toPincode": int(ship.zip_code) if ship and ship.zip_code and PIN.match(ship.zip_code) else 0,
        "toStateCode": int(bill_state.gst_code) if bill_state and bill_state.gst_code else 0,
        "actToStateCode": int(to_state.gst_code) if to_state and to_state.gst_code else 0,
        "transactionType": 1, "totalValue": _m(sum(Decimal(str(i["AssAmt"])) for i in goods)),
        "cgstValue": _m(sum(Decimal(str(i["CgstAmt"])) for i in goods)), "sgstValue": _m(sum(Decimal(str(i["SgstAmt"])) for i in goods)),
        "igstValue": _m(sum(Decimal(str(i["IgstAmt"])) for i in goods)), "cessValue": _m(sum(Decimal(str(i["CesAmt"])) for i in goods)),
        "totInvValue": _m(value),
        "transMode": transport.get("trans_mode", "1"), "transDistance": str(transport.get("distance") or ""),
        "transporterId": transport.get("transporter_id") or "", "transporterName": transport.get("transporter_name") or "",
        "transDocNo": transport.get("trans_doc_no") or "",
        "transDocDate": transport["trans_doc_date"].strftime("%d/%m/%Y") if transport.get("trans_doc_date") else "",
        "vehicleNo": transport.get("vehicle_no") or "", "vehicleType": transport.get("vehicle_type") or "R",
        "itemList": [{"productName": i["PrdDesc"][:100], "productDesc": i["PrdDesc"][:100], "hsnCode": int(i["HsnCd"]) if i["HsnCd"].isdigit() else 0,
                      "quantity": i["Qty"], "qtyUnit": i["Unit"], "taxableAmount": i["AssAmt"],
                      "cgstRate": i["GstRt"] / 2 if i["CgstAmt"] else 0, "sgstRate": i["GstRt"] / 2 if i["SgstAmt"] else 0,
                      "igstRate": i["GstRt"] if i["IgstAmt"] else 0, "cessRate": 0} for i in goods],
    }
    return payload, issues


def ewb_required(session: Session, obj: str, doc_entry: int) -> bool:
    if obj not in EWB_OBJS:
        return False
    doc = get_document(session, obj, doc_entry)
    goods = any(not ((session.get(Item, l.item_code).chapter_id or "").startswith("99") if l.item_code and session.get(Item, l.item_code) else True)
                for l in doc.lines)
    return goods and doc.doc_total > EWB_LIMIT


def generate_ewb(session: Session, obj: str, doc_entry: int, data: dict) -> EDocument:
    c = company(session)
    if c.e_way_bill != "Y":
        raise B1Error("E-way bills are not active (Administration -> E-Documents)")
    if active(session, obj, doc_entry, "E") is not None:
        raise B1Error("The document already has an active e-way bill")
    tr = _transport(data)
    payload, issues = ewb_payload(session, obj, doc_entry, tr)
    if issues:
        raise B1Error("Cannot generate the e-way bill: " + "; ".join(issues))
    if c.edoc_mode != "T":
        raise B1Error("Live mode: download the e-way bill JSON, generate it on the portal / through your GSP and import the response")
    entry, now = _next_entry(session), _now()
    part_b = bool(tr["vehicle_no"] or tr["trans_doc_no"])  # without Part B the e-way bill is not valid for movement yet
    e = EDocument(abs_entry=entry, obj_type=obj, doc_entry=doc_entry, kind="E", status="A", mode="T", ewb_no=f"9{entry:011d}",
                  ewb_date=now, valid_until=validity(tr["distance"], tr["vehicle_type"], now) if part_b else None,
                  payload=json.dumps(payload), user_sign=_user(), created=now, **tr)
    session.add(e)
    session.commit()
    return e


def import_ewb(session: Session, obj: str, doc_entry: int, response: dict, data: dict) -> EDocument:
    """Store the e-way bill portal response (ewayBillNo, ewayBillDate, validUpto)."""
    if active(session, obj, doc_entry, "E") is not None:
        raise B1Error("The document already has an active e-way bill")
    no = str(response.get("ewayBillNo") or response.get("EwbNo") or "")
    if not re.match(r"^[0-9]{12}$", no):
        raise B1Error("The response needs ewayBillNo (12 digits)")
    tr = _transport(data)
    payload, _ = ewb_payload(session, obj, doc_entry, tr)
    entry, now = _next_entry(session), _now()
    e = EDocument(abs_entry=entry, obj_type=obj, doc_entry=doc_entry, kind="E", status="A", mode="L", ewb_no=no,
                  ewb_date=_parse_dt(str(response.get("ewayBillDate") or response.get("EwbDt") or "")) or now,
                  valid_until=_parse_dt(str(response.get("validUpto") or response.get("EwbValidTill") or "")),
                  payload=json.dumps(payload), user_sign=_user(), created=now, **tr)
    session.add(e)
    session.commit()
    return e


def update_vehicle(session: Session, obj: str, doc_entry: int, data: dict, when: datetime | None = None) -> EDocument:
    """Part B: new vehicle (or first vehicle); the validity runs from this update when it was not valid yet."""
    e = active(session, obj, doc_entry, "E")
    if e is None:
        raise B1Error("The document has no active e-way bill")
    now = when or _now()
    if e.valid_until and now > e.valid_until:
        raise B1Error("The e-way bill has expired; it cannot be updated")
    tr = _transport({"trans_mode": data.get("trans_mode") or e.trans_mode, "distance": data.get("distance") or e.distance,
                     "vehicle_type": data.get("vehicle_type") or e.vehicle_type, "vehicle_no": data.get("vehicle_no"),
                     "transporter_id": e.transporter_id, "transporter_name": e.transporter_name,
                     "trans_doc_no": data.get("trans_doc_no") or e.trans_doc_no, "trans_doc_date": data.get("trans_doc_date") or e.trans_doc_date})
    if tr["trans_mode"] == "1" and not tr["vehicle_no"]:
        raise B1Error("Enter the vehicle number")
    if e.valid_until is None:
        e.valid_until = validity(tr["distance"], tr["vehicle_type"], now)
    e.vehicle_no, e.vehicle_type, e.trans_mode, e.trans_doc_no, e.trans_doc_date = (
        tr["vehicle_no"], tr["vehicle_type"], tr["trans_mode"], tr["trans_doc_no"], tr["trans_doc_date"])
    session.commit()
    return e


def cancel_ewb(session: Session, obj: str, doc_entry: int, reason: str, remark: str | None, when: datetime | None = None) -> EDocument:
    return _cancel(session, active(session, obj, doc_entry, "E"), "e-way bill", reason, remark, when)


# ------------------------------------------------------------- output
def qr_svg(content: str) -> str:
    import segno

    return segno.make(content, error="m").svg_inline(scale=2, border=1, dark="#000", light="#fff")


def edoc_out(e: EDocument) -> dict:
    now = _now()
    started = e.ack_date if e.kind == "I" else e.ewb_date
    return {"abs_entry": e.abs_entry, "obj_type": e.obj_type, "doc_entry": e.doc_entry, "kind": e.kind,
            "kind_name": "E-invoice (IRN)" if e.kind == "I" else "E-way bill", "status": e.status, "mode": e.mode,
            "irn": e.irn, "ack_no": e.ack_no, "ack_date": e.ack_date, "ewb_no": e.ewb_no, "ewb_date": e.ewb_date,
            "valid_until": e.valid_until, "trans_mode": e.trans_mode, "distance": e.distance, "transporter_id": e.transporter_id,
            "transporter_name": e.transporter_name, "vehicle_no": e.vehicle_no, "vehicle_type": e.vehicle_type,
            "trans_doc_no": e.trans_doc_no, "trans_doc_date": e.trans_doc_date, "cancel_reason": e.cancel_reason,
            "cancel_remark": e.cancel_remark, "cancel_date": e.cancel_date, "user_sign": e.user_sign, "created": e.created,
            "cancelable": e.status == "A" and bool(started) and now - started <= CANCEL_WINDOW,
            "expired": bool(e.kind == "E" and e.status == "A" and e.valid_until and now > e.valid_until)}


def status(session: Session, obj: str, doc_entry: int) -> dict:
    c = company(session)
    rows = session.scalars(select(EDocument).where(EDocument.obj_type == obj, EDocument.doc_entry == doc_entry)
                           .order_by(EDocument.abs_entry)).all()
    irn = active(session, obj, doc_entry, "I")
    ewb = active(session, obj, doc_entry, "E")
    einv_issues = einvoice_payload(session, obj, doc_entry)[1] if obj in EINV_OBJS else []
    b2c = any("not GST-registered" in i for i in einv_issues)
    return {
        "settings": {"e_invoice": c.e_invoice == "Y", "e_way_bill": c.e_way_bill == "Y", "mode": c.edoc_mode},
        "einvoice_applicable": obj in EINV_OBJS and not b2c, "einvoice_issues": einv_issues,
        "ewb_applicable": obj in EWB_OBJS, "ewb_required": ewb_required(session, obj, doc_entry) if obj in EWB_OBJS else False,
        "irn": edoc_out(irn) if irn else None, "ewb": edoc_out(ewb) if ewb else None,
        "qr_svg": qr_svg(irn.signed_qr) if irn and irn.signed_qr else None,
        "history": [edoc_out(e) for e in rows],
        "cancel_reasons": CANCEL_REASONS, "trans_modes": TRANS_MODES, "vehicle_types": VEHICLE_TYPES,
    }


def register(session: Session, kind: str | None = None, limit: int = 200) -> list[dict]:
    q = select(EDocument).order_by(EDocument.abs_entry.desc()).limit(limit)
    if kind:
        q = q.where(EDocument.kind == kind)
    out = []
    for e in session.scalars(q):
        row = edoc_out(e)
        try:
            d = get_document(session, e.obj_type, e.doc_entry)
            row.update({"doc_num": d.doc_num, "card_code": d.card_code, "card_name": d.card_name, "doc_total": d.doc_total})
        except B1Error:
            pass
        out.append(row)
    return out


def pending(session: Session, date_from: date) -> list[dict]:
    """Documents since a date that need an IRN (B2B / SEZ / export) or an e-way bill (> 50,000, goods) but have none."""
    from app.models.documents import DOCUMENT_CLASSES

    c = company(session)
    out = []
    objs = sorted(set(EINV_OBJS) | set(EWB_OBJS))
    for obj in objs:
        hcls = DOCUMENT_CLASSES[obj][0]
        for d in session.scalars(select(hcls).where(hcls.doc_date >= date_from, hcls.canceled == "N").order_by(hcls.doc_num)):
            need = []
            if c.e_invoice == "Y" and obj in EINV_OBJS and active(session, obj, d.doc_entry, "I") is None:
                issues = einvoice_payload(session, obj, d.doc_entry)[1]
                if not any("not GST-registered" in i for i in issues):
                    need.append("IRN")
            if c.e_way_bill == "Y" and obj in EWB_OBJS and active(session, obj, d.doc_entry, "E") is None \
                    and ewb_required(session, obj, d.doc_entry):
                need.append("e-way bill")
            if need:
                out.append({"obj_type": obj, "doc_entry": d.doc_entry, "doc_num": d.doc_num, "doc_date": d.doc_date,
                            "card_code": d.card_code, "card_name": d.card_name, "doc_total": d.doc_total, "needs": need})
    return out
