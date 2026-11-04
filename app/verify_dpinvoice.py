"""End-to-end check for down payment invoices (GST on advances).

June 2027: an A/R down payment invoice (DpmType I) of 10,000 + GST 1,800 posts customer / clearing account
219000 / output CGST + SGST; it is paid like an invoice. An A/R invoice of 20,000 + 3,600 draws it: the
clearing account and the tax on the advance are reversed, the customer line is 11,800 lower, the invoice
counts the 11,800 as paid. GSTR-1 table 11A (advance) and 11B (adjusted), receipt vouchers issued, JSON
at / txpd; GSTR-3B 3.1(a) +20,000 net and = journal. Unpaid / partial / double draws and canceling a
drawn down payment are refused; canceling the invoice releases the down payment, which is drawn again.
A/P: a down payment invoice to a vendor posts input tax on 119000 (ITC in GSTR-3B).

Run after app.seed (rerunnable):  python -m app.verify_dpinvoice
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models.finance import JournalLine
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import banking, reports
from app.services import documents as docs
from app.services import gst_returns as gr
from app.services.admin import B1Error
from app.services.banking import PaidItem
from app.services.banking import PaymentRequest as PR
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR
from app.services.documents import DownPaymentDraw as DPD

D = Decimal
Y, M = 2027, 6
DAY = date(2027, 6, 10)
KEYS = ("taxable", "igst", "cgst", "sgst", "cess")


def _partners(s) -> None:
    for code, name, typ, group, gstin in [("C95010", "Advance Consulting Pvt Ltd", "C", 100, "29AABCA1234F1Z5"),
                                          ("V95010", "Advance Supplies LLP", "S", 102, "29AABCS1234F1Z5")]:
        if s.get(BusinessPartner, code) is None:
            s.add(BusinessPartner(card_code=code, card_name=name, card_type=typ, group_code=group, currency="##",
                                  deb_pay_acct="114000" if typ == "C" else "211000", group_num=1, list_num=1 if typ == "C" else 3,
                                  vat_group="OCS18" if typ == "C" else "ICS18", country="IN", lic_trad_num=gstin, balance=D(0), dnotes_bal=D(0),
                                  orders_bal=D(0), frozen_for="N", bill_to_def="Main", ship_to_def="Main", credit_line=D(0)))
            s.flush()
            for kind in ("B", "S"):
                s.add(PartnerAddress(card_code=code, adres_type=kind, address="Main", street="1 Residency Road", city="Bengaluru",
                                     state="KA", country="IN", gst_regn_no=gstin, gst_type="R"))
            s.flush()
    s.commit()


def _refused(s, fn, text: str) -> None:
    try:
        fn()
    except B1Error as exc:
        assert text in str(exc), exc
        s.rollback()
        return
    raise AssertionError(f"expected refusal: {text}")


def _je(s, trans_id) -> dict:
    out = {}
    for l in s.scalars(select(JournalLine).where(JournalLine.trans_id == trans_id)):
        out[l.short_name] = out.get(l.short_name, D(0)) + l.debit - l.credit
    return out


def _bp_line(s, doc):
    return s.scalars(select(JournalLine).where(JournalLine.trans_id == doc.trans_id, JournalLine.short_name == doc.card_code)).first()


def _pay(s, doc, amount, obj="24"):
    line = _bp_line(s, doc)
    return banking.create_payment(s, PR(obj=obj, doc_date=DAY, doc_type="C" if obj == "24" else "S", card_code=doc.card_code, trsfr_acct="112000",
                                        trsfr_sum=D(amount), items=[PaidItem(trans_id=line.trans_id, line_id=line.line_id, sum_applied=D(amount))]))


def _dp(s, card, amount, obj="203", vat="OCS18"):
    return docs.create_document(s, DR(obj=obj, doc_date=DAY, card_code=card, doc_type="S", disc_prcnt=D(0), dpm_type="I",
                                      lines=[DL(acct_code="411000" if obj == "203" else "611000", price=D(amount), vat_group=vat)]))


def _inv(s, draws, qty=2):
    return docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C95010", disc_prcnt=D(0), down_payments=draws,
                                      lines=[DL(item_code="S00001", quantity=D(qty), price=D(10000), vat_group="OCS18")]))


def _agrees(s) -> dict:
    r3 = gr.gstr3b(s, Y, M)
    comp = {x["component"]: x for x in reports.tax_report(s, *gr.period(Y, M))["summary"]}
    for head, code in (("igst", "IGST"), ("cgst", "CGST"), ("sgst", "SGST")):
        assert r3["liability"][head] == comp.get(code, {}).get("output", 0), (head, r3["liability"][head], comp.get(code))
        assert r3["itc"]["net"][head] == comp.get(code, {}).get("input", 0), (head, r3["itc"]["net"][head], comp.get(code))
    return r3


def _row(rows, rate=18):
    return next((x for x in rows if x["pos"] == "29" and x["supply"] == "INTRA" and x["rate"] == rate), {k: D(0) for k in KEYS})


def main() -> None:
    with SessionLocal() as s:
        _partners(s)
        b3, b1 = _agrees(s), gr.gstr1(s, Y, M)
        dp = _dp(s, "C95010", 10000)
        assert dp.dpm_type == "I" and dp.doc_total == 11800 and dp.vat_sum == 1800
        assert _je(s, dp.trans_id) == {"C95010": 11800, "219000": -10000, "216100": -900, "216200": -900}
        _refused(s, lambda: _inv(s, [DPD(dp_entry=dp.doc_entry)]), "not paid yet")
        _refused(s, lambda: banking.create_payment(s, PR(obj="24", doc_date=DAY, card_code="C95010", trsfr_acct="112000", trsfr_sum=D(11800),
                                                         down_payments=[banking.DownPaymentPay(dp_entry=dp.doc_entry, amount=D(11800))])),
                 "pay its open item")
        pay = _pay(s, dp, 11800)
        s.refresh(dp)
        assert dp.paid_to_date == 11800
        print(f"1 Down payment invoice {dp.doc_num}: customer 11,800 / clearing 219000 10,000 / CGST + SGST 900 each; drawing it unpaid "
              f"and paying it as a request refused; incoming payment {pay.doc_num} pays its open item")

        _refused(s, lambda: _inv(s, [DPD(dp_entry=dp.doc_entry, amount=D(5000))]), "drawn in full")
        inv = _inv(s, [DPD(dp_entry=dp.doc_entry)])
        je = _je(s, inv.trans_id)
        assert je["C95010"] == 11800 and je["219000"] == 10000 and je["216100"] == -900 and je["216200"] == -900 and je["412000"] == -20000, je  # services revenue
        assert inv.doc_total == 23600 and inv.dpm_amnt == 11800 and inv.paid_to_date == 11800 and _bp_line(s, inv).bal_due_deb == 11800
        s.refresh(dp)
        assert dp.dpm_appl == 11800 and dp.doc_status == "C"
        _refused(s, lambda: _inv(s, [DPD(dp_entry=dp.doc_entry)]), "already drawn")
        _refused(s, lambda: docs.cancel_document(s, "203", dp.doc_entry), "drawn on an invoice")
        print(f"2 Invoice {inv.doc_num} 23,600 draws it: customer line 11,800, clearing and the advance's GST reversed, PaidToDate 11,800; "
              "partial / double draws and canceling the drawn down payment refused")

        a1, a3 = gr.gstr1(s, Y, M), _agrees(s)
        rec, adj = _row(a1["advances"]["received"]), _row(a1["advances"]["adjusted"])
        rec0, adj0 = _row(b1["advances"]["received"]), _row(b1["advances"]["adjusted"])
        assert rec["taxable"] - rec0["taxable"] == 10000 and rec["cgst"] - rec0["cgst"] == 900
        assert adj["taxable"] - adj0["taxable"] == 10000 and adj["sgst"] - adj0["sgst"] == 900
        assert any(x["nature"] == "Receipt voucher" for x in a1["doc_issue"])
        d31 = {k: a3["outward"]["a_taxable"][k] - b3["outward"]["a_taxable"][k] for k in KEYS}
        assert d31 == {"taxable": 20000, "igst": 0, "cgst": 1800, "sgst": 1800, "cess": 0}, d31
        j1 = gr.gstr1_json(s, Y, M)
        assert j1["at"] and j1["txpd"] and any(d["doc_num"] == 6 for d in j1["doc_issue"]["doc_det"])
        print("3 GSTR-1 11A advance 10,000 (CGST / SGST 900), 11B adjusted 10,000, receipt vouchers issued; JSON at / txpd; "
              "GSTR-3B 3.1(a) +20,000 (advance + invoice - adjustment) = journal")

        docs.cancel_document(s, "13", inv.doc_entry)
        s.refresh(dp)
        assert dp.dpm_appl == 0 and dp.doc_status == "O"
        _agrees(s)
        inv2 = _inv(s, [DPD(dp_entry=dp.doc_entry)], qty=1)
        assert inv2.doc_total == 11800 and inv2.doc_status == "C" and _bp_line(s, inv2) is None
        _agrees(s)
        print(f"4 Invoice {inv.doc_num} canceled: the down payment is free again; invoice {inv2.doc_num} of 11,800 draws it and is fully paid "
              "(no open customer line)")

        apd = _dp(s, "V95010", 5000, obj="204", vat="ICS18")
        assert _je(s, apd.trans_id) == {"V95010": -5900, "119000": 5000, "116100": 450, "116200": 450}
        r3 = _agrees(s)
        assert r3["itc"]["available_other"]["cgst"] - a3["itc"]["available_other"]["cgst"] == 450
        print(f"5 A/P down payment invoice {apd.doc_num}: 119000 5,000 + input CGST / SGST 450 each against the vendor 5,900; ITC in GSTR-3B")
    print("\nOK - down payment invoices post GST on advances and are drawn on invoices.")


if __name__ == "__main__":
    main()
