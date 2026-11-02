"""End-to-end check for the tax setup: user-defined tax types, authorities, codes, HSN / SAC codes and
tax code determination rules.

A Cess tax type and authority, a tax code CGST 14 % + SGST 14 % + Cess 12 % posting each component
to its account; a used tax code keeps its rate; HSN / SAC master validates items; determination
rules choose the tax code (BP, item group, SAC, supply), the entered code wins, an intra-state rule
code still switches to IGST between states.

Run after app.seed (rerunnable):  python -m app.verify_taxsetup
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models.admin import TaxDetermination, TaxGroup
from app.models.finance import JournalLine
from app.models.inventory import Item
from app.services import documents as docs
from app.services import masterdata, tax
from app.services.admin import B1Error
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 2, 10)


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def _invoice(s, card: str, vat: str | None = None, qty: str = "1"):
    return docs.create_document(s, DR(obj="13", doc_date=DAY, card_code=card, disc_prcnt=D(0),
                                      lines=[DL(item_code="S00001", quantity=D(qty), vat_group=vat)]))


def main() -> None:
    s = SessionLocal()
    try:
        # 1) user-defined tax type, authority and a three-component tax code
        tax.save_tax_type(s, "CESS", "Compensation cess")
        tax.save_tax_authority(s, "CESS", "Compensation cess", "CESS", "216000", "116000")
        if s.get(TaxGroup, "OCSC40") is None:
            tax.save_tax_code(s, "OCSC40", "GST 28% + cess 12%", "O", [("CGST", D(14)), ("SGST", D(14)), ("CESS", D(12))])
        tg = s.get(TaxGroup, "OCSC40")
        print(f"1 Tax code {tg.code}: rate {tg.rate}% = " + " + ".join(f"{a.code} {r}%" for a, r in tax.components(s, tg)))
        assert tg.rate == D(40)

        # 2) its postings: one line per component account
        inv = _invoice(s, "C10000", "OCSC40")  # 1 hour at 1500
        lines = {l.account: l.credit for l in s.scalars(select(JournalLine).where(
            JournalLine.trans_id == inv.trans_id, JournalLine.vat_group.is_not(None)))}
        print(f"2 A/R invoice {inv.doc_num}: tax {lines}, total {inv.doc_total}")
        assert lines == {"216100": D(210), "216200": D(210), "216000": D(180)} and inv.doc_total == D(2100)

        # 3) a used tax code keeps category, rate and components; its name may change
        _rejects(lambda: tax.save_tax_code(s, "OCSC40", "x", "O", [("CGST", D(14)), ("SGST", D(14))]), "used tax code changed")
        tax.save_tax_code(s, "OCSC40", "GST 28% + compensation cess", "O", [("CGST", D(14)), ("SGST", D(14)), ("CESS", D(12))])
        _rejects(lambda: tax.save_tax_code(s, "XBAD", "x", "O", [("CGST", D(60)), ("SGST", D(50))]), "rate of 100 % or more")
        _rejects(lambda: tax.save_tax_authority(s, "XBAD", "x", None, "114000", "116000"), "control account as tax account")

        # 4) HSN / SAC master validates items
        hsn = next((h for h in tax_setup_hsn(s) if h.chapter_id == "998719"), None) or tax.save_hsn(
            s, "998719", "Other maintenance and repair services", "S")
        _rejects(lambda: masterdata.validate_item_fields(s, {"chapter_id": "12345678"}), "unknown HSN code")
        _rejects(lambda: tax.save_hsn(s, "99AB", "x"), "malformed HSN code")
        print(f"4 SAC {hsn.chapter_id} '{hsn.dscription}' available for items")

        # 5) determination rules (remove leftovers of an earlier run first)
        for r in s.scalars(select(TaxDetermination).where(TaxDetermination.descr.like("verify%"))):
            s.delete(r)
        s.commit()
        sac = s.get(Item, "S00001").chapter_id
        r1 = tax.save_determination(s, {"priority": 1, "doc_area": "S", "card_code": "C10000", "itms_grp_cod": 102,
                                        "tax_code": "OCS5", "descr": "verify: C10000 services at 5 %", "active": "Y"})
        r2 = tax.save_determination(s, {"priority": 2, "doc_area": "S", "chapter_id": sac, "tax_code": "OCS12",
                                        "descr": "verify: installation SAC at 12 %", "active": "Y"})
        a = _invoice(s, "C10000")          # rule 1 (priority 1)
        b = _invoice(s, "C20000")          # rule 2, intra-state code switched to IGST for Maharashtra
        c = _invoice(s, "C10000", "OCS18")  # entered code wins
        print(f"5 Rules: C10000 -> {a.lines[0].vat_group}, C20000 -> {b.lines[0].vat_group}, entered -> {c.lines[0].vat_group}")
        assert (a.lines[0].vat_group, b.lines[0].vat_group, c.lines[0].vat_group) == ("OCS5", "OIG12", "OCS18")
        r3 = tax.save_determination(s, {"priority": 0, "doc_area": "S", "supply": "O", "chapter_id": sac, "tax_code": "OIG18",
                                        "descr": "verify: inter-state installation at 18 %", "active": "Y"})
        d = _invoice(s, "C20000")
        assert d.lines[0].vat_group == "OIG18", "a rule with a supply condition is taken as it is"
        _rejects(lambda: tax.save_determination(s, {"doc_area": "S", "tax_code": "ICS18"}), "input code for sales")
        for r in (r1, r2, r3):
            s.delete(r)
        s.commit()
        print("\nOK - tax types, authorities, codes, HSN / SAC codes and determination rules work together.")
    finally:
        s.close()


def tax_setup_hsn(s):
    from app.models.admin import HsnCode

    return s.scalars(select(HsnCode)).all()


if __name__ == "__main__":
    main()
