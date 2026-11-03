"""End-to-end check for printed documents (GST layout).

Amount in words with the Indian system; a Karnataka tax invoice prints CGST + SGST per line,
the HSN / SAC codes and an HSN-wise summary that adds up to the document; a Maharashtra one
prints IGST and its place of supply; a delivery challan prints without prices.

Run after app.seed (rerunnable):  python -m app.verify_print
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.services import printing
from app.services import documents as docs
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
DAY = date(2027, 10, 4)


def main() -> None:
    w = printing.amount_in_words
    assert w(D("123456789.50"), "INR") == "Rupees Twelve Crore Thirty Four Lakh Fifty Six Thousand Seven Hundred Eighty Nine and Fifty Paise Only"
    assert w(D("1180"), "INR") == "Rupees One Thousand One Hundred Eighty Only"
    assert w(D("100000"), "INR") == "Rupees One Lakh Only" and w(D("19.05"), "USD") == "US Dollars Nineteen and Five Cents Only"
    print("1 Amount in words: 12,34,56,789.50 ->", w(D("123456789.50"), "INR"))

    s = SessionLocal()
    try:
        inv = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", disc_prcnt=D(0), lines=[
            DL(item_code="S00001", quantity=D(2))]))
        p = printing.print_data(s, "13", inv.doc_entry)
        line = p["lines"][0]
        print(f"2 {p['title']} {p['doc_num']}: {p['company']['name']} ({p['company']['gstin']}) -> {p['bill_to']['name']} "
              f"({p['bill_to']['gstin']}, {p['bill_to']['state']}); place of supply {p['place_of_supply']} ({p['supply']}); "
              f"line HSN/SAC {line['hsn']} taxable {line['taxable']} CGST {line['cgst']} SGST {line['sgst']}; total {p['totals']['total']}")
        assert p["title"] == "Tax Invoice" and p["supply"] == "intra-state" and p["place_of_supply"] == "Karnataka"
        assert line["hsn"] == "998713" and line["cgst"] == (D(9), D(270)) and line["sgst"] == (D(9), D(270)) and line["igst"] is None
        hsn = p["hsn_summary"][0]
        assert hsn["taxable"] + hsn["CGST"] + hsn["SGST"] == p["totals"]["total"] == D(3540)
        assert p["amount_in_words"] == "Rupees Three Thousand Five Hundred Forty Only" and p["bill_to"]["gstin"].startswith("29")

        inv2 = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C20000", disc_prcnt=D(0), lines=[
            DL(item_code="S00001", quantity=D(1))]))
        p2 = printing.print_data(s, "13", inv2.doc_entry)
        assert p2["supply"] == "inter-state" and p2["place_of_supply"] == "Maharashtra" and p2["lines"][0]["igst"][0] == D(18)
        print(f"3 Inter-state invoice {p2['doc_num']}: IGST {p2['lines'][0]['igst']}, place of supply {p2['place_of_supply']}")

        so = docs.create_document(s, DR(obj="17", doc_date=DAY, card_code="C10000", lines=[DL(item_code="A00001", quantity=D(1))]))
        assert printing.print_data(s, "17", so.doc_entry)["title"] == "Sales Order"
        from app.services import documents as d2

        grpo = d2.create_document(s, DR(obj="20", doc_date=DAY, card_code="V10000", lines=[DL(item_code="A00001", quantity=D(2))]))
        dn = d2.create_document(s, DR(obj="15", doc_date=DAY, card_code="C10000", lines=[
            DL(base_type="17", base_entry=so.doc_entry, base_line=0)]))
        pd = printing.print_data(s, "15", dn.doc_entry)
        assert pd["title"] == "Delivery Challan" and pd["no_prices"] and printing.print_data(s, "20", grpo.doc_entry)["title"] == "Goods Receipt Note"
        print(f"4 {pd['title']} {pd['doc_num']} prints quantities only; GRPO prints as Goods Receipt Note")

        # print layouts: every document type has a seeded default; a second layout can be chosen or made default
        assert all(printing.layout_for(s, obj) is not None for obj in printing.TITLES)
        assert p["layout"]["doc_code"] == "STD-13" and p["layout"]["default"] and p["layout"]["style"] == "classic"
        code = f"MOD{inv.doc_entry}"
        printing.save_layout(s, {"doc_code": code, "doc_name": "Modern blue", "type_code": "13", "style": "modern",
                                 "color": "#0A66C2", "show_hsn": False, "show_bank": False, "footer": "Thank you for your business"})
        pm = printing.print_data(s, "13", inv.doc_entry, code)
        assert pm["layout"]["style"] == "modern" and pm["layout"]["color"] == "#0a66c2" and not pm["layout"]["show_hsn"]
        assert pm["totals"] == p["totals"] and printing.print_data(s, "13", inv.doc_entry)["layout"]["doc_code"] == "STD-13"
        assert code in [l["doc_code"] for l in pm["layouts"]]
        for bad, msg in [(lambda: printing.print_data(s, "17", so.doc_entry, code), "is not a layout of"),
                         (lambda: printing.save_layout(s, {"color": "blue"}, code), "hex value"),
                         (lambda: printing.save_layout(s, {"style": "fancy"}, code), "Unknown style"),
                         (lambda: printing.delete_layout(s, "STD-13"), "cannot be removed"),
                         (lambda: printing.save_layout(s, {"default": False}, "STD-13"), "needs a default")]:
            try:
                bad()
                raise AssertionError(f"expected an error: {msg}")
            except printing.B1Error as exc:
                assert msg in str(exc), exc
                s.rollback()
        printing.save_layout(s, {"default": True}, code)
        assert printing.layout_for(s, "13").doc_code == code and s.get(printing.PrintLayout, "STD-13").default == "N"
        printing.save_layout(s, {"default": True}, "STD-13")
        printing.delete_layout(s, code)
        print(f"5 Layouts: STD-13 (classic, default); {code} (modern, #0a66c2, no HSN summary) printed on request, "
              "made default and back, removed; bad colour / style / foreign layout / removing the default refused")

        # company logo: PNG / JPEG / GIF up to 512 KB, printed when the layout shows it
        import base64

        from app.services.admin import company

        before = company(s).logo_image
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 64).decode()
        printing.save_logo(s, f"data:image/png;base64,{png}")
        assert printing.print_data(s, "13", inv.doc_entry)["company"]["logo"].startswith("data:image/png;base64,")
        for bad in (f"data:image/svg+xml;base64,{png}", "data:image/png;base64," + base64.b64encode(b"<svg/>").decode(),
                    "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * (513 * 1024)).decode()):
            try:
                printing.save_logo(s, bad)
                raise AssertionError("bad logo accepted")
            except printing.B1Error:
                s.rollback()
        company(s).logo_image = before
        s.commit()
        print("6 Logo: PNG stored and printed; SVG, non-image content and > 512 KB refused")
        print("\nOK - print data (GST layout) is consistent with the documents.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
