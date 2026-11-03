"""Withholding tax (India: TDS) on A/P invoices and credit memos.

A vendor with WTLiable Y and withholding codes (CRD4) gets TDS on each A/P invoice: base = net
amount excl. GST (CBDT circular 23/2017), rate of the code, or RateNoPAN (section 206AA) without a
PAN; whole rupees (section 288B). Thresholds per vendor and code in the financial year (April -
March): deducted when the invoice exceeds ThrSingle or the year's base (with this invoice) exceeds
ThrAnnual; ThrType A then taxes the whole year's base (earlier invoices caught up), ThrType E only
the excess (194Q). The vendor line is credited with the total less TDS, the code's account with
the TDS (PCH5). A credit memo copied from an invoice reverses its TDS in proportion (RPC5).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.admin import WithholdingTax
from app.models.documents import DOCUMENT_CLASSES, DOCUMENT_WITHHOLDING
from app.models.finance import Account
from app.models.partners import BusinessPartner, PartnerWithholding
from app.services.admin import B1Error

ZERO = Decimal("0")
PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN = re.compile(r"^[0-9]{2}([A-Z]{5}[0-9]{4}[A-Z])[0-9A-Z]Z[0-9A-Z]$")


def rupees(x: Decimal) -> Decimal:
    return Decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def fy_start(d: date) -> date:
    return date(d.year if d.month >= 4 else d.year - 1, 4, 1)


def pan_of(bp: BusinessPartner) -> str | None:
    """PAN of the partner: entered, else taken from its GSTIN (characters 3-12)."""
    if bp.pan_no and PAN.match(bp.pan_no):
        return bp.pan_no
    m = GSTIN.match((bp.lic_trad_num or "").upper())
    return m.group(1) if m else None


def codes_of(session: Session, bp: BusinessPartner) -> list[WithholdingTax]:
    if bp.wt_liable != "Y":
        return []
    rows = session.scalars(select(WithholdingTax).join(PartnerWithholding, PartnerWithholding.wt_code == WithholdingTax.wt_code)
                           .where(PartnerWithholding.card_code == bp.card_code, WithholdingTax.inactive == "N")
                           .order_by(WithholdingTax.wt_code)).all()
    return list(rows)


def year_to_date(session: Session, card_code: str, wt_code: str, start: date, before: date | None = None) -> tuple[Decimal, Decimal]:
    """(base, TDS) of a vendor and code in the financial year: invoices less credit memos, canceled left out."""
    base = tds = ZERO
    for obj, sign in (("18", 1), ("19", -1)):
        hcls, wcls = DOCUMENT_CLASSES[obj][0], DOCUMENT_WITHHOLDING[obj]
        q = select(func.coalesce(func.sum(wcls.taxble_amnt), 0), func.coalesce(func.sum(wcls.wt_amnt), 0)).join(
            hcls, hcls.doc_entry == wcls.doc_entry).where(hcls.card_code == card_code, wcls.wt_code == wt_code,
                                                          hcls.canceled == "N", hcls.doc_date >= start)
        if before is not None:
            q = q.where(hcls.doc_date <= before)
        b, t = session.execute(q).one()
        base += sign * Decimal(b)
        tds += sign * Decimal(t)
    return base, tds


def compute(session: Session, obj: str, doc, bp: BusinessPartner, net_lc: Decimal, rate: Decimal, codes: list[str] | None,
            base_invoice=None) -> list[dict]:
    """TDS rows of a new A/P invoice (18) or credit memo (19); codes None = the vendor's codes, [] = none."""
    if obj not in DOCUMENT_WITHHOLDING or bp is None or bp.card_type != "S":
        return []
    if codes is None:
        wts = codes_of(session, bp)
    else:
        wts = []
        for c in codes:
            wt = session.get(WithholdingTax, c)
            if wt is None or wt.inactive == "Y":
                raise B1Error(f"Withholding tax code {c} does not exist or is inactive")
            wts.append(wt)
    rows = []
    if obj == "19":
        # credit memo: reverse the TDS of the base invoice in proportion of the base
        if base_invoice is None:
            return []
        wcls = DOCUMENT_WITHHOLDING["18"]
        for w in session.scalars(select(wcls).where(wcls.doc_entry == base_invoice.doc_entry)):
            if not w.taxble_amnt:
                continue
            base = min(net_lc, w.taxble_amnt)
            amount = rupees(w.wt_amnt * base / w.taxble_amnt) if w.wt_amnt else ZERO
            rows.append({"wt_code": w.wt_code, "rate": w.rate, "taxble_amnt": base, "wt_amnt": amount, "account": w.account,
                         "section": w.section, "no_pan": w.no_pan})
        return rows
    pan = pan_of(bp)
    start = fy_start(doc.doc_date)
    for wt in wts:
        pct = wt.rate if pan else max(wt.rate, wt.rate_no_pan)
        ytd_base, ytd_tds = year_to_date(session, bp.card_code, wt.wt_code, start)
        total_base = ytd_base + net_lc
        crossed = (wt.thr_single and net_lc > wt.thr_single) or (wt.thr_annual and total_base > wt.thr_annual) \
            or (not wt.thr_single and not wt.thr_annual)
        if not crossed:
            amount = ZERO
        elif wt.thr_type == "E":  # only the part of the year's base above the threshold (194Q)
            amount = rupees(max(ZERO, total_base - wt.thr_annual) * pct / 100) - ytd_tds
        else:  # the whole year's base once crossed: earlier invoices are caught up
            amount = max(rupees(net_lc * pct / 100), rupees(total_base * pct / 100) - ytd_tds) \
                if wt.thr_annual and total_base > wt.thr_annual else rupees(net_lc * pct / 100)
        amount = max(ZERO, min(amount, net_lc))
        rows.append({"wt_code": wt.wt_code, "rate": pct, "taxble_amnt": net_lc, "wt_amnt": amount, "account": wt.account,
                     "section": wt.section, "no_pan": "N" if pan else "Y"})
    return rows


def store(session: Session, obj: str, doc, rows: list[dict], rate: Decimal, fc: bool) -> Decimal:
    """Write PCH5 / RPC5 rows; returns the TDS total (LC)."""
    cls = DOCUMENT_WITHHOLDING[obj]
    total = ZERO
    for n, r in enumerate(rows):
        fc_amount = (r["wt_amnt"] / rate).quantize(Decimal("0.01")) if fc and rate else ZERO
        session.add(cls(doc_entry=doc.doc_entry, line_num=n, wt_code=r["wt_code"], rate=r["rate"], taxble_amnt=r["taxble_amnt"],
                        wt_amnt=r["wt_amnt"], wt_amnt_fc=fc_amount, account=r["account"], category="I", section=r["section"],
                        no_pan=r["no_pan"]))
        total += r["wt_amnt"]
    return total


def rows_of(session: Session, obj: str, doc_entry: int) -> list[dict]:
    if obj not in DOCUMENT_WITHHOLDING:
        return []
    cls = DOCUMENT_WITHHOLDING[obj]
    return [{"wt_code": w.wt_code, "rate": w.rate, "taxble_amnt": w.taxble_amnt, "wt_amnt": w.wt_amnt, "account": w.account,
             "section": w.section, "no_pan": w.no_pan == "Y"}
            for w in session.scalars(select(cls).where(cls.doc_entry == doc_entry).order_by(cls.line_num))]


# ------------------------------------------------------------- maintenance
def code_out(w: WithholdingTax) -> dict:
    return {"wt_code": w.wt_code, "wt_name": w.wt_name, "rate": w.rate, "section": w.section, "account": w.account,
            "thr_single": w.thr_single, "thr_annual": w.thr_annual, "thr_type": w.thr_type, "rate_no_pan": w.rate_no_pan,
            "base_type": w.base_type, "category": w.category, "inactive": w.inactive == "Y"}


def save_code(session: Session, data: dict, code: str | None = None) -> WithholdingTax:
    if code is None:
        code = (data.get("wt_code") or "").strip().upper()
        if not re.match(r"^[A-Z0-9]{1,4}$", code):
            raise B1Error("A withholding tax code has 1-4 letters or digits")
        if session.get(WithholdingTax, code) is not None:
            raise B1Error(f"Withholding tax code {code} already exists")
        w = WithholdingTax(wt_code=code, category="I", base_type="N")
        session.add(w)
    else:
        w = session.get(WithholdingTax, code)
        if w is None:
            raise B1Error(f"Withholding tax code {code} does not exist")
    for key in ("wt_name", "section"):
        if data.get(key) is not None:
            setattr(w, key, data[key].strip())
    if not w.wt_name or not w.section:
        raise B1Error("Enter the name and the section")
    for key in ("rate", "thr_single", "thr_annual", "rate_no_pan"):
        if data.get(key) is not None:
            v = Decimal(str(data[key]))
            if v < 0 or (key in {"rate", "rate_no_pan"} and v > 100):
                raise B1Error(f"{key.replace('_', ' ')} must be 0-100 %" if "rate" in key else "Thresholds cannot be negative")
            setattr(w, key, v)
    if w.rate is None:
        raise B1Error("Enter the rate")
    w.thr_single = w.thr_single if w.thr_single is not None else ZERO
    w.thr_annual = w.thr_annual if w.thr_annual is not None else ZERO
    w.rate_no_pan = w.rate_no_pan if w.rate_no_pan is not None else Decimal("20")
    if data.get("thr_type") is not None:
        if data["thr_type"] not in {"A", "E"}:
            raise B1Error("Threshold type: A whole amount once crossed, E only the excess")
        w.thr_type = data["thr_type"]
    w.thr_type = w.thr_type or "A"
    if data.get("account") is not None:
        acct = session.get(Account, data["account"])
        if acct is None or acct.postable != "Y":
            raise B1Error(f"Account {data['account']} does not exist or is a title account")
        w.account = data["account"]
    if not w.account:
        raise B1Error("Enter the TDS account")
    if data.get("inactive") is not None:
        w.inactive = "Y" if data["inactive"] else "N"
    session.commit()
    return w


def set_partner(session: Session, bp: BusinessPartner, data: dict) -> None:
    """WTLiable, PAN and the withholding codes (CRD4) of a business partner."""
    if data.get("wt_liable") is not None:
        bp.wt_liable = "Y" if data["wt_liable"] else "N"
    if "pan_no" in data:
        pan = (data["pan_no"] or "").strip().upper() or None
        if pan and not PAN.match(pan):
            raise B1Error(f"PAN {pan} is not in the format AAAAA9999A")
        bp.pan_no = pan
    if data.get("wt_codes") is not None:
        for c in data["wt_codes"]:
            if session.get(WithholdingTax, c) is None:
                raise B1Error(f"Withholding tax code {c} does not exist")
        for row in session.scalars(select(PartnerWithholding).where(PartnerWithholding.card_code == bp.card_code)):
            session.delete(row)
        session.flush()
        for c in dict.fromkeys(data["wt_codes"]):
            session.add(PartnerWithholding(card_code=bp.card_code, wt_code=c))
        session.flush()
    if bp.wt_liable == "Y" and not session.scalar(
            select(func.count()).select_from(PartnerWithholding).where(PartnerWithholding.card_code == bp.card_code)):
        raise B1Error("A business partner subject to withholding tax needs at least one withholding tax code")


def partner_out(session: Session, bp: BusinessPartner) -> dict:
    return {"wt_liable": bp.wt_liable == "Y", "pan_no": bp.pan_no, "pan": pan_of(bp),
            "wt_codes": [r.wt_code for r in session.scalars(select(PartnerWithholding).where(PartnerWithholding.card_code == bp.card_code))]}


# ------------------------------------------------------------- report
def due_date(d: date) -> date:
    """TDS deposit due date: 7th of the next month; deductions of March by 30 April."""
    if d.month == 3:
        return date(d.year, 4, 30)
    return date(d.year + (d.month == 12), d.month % 12 + 1, 7)


def report(session: Session, date_from: date, date_to: date) -> dict:
    """TDS register (per document), summary per section and month with the deposit due date."""
    rows = []
    for obj, sign in (("18", 1), ("19", -1)):
        hcls, wcls = DOCUMENT_CLASSES[obj][0], DOCUMENT_WITHHOLDING[obj]
        q = select(hcls, wcls).join(wcls, wcls.doc_entry == hcls.doc_entry).where(
            hcls.canceled == "N", hcls.doc_date >= date_from, hcls.doc_date <= date_to).order_by(hcls.doc_date, hcls.doc_num)
        for h, w in session.execute(q):
            bp = session.get(BusinessPartner, h.card_code)
            rows.append({"obj": obj, "doc_entry": h.doc_entry, "doc_num": h.doc_num, "doc_date": h.doc_date, "card_code": h.card_code,
                         "card_name": h.card_name, "pan": pan_of(bp) if bp else None, "wt_code": w.wt_code, "section": w.section,
                         "rate": w.rate, "base": sign * w.taxble_amnt, "tds": sign * w.wt_amnt, "no_pan": w.no_pan == "Y"})
    summary: dict[tuple, dict] = {}
    for r in rows:
        month = r["doc_date"].replace(day=1)
        s = summary.setdefault((r["section"], month), {"section": r["section"], "month": month.strftime("%Y-%m"),
                                                        "due_date": due_date(month), "base": ZERO, "tds": ZERO, "documents": 0})
        s["base"] += r["base"]
        s["tds"] += r["tds"]
        s["documents"] += 1
    return {"date_from": date_from, "date_to": date_to, "rows": rows,
            "summary": sorted(summary.values(), key=lambda s: (s["month"], s["section"])),
            "total": sum((r["tds"] for r in rows), ZERO)}
