"""End-to-end check for TCS, TDS on advances, challans, quarterly returns (26Q / 27EQ) and Form 16A.

TCS: an A/R invoice of a TCS customer (206C(1), 1 % of the gross incl. GST) collects 118 on 11,800: the
customer is charged 11,918, 217100 credited; GSTR-1 keeps the invoice value without TCS; a credit memo
copied from it reverses the TCS. TDS on an advance: 90,000 paid on account to a 194J(b) vendor is grossed
up to an advance of 1,00,000 with TDS 10,000; the vendor's invoice later deducts no further TDS (adjusted
from the advance) and the advance payment cannot be canceled any more. Challans: the TDS is deposited
(bank JE, rows linked); documents in a challan cannot be canceled; TCS deposited late carries interest
(1 % per month or part); canceling a challan reopens the rows. Form 26Q / 27EQ of Q3 2027-28 list the
records with their challans; Form 16A for the vendor; the CSV has the deductee records.

Run after app.seed (rerunnable):  python -m app.verify_tdstcs
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models.finance import JournalLine
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import banking, withholding
from app.services import documents as docs
from app.services import gst_returns as gr
from app.services.admin import B1Error, company
from app.services.banking import PaymentRequest as PR
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR

D = Decimal
OCT, NOV = date(2027, 10, 15), date(2027, 11, 15)


def _partners(s) -> None:
    for code, name, typ, group, gstin, codes in [("C95020", "Metro Scrap Buyers Pvt Ltd", "C", 100, "29AABCM5678F1Z5", ["TSCR"]),
                                                 ("V95020", "Kumar & Associates (CA)", "S", 102, "29AABFK1234F1Z5", ["J2"])]:
        if s.get(BusinessPartner, code) is None:
            s.add(BusinessPartner(card_code=code, card_name=name, card_type=typ, group_code=group, currency="##",
                                  deb_pay_acct="114000" if typ == "C" else "211000", group_num=1, list_num=1 if typ == "C" else 3,
                                  vat_group="OCS18" if typ == "C" else "ICS18", country="IN", lic_trad_num=gstin, balance=D(0), dnotes_bal=D(0),
                                  orders_bal=D(0), frozen_for="N", bill_to_def="Main", ship_to_def="Main", credit_line=D(0)))
            s.flush()
            for kind in ("B", "S"):
                s.add(PartnerAddress(card_code=code, adres_type=kind, address="Main", street="12 Brigade Road", city="Bengaluru", state="KA",
                                     country="IN", gst_regn_no=gstin, gst_type="R"))
            s.flush()
            withholding.set_partner(s, s.get(BusinessPartner, code), {"wt_liable": True, "wt_codes": codes})
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


def _ar(s, on, obj="13", base=None):
    lines = [DL(base_type="13", base_entry=base.doc_entry, base_line=0, quantity=D(1))] if base else \
        [DL(item_code="S00001", quantity=D(1), price=D(10000), vat_group="OCS18")]
    return docs.create_document(s, DR(obj=obj, doc_date=on, card_code="C95020", disc_prcnt=D(0), lines=lines))


def main() -> None:
    with SessionLocal() as s:
        _partners(s)
        company(s).tan_no = "BLRD12345E"
        s.commit()
        _refused(s, lambda: withholding.set_partner(s, s.get(BusinessPartner, "C95020"), {"wt_codes": ["J2"]}), "TDS codes belong to vendors")

        inv = _ar(s, NOV)
        assert inv.wt_sum == 118 and inv.doc_total == 11918, (inv.wt_sum, inv.doc_total)
        je = _je(s, inv.trans_id)
        assert je["C95020"] == 11918 and je["217100"] == -118 and je["412000"] == -10000, je
        b2b = next(x for x in gr.gstr1(s, 2027, 11)["b2b"] if x["doc_entry"] == inv.doc_entry)
        assert b2b["value"] == 11800
        cm = _ar(s, NOV, obj="14", base=inv)
        assert cm.wt_sum == 118 and cm.doc_total == 11918 and _je(s, cm.trans_id)["217100"] == 118
        print(f"1 TCS: A/R invoice {inv.doc_num} collects 118 (1 % of 11,800): customer 11,918, 217100 credited; GSTR-1 value 11,800; "
              f"credit memo {cm.doc_num} reverses it; a TDS code on a customer refused")

        pay = banking.create_payment(s, PR(obj="46", doc_date=NOV, doc_type="S", card_code="V95020", trsfr_acct="112000",
                                           trsfr_sum=D(90000), wt_on_account=True))
        assert pay.wt_sum == 10000 and pay.open_bal == 100000 and pay.doc_total == 90000
        je = _je(s, pay.trans_id)
        assert je["V95020"] == 100000 and je["217000"] == -10000 and je["112000"] == -90000, je
        _refused(s, lambda: banking.create_payment(s, PR(obj="24", doc_date=NOV, card_code="C95020", trsfr_acct="112000", trsfr_sum=D(10),
                                                         wt_on_account=True)), "outgoing payments to vendors")
        ap = docs.create_document(s, DR(obj="18", doc_date=NOV, card_code="V95020", doc_type="S", disc_prcnt=D(0), num_at_card=f"KA/{pay.doc_num}",
                                        lines=[DL(acct_code="611000", price=D(100000), vat_group="ICS18")]))
        w = withholding.rows_of(s, "18", ap.doc_entry)[0]
        assert w["wt_amnt"] == 0 and w["adv_adj"] == 10000 and ap.doc_total == 118000, (w, ap.doc_total)
        _refused(s, lambda: banking.cancel_payment(s, "46", pay.doc_entry, NOV), "adjusted by an A/P invoice")
        print(f"2 Advance {pay.doc_num}: 90,000 paid, vendor debited 1,00,000, TDS 10,000 (194J(b)); A/P invoice {ap.doc_num} 1,18,000 deducts no "
              "more TDS (10,000 adjusted from the advance); the advance cannot be canceled; TDS on incoming payments refused")

        pv = withholding.challan_preview(s, "D", "194J(b)", date(2027, 11, 30), date(2027, 12, 5))
        assert any(r["obj"] == "46" and r["doc_entry"] == pay.doc_entry for r in pv["rows"]) and pv["interest"] == 0
        _refused(s, lambda: withholding.create_challan(s, {"wt_kind": "D", "section": "194J(b)", "period_to": "2027-11-30", "dep_date": "2027-12-05",
                                                            "bsr_code": "12", "challan_no": "1", "bank_acct": "112000"}), "BSR code")
        ch = withholding.create_challan(s, {"wt_kind": "D", "section": "194J(b)", "period_to": "2027-11-30", "dep_date": "2027-12-05",
                                            "bsr_code": "0510308", "challan_no": "10001", "bank_acct": "112000"})
        je = _je(s, ch.trans_id)
        assert je["217000"] == ch.tax_amnt and je["112000"] == -ch.tax_amnt and ch.tax_amnt >= 10000
        _refused(s, lambda: banking.cancel_payment(s, "46", pay.doc_entry, NOV), "challan")
        print(f"3 Challan 0510308/10001 deposits {ch.tax_amnt:,.0f} of 194J(b) on 05.12.2027 (on time, no interest): Dr 217000 / Cr bank; "
              "the advance is locked; a wrong BSR code refused")

        _refused(s, lambda: withholding.create_challan(s, {"wt_kind": "C", "section": "206C(1)", "period_to": "2027-11-30", "dep_date": "2027-12-20",
                                                            "bsr_code": "0510308", "challan_no": "10002", "bank_acct": "112000"}), "Nothing to deposit")
        late = _ar(s, OCT)
        tcs = withholding.create_challan(s, {"wt_kind": "C", "section": "206C(1)", "period_to": "2027-11-30", "dep_date": "2027-12-20",
                                             "bsr_code": "0510308", "challan_no": "10002", "bank_acct": "112000"})
        assert tcs.tax_amnt == 118 and tcs.interest == 4, (tcs.tax_amnt, tcs.interest)  # 1 % x 3 months (15.10. - 20.12.) x 118 = 3.54
        assert _je(s, tcs.trans_id) == {"217100": 118, "619000": 4, "112000": -122}
        _refused(s, lambda: docs.cancel_document(s, "13", late.doc_entry), "deposited with a challan")
        withholding.cancel_challan(s, tcs.abs_entry)
        assert withholding.rows_of(s, "13", late.doc_entry)[0]["challan_abs"] is None
        tcs = withholding.create_challan(s, {"wt_kind": "C", "section": "206C(1)", "period_to": "2027-11-30", "dep_date": "2027-12-20",
                                             "bsr_code": "0510308", "challan_no": "10003", "bank_acct": "112000"})
        print(f"4 TCS: credit memo and invoice net to nothing (refused); invoice {late.doc_num} of October deposited late on 20.12.2027: "
              "118 + interest 4; it cannot be canceled; challan canceled (rows open again) and posted again")

        r26 = withholding.quarterly_return(s, "D", 2027, 3)
        rec = next(d for d in r26["deductees"] if d["document"] == f"46/{pay.doc_num}")
        assert rec["pan"] == "AABFK1234F" and rec["tax"] == 10000 and rec["challan"] == "0510308/10001" and r26["deductor"]["tan"] == "BLRD12345E"
        assert any(c["challan_no"] == "10001" for c in r26["challans"]) and r26["form"] == "26Q"
        r27 = withholding.quarterly_return(s, "C", 2027, 3)
        assert r27["form"] == "27EQ" and any(d["challan"] == "0510308/10003" for d in r27["deductees"])
        csv = withholding.quarterly_csv(s, "D", 2027, 3)
        assert csv.splitlines()[0].startswith("Sr. No") and "AABFK1234F" in csv
        f16 = withholding.certificate(s, "D", "V95020", 2027, 3)
        assert f16["form"] == "16A" and f16["deductee"]["pan"] == "AABFK1234F" and f16["deposited"] >= 10000
        _refused(s, lambda: withholding.quarterly_return(s, "D", 2027, 5), "Quarter")
        print(f"5 Form 26Q 2027-28 Q3: {len(r26['deductees'])} records (advance {pay.doc_num}: PAN AABFK1234F, 10,000, challan 0510308/10001), "
              f"27EQ with the TCS challan; CSV; Form 16A of V95020")
    print("\nOK - TCS, TDS on advances, challans, 26Q / 27EQ and Form 16A work.")


if __name__ == "__main__":
    main()
