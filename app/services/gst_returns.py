"""India GST returns from the posted A/R and A/P documents: GSTR-1 (outward supplies) and
GSTR-3B (summary return with input tax credit and its set-off), with the JSON of the GSTN
offline tool layout.

Outward documents are A/R invoices (13) and A/R credit memos (14); inward documents A/P
invoices (18) and A/P credit memos (19) — canceled documents are left out (and counted as
canceled in the documents-issued table). Every line is taken again the way it was posted
(net after header discount, each tax component rounded on its own in the document currency
and converted at the document rate), so the returns agree with the tax accounts.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import NumberingSeries, State, TaxGroup
from app.models.documents import DOCUMENT_CLASSES
from app.models.inventory import Item
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import tax
from app.services.admin import B1Error, company

ZERO = Decimal("0")
CENT = Decimal("0.01")
B2CL_LIMIT = Decimal("100000")  # inter-state B2C invoice above this value: B2CL (from 1 Aug 2024; before: 2,50,000)
GSTIN = re.compile(r"^[0-9]{2}[A-Z0-9]{10}[0-9A-Z]Z[0-9A-Z]$")
UQC = {"pcs": "PCS", "piece": "PCS", "pieces": "PCS", "nos": "NOS", "no": "NOS", "each": "NOS", "ea": "NOS", "unit": "UNT",
       "units": "UNT", "box": "BOX", "boxes": "BOX", "pack": "PAC", "packet": "PAC", "set": "SET", "dozen": "DOZ",
       "doz": "DOZ", "kg": "KGS", "kgs": "KGS", "g": "GMS", "gram": "GMS", "ltr": "LTR", "litre": "LTR", "l": "LTR",
       "ml": "MLT", "m": "MTR", "mtr": "MTR", "meter": "MTR", "ream": "OTH", "roll": "ROL", "bag": "BAG", "ton": "TON"}


def _m(x: Decimal) -> Decimal:
    return Decimal(x).quantize(CENT)


def period(year: int, month: int) -> tuple[date, date]:
    if not 1 <= month <= 12:
        raise B1Error("Month must be 1-12")
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


@dataclass
class Line:
    rate: Decimal  # total GST rate %
    taxable: Decimal
    igst: Decimal = ZERO
    cgst: Decimal = ZERO
    sgst: Decimal = ZERO
    cess: Decimal = ZERO
    hsn: str | None = None
    description: str | None = None
    uqc: str = "NA"
    qty: Decimal = ZERO
    nil: bool = False  # nil-rated / exempt tax code (rate 0)
    kind: str | None = None  # intra / inter

    @property
    def tax(self) -> Decimal:
        return self.igst + self.cgst + self.sgst + self.cess


@dataclass
class Doc:
    obj: str
    doc_entry: int
    doc_num: int
    doc_date: date
    card_code: str | None
    card_name: str | None
    gstin: str | None
    gst_type: str | None  # R regular, U unregistered, C composition, E SEZ
    export: bool
    pos_state: str | None  # OCST code
    pos: str | None  # GST state code, e.g. "29"
    pos_name: str | None
    inter: bool
    value: Decimal  # invoice value (LC, gross)
    lines: list[Line] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def registered(self) -> bool:
        return bool(self.gstin) and self.gst_type != "U"


def _uqc(unit: str | None, hsn: str | None) -> tuple[str, bool]:
    if hsn and hsn.startswith("99"):  # services (SAC): no quantity
        return "NA", False
    return UQC.get((unit or "").strip().lower(), "OTH"), True


def _docs(session: Session, objs: tuple[str, ...], date_from: date, date_to: date, canceled: bool = False) -> list[Doc]:
    comp = company(session)
    out = []
    for obj in objs:
        hcls = DOCUMENT_CLASSES[obj][0]
        q = select(hcls).where(hcls.doc_date >= date_from, hcls.doc_date <= date_to).order_by(hcls.doc_num)
        for d in session.scalars(q.where(hcls.canceled == ("Y" if canceled else "N"))):
            bp = session.get(BusinessPartner, d.card_code) if d.card_code else None
            addr = session.get(PartnerAddress, (bp.card_code, "B", d.pay_to_code)) if bp and d.pay_to_code else None
            gstin = ((addr.gst_regn_no if addr else None) or (bp.lic_trad_num if bp else None) or d.lic_trad_num or "").strip().upper() or None
            country = (addr.country if addr and addr.country else None) or (bp.country if bp else None) or comp.country
            side = "S" if obj in {"13", "14"} else "P"
            kind, st = tax.supply(session, side, bp, {"ship_to_code": d.ship_to_code, "pay_to_code": d.pay_to_code}) if bp else (None, None)
            state = session.get(State, ((comp.country or "IN"), st)) if st else None
            doc = Doc(obj=obj, doc_entry=d.doc_entry, doc_num=d.doc_num, doc_date=d.doc_date, card_code=d.card_code,
                      card_name=d.card_name, gstin=gstin, gst_type=(addr.gst_type if addr else None) or ("R" if gstin else "U"),
                      export=bool(country) and country != (comp.country or "IN"), pos_state=st,
                      pos=state.gst_code if state else None, pos_name=state.name if state else None,
                      inter=kind == "inter", value=_m(d.doc_total))
            if doc.export:
                doc.inter, doc.pos, doc.pos_name = True, "96", "Other countries"
            if gstin and not GSTIN.match(gstin):
                doc.issues.append(f"GSTIN {gstin} has not the GSTIN format")
            rate = d.doc_rate or Decimal(1)
            fc = d.doc_cur != comp.main_curncy
            kinds = set()
            for l in d.lines:
                tg = session.get(TaxGroup, l.vat_group) if l.vat_group else None
                net_fc = _m((l.total_frgn if fc else l.line_total) * (1 - d.disc_prcnt / 100))
                comps = tax.split(session, tg, net_fc)
                item = session.get(Item, l.item_code) if l.item_code else None
                hsn = item.chapter_id if item else None
                unit = l.unit_msr or (item.sal_unit_msr if side == "S" else item.buy_unit_msr) if item else l.unit_msr
                uqc, has_qty = _uqc(unit, hsn)
                line = Line(rate=tg.rate if tg else ZERO, taxable=_m(net_fc * rate), hsn=hsn,
                            description=(item.item_name if item else None) or l.dscription, uqc=uqc,
                            qty=l.quantity if has_qty else ZERO, nil=tg is None or tg.rate == 0, kind=tax.gst_kind(session, tg))
                for _, amount, name in comps:
                    lc = _m(amount * rate)
                    attr = {"IGST": "igst", "CGST": "cgst", "SGST": "sgst", "UTGST": "sgst"}.get(name, "cess")
                    setattr(line, attr, getattr(line, attr) + lc)
                if line.kind:
                    kinds.add(line.kind)
                if not hsn:
                    doc.issues.append(f"line {l.line_num + 1}: item {l.item_code or '-'} has no HSN / SAC code")
                doc.lines.append(line)
            if kinds == {"inter"}:
                doc.inter = True
            elif kinds == {"intra"}:
                doc.inter = False
            elif len(kinds) > 1:
                doc.issues.append("intra-state and inter-state tax codes on the same document")
            if doc.pos is None and not doc.export:
                doc.issues.append("place of supply unknown (no state on the partner address)")
            out.append(doc)
    return out


def _by_rate(lines: list[Line], sign: int = 1) -> list[dict]:
    rows: dict[Decimal, dict] = {}
    for l in lines:
        r = rows.setdefault(l.rate, {"rate": l.rate, "taxable": ZERO, "igst": ZERO, "cgst": ZERO, "sgst": ZERO, "cess": ZERO})
        for k in ("taxable", "igst", "cgst", "sgst", "cess"):
            r[k] += sign * getattr(l, k)
    return [rows[k] for k in sorted(rows)]


def _sum(rows: list[dict], keys=("taxable", "igst", "cgst", "sgst", "cess")) -> dict:
    return {k: sum((r[k] for r in rows), ZERO) for k in keys}


def _doc_row(d: Doc, sign: int = 1) -> dict:
    """Document with its items by rate: nil-rated lines are left out (Table 8), except on exports
    (zero-rated supplies are reported with rate 0)."""
    return {"doc_entry": d.doc_entry, "doc_num": d.doc_num, "doc_date": d.doc_date, "card_code": d.card_code,
            "card_name": d.card_name, "gstin": d.gstin, "gst_type": d.gst_type, "pos": d.pos, "pos_name": d.pos_name,
            "value": d.value, "supply": "inter" if d.inter else "intra",
            "items": _by_rate([l for l in d.lines if d.export or not l.nil], sign)}


# ------------------------------------------------------------- GSTR-1
def gstr1(session: Session, year: int, month: int) -> dict:
    date_from, date_to = period(year, month)
    docs = _docs(session, ("13", "14"), date_from, date_to)
    b2b, b2cl, exp, cdnr, cdnur = [], [], [], [], []
    b2cs: dict[tuple, dict] = {}
    nil: dict[str, dict] = {k: {"supply": k, "nil": ZERO, "exempt": ZERO, "non_gst": ZERO}
                            for k in ("Inter-state to registered", "Intra-state to registered",
                                      "Inter-state to unregistered", "Intra-state to unregistered")}
    hsn: dict[str, dict] = {"b2b": {}, "b2c": {}}
    issues = []

    def add_b2cs(d: Doc, sign: int) -> None:
        for l in d.lines:
            if l.nil:
                continue
            key = (d.pos, "INTER" if d.inter else "INTRA", l.rate)
            r = b2cs.setdefault(key, {"pos": d.pos, "pos_name": d.pos_name, "supply": key[1], "rate": l.rate, "type": "OE",
                                      "taxable": ZERO, "igst": ZERO, "cgst": ZERO, "sgst": ZERO, "cess": ZERO})
            for k in ("taxable", "igst", "cgst", "sgst", "cess"):
                r[k] += sign * getattr(l, k)

    for d in docs:
        sign = 1 if d.obj == "13" else -1
        for msg in d.issues:
            issues.append(f"{'Invoice' if d.obj == '13' else 'Credit memo'} {d.doc_num} ({d.card_code}): {msg}")
        b2b_like = d.registered and not d.export
        for l in d.lines:  # HSN summary (Table 12), split B2B / B2C
            if not l.hsn and l.nil:
                continue
            key = f"{l.hsn or '-'}|{l.uqc}|{l.rate}"
            h = hsn["b2b" if b2b_like else "b2c"].setdefault(key, {"hsn": l.hsn, "description": l.description, "uqc": l.uqc,
                                                                    "rate": l.rate, "qty": ZERO, "value": ZERO, "taxable": ZERO,
                                                                    "igst": ZERO, "cgst": ZERO, "sgst": ZERO, "cess": ZERO})
            h["qty"] += sign * l.qty
            h["value"] += sign * (l.taxable + l.tax)
            for k in ("taxable", "igst", "cgst", "sgst", "cess"):
                h[k] += sign * getattr(l, k)
            if l.nil and not d.export:
                bucket = f"{'Inter' if d.inter else 'Intra'}-state to {'registered' if d.registered else 'unregistered'}"
                nil[bucket]["nil"] += sign * l.taxable
        if not d.export and all(l.nil for l in d.lines):
            continue  # only nil-rated / exempt lines: Table 8 only
        if d.export:
            if d.obj == "13":
                exp.append({**_doc_row(d), "type": "WPAY" if any(l.igst for l in d.lines) else "WOPAY"})
            else:
                cdnur.append({**_doc_row(d), "type": "EXPWP" if any(l.igst for l in d.lines) else "EXPWOP", "note_type": "C"})
        elif d.registered:
            row = {**_doc_row(d), "invoice_type": ("SEZWP" if any(l.igst for l in d.lines) else "SEZWOP") if d.gst_type == "E" else "R",
                   "reverse_charge": "N"}
            if d.obj == "13":
                b2b.append(row)
            else:
                cdnr.append({**row, "note_type": "C"})
        elif d.inter and d.value > B2CL_LIMIT:
            if d.obj == "13":
                b2cl.append(_doc_row(d))
            else:
                cdnur.append({**_doc_row(d), "type": "B2CL", "note_type": "C"})
        else:
            add_b2cs(d, sign)

    canceled = _docs(session, ("13", "14"), date_from, date_to, canceled=True)
    doc_issue = []
    for obj, nature in (("13", "Invoices for outward supply"), ("14", "Credit note")):
        nums = sorted([d.doc_num for d in docs if d.obj == obj] + [d.doc_num for d in canceled if d.obj == obj])
        if nums:
            ser = session.scalar(select(NumberingSeries).where(NumberingSeries.object_code == obj, NumberingSeries.is_default.is_(True)))
            doc_issue.append({"nature": nature, "series": ser.series_name if ser else "", "from": nums[0], "to": nums[-1],
                              "total": len(nums), "canceled": sum(1 for d in canceled if d.obj == obj),
                              "net_issued": len(nums) - sum(1 for d in canceled if d.obj == obj)})

    hsn_out = {k: sorted(v.values(), key=lambda h: (h["hsn"] or "", h["rate"])) for k, v in hsn.items()}
    b2cs_rows = sorted(b2cs.values(), key=lambda r: (r["pos"] or "", r["supply"], r["rate"]))
    sections = {"b2b": b2b, "b2cl": b2cl, "b2cs": b2cs_rows, "exp": exp, "cdnr": cdnr, "cdnur": cdnur}
    totals = {
        "b2b": _sum([i for r in b2b for i in r["items"]]), "b2cl": _sum([i for r in b2cl for i in r["items"]]),
        "b2cs": _sum(b2cs_rows), "exp": _sum([i for r in exp for i in r["items"]]),
        "cdnr": _sum([i for r in cdnr for i in r["items"]]), "cdnur": _sum([i for r in cdnur for i in r["items"]]),
    }
    hsn_total = _sum(hsn_out["b2b"] + hsn_out["b2c"])
    doc_total = _sum([i for d in docs for i in _by_rate(d.lines, 1 if d.obj == "13" else -1)])
    if any(abs(hsn_total[k] - doc_total[k]) > CENT for k in ("igst", "cgst", "sgst")):
        issues.append("HSN summary tax differs from the document tax")
    comp = company(session)
    return {"gstin": comp.tax_id, "period": f"{month:02d}{year}", "date_from": date_from, "date_to": date_to,
            **sections, "nil": list(nil.values()), "hsn": hsn_out, "doc_issue": doc_issue, "totals": totals,
            "total": doc_total, "documents": len(docs), "issues": issues}


# ------------------------------------------------------------- GSTR-3B
HEADS = ("igst", "cgst", "sgst", "cess")


def set_off(liability: dict, credit: dict) -> dict:
    """Utilisation of input tax credit (sections 49 / 49A / 49B, rule 88A): IGST credit first
    against IGST, then CGST and SGST; CGST credit against CGST, then IGST; SGST credit against
    SGST, then IGST; CGST never against SGST or the reverse; cess only against cess.
    Returns the credit used per (credit head, liability head) and the cash to pay per head."""
    due = {h: max(liability.get(h, ZERO), ZERO) for h in HEADS}
    left = {h: max(credit.get(h, ZERO), ZERO) for h in HEADS}
    used = defaultdict(lambda: ZERO)

    def use(c: str, t: str) -> None:
        x = min(left[c], due[t])
        if x > 0:
            left[c] -= x
            due[t] -= x
            used[(c, t)] += x

    use("igst", "igst")
    # remaining IGST credit against CGST and SGST: CGST first, then SGST (any order is allowed)
    use("igst", "cgst")
    use("igst", "sgst")
    use("cgst", "cgst")
    use("cgst", "igst")
    use("sgst", "sgst")
    use("sgst", "igst")
    use("cess", "cess")
    return {"used": [{"credit": c, "against": t, "amount": v} for (c, t), v in used.items()],
            "cash": due, "credit_left": left}


def gstr3b(session: Session, year: int, month: int) -> dict:
    date_from, date_to = period(year, month)
    out_docs = _docs(session, ("13", "14"), date_from, date_to)
    in_docs = _docs(session, ("18", "19"), date_from, date_to)
    zero = lambda: {"taxable": ZERO, "igst": ZERO, "cgst": ZERO, "sgst": ZERO, "cess": ZERO}  # noqa: E731
    t31 = {"a": zero(), "b": zero(), "c": zero(), "d": zero(), "e": zero()}
    unreg: dict[str, dict] = {}
    comp_sup: dict[str, dict] = {}
    for d in out_docs:
        sign = 1 if d.obj == "13" else -1
        for l in d.lines:
            box = "b" if d.export or d.gst_type == "E" else "c" if l.nil else "a"
            for k in ("taxable", "igst", "cgst", "sgst", "cess"):
                t31[box][k] += sign * getattr(l, k)
            if d.inter and not d.export and not l.nil and d.gst_type in {"U", "C"}:
                target = unreg if d.gst_type == "U" else comp_sup
                r = target.setdefault(d.pos or "-", {"pos": d.pos, "pos_name": d.pos_name, "taxable": ZERO, "igst": ZERO})
                r["taxable"] += sign * l.taxable
                r["igst"] += sign * l.igst
    itc = {h: ZERO for h in HEADS}
    exempt_in = {"inter": ZERO, "intra": ZERO}
    issues = []
    for d in in_docs:
        sign = 1 if d.obj == "18" else -1
        for msg in d.issues:
            issues.append(f"{'A/P invoice' if d.obj == '18' else 'A/P credit memo'} {d.doc_num} ({d.card_code}): {msg}")
        for l in d.lines:
            if l.nil:
                exempt_in["inter" if d.inter else "intra"] += sign * l.taxable
            for h in HEADS:
                itc[h] += sign * getattr(l, h)
    liability = {h: t31["a"][h] + t31["b"][h] for h in HEADS}
    payment = set_off(liability, itc)
    comp = company(session)
    return {
        "gstin": comp.tax_id, "period": f"{month:02d}{year}", "date_from": date_from, "date_to": date_to,
        "outward": {"a_taxable": t31["a"], "b_zero_rated": t31["b"], "c_nil_exempt": t31["c"],
                    "d_reverse_charge": t31["d"], "e_non_gst": t31["e"]},
        "inter_state_unregistered": sorted(unreg.values(), key=lambda r: r["pos"] or ""),
        "inter_state_composition": sorted(comp_sup.values(), key=lambda r: r["pos"] or ""),
        "itc": {"available_other": itc, "reversed": {h: ZERO for h in HEADS}, "net": dict(itc), "ineligible": {h: ZERO for h in HEADS}},
        "exempt_inward": exempt_in,
        "liability": liability,
        "payment": payment,
        "issues": issues,
    }


# ------------------------------------------------------------- JSON (GSTN offline tool layout)
def _f(x: Decimal) -> float:
    return float(_m(x))


def _dt(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _itms(items: list[dict], igst_only: bool = False) -> list[dict]:
    out = []
    for n, i in enumerate(items, 1):
        det = {"rt": float(i["rate"]), "txval": _f(abs(i["taxable"])), "iamt": _f(abs(i["igst"])), "csamt": _f(abs(i["cess"]))}
        if not igst_only:
            det.update({"camt": _f(abs(i["cgst"])), "samt": _f(abs(i["sgst"]))})
        out.append({"num": n, "itm_det": det})
    return out


def gstr1_json(session: Session, year: int, month: int) -> dict:
    r = gstr1(session, year, month)
    by_ctin: dict[str, list] = defaultdict(list)
    for x in r["b2b"]:
        by_ctin[x["gstin"]].append({"inum": str(x["doc_num"]), "idt": _dt(x["doc_date"]), "val": _f(x["value"]), "pos": x["pos"],
                                    "rchrg": "N", "inv_typ": x["invoice_type"], "itms": _itms(x["items"])})
    cdnr: dict[str, list] = defaultdict(list)
    for x in r["cdnr"]:
        cdnr[x["gstin"]].append({"ntty": "C", "nt_num": str(x["doc_num"]), "nt_dt": _dt(x["doc_date"]), "val": _f(x["value"]),
                                 "pos": x["pos"], "rchrg": "N", "inv_typ": x["invoice_type"], "itms": _itms(x["items"])})
    b2cl: dict[str, list] = defaultdict(list)
    for x in r["b2cl"]:
        b2cl[x["pos"]].append({"inum": str(x["doc_num"]), "idt": _dt(x["doc_date"]), "val": _f(x["value"]), "itms": _itms(x["items"], True)})
    exp: dict[str, list] = defaultdict(list)
    for x in r["exp"]:
        exp[x["type"]].append({"inum": str(x["doc_num"]), "idt": _dt(x["doc_date"]), "val": _f(x["value"]),
                               "itms": [{"rt": float(i["rate"]), "txval": _f(i["taxable"]), "iamt": _f(i["igst"]), "csamt": _f(i["cess"])}
                                        for i in x["items"]]})
    nil_map = {"Inter-state to registered": "INTRB2B", "Intra-state to registered": "INTRAB2B",
               "Inter-state to unregistered": "INTRB2C", "Intra-state to unregistered": "INTRAB2C"}

    def hsn_rows(rows):
        return [{"num": n, "hsn_sc": h["hsn"] or "", "desc": (h["description"] or "")[:30], "uqc": h["uqc"], "qty": float(h["qty"]),
                 "rt": float(h["rate"]), "txval": _f(h["taxable"]), "iamt": _f(h["igst"]), "camt": _f(h["cgst"]),
                 "samt": _f(h["sgst"]), "csamt": _f(h["cess"])} for n, h in enumerate(rows, 1)]

    return {
        "gstin": r["gstin"], "fp": r["period"], "version": "GST3.2", "hash": "hash",
        "b2b": [{"ctin": k, "inv": v} for k, v in by_ctin.items()],
        "b2cl": [{"pos": k, "inv": v} for k, v in b2cl.items()],
        "b2cs": [{"sply_ty": x["supply"], "pos": x["pos"], "typ": "OE", "rt": float(x["rate"]), "txval": _f(x["taxable"]),
                  "iamt": _f(x["igst"]), "camt": _f(x["cgst"]), "samt": _f(x["sgst"]), "csamt": _f(x["cess"])} for x in r["b2cs"]],
        "exp": [{"exp_typ": k, "inv": v} for k, v in exp.items()],
        "cdnr": [{"ctin": k, "nt": v} for k, v in cdnr.items()],
        "cdnur": [{"typ": x["type"], "ntty": "C", "nt_num": str(x["doc_num"]), "nt_dt": _dt(x["doc_date"]), "val": _f(x["value"]),
                   **({"pos": x["pos"]} if x["type"] == "B2CL" else {}), "itms": _itms(x["items"], True)} for x in r["cdnur"]],
        "nil": {"inv": [{"sply_ty": nil_map[x["supply"]], "nil_amt": _f(x["nil"]), "expt_amt": _f(x["exempt"]),
                         "ngsup_amt": _f(x["non_gst"])} for x in r["nil"] if x["nil"] or x["exempt"] or x["non_gst"]]},
        "hsn": {"hsn_b2b": hsn_rows(r["hsn"]["b2b"]), "hsn_b2c": hsn_rows(r["hsn"]["b2c"])},
        "doc_issue": {"doc_det": [{"doc_num": 1 if x["nature"].startswith("Invoices") else 5, "doc_typ": x["nature"],
                                   "docs": [{"num": 1, "from": str(x["from"]), "to": str(x["to"]), "totnum": x["total"],
                                             "cancel": x["canceled"], "net_issue": x["net_issued"]}]} for x in r["doc_issue"]]},
    }


def gstr3b_json(session: Session, year: int, month: int) -> dict:
    r = gstr3b(session, year, month)
    o = r["outward"]

    def amt(x, keys=("taxable", "igst", "cgst", "sgst", "cess")):
        names = {"taxable": "txval", "igst": "iamt", "cgst": "camt", "sgst": "samt", "cess": "csamt"}
        return {names[k]: _f(x[k]) for k in keys}

    itc = r["itc"]
    heads = lambda x: {"iamt": _f(x["igst"]), "camt": _f(x["cgst"]), "samt": _f(x["sgst"]), "csamt": _f(x["cess"])}  # noqa: E731
    zero = {"iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0}
    return {
        "gstin": r["gstin"], "ret_period": r["period"],
        "sup_details": {"osup_det": amt(o["a_taxable"]), "osup_zero": amt(o["b_zero_rated"], ("taxable", "igst", "cess")),
                        "osup_nil_exmp": amt(o["c_nil_exempt"], ("taxable",)), "isup_rev": amt(o["d_reverse_charge"]),
                        "osup_nongst": amt(o["e_non_gst"], ("taxable",))},
        "inter_sup": {"unreg_details": [{"pos": x["pos"], "txval": _f(x["taxable"]), "iamt": _f(x["igst"])} for x in r["inter_state_unregistered"]],
                      "comp_details": [{"pos": x["pos"], "txval": _f(x["taxable"]), "iamt": _f(x["igst"])} for x in r["inter_state_composition"]],
                      "uin_details": []},
        "itc_elg": {"itc_avl": [{"ty": "IMPG", **zero}, {"ty": "IMPS", **zero}, {"ty": "ISRC", **zero}, {"ty": "ISD", **zero},
                                {"ty": "OTH", **heads(itc["available_other"])}],
                    "itc_rev": [{"ty": "RUL", **zero}, {"ty": "OTH", **zero}],
                    "itc_net": heads(itc["net"]),
                    "itc_inelg": [{"ty": "RUL", **zero}, {"ty": "OTH", **zero}]},
        "inward_sup": {"isup_details": [{"ty": "GST", "inter": _f(r["exempt_inward"]["inter"]), "intra": _f(r["exempt_inward"]["intra"])},
                                        {"ty": "NONGST", "inter": 0.0, "intra": 0.0}]},
    }
