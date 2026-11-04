"""Withholding tax (India): TDS on A/P invoices / credit memos and on advances (outgoing payments on
account), TCS on A/R invoices / credit memos, challans (deposit with the government), quarterly returns
(Form 26Q TDS / 27EQ TCS) and certificates (Form 16A / 27D).

TCS (codes with WTKind C, customers with WTLiable Y): collected on top of the invoice (DocTotal = gross +
TCS), base gross incl. GST (BaseType G), same thresholds; INV5 / RIN5. Advances: an outgoing payment on
account to a TDS vendor can deduct TDS (VPM5): the cash paid is grossed up (the vendor is debited the
advance before TDS); a later A/P invoice deducts its TDS less the advance TDS not yet adjusted (AdvAdj).

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


KIND_OBJS = {"D": (("18", 1), ("19", -1)), "C": (("13", 1), ("14", -1))}


def year_to_date(session: Session, card_code: str, wt_code: str, start: date, before: date | None = None) -> tuple[Decimal, Decimal]:
    """(base, TDS / TCS) of a partner and code in the financial year: invoices less credit memos, canceled left out."""
    base = tds = ZERO
    wt = session.get(WithholdingTax, wt_code)
    for obj, sign in KIND_OBJS[wt.wt_kind if wt else "D"]:
        hcls, wcls = DOCUMENT_CLASSES[obj][0], DOCUMENT_WITHHOLDING[obj]
        # the tax borne by the year's invoices: withheld on them plus what was deducted on advances (AdvAdj)
        q = select(func.coalesce(func.sum(wcls.taxble_amnt), 0), func.coalesce(func.sum(wcls.wt_amnt + wcls.adv_adj), 0)).join(
            hcls, hcls.doc_entry == wcls.doc_entry).where(hcls.card_code == card_code, wcls.wt_code == wt_code,
                                                          hcls.canceled == "N", hcls.doc_date >= start)
        if before is not None:
            q = q.where(hcls.doc_date <= before)
        b, t = session.execute(q).one()
        base += sign * Decimal(b)
        tds += sign * Decimal(t)
    return base, tds


def advance_open(session: Session, card_code: str, wt_code: str) -> Decimal:
    """TDS deducted on advances of a vendor and code (active payments) not yet adjusted by A/P invoices."""
    from app.models.banking import OutgoingPayment, PaymentWithholding

    paid = session.scalar(select(func.coalesce(func.sum(PaymentWithholding.wt_amnt), 0)).join(
        OutgoingPayment, OutgoingPayment.doc_entry == PaymentWithholding.doc_entry).where(
        OutgoingPayment.card_code == card_code, OutgoingPayment.canceled == "N", PaymentWithholding.wt_code == wt_code))
    hcls, wcls = DOCUMENT_CLASSES["18"][0], DOCUMENT_WITHHOLDING["18"]
    used = session.scalar(select(func.coalesce(func.sum(wcls.adv_adj), 0)).join(hcls, hcls.doc_entry == wcls.doc_entry).where(
        hcls.card_code == card_code, hcls.canceled == "N", wcls.wt_code == wt_code))
    return Decimal(paid) - Decimal(used)


def advance_rows(session: Session, bp: BusinessPartner, cash: Decimal) -> tuple[list[dict], Decimal]:
    """TDS on an advance of `cash` (LC, paid to the vendor): rows per TDS code of the vendor and the advance
    before TDS (cash grossed up: advance = cash + TDS)."""
    wts = [w for w in codes_of(session, bp) if w.wt_kind == "D"]
    if not wts:
        raise B1Error(f"{bp.card_code} has no TDS codes (withholding tax liable with CRD4 codes)")
    pan = pan_of(bp)
    pcts = [(w, w.rate if pan else max(w.rate, w.rate_no_pan)) for w in wts]
    total_pct = sum((p for _, p in pcts), ZERO)
    if total_pct >= 100:
        raise B1Error("The TDS rates add up to 100 % or more")
    gross0 = cash * 100 / (100 - total_pct)
    rows = [{"wt_code": w.wt_code, "rate": p, "wt_amnt": rupees(gross0 * p / 100), "account": w.account, "section": w.section,
             "no_pan": "N" if pan else "Y"} for w, p in pcts]
    gross = cash + sum((r["wt_amnt"] for r in rows), ZERO)
    for r in rows:
        r["taxble_amnt"] = gross
    return rows, gross


def compute(session: Session, obj: str, doc, bp: BusinessPartner, net_lc: Decimal, rate: Decimal, codes: list[str] | None,
            base_invoice=None, gross_lc: Decimal | None = None) -> list[dict]:
    """TDS rows of a new A/P invoice (18) / credit memo (19), TCS rows of an A/R invoice (13) / credit memo (14);
    codes None = the partner's codes, [] = none."""
    kind = "C" if obj in {"13", "14"} else "D"
    if obj not in DOCUMENT_WITHHOLDING or bp is None or bp.card_type != ("C" if kind == "C" else "S"):
        return []
    if codes is None:
        wts = [w for w in codes_of(session, bp) if w.wt_kind == kind]
    else:
        wts = []
        for c in codes:
            wt = session.get(WithholdingTax, c)
            if wt is None or wt.inactive == "Y":
                raise B1Error(f"Withholding tax code {c} does not exist or is inactive")
            if wt.wt_kind != kind:
                raise B1Error(f"Withholding tax code {c} is a {'TCS' if wt.wt_kind == 'C' else 'TDS'} code")
            wts.append(wt)
    rows = []
    if obj in {"19", "14"}:
        # credit memo: reverse the TDS / TCS of the base invoice in proportion of the base
        if base_invoice is None:
            return []
        wcls = DOCUMENT_WITHHOLDING["18" if obj == "19" else "13"]
        for w in session.scalars(select(wcls).where(wcls.doc_entry == base_invoice.doc_entry)):
            if not w.taxble_amnt:
                continue
            wt = session.get(WithholdingTax, w.wt_code)
            mine = gross_lc if wt is not None and wt.base_type == "G" and gross_lc is not None else net_lc
            base = min(mine, w.taxble_amnt)
            amount = rupees(w.wt_amnt * base / w.taxble_amnt) if w.wt_amnt else ZERO  # the TDS the invoice held
            rows.append({"wt_code": w.wt_code, "rate": w.rate, "taxble_amnt": base, "wt_amnt": amount, "account": w.account,
                         "section": w.section, "no_pan": w.no_pan})
        return rows
    pan = pan_of(bp)
    start = fy_start(doc.doc_date)
    for wt in wts:
        pct = wt.rate if pan else max(wt.rate, wt.rate_no_pan)
        base_lc = gross_lc if wt.base_type == "G" and gross_lc is not None else net_lc
        ytd_base, ytd_tds = year_to_date(session, bp.card_code, wt.wt_code, start)
        total_base = ytd_base + base_lc
        crossed = (wt.thr_single and base_lc > wt.thr_single) or (wt.thr_annual and total_base > wt.thr_annual) \
            or (not wt.thr_single and not wt.thr_annual)
        if not crossed:
            amount = ZERO
        elif wt.thr_type == "E":  # only the part of the year's base above the threshold (194Q, 206C(1H))
            amount = rupees(max(ZERO, total_base - wt.thr_annual) * pct / 100) - ytd_tds
        else:  # the whole year's base once crossed: earlier invoices are caught up
            amount = max(rupees(base_lc * pct / 100), rupees(total_base * pct / 100) - ytd_tds) \
                if wt.thr_annual and total_base > wt.thr_annual else rupees(base_lc * pct / 100)
        amount = max(ZERO, min(amount, base_lc))
        adj = ZERO
        if obj == "18" and amount:  # TDS already deducted on advances to the vendor (not yet adjusted)
            adj = min(amount, max(ZERO, advance_open(session, bp.card_code, wt.wt_code)))
        rows.append({"wt_code": wt.wt_code, "rate": pct, "taxble_amnt": base_lc, "wt_amnt": amount - adj, "adv_adj": adj,
                     "account": wt.account, "section": wt.section, "no_pan": "N" if pan else "Y"})
    return rows


def store(session: Session, obj: str, doc, rows: list[dict], rate: Decimal, fc: bool) -> Decimal:
    """Write PCH5 / RPC5 rows; returns the TDS total (LC)."""
    cls = DOCUMENT_WITHHOLDING[obj]
    total = ZERO
    for n, r in enumerate(rows):
        fc_amount = (r["wt_amnt"] / rate).quantize(Decimal("0.01")) if fc and rate else ZERO
        session.add(cls(doc_entry=doc.doc_entry, line_num=n, wt_code=r["wt_code"], rate=r["rate"], taxble_amnt=r["taxble_amnt"],
                        wt_amnt=r["wt_amnt"], wt_amnt_fc=fc_amount, account=r["account"], category="I", section=r["section"],
                        no_pan=r["no_pan"], adv_adj=r.get("adv_adj", ZERO)))
        total += r["wt_amnt"]
    return total


def rows_of(session: Session, obj: str, doc_entry: int) -> list[dict]:
    if obj not in DOCUMENT_WITHHOLDING:
        return []
    cls = DOCUMENT_WITHHOLDING[obj]
    return [{"wt_code": w.wt_code, "rate": w.rate, "taxble_amnt": w.taxble_amnt, "wt_amnt": w.wt_amnt, "account": w.account,
             "section": w.section, "no_pan": w.no_pan == "Y", "adv_adj": w.adv_adj, "challan_abs": w.challan_abs}
            for w in session.scalars(select(cls).where(cls.doc_entry == doc_entry).order_by(cls.line_num))]


# ------------------------------------------------------------- maintenance
def code_out(w: WithholdingTax) -> dict:
    return {"wt_code": w.wt_code, "wt_name": w.wt_name, "rate": w.rate, "section": w.section, "account": w.account,
            "thr_single": w.thr_single, "thr_annual": w.thr_annual, "thr_type": w.thr_type, "rate_no_pan": w.rate_no_pan,
            "base_type": w.base_type, "category": w.category, "wt_kind": w.wt_kind, "inactive": w.inactive == "Y"}


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
    if data.get("wt_kind") is not None:
        if data["wt_kind"] not in {"D", "C"}:
            raise B1Error("Kind: D TDS (deducted on purchases) or C TCS (collected on sales)")
        w.wt_kind = data["wt_kind"]
    w.wt_kind = w.wt_kind or "D"
    if data.get("base_type") is not None:
        if data["base_type"] not in {"N", "G"}:
            raise B1Error("Base: N net (excl. GST) or G gross (incl. GST)")
        w.base_type = data["base_type"]
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
            wt = session.get(WithholdingTax, c)
            if wt is None:
                raise B1Error(f"Withholding tax code {c} does not exist")
            if (wt.wt_kind == "C") != (bp.card_type != "S"):
                raise B1Error(f"Code {c} is a {'TCS' if wt.wt_kind == 'C' else 'TDS'} code: TDS codes belong to vendors, TCS codes to customers")
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
QUARTERS = {1: (4, 6), 2: (7, 9), 3: (10, 12), 4: (1, 3)}  # financial-year quarter -> months
INTEREST = {"D": Decimal("1.5"), "C": Decimal("1")}  # % per month (part of a month = a month) for late deposit


def due_date(d: date) -> date:
    """Deposit due date of TDS / TCS: 7th of the next month; deductions of March by 30 April."""
    if d.month == 3:
        return date(d.year, 4, 30)
    return date(d.year + (d.month == 12), d.month % 12 + 1, 7)


def _months(a: date, b: date) -> int:
    """Months or parts of a month from a to b (interest under 201(1A) / 206C(7))."""
    if b <= a:
        return 0
    n = (b.year - a.year) * 12 + b.month - a.month + (1 if b.day >= a.day else 0)
    return max(n, 1)


def deductions(session: Session, kind: str | None = None, date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    """Every TDS / TCS row: documents (signed; credit memos negative) and advances, canceled left out."""
    from app.models.banking import OutgoingPayment, PaymentWithholding

    found = []
    for k in ("D", "C") if kind is None else (kind,):
        for obj, sign in KIND_OBJS[k]:
            hcls, wcls = DOCUMENT_CLASSES[obj][0], DOCUMENT_WITHHOLDING[obj]
            q = select(hcls, wcls).join(wcls, wcls.doc_entry == hcls.doc_entry).where(hcls.canceled == "N")
            if date_from:
                q = q.where(hcls.doc_date >= date_from)
            if date_to:
                q = q.where(hcls.doc_date <= date_to)
            for h, w in session.execute(q.order_by(hcls.doc_date, hcls.doc_num)):
                found.append((k, obj, h, w, sign))
        if k == "D":
            q = select(OutgoingPayment, PaymentWithholding).join(PaymentWithholding, PaymentWithholding.doc_entry == OutgoingPayment.doc_entry).where(
                OutgoingPayment.canceled == "N")
            if date_from:
                q = q.where(OutgoingPayment.doc_date >= date_from)
            if date_to:
                q = q.where(OutgoingPayment.doc_date <= date_to)
            for h, w in session.execute(q.order_by(OutgoingPayment.doc_date, OutgoingPayment.doc_num)):
                found.append((k, "46", h, w, 1))
    rows = []
    for k, obj, h, w, sign in found:
        bp = session.get(BusinessPartner, h.card_code)
        rows.append({"kind": k, "obj": obj, "doc_entry": h.doc_entry, "line_num": w.line_num, "doc_num": h.doc_num, "doc_date": h.doc_date,
                     "card_code": h.card_code, "card_name": h.card_name, "pan": pan_of(bp) if bp else None, "wt_code": w.wt_code,
                     "section": w.section, "rate": w.rate, "base": sign * w.taxble_amnt, "tds": sign * w.wt_amnt, "no_pan": w.no_pan == "Y",
                     "adv_adj": getattr(w, "adv_adj", ZERO), "account": w.account, "challan_abs": w.challan_abs,
                     "due_date": due_date(h.doc_date)})
    return rows


def _row_obj(session: Session, r: dict):
    from app.models.banking import PaymentWithholding

    cls = PaymentWithholding if r["obj"] == "46" else DOCUMENT_WITHHOLDING[r["obj"]]
    return session.get(cls, (r["doc_entry"], r["line_num"]))


def challan_preview(session: Session, kind: str, section: str, period_to: date, dep_date: date) -> dict:
    rows = [r for r in deductions(session, kind, date_to=period_to) if r["section"] == section and r["challan_abs"] is None and r["tds"]]
    tax = sum((r["tds"] for r in rows), ZERO)
    interest = ZERO
    for r in rows:  # late deposit: from the date of deduction / collection, per month or part of it
        if dep_date > r["due_date"]:  # signed: a credit memo reduces the interest of its month
            interest += r["tds"] * INTEREST[kind] / 100 * _months(r["doc_date"], dep_date)
    return {"kind": kind, "section": section, "period_to": period_to, "rows": rows, "tax": tax, "interest": rupees(max(interest, ZERO))}


def _date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def create_challan(session: Session, data: dict):
    """Deposit the TDS / TCS of a section up to a date: Dr TDS / TCS payable (and interest / fee expense) / Cr bank."""
    from app.models.banking import TaxChallan
    from app.services import journal

    kind, section = data.get("wt_kind") or "D", (data.get("section") or "").strip()
    if kind not in {"D", "C"}:
        raise B1Error("Kind: D TDS or C TCS")
    if not data.get("period_to") or not data.get("dep_date"):
        raise B1Error("Enter the period (deductions up to) and the deposit date")
    period_to, dep_date = _date(data["period_to"]), _date(data["dep_date"])
    bsr, no = (data.get("bsr_code") or "").strip(), (data.get("challan_no") or "").strip()
    if not re.match(r"^[0-9]{7}$", bsr) or not re.match(r"^[0-9]{1,5}$", no):
        raise B1Error("Enter the BSR code (7 digits) and the challan serial number (up to 5 digits)")
    acct = session.get(Account, data.get("bank_acct") or "")
    if acct is None or acct.postable != "Y":
        raise B1Error("Choose the bank account the challan is paid from")
    pv = challan_preview(session, kind, section, period_to, dep_date)
    if pv["tax"] <= 0:
        raise B1Error(f"Nothing to deposit for section {section} up to {period_to}")
    interest = rupees(Decimal(str(data["interest"]))) if data.get("interest") is not None else pv["interest"]
    fee = rupees(Decimal(str(data.get("fee") or 0)))
    by_acct: dict[str, Decimal] = {}
    for r in pv["rows"]:
        by_acct[r["account"]] = by_acct.get(r["account"], ZERO) + r["tds"]
    lines = [journal.JournalLineRequest(account=a, debit=v if v > 0 else ZERO, credit=-v if v < 0 else ZERO, line_memo=f"{section} {no}")
             for a, v in by_acct.items() if v]
    if interest or fee:
        lines.append(journal.JournalLineRequest(account=data.get("expense_acct") or "619000", debit=interest + fee, line_memo="Interest / fee"))
    lines.append(journal.JournalLineRequest(account=acct.acct_code, credit=pv["tax"] + interest + fee, line_memo=f"Challan {bsr} {no}"))
    abs_ = (session.scalar(select(func.max(TaxChallan.abs_entry))) or 0) + 1
    memo = f"{'TDS' if kind == 'D' else 'TCS'} {section} challan {no}"[:50]
    try:
        je = journal.post_entry(session, journal.JournalRequest(ref_date=dep_date, lines=lines, memo=memo, ref1=no, ref2=bsr,
                                                                ref3=f"CHALLAN:{abs_}", manual=False), commit=False)
        ch = TaxChallan(abs_entry=abs_, wt_kind=kind, section=section, period_to=period_to, dep_date=dep_date, bsr_code=bsr, challan_no=no,
                        tax_amnt=pv["tax"], interest=interest, fee=fee, bank_acct=acct.acct_code, trans_id=je.trans_id, canceled="N")
        session.add(ch)
        for r in pv["rows"]:
            _row_obj(session, r).challan_abs = abs_
        session.commit()
    except Exception:
        session.rollback()
        raise
    return ch


def cancel_challan(session: Session, abs_entry: int) -> None:
    from app.models.banking import PaymentWithholding, TaxChallan
    from app.services import journal

    ch = session.get(TaxChallan, abs_entry)
    if ch is None or ch.canceled == "Y":
        raise B1Error(f"Challan {abs_entry} does not exist or is canceled")
    try:
        journal.reverse_entry(session, ch.trans_id, ref_date=ch.dep_date, commit=False)
        for cls in [*DOCUMENT_WITHHOLDING.values(), PaymentWithholding]:
            for w in session.scalars(select(cls).where(cls.challan_abs == abs_entry)):
                w.challan_abs = None
        ch.canceled = "Y"
        session.commit()
    except Exception:
        session.rollback()
        raise


def challan_out(c) -> dict:
    return {"abs_entry": c.abs_entry, "wt_kind": c.wt_kind, "section": c.section, "period_to": c.period_to, "dep_date": c.dep_date,
            "bsr_code": c.bsr_code, "challan_no": c.challan_no, "tax_amnt": c.tax_amnt, "interest": c.interest, "fee": c.fee,
            "total": c.tax_amnt + c.interest + c.fee, "bank_acct": c.bank_acct, "trans_id": c.trans_id, "canceled": c.canceled == "Y"}


def blocks_cancel(session: Session, obj: str, doc_entry: int) -> str | None:
    """A document / payment whose TDS / TCS is deposited (challan) cannot be canceled."""
    from app.models.banking import PaymentWithholding

    cls = PaymentWithholding if obj == "46" else DOCUMENT_WITHHOLDING.get(obj)
    if cls is None:
        return None
    if session.scalar(select(cls.line_num).where(cls.doc_entry == doc_entry, cls.challan_abs.is_not(None)).limit(1)) is not None:
        return "its TDS / TCS is deposited with a challan; cancel the challan first"
    return None


def report(session: Session, date_from: date, date_to: date, kind: str | None = None) -> dict:
    """TDS / TCS register: every deduction with its challan; summary per kind, section and month with the deposit
    due date, deposited and outstanding amounts."""
    from app.models.banking import TaxChallan

    rows = deductions(session, kind, date_from, date_to)
    chal = {c.abs_entry: c for c in session.scalars(select(TaxChallan))}
    summary: dict[tuple, dict] = {}
    for r in rows:
        c = chal.get(r["challan_abs"])
        r["challan"] = f"{c.bsr_code}/{c.challan_no} {c.dep_date}" if c else None
        month = r["doc_date"].replace(day=1)
        s = summary.setdefault((r["kind"], r["section"], month), {"kind": r["kind"], "section": r["section"], "month": month.strftime("%Y-%m"),
                                                                  "due_date": due_date(month), "base": ZERO, "tds": ZERO, "deposited": ZERO,
                                                                  "documents": 0})
        s["base"] += r["base"]
        s["tds"] += r["tds"]
        s["deposited"] += r["tds"] if c else ZERO
        s["documents"] += 1
    for s in summary.values():
        s["outstanding"] = s["tds"] - s["deposited"]
    return {"date_from": date_from, "date_to": date_to, "rows": rows,
            "summary": sorted(summary.values(), key=lambda s: (s["month"], s["kind"], s["section"])),
            "total": sum((r["tds"] for r in rows if r["kind"] == "D"), ZERO), "total_tcs": sum((r["tds"] for r in rows if r["kind"] == "C"), ZERO),
            "challans": [challan_out(c) for c in sorted(chal.values(), key=lambda c: c.abs_entry, reverse=True)]}


def _quarter(fy: int, q: int) -> tuple[date, date]:
    """Financial year fy (starting April fy) quarter q -> (first day, last day)."""
    import calendar

    if q not in QUARTERS:
        raise B1Error("Quarter: 1 (Apr-Jun), 2 (Jul-Sep), 3 (Oct-Dec), 4 (Jan-Mar)")
    m1, m2 = QUARTERS[q]
    year = fy if q < 4 else fy + 1
    return date(year, m1, 1), date(year, m2, calendar.monthrange(year, m2)[1])


def quarterly_return(session: Session, kind: str, fy: int, q: int) -> dict:
    """Form 26Q (TDS, non-salary) / 27EQ (TCS): deductor, challans and the deductee records of a quarter."""
    from app.models.banking import TaxChallan
    from app.services.admin import company

    if kind not in {"D", "C"}:
        raise B1Error("Kind: D TDS (26Q) or C TCS (27EQ)")
    start, end = _quarter(fy, q)
    comp = company(session)
    # records with tax only: an invoice below the threshold, or whose TDS was deducted on the advance, has no deduction
    rows = [r for r in deductions(session, kind, start, end) if r["tds"]]
    chal = {c.abs_entry: c for c in session.scalars(select(TaxChallan).where(TaxChallan.canceled == "N"))}
    issues = []
    if not comp.tan_no:
        issues.append("The company has no TAN (Administration -> Company details)")
    challans: dict[int, dict] = {}
    deductees = []
    for n, r in enumerate(rows, 1):
        c = chal.get(r["challan_abs"])
        if c is None and r["tds"]:
            issues.append(f"{r['card_code']} {r['section']} {r['doc_date']}: {r['tds']:,.0f} not deposited (no challan)")
        if not r["pan"]:
            issues.append(f"{r['card_code']}: no PAN (higher rate {'206AA' if kind == 'D' else '206CC'}; PANNOTAVBL in the return)")
        if c is not None:
            ch = challans.setdefault(c.abs_entry, {**challan_out(c), "booked": ZERO, "records": 0})
            ch["booked"] += r["tds"]
            ch["records"] += 1
        deductees.append({"record": n, "pan": r["pan"] or "PANNOTAVBL", "name": r["card_name"], "section": r["section"],
                          "date_paid_credited": r["doc_date"], "amount": r["base"], "rate": r["rate"], "tax": r["tds"],
                          "date_deducted": r["doc_date"] if r["tds"] else None, "challan": f"{c.bsr_code}/{c.challan_no}" if c else None,
                          "deposit_date": c.dep_date if c else None, "higher_rate": "A" if r["no_pan"] else "",
                          "document": f"{r['obj']}/{r['doc_num']}", "card_code": r["card_code"]})
    return {"form": "26Q" if kind == "D" else "27EQ", "fy": f"{fy}-{(fy + 1) % 100:02d}", "quarter": q, "date_from": start, "date_to": end,
            "deductor": {"tan": comp.tan_no, "pan": (comp.tax_id or "")[2:12] or None, "name": comp.company_name, "gstin": comp.tax_id},
            "challans": sorted(challans.values(), key=lambda c: c["dep_date"]), "deductees": deductees,
            "total_amount": sum((d["amount"] for d in deductees), ZERO), "total_tax": sum((d["tax"] for d in deductees), ZERO),
            "issues": issues}


def quarterly_csv(session: Session, kind: str, fy: int, q: int) -> str:
    """Deductee records in the column order of the return preparation utility (deductee details sheet)."""
    import csv
    import io

    r = quarterly_return(session, kind, fy, q)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Sr. No", "Deductee / collectee PAN", "Name", "Section", "Date of payment / credit", "Amount paid / credited",
                "Rate %", "Tax deducted / collected", "Date of deduction / collection", "BSR code / challan no.", "Date of deposit",
                "Reason (higher rate)"])
    for d in r["deductees"]:
        w.writerow([d["record"], d["pan"], d["name"], d["section"], d["date_paid_credited"].strftime("%d/%m/%Y"), f"{d['amount']:.2f}",
                    f"{d['rate']:.4f}".rstrip("0").rstrip("."), f"{d['tax']:.2f}",
                    d["date_deducted"].strftime("%d/%m/%Y") if d["date_deducted"] else "", d["challan"] or "",
                    d["deposit_date"].strftime("%d/%m/%Y") if d["deposit_date"] else "", d["higher_rate"]])
    return buf.getvalue()


def certificate(session: Session, kind: str, card_code: str, fy: int, q: int) -> dict:
    """Form 16A (TDS) / 27D (TCS) of a deductee / collectee for a quarter: amounts paid, tax and the challans."""
    bp = session.get(BusinessPartner, card_code)
    if bp is None:
        raise B1Error(f"Business partner {card_code} does not exist")
    r = quarterly_return(session, kind, fy, q)
    mine = [d for d in r["deductees"] if d["card_code"] == card_code]
    if not mine:
        raise B1Error(f"No {'TDS' if kind == 'D' else 'TCS'} of {card_code} in quarter {q} of {r['fy']}")
    return {"form": "16A" if kind == "D" else "27D", "fy": r["fy"], "quarter": q, "date_from": r["date_from"], "date_to": r["date_to"],
            "deductor": r["deductor"], "deductee": {"card_code": bp.card_code, "name": bp.card_name, "pan": pan_of(bp) or "PANNOTAVBL",
                                                    "address": ", ".join(filter(None, [bp.address, bp.city]))},
            "rows": mine, "total_amount": sum((d["amount"] for d in mine), ZERO), "total_tax": sum((d["tax"] for d in mine), ZERO),
            "deposited": sum((d["tax"] for d in mine if d["challan"]), ZERO)}
