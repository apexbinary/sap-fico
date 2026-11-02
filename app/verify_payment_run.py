"""End-to-end check for the automatic payment program (F110).

Posts vendor items that exercise every proposal rule, then runs
proposal -> payment run -> SEPA file and checks the outcome.
Run after app.seed:  python -m app.verify_payment_run
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal

from app.database import SessionLocal
from app.models.documents import AccountingDocumentItem
from app.services import payment_run as f110
from app.services import reporting
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, LineRequest, post_document

MANDT, BUKRS = "100", "1000"
BETA, GAMMA = "0000020000", "0000020001"
D = Decimal
NS = {"p": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"}


def _vendor_doc(s, lifnr, budat, amount, *, bschl="31", ref=None, **line):
    gl = "40" if bschl == "31" else "50"
    doc = post_document(s, DocumentRequest(
        bukrs=BUKRS, blart="KR", bldat=budat, budat=budat, waers="EUR", xblnr=ref,
        bktxt="Vendor credit memo" if bschl == "21" else "Vendor invoice",
        lines=[
            LineRequest(bschl=bschl, account=lifnr, wrbtr=D(amount), sgtxt=ref, **line),
            LineRequest(bschl=gl, account="476000", wrbtr=D(amount)),
        ]))
    it = next(i for i in doc.items if i.koart == "K")
    return (it.belnr, it.gjahr, it.buzei)


def main() -> None:
    s = SessionLocal()
    try:
        a = _vendor_doc(s, BETA, date(2026, 6, 1), "1190.00", ref="INV-A")                # discount would drop 3% -> 2%
        b = _vendor_doc(s, BETA, date(2026, 6, 5), "595.00", ref="INV-B", zterm="NT30")    # due 2026-07-05: waits
        c = _vendor_doc(s, BETA, date(2026, 6, 1), "238.00", ref="INV-C", zlspr="A")       # payment block
        d = _vendor_doc(s, BETA, date(2026, 6, 2), "100.00", ref="CM-D", bschl="21")       # credit memo: offset
        e = _vendor_doc(s, GAMMA, date(2026, 6, 1), "500.00", ref="INV-E")                 # no bank details

        laufd, laufi = date.today(), datetime.now().strftime("%H%M%S")
        run = f110.create_proposal(s, MANDT, laufd=laufd, laufi=laufi, zbukr=BUKRS, zwels="T",
                                   zaldt=date(2026, 6, 10), nedat=date(2026, 6, 24))
        summary = f110.run_summary(run)
        print(f"Proposal {laufd}/{laufi}: {summary['payments']} payment(s), {summary['exceptions']} exception(s)")
        for p in summary["payees"]:
            print(f"   {p['lifnr']} {p['name1']:<22} method {p['zlsch'] or '-'}  {p['rwbtr']:>10}"
                  f"  discount {p['rskon']:>7}  items {len(p['items'])}  {p['exception'] or ''}")

        def group_of(key):
            for p in summary["payees"]:
                if any((i["belnr"], i["gjahr"], i["buzei"]) == key for i in p["items"]):
                    return p
            return None

        pa, pd = group_of(a), group_of(d)
        assert pa and pa is pd and not pa["exception"] and pa["zlsch"] == "T", "A and D are paid together"
        item_a = next(i for i in pa["items"] if i["belnr"] == a[0])
        assert item_a["wskto"] == D("35.70"), item_a
        assert group_of(b) is None, "B is not due before the next run"
        assert group_of(c)["zlsch"] == "" and "payment block A" in group_of(c)["exception"]
        assert "bank details" in group_of(e)["exception"]

        run = f110.execute(s, MANDT, laufd, laufi)
        paid = [p for p in run.payees if p.vblnr]
        for p in paid:
            print(f"Payment document {p.vblnr}/{p.gjahr}: vendor {p.lifnr}  {p.rwbtr} EUR via {p.hbkid}/{p.hktid}")
        get = lambda k: s.get(AccountingDocumentItem, (MANDT, BUKRS, *k))  # noqa: E731
        beta_doc = next(p.vblnr for p in paid if p.lifnr == BETA)
        assert get(a).augbl == beta_doc and get(d).augbl == beta_doc
        assert get(b).augbl is None and get(c).augbl is None and get(e).augbl is None

        try:
            f110.execute(s, MANDT, laufd, laufi)
        except PostingError as exc:
            print("Second execution rejected:", exc)
        else:
            raise AssertionError("a payment run must not execute twice")

        xml = f110.sepa_credit_transfer(s, MANDT, laufd, laufi)
        root = ET.fromstring(xml)
        n = int(root.find("p:CstmrCdtTrfInitn/p:GrpHdr/p:NbOfTxs", NS).text)
        total = D(root.find("p:CstmrCdtTrfInitn/p:GrpHdr/p:CtrlSum", NS).text)
        ibans = [x.text for x in root.iterfind(".//p:CdtTrfTxInf/p:CdtrAcct/p:Id/p:IBAN", NS)]
        print(f"SEPA pain.001: {n} transaction(s), control sum {total}, creditor IBANs {ibans}")
        assert n == len(paid) and total == sum(p.rwbtr for p in paid)
        assert "DE84200000000987654321" in ibans

        tb = reporting.trial_balance(s, MANDT, BUKRS, 2026)
        print(f"Trial balance: debit {tb['total_debit']}  credit {tb['total_credit']}  balanced={tb['balanced']}")
        assert tb["balanced"], "Trial balance not balanced!"
        print("\nOK - F110 proposal, payment run and SEPA file are consistent; the ledger balances.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
