"""End-to-end check for freight / additional expenses on documents.

An A/R invoice with 10 % header discount and freight 500: the discount does not touch the
freight, freight + its GST are in the totals, the revenue account 413000 is credited and the
output tax gets the freight's GST; inter-state freight switches to IGST; A/P freight debits
616000 with input tax; a credit memo and a cancel reverse it; FC freight is converted at the
document rate; the GST returns and the journal agree, and the e-invoice lists the freight with
its SAC code; bad freight is refused.

Run after app.seed (rerunnable):  python -m app.verify_freight
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models.finance import JournalLine
from app.services import documents as docs
from app.services import edocs
from app.services import gst_returns as gr
from app.services import reports
from app.services.admin import B1Error, exchange_rate
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR
from app.services.documents import ExpenseRequest as EX

D = Decimal
Y, M = 2027, 9
DAY = date(2027, 9, 14)


def _je(s, doc) -> dict:
    out: dict[str, D] = {}
    for l in s.scalars(select(JournalLine).where(JournalLine.trans_id == doc.trans_id)):
        key = l.short_name if l.short_name != l.account else l.account
        out[key] = out.get(key, D(0)) + l.debit - l.credit
    return out


def _refused(fn, text: str) -> None:
    try:
        fn()
    except B1Error as exc:
        assert text in str(exc), exc
        return
    raise AssertionError(f"expected refusal: {text}")


def main() -> None:
    s = SessionLocal()
    try:
        inv = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", disc_prcnt=D(10),
                                         lines=[DL(item_code="S00001", quantity=D(2), price=D(1500))], expenses=[EX(expns_code=1, amount=D(500))]))
        assert inv.total_expns == 500 and inv.vat_sum == D("486") + 90 and inv.doc_total == D("2700") + 486 + 500 + 90, (inv.vat_sum, inv.doc_total)
        e = inv.expenses[0]
        assert e.vat_group == "OCS18" and e.vat_sum == 90 and e.grs_amount == 590
        je = _je(s, inv)
        assert je["413000"] == -500 and je["216100"] == -(243 + 45) and je["216200"] == -(243 + 45) and je["C10000"] == inv.doc_total
        assert sum(je.values()) == 0
        print(f"1 A/R invoice {inv.doc_num}: lines 3,000 - 10 % = 2,700 + GST 486, freight 500 (no discount) + GST 90 = {inv.doc_total}; "
              "413000 credited 500, CGST / SGST 45 each from the freight")

        inter = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C20000", disc_prcnt=D(0),
                                           lines=[DL(item_code="S00001", quantity=D(1), price=D(1500))], expenses=[EX(expns_code=1, amount=D(300))]))
        assert inter.expenses[0].vat_group == "OIG18" and _je(s, inter)["216300"] == -(270 + 54)
        ap = docs.create_document(s, DR(obj="18", doc_date=DAY, card_code="V10000", disc_prcnt=D(0),
                                        lines=[DL(item_code="C00001", quantity=D(1), price=D(2000))], expenses=[EX(expns_code=1, amount=D(1000))]))
        jap = _je(s, ap)
        assert jap["616000"] == 1000 and jap["116100"] == 180 + 90 and jap["V10000"] == -ap.doc_total == -(2000 + 360 + 1000 + 180)
        print(f"2 Inter-state freight switched to OIG18 (IGST 54); A/P invoice {ap.doc_num}: 616000 debited 1,000, input GST 180 on the freight")

        cm = docs.create_document(s, DR(obj="14", doc_date=DAY, card_code="C10000", disc_prcnt=D(0),
                                        lines=[DL(item_code="S00001", quantity=D(1), price=D(1000))], expenses=[EX(expns_code=1, amount=D(200))]))
        assert _je(s, cm)["413000"] == 200
        extra = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", disc_prcnt=D(0),
                                           lines=[DL(item_code="S00001", quantity=D(1), price=D(1000))], expenses=[EX(expns_code=2, amount=D(150), vat_group="ONIL")]))
        assert extra.expenses[0].vat_sum == 0 and extra.doc_total == 1180 + 150
        docs.cancel_document(s, "13", extra.doc_entry, DAY)
        rev = s.scalars(select(JournalLine).where(JournalLine.account == "413000", JournalLine.trans_id != extra.trans_id,
                                                  JournalLine.ref1 == str(extra.doc_num))).all()
        print(f"3 Credit memo debits 413000 by 200; insurance 150 at nil rate; canceled invoice {extra.doc_num} reverses its freight")

        usd = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", disc_prcnt=D(0), doc_cur="USD",
                                         lines=[DL(item_code="S00001", quantity=D(1), price=D(100))], expenses=[EX(expns_code=1, amount=D(10))]))
        r = exchange_rate(s, "USD", DAY)
        assert usd.total_exp_fc == 10 and usd.total_expns == (D(10) * r).quantize(D("0.01")) and usd.doc_total_fc == D(118) + D("11.8")
        print(f"4 USD invoice: freight 10 USD = {usd.total_expns} INR at {r}; total 129.80 USD")

        _refused(lambda: docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", lines=[DL(item_code="S00001", quantity=D(1))],
                                                    expenses=[EX(expns_code=99, amount=D(10))])), "does not exist")
        _refused(lambda: docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", lines=[DL(item_code="S00001", quantity=D(1))],
                                                    expenses=[EX(expns_code=1, amount=D(-5))])), "must be positive")
        _refused(lambda: docs.create_document(s, DR(obj="59", doc_date=DAY, lines=[DL(item_code="C00001", quantity=D(1), price=D(10))],
                                                    expenses=[EX(expns_code=1, amount=D(5))])), "no freight")
        print("5 Unknown charge, negative amount and freight on inventory documents refused")

        # GST: returns = journal for the month, e-invoice lists the freight with its SAC
        r3 = gr.gstr3b(s, Y, M)
        comp = {x["component"]: x for x in reports.tax_report(s, *gr.period(Y, M))["summary"]}
        for head, code in (("igst", "IGST"), ("cgst", "CGST"), ("sgst", "SGST")):
            assert r3["liability"][head] == comp.get(code, {}).get("output", 0), (head, r3["liability"][head], comp.get(code))
            assert r3["itc"]["net"][head] == comp.get(code, {}).get("input", 0), (head, r3["itc"]["net"][head], comp.get(code))
        r1 = gr.gstr1(s, Y, M)
        assert any(h["hsn"] == "996511" for h in r1["hsn"]["b2b"]) and not [i for i in r1["issues"] if "HSN summary" in i]
        p, issues = edocs.einvoice_payload(s, "13", inv.doc_entry)
        fr = [i for i in p["ItemList"] if i["HsnCd"] == "996511"]
        v = p["ValDtls"]
        assert not issues and fr and fr[0]["AssAmt"] == 500 and fr[0]["CgstAmt"] == 45
        assert round(v["AssVal"] + v["CgstVal"] + v["SgstVal"] + v["IgstVal"] + v["RndOffAmt"], 2) == v["TotInvVal"] == float(inv.doc_total)
        print("6 GSTR-3B liability / ITC = journal with freight; HSN summary has SAC 996511; e-invoice item 'Freight' 500 + CGST 45 + SGST 45")
        assert rev is not None
        print("\nOK - freight is taxed, totaled and posted like B1.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
