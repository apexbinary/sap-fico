"""GST input tax credit: reversals / reclaims (journal entries) and GSTR-2B reconciliation.

ITC reversals are journal entries (TransType 30, Ref3 "ITC:<kind>", Ref1 the kind) on the input tax
accounts of the GST authorities (OSTA PurchTax):
    B1  permanent reversal (rules 38 / 42 / 43, section 17(5))   Cr input tax / Dr OACP ItcRevAcct (618000)
    B2  temporary reversal (rule 37: not paid within 180 days ...) Cr input tax / Dr OACP ItcRclAcct (116900)
    D1  reclaim of a temporary reversal                           Dr input tax / Cr ItcRclAcct
A reclaim cannot exceed what is still reversed per head; canceling reverses the entry (a temporary
reversal only while its amount has not been reclaimed). GSTR-3B 4(B)(1) / 4(B)(2) / 4(D)(1) read them.

GSTR-2B reconciliation compares the portal's GSTR-2B JSON (B2B invoices, CDNR credit / debit notes,
IMPG bills of entry) with the A/P invoices / credit memos of the month: vendor GSTIN + vendor invoice
number (NumAtCard), taxable value and tax per head (tolerance 1 rupee).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import TaxAuthority
from app.models.documents import DOCUMENT_CLASSES
from app.models.finance import AccountDetermination, JournalEntry, JournalLine
from app.services import journal
from app.services.admin import B1Error

ZERO = Decimal("0")
HEADS = ("igst", "cgst", "sgst", "cess")
KINDS = {"B1": "Permanent reversal (rules 38 / 42 / 43, section 17(5))", "B2": "Temporary reversal (rule 37, 180 days ...)",
         "D1": "Reclaim of a temporary reversal"}
HEAD_AUTHORITY = {"igst": "IGST", "cgst": "CGST", "sgst": "SGST", "cess": "CESS"}
TOLERANCE = Decimal("1")


def _m(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"))


def _det(session: Session, on: date) -> AccountDetermination:
    det = session.get(AccountDetermination, str(on.year))
    if det is None:
        raise B1Error(f"No G/L account determination for {on.year}")
    return det


def _input_account(session: Session, head: str) -> str:
    a = session.get(TaxAuthority, HEAD_AUTHORITY[head])
    if a is None:
        raise B1Error(f"Tax authority {HEAD_AUTHORITY[head]} does not exist")
    return a.purch_tax


def _entries(session: Session, kinds=tuple(KINDS), date_from: date | None = None, date_to: date | None = None):
    q = select(JournalEntry).where(JournalEntry.ref3.in_([f"ITC:{k}" for k in kinds])).order_by(JournalEntry.ref_date, JournalEntry.trans_id)
    if date_from:
        q = q.where(JournalEntry.ref_date >= date_from)
    if date_to:
        q = q.where(JournalEntry.ref_date <= date_to)
    return session.scalars(q).all()


def _amounts(session: Session, je: JournalEntry) -> dict:
    """Amount per head of a reversal entry (positive), from its input tax lines."""
    by_acct = {_input_account(session, h): h for h in HEADS if session.get(TaxAuthority, HEAD_AUTHORITY[h]) is not None}
    out = {h: ZERO for h in HEADS}
    for l in session.scalars(select(JournalLine).where(JournalLine.trans_id == je.trans_id)):
        if l.account in by_acct:
            out[by_acct[l.account]] += abs(l.debit - l.credit)
    return out


def _active(je: JournalEntry) -> bool:
    return not je.storno_to_tr  # canceled entries and their reversals both carry StornoToTr


def still_reversed(session: Session) -> dict:
    """Temporary reversals not yet reclaimed, per head."""
    out = {h: ZERO for h in HEADS}
    for je in _entries(session, ("B2", "D1")):
        if not _active(je):
            continue
        sign = 1 if je.ref3 == "ITC:B2" else -1
        for h, v in _amounts(session, je).items():
            out[h] += sign * v
    return out


def post(session: Session, kind: str, on: date, amounts: dict, memo: str | None = None) -> JournalEntry:
    if kind not in KINDS:
        raise B1Error("Kind: B1 permanent reversal, B2 temporary reversal, D1 reclaim")
    amounts = {h: _m(amounts.get(h) or 0) for h in HEADS}
    if any(v < 0 for v in amounts.values()) or not any(amounts.values()):
        raise B1Error("Enter the IGST / CGST / SGST / cess amounts (positive)")
    if kind == "D1":
        left = still_reversed(session)
        for h, v in amounts.items():
            if v > left[h]:
                raise B1Error(f"Only {left[h]:,.2f} {h.upper()} is reversed temporarily and can be reclaimed")
    det = _det(session, on)
    offset = det.itc_rev_acct if kind == "B1" else det.itc_rcl_acct
    lines = []
    for h, v in amounts.items():
        if v:
            acct = _input_account(session, h)
            lines.append(journal.JournalLineRequest(account=acct, debit=v if kind == "D1" else ZERO, credit=ZERO if kind == "D1" else v,
                                                    line_memo=f"ITC {h.upper()}"))
    total = sum(amounts.values(), ZERO)
    lines.append(journal.JournalLineRequest(account=offset, debit=ZERO if kind == "D1" else total, credit=total if kind == "D1" else ZERO))
    return journal.post_entry(session, journal.JournalRequest(ref_date=on, lines=lines, memo=(memo or KINDS[kind])[:50], ref1=kind,
                                                              ref3=f"ITC:{kind}", manual=False))


def cancel(session: Session, trans_id: int) -> JournalEntry:
    je = session.get(JournalEntry, trans_id)
    if je is None or not (je.ref3 or "").startswith("ITC:"):
        raise B1Error(f"Journal entry {trans_id} is no ITC reversal")
    if not _active(je):
        raise B1Error(f"ITC entry {trans_id} is already canceled")
    if je.ref3 == "ITC:B2":
        left, amt = still_reversed(session), _amounts(session, je)
        if any(amt[h] > left[h] for h in HEADS):
            raise B1Error("This temporary reversal has been reclaimed; cancel the reclaim first")
    return journal.reverse_entry(session, trans_id, ref_date=je.ref_date)


def listing(session: Session, date_from: date | None = None, date_to: date | None = None) -> dict:
    rows = [{"trans_id": je.trans_id, "number": je.number, "ref_date": je.ref_date, "kind": je.ref3[4:], "kind_name": KINDS[je.ref3[4:]],
             "memo": je.memo, "active": _active(je), **_amounts(session, je)} for je in _entries(session, date_from=date_from, date_to=date_to)
            if not (je.storno_to_tr and je.storno_to_tr < je.trans_id)]  # without the cancellation entries
    return {"rows": rows, "still_reversed": still_reversed(session), "kinds": KINDS}


def month_totals(session: Session, date_from: date, date_to: date) -> dict:
    """GSTR-3B: B1 / B2 / D1 totals of the month (canceled entries and their reversals cancel out)."""
    out = {k: {h: ZERO for h in HEADS} for k in KINDS}
    for je in _entries(session, date_from=date_from, date_to=date_to):
        if not _active(je):
            continue
        for h, v in _amounts(session, je).items():
            out[je.ref3[4:]][h] += v
    return out


# ------------------------------------------------------------- GSTR-2B reconciliation
def _norm(no) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(no or "").upper()).lstrip("0")


def _f(x) -> Decimal:
    return _m(Decimal(str(x or 0)))


def _portal_rows(data: dict) -> list[dict]:
    """Invoices / notes / bills of entry of a GSTR-2B JSON (portal download, data.docdata)."""
    doc = (data.get("data") or data).get("docdata") or {}
    rows = []

    def items(x):
        its = x.get("items") or [x]
        return {"taxable": sum((_f(i.get("txval")) for i in its), ZERO), "igst": sum((_f(i.get("igst")) for i in its), ZERO),
                "cgst": sum((_f(i.get("cgst")) for i in its), ZERO), "sgst": sum((_f(i.get("sgst")) for i in its), ZERO),
                "cess": sum((_f(i.get("cess")) for i in its), ZERO)}

    for party in doc.get("b2b") or []:
        for inv in party.get("inv") or []:
            rows.append({"section": "B2B", "gstin": (party.get("ctin") or "").upper(), "name": party.get("trdnm"), "number": inv.get("inum"),
                         "date": inv.get("dt"), "value": _f(inv.get("val")), "rev": inv.get("rev") == "Y", "itc_available": inv.get("itcavl", "Y") != "N",
                         "sign": 1, **items(inv)})
    for party in doc.get("cdnr") or []:
        for nt in party.get("nt") or []:
            sign = -1 if nt.get("typ", "C") == "C" else 1
            rows.append({"section": "CDNR", "gstin": (party.get("ctin") or "").upper(), "name": party.get("trdnm"), "number": nt.get("ntnum"),
                         "date": nt.get("dt"), "value": _f(nt.get("val")), "rev": nt.get("rev") == "Y", "itc_available": nt.get("itcavl", "Y") != "N",
                         "sign": sign, **items(nt)})
    for boe in doc.get("impg") or []:
        rows.append({"section": "IMPG", "gstin": None, "name": f"Port {boe.get('portcode', '')}", "number": boe.get("boenum"), "date": boe.get("boedt"),
                     "value": _f(boe.get("txval")), "rev": False, "itc_available": True, "sign": 1, "taxable": _f(boe.get("txval")),
                     "igst": _f(boe.get("igst")), "cgst": ZERO, "sgst": ZERO, "cess": _f(boe.get("cess"))})
    return rows


def _book_rows(session: Session, date_from: date, date_to: date) -> list[dict]:
    from app.services.gst_returns import _docs

    rows = []
    for d in _docs(session, ("18", "19"), date_from, date_to):
        h = session.get(DOCUMENT_CLASSES[d.obj][0], d.doc_entry)
        sums = {k: sum((getattr(l, k) for l in d.lines), ZERO) for k in ("taxable", *HEADS)}
        imp = bool(h.boe_num) and any(l.rc == "I" for l in d.lines)
        if not any(sums[k] for k in HEADS) and not imp:
            continue  # nil-rated / exempt: no ITC
        rows.append({"obj": d.obj, "doc_entry": d.doc_entry, "doc_num": d.doc_num, "card_code": d.card_code, "card_name": d.card_name,
                     "section": "IMPG" if imp else ("CDNR" if d.obj == "19" else "B2B"), "gstin": d.gstin,
                     "number": h.boe_num if imp else h.num_at_card, "date": h.tax_date, "sign": -1 if d.obj == "19" else 1, **sums})
    return rows


def reconcile(session: Session, year: int, month: int, data: dict) -> dict:
    from app.services.gst_returns import period

    date_from, date_to = period(year, month)
    portal, books = _portal_rows(data), _book_rows(session, date_from, date_to)
    key = lambda r: (r["section"], r["gstin"] or "", _norm(r["number"]))  # noqa: E731
    open_books = {}
    for b in books:
        open_books.setdefault(key(b), []).append(b)
    out = []
    for p in portal:
        cands = open_books.get(key(p)) or []
        b = cands.pop(0) if cands else None
        row = {"section": p["section"], "gstin": p["gstin"], "name": p["name"], "number": p["number"], "portal_date": p["date"],
               "portal": {k: p[k] for k in ("taxable", *HEADS)}, "itc_available": p["itc_available"], "rev": p["rev"]}
        if b is None:
            row.update(status="portal_only", note="in GSTR-2B, not booked (book the A/P invoice or check the number)")
        else:
            diff = {k: p[k] - b[k] for k in ("taxable", *HEADS)}
            row.update(book={k: b[k] for k in ("taxable", *HEADS)}, obj=b["obj"], doc_entry=b["doc_entry"], doc_num=b["doc_num"],
                       card_code=b["card_code"], book_date=b["date"], diff=diff)
            if any(abs(v) > TOLERANCE for v in diff.values()):
                row.update(status="mismatch", note="amounts differ")
            else:
                row.update(status="matched", note=None if p["itc_available"] else "ITC not available per GSTR-2B: reverse it")
        out.append(row)
    for rest in open_books.values():
        for b in rest:
            out.append({"section": b["section"], "gstin": b["gstin"], "name": b["card_name"], "number": b["number"], "book_date": b["date"],
                        "book": {k: b[k] for k in ("taxable", *HEADS)}, "obj": b["obj"], "doc_entry": b["doc_entry"], "doc_num": b["doc_num"],
                        "card_code": b["card_code"], "status": "books_only",
                        "note": "booked, not in GSTR-2B (vendor has not filed or the number / GSTIN differs): ITC at risk"})
    summary = {}
    for r in out:
        s = summary.setdefault(r["status"], {"count": 0, **{h: ZERO for h in HEADS}})
        s["count"] += 1
        src = r.get("portal") or r.get("book")
        for h in HEADS:
            s[h] += src[h]
    order = {"mismatch": 0, "portal_only": 1, "books_only": 2, "matched": 3}
    out.sort(key=lambda r: (order[r["status"]], r["section"], r["gstin"] or "", str(r["number"] or "")))
    return {"period": f"{month:02d}{year}", "rows": out, "summary": summary}
