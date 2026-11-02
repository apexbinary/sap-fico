"""Print data of marketing documents (GST layout): parties, lines with HSN / SAC and tax components,
HSN-wise tax summary, totals and the amount in words."""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import PaymentTerms, State, TaxGroup
from app.models.banking import Bank, HouseBankAccount
from app.models.inventory import Item
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import tax
from app.services.admin import B1Error, company
from app.services.documents import DEFS, get_document

ZERO = Decimal("0")
TITLES = {  # document type -> printed title (India)
    "23": "Quotation", "17": "Sales Order", "15": "Delivery Challan", "16": "Sales Return", "13": "Tax Invoice",
    "14": "Credit Note", "540000006": "Request for Quotation", "22": "Purchase Order", "20": "Goods Receipt Note",
    "21": "Purchase Return", "18": "Purchase Invoice", "19": "Debit Note",
}
NO_PRICES = {"15", "20", "21", "16"}  # delivery challans / receipts / returns print quantities only

ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen",
        "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_100(n: int) -> str:
    return ONES[n] if n < 20 else (TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else ""))


def _below_1000(n: int) -> str:
    h, rest = divmod(n, 100)
    return " ".join(p for p in (f"{ONES[h]} Hundred" if h else "", _below_100(rest) if rest else "") if p)


def words_indian(n: int) -> str:
    """Integer in words with the Indian system (thousand, lakh, crore)."""
    if n == 0:
        return "Zero"
    parts = []
    crore, n = divmod(n, 10_000_000)
    if crore:
        parts.append(f"{words_indian(crore)} Crore")
    lakh, n = divmod(n, 100_000)
    if lakh:
        parts.append(f"{_below_100(lakh)} Lakh")
    thousand, n = divmod(n, 1000)
    if thousand:
        parts.append(f"{_below_100(thousand)} Thousand")
    if n:
        parts.append(_below_1000(n))
    return " ".join(parts)


def amount_in_words(amount: Decimal, currency: str) -> str:
    amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, frac = int(amount), int((amount - int(amount)) * 100)
    unit, sub = {"INR": ("Rupees", "Paise"), "USD": ("US Dollars", "Cents"), "EUR": ("Euros", "Cents"),
                 "GBP": ("Pounds", "Pence")}.get(currency, (currency, "Cents"))
    text = f"{unit} {words_indian(whole)}"
    if frac:
        text += f" and {words_indian(frac)} {sub}"
    return text + " Only"


def _party(session: Session, bp: BusinessPartner | None, kind: str, address_id: str | None, text: str | None) -> dict:
    a = session.get(PartnerAddress, (bp.card_code, kind, address_id)) if bp is not None and address_id else None
    state = session.get(State, (a.country or "IN", a.state)) if a is not None and a.state else None
    return {"name": bp.card_name if bp else None, "code": bp.card_code if bp else None, "address": text,
            "gstin": (a.gst_regn_no if a is not None else None) or (bp.lic_trad_num if bp else None),
            "state": state.name if state else None, "state_code": state.gst_code if state else None}


def print_data(session: Session, obj: str, doc_entry: int) -> dict:
    if obj not in DEFS or DEFS[obj].side == "I":
        raise B1Error("Only sales and purchasing documents have a print layout")
    doc = get_document(session, obj, doc_entry)
    comp = company(session)
    comp_state = session.get(State, ("IN", comp.state)) if comp.state else None
    bp = session.get(BusinessPartner, doc.card_code) if doc.card_code else None
    bill_to = _party(session, bp, "B", doc.pay_to_code, doc.address)
    ship_to = _party(session, bp, "S", doc.ship_to_code, doc.address2 or doc.address)
    fc = doc.doc_cur != comp.main_curncy
    lines, hsn_summary, kinds = [], defaultdict(lambda: defaultdict(lambda: ZERO)), set()
    for l in doc.lines:
        tg = session.get(TaxGroup, l.vat_group) if l.vat_group else None
        net = (l.total_frgn if fc else l.line_total) * (1 - doc.disc_prcnt / 100)
        rates = {a.code: r for a, r in tax.components(session, tg)} if tg else {}
        comps = {name: (rates.get(name, tg.rate), amount) for _, amount, name in tax.split(session, tg, net)} if tg else {}
        kind = tax.gst_kind(session, tg)
        kinds.add(kind)
        item = session.get(Item, l.item_code) if l.item_code else None
        hsn = item.chapter_id if item else None
        row = {"line": l.line_num + 1, "description": l.dscription, "item_code": l.item_code, "hsn": hsn,
               "quantity": l.quantity, "uom": l.unit_msr, "rate": l.price_bef_di, "disc_prcnt": l.disc_prcnt,
               "taxable": net.quantize(Decimal("0.01")), "tax_code": l.vat_group,
               "cgst": comps.get("CGST"), "sgst": comps.get("SGST"), "igst": comps.get("IGST"),
               "other_tax": {k: v for k, v in comps.items() if k not in {"CGST", "SGST", "IGST"}},
               "total": (l.gtotal_fc if fc else l.gtotal)}
        lines.append(row)
        s = hsn_summary[hsn or "—"]
        s["taxable"] += row["taxable"]
        for name, (_, amount) in comps.items():
            s[name] += amount
    terms = session.get(PaymentTerms, doc.group_num) if doc.group_num is not None else None
    house = session.scalars(select(HouseBankAccount).order_by(HouseBankAccount.abs_entry)).first()
    bank = session.scalar(select(Bank).where(Bank.bank_code == house.bank_code)) if house else None
    total = doc.doc_total_fc if fc else doc.doc_total
    return {
        "obj": obj, "title": TITLES[obj], "doc_name": DEFS[obj].name, "no_prices": obj in NO_PRICES,
        "doc_num": doc.doc_num, "doc_date": doc.doc_date, "doc_due_date": doc.doc_due_date, "tax_date": doc.tax_date,
        "num_at_card": doc.num_at_card, "canceled": doc.canceled == "Y", "currency": doc.doc_cur, "rate": doc.doc_rate,
        "company": {"name": comp.company_name, "address": comp.address, "gstin": comp.tax_id, "phone": comp.phone,
                    "e_mail": comp.e_mail, "state": comp_state.name if comp_state else None,
                    "state_code": comp_state.gst_code if comp_state else None},
        "bill_to": bill_to, "ship_to": ship_to,
        "place_of_supply": ship_to["state"] if DEFS[obj].side == "S" else bill_to["state"],
        "supply": "inter-state" if "inter" in kinds else "intra-state" if "intra" in kinds else None,
        "lines": lines,
        "hsn_summary": [{"hsn": k, **{n: v for n, v in vals.items()}} for k, vals in hsn_summary.items()],
        "totals": {"before_discount": sum(((l.total_frgn if fc else l.line_total) for l in doc.lines), ZERO),
                   "discount": doc.disc_sum_fc if fc else doc.disc_sum, "disc_prcnt": doc.disc_prcnt,
                   "tax": doc.vat_sum_fc if fc else doc.vat_sum, "total": total,
                   "paid": doc.paid_fc if fc else doc.paid_to_date},
        "amount_in_words": amount_in_words(total, doc.doc_cur),
        "payment_terms": terms.pymnt_group if terms else None, "comments": doc.comments,
        "bank": {"name": bank.bank_name if bank else None, "account": house.account if house else None,
                 "branch": house.branch if house else None, "swift": bank.swift_num if bank else None} if house else None,
    }
