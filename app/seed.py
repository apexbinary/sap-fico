"""Seed a demo client with a complete, postable FI/CO configuration.

Creates:
  * Client 100, Company code 1000 (Germany, EUR), Chart of accounts INT
  * Fiscal year variant K4 (calendar year) + open posting periods (T001B)
  * Controlling area 1000 with cost center 1000 and primary cost elements
  * Document types, posting keys, document number ranges
  * A small chart of accounts (bank, receivables, payables, tax, revenue, expense)
  * German tax procedure TAXD with input (V1) and output (A1) VAT at 19%
  * Terms of payment 0001 / NT30 / ZB01 and cash discount accounts (SKT/SKE)
  * F110: methods T (SEPA transfer) / E (SEPA direct debit), bank determination,
    vendor/customer bank details, a SEPA mandate for the demo customer
  * Payment-difference tolerances (T043G, key ZDI) and open-item G/L account 113109
  * Financial statement version INT and retained earnings 109000 (T030 BIL)
  * Dunning procedure 0001 (four levels) and dunning data for the demo customer
  * One demo customer and one demo vendor (vendor on ZB01 cash discount terms)

Run:  python -m app.seed
Re-running is idempotent (records are merged by primary key).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal, create_all
from app.models.assets import (
    AssetAccountDetermination,
    AssetClass,
    AssetTransactionType,
    DepreciationArea,
)
from app.models.bank import Bank, HouseBank, HouseBankAccount
from app.models.controlling import CostCenter, CostElement, CostElementCO
from app.models.documents import DocumentType, NumberRange, PostingKey
from app.models.dunning import DunningCharge, DunningLevel, DunningProcedure
from app.models.fsv import FinancialStatementVersion, FSVAccountAssignment, FSVNode
from app.models.gl_master import (
    GLAccountCOA,
    GLAccountCompanyCode,
    GLAccountGroup,
    GLAccountText,
)
from app.models.organizational import (
    ChartOfAccounts,
    Client,
    CompanyCode,
    ControllingArea,
    ControllingAreaAssignment,
    Currency,
    FiscalYearPeriod,
    FiscalYearVariant,
    PostingPeriodControl,
)
from app.models.partners import (
    Customer,
    CustomerBankDetails,
    CustomerCompanyCode,
    CustomerDunningData,
    SepaMandate,
    Vendor,
    VendorBankDetails,
    VendorCompanyCode,
)
from app.models.payments import (
    AutomaticAccountDetermination,
    BankDetermination,
    CompanyCodePaymentMethod,
    CustomerVendorTolerance,
    PaymentMethod,
    PaymentTerms,
)
from app.models.tax import Country, TaxAccount, TaxCode, TaxRate

# G/L accounts managed on an open item basis (SKB1-XOPVW), cleared with F-03.
OPEN_ITEM_GL = {"113109"}

MANDT = "100"
BUKRS = "1000"
KTOPL = "INT"
KOKRS = "1000"
PERIV = "K4"
HIGH = date(9999, 12, 31)
LOW = date(1900, 1, 1)


def _gl_accounts():
    """(account, name, is_balance_sheet, account_group, [recon_type], [tax_cat])."""
    return [
        ("100000", "Subscribed capital", True, "GL00", None, None),
        ("109000", "Retained earnings", True, "GL00", None, None),
        ("113100", "Bank (main account)", True, "GL00", None, None),
        ("113109", "Bank clearing account (open items)", True, "GL00", None, None),
        ("140000", "Trade receivables - domestic", True, "RECN", "D", None),
        ("154000", "Input tax (VST)", True, "GL00", None, "<"),
        ("160000", "Trade payables - domestic", True, "RECN", "K", None),
        ("175000", "Output tax (MWS)", True, "GL00", None, ">"),
        ("400000", "Consumption of raw materials", False, "PL00", None, "V1"),
        ("476000", "Office supplies expense", False, "PL00", None, "V1"),
        ("480000", "Depreciation expense", False, "PL00", None, None),
        ("800000", "Sales revenue - domestic", False, "PL00", None, "A1"),
        ("880000", "Cash discount granted", False, "PL00", None, None),
        ("880100", "Payment differences - loss", False, "PL00", None, None),
        ("880200", "Payment differences - gain", False, "PL00", None, None),
        ("276000", "Cash discount received", False, "GL00", None, None),
        ("011000", "Machinery (acquisition cost)", True, "GL00", None, None),
        ("011010", "Accumulated depreciation - machinery", True, "GL00", None, None),
    ]


# Financial statement version INT: (id, parent, item key, text, kind, sign, [(from, to, debit, credit)])
FSV_ITEMS = [
    (1, None, "1", "ASSETS", "A", 1, []),
    (11, 1, "11", "Fixed assets", "", 1, [("011000", "011999", True, True)]),
    (12, 1, "12", "Receivables and other assets", "", 1, [("140000", "149999", True, True), ("154000", "154999", True, True)]),
    (13, 1, "13", "Bank and cash", "", 1, [("113000", "113999", True, False)]),
    (2, None, "2", "LIABILITIES AND EQUITY", "L", -1, []),
    (21, 2, "21", "Equity", "", 1, [("100000", "109999", True, True)]),
    (22, 2, "22", "Net result for the year", "N", 1, []),
    (23, 2, "23", "Payables and other liabilities", "", 1, [("160000", "169999", True, True), ("175000", "175999", True, True)]),
    (24, 2, "24", "Bank overdrafts", "", 1, [("113000", "113999", False, True)]),
    (3, None, "3", "PROFIT AND LOSS", "P", -1, []),
    (31, 3, "31", "Sales revenue", "", 1, [("800000", "849999", True, True)]),
    (32, 3, "32", "Sales deductions and payment differences", "", 1, [("880000", "889999", True, True)]),
    (33, 3, "33", "Other operating income", "", 1, [("270000", "279999", True, True)]),
    (34, 3, "34", "Cost of materials", "", 1, [("400000", "409999", True, True)]),
    (35, 3, "35", "Other operating expenses", "", 1, [("410000", "479999", True, True)]),
    (36, 3, "36", "Depreciation", "", 1, [("480000", "489999", True, True)]),
    (9, None, "9", "NOT ASSIGNED", "U", 1, []),
]


# TBSL-STBSL: the reversal key flips debit/credit and keeps the account type.
REVERSAL_KEYS = {
    "40": "50", "50": "40", "70": "75", "75": "70",
    "01": "12", "12": "01", "11": "02", "02": "11", "15": "05", "05": "15",
    "06": "16", "16": "06", "07": "17", "17": "07",
    "21": "32", "32": "21", "31": "22", "22": "31", "25": "35", "35": "25",
    "26": "36", "36": "26", "27": "37", "37": "27",
}


def seed() -> None:
    create_all()
    s = SessionLocal()
    try:
        # --- Client & currency ---
        s.merge(Client(mandt=MANDT, mtext="Demo Group", ort01="Walldorf", mwaer="EUR", cccategory="C"))
        for cur, name, iso in [("EUR", "Euro", "EUR"), ("USD", "US Dollar", "USD")]:
            s.merge(Currency(mandt=MANDT, waers=cur, isocd=iso, ltext=name, currdec=2))

        # --- Country & tax procedure ---
        s.merge(Country(mandt=MANDT, land1="DE", landx="Germany", kalsm="TAXD", intca="DE", waers="EUR", xegld=True))

        # --- Chart of accounts & account groups ---
        s.merge(ChartOfAccounts(mandt=MANDT, ktopl=KTOPL, ktplt="Chart of accounts - international", seona=6, spras="E"))
        for grp, txt, lo, hi in [
            ("GL00", "General G/L accounts", "0", "399999"),
            ("PL00", "P&L accounts", "400000", "899999"),
            ("RECN", "Reconciliation accounts", "100000", "199999"),
        ]:
            s.merge(GLAccountGroup(mandt=MANDT, ktopl=KTOPL, ktoks=grp, txt30=txt, vonkt=lo, biskt=hi))

        # --- Fiscal year variant K4 (calendar) + open periods ---
        s.merge(FiscalYearVariant(mandt=MANDT, periv=PERIV, xmon=True, anzbp=12, anzsp=4, beztx="Calendar year, 4 special periods"))

        # --- Company code 1000 ---
        s.merge(CompanyCode(
            mandt=MANDT, bukrs=BUKRS, butxt="Demo Company AG", ort01="Walldorf", land1="DE",
            waers="EUR", spras="E", ktopl=KTOPL, periv=PERIV, kokfi=KOKRS, stceg="DE123456789",
            land1_iso="DE", waers_iso="EUR",
        ))

        # Open posting periods for all account types ('+')
        s.merge(PostingPeriodControl(
            mandt=MANDT, bukrs=BUKRS, koart="+", konti_von="",
            frpe1=1, frgj1=0, tope1=12, tagj1=9999, frpe2=13, frgj2=0, tope2=16, tagj2=9999,
        ))

        # --- Controlling area 1000 ---
        s.merge(ControllingArea(mandt=MANDT, kokrs=KOKRS, bezei="Controlling area 1000", waers="EUR", ctyp="10", ktopl=KTOPL, lmona=PERIV, bukrs=BUKRS, khinr="H1000"))
        s.merge(ControllingAreaAssignment(mandt=MANDT, kokrs=KOKRS, bukrs=BUKRS))
        s.merge(CostCenter(mandt=MANDT, kokrs=KOKRS, kostl="0000001000", datbi=HIGH, datab=LOW, ktext="Admin", ltext="Administration cost center", bukrs=BUKRS, prctr="0000001000", waers="EUR", kosar="1"))

        # --- G/L accounts ---
        for saknr, name, is_bs, grp, recon, taxcat in _gl_accounts():
            s.merge(GLAccountCOA(mandt=MANDT, ktopl=KTOPL, saknr=saknr, xbilk=is_bs, gvtyp=None if is_bs else "X", ktoks=grp, erdat="20260101", ernam="SEED"))
            s.merge(GLAccountText(mandt=MANDT, spras="E", ktopl=KTOPL, saknr=saknr, txt20=name[:20], txt50=name, mcod1=name[:25].upper()))
            s.merge(GLAccountCompanyCode(
                mandt=MANDT, bukrs=BUKRS, saknr=saknr, waers="EUR", xkres=True,
                mwskz=taxcat, mitkz=recon, xopvw=recon is not None or saknr in OPEN_ITEM_GL,
                fstag="G001", zuawa="001", erdat="20260101", ernam="SEED",
            ))

        # --- Cost elements for P&L accounts ---
        for kstar, katyp in [("400000", "1"), ("476000", "1"), ("480000", "1"), ("800000", "11")]:
            s.merge(CostElement(mandt=MANDT, ktopl=KTOPL, kstar=kstar, erdat="20260101"))
            s.merge(CostElementCO(mandt=MANDT, kokrs=KOKRS, kstar=kstar, datbi=HIGH, datab=LOW, katyp=katyp, ktext=kstar))

        # --- Tax codes (TAXD) ---
        s.merge(TaxCode(mandt=MANDT, kalsm="TAXD", mwskz="A1", mwart="A", text1="Output VAT 19%"))
        s.merge(TaxCode(mandt=MANDT, kalsm="TAXD", mwskz="V1", mwart="V", text1="Input VAT 19%"))
        s.merge(TaxRate(mandt=MANDT, kalsm="TAXD", mwskz="A1", ktosl="MWS", kschl="MWAS", kbetr=Decimal("19.000")))
        s.merge(TaxRate(mandt=MANDT, kalsm="TAXD", mwskz="V1", ktosl="VST", kschl="MWVS", kbetr=Decimal("19.000")))
        s.merge(TaxAccount(mandt=MANDT, ktopl=KTOPL, ktosl="MWS", mwskz="A1", bukrs="", konts="175000", shkzg="H"))
        s.merge(TaxAccount(mandt=MANDT, ktopl=KTOPL, ktosl="VST", mwskz="V1", bukrs="", konts="154000", shkzg="S"))

        # --- Document types ---
        for blart, txt, numkr, flags in [
            ("SA", "G/L account document", "01", dict(xsach=True)),
            ("DR", "Customer invoice", "18", dict(xsach=True, xkund=True)),
            ("DZ", "Customer payment", "14", dict(xsach=True, xkund=True)),
            ("KR", "Vendor invoice", "19", dict(xsach=True, xlief=True)),
            ("KZ", "Vendor payment", "15", dict(xsach=True, xlief=True)),
            ("AA", "Asset posting", "01", dict(xsach=True, xanlg=True, xlief=True, xkund=True)),
            ("AF", "Depreciation posting", "01", dict(xsach=True)),
            ("AB", "Accounting document", "01", dict(xsach=True, xkund=True, xlief=True, xanlg=True)),
            ("ZP", "Payment posting (F110)", "15", dict(xsach=True, xkund=True, xlief=True)),
        ]:
            s.merge(DocumentType(mandt=MANDT, blart=blart, ltext=txt, numkr=numkr, **flags))

        # --- Number ranges (per company code, year-independent) ---
        for numkr, lo, hi in [
            ("01", 100000000, 199999999),
            ("14", 140000000, 149999999),
            ("15", 150000000, 159999999),
            ("18", 180000000, 189999999),
            ("19", 190000000, 199999999),
            ("X1", 9100000000, 9199999999),  # recurring entry originals
        ]:
            # Only create missing intervals: NRLEVEL is the live counter and must survive re-seeding.
            if s.get(NumberRange, (MANDT, "RF_BELEG", BUKRS, numkr, 0)) is None:
                s.add(NumberRange(mandt=MANDT, object="RF_BELEG", subobject=BUKRS, nrrangenr=numkr, toyear=0, fromnumber=str(lo), tonumber=str(hi), nrlevel=str(lo - 1)))

        # --- Posting keys (standard SAP) ---
        for bschl, txt, shkzg, koart, extra in [
            ("40", "Debit entry", "S", "S", {}),
            ("50", "Credit entry", "H", "S", {}),
            ("01", "Invoice (customer)", "S", "D", dict(xumsw=True)),
            ("11", "Credit memo (customer)", "H", "D", dict(xumsw=True)),
            ("15", "Incoming payment", "H", "D", dict(xzahl=True)),
            ("05", "Outgoing payment (customer)", "S", "D", dict(xzahl=True)),
            ("06", "Payment difference (customer)", "S", "D", {}),
            ("07", "Other clearing (customer)", "S", "D", {}),
            ("16", "Payment difference (customer)", "H", "D", {}),
            ("17", "Other clearing (customer)", "H", "D", {}),
            ("21", "Credit memo (vendor)", "S", "K", dict(xumsw=True)),
            ("25", "Outgoing payment", "S", "K", dict(xzahl=True)),
            ("26", "Payment difference (vendor)", "S", "K", {}),
            ("27", "Clearing (vendor)", "S", "K", {}),
            ("31", "Invoice (vendor)", "H", "K", dict(xumsw=True)),
            ("35", "Incoming payment (vendor)", "H", "K", dict(xzahl=True)),
            ("36", "Payment difference (vendor)", "H", "K", {}),
            ("37", "Other clearing (vendor)", "H", "K", {}),
            ("70", "Debit asset", "S", "A", {}),
            ("75", "Credit asset", "H", "A", {}),
            ("02", "Reverse credit memo (customer)", "S", "D", dict(xumsw=True)),
            ("12", "Reverse invoice (customer)", "H", "D", dict(xumsw=True)),
            ("22", "Reverse invoice (vendor)", "S", "K", dict(xumsw=True)),
            ("32", "Reverse credit memo (vendor)", "H", "K", dict(xumsw=True)),
        ]:
            s.merge(PostingKey(mandt=MANDT, bschl=bschl, ltext=txt, shkzg=shkzg, koart=koart,
                               stbsl=REVERSAL_KEYS[bschl], **extra))

        # --- Terms of payment (T052) & cash discount accounts (T030) ---
        for zterm, text, t1, p1, t2, p2, t3 in [
            ("0001", "Payable immediately, due net", 0, "0", 0, "0", 0),
            ("NT30", "30 days due net", 0, "0", 0, "0", 30),
            ("ZB01", "14 days 3%, 30 days 2%, 45 days due net", 14, "3", 30, "2", 45),
        ]:
            s.merge(PaymentTerms(
                mandt=MANDT, zterm=zterm, ztagg=0, text1=text, zdart="B",
                ztag1=t1, zprz1=Decimal(p1), ztag2=t2, zprz2=Decimal(p2), ztag3=t3,
            ))
        s.merge(AutomaticAccountDetermination(mandt=MANDT, ktopl=KTOPL, ktosl="SKT", bwmod="", komok="", bklas="", konts="880000"))
        s.merge(AutomaticAccountDetermination(mandt=MANDT, ktopl=KTOPL, ktosl="SKE", bwmod="", komok="", bklas="", konts="276000"))
        s.merge(AutomaticAccountDetermination(mandt=MANDT, ktopl=KTOPL, ktosl="ZDI", bwmod="", komok="", bklas="", konts="880100", konth="880200"))
        # Retained earnings for the balance carryforward (P&L statement account type X)
        s.merge(AutomaticAccountDetermination(mandt=MANDT, ktopl=KTOPL, ktosl="BIL", bwmod="", komok="X", bklas="", konts="109000"))

        # --- Financial statement version INT ---
        s.merge(FinancialStatementVersion(mandt=MANDT, versn="INT", vstxt="Balance sheet / P&L (international)", ktopl=KTOPL))
        for seqno, (node_id, parent, ergsl, text, kind, sign, ranges) in enumerate(FSV_ITEMS):
            s.merge(FSVNode(mandt=MANDT, versn="INT", id=node_id, parent=parent, ergsl=ergsl, txt45=text,
                            seqno=seqno, kind=kind, sign=sign))
            for vonkt, biskt, soll, haben in ranges:
                s.merge(FSVAccountAssignment(mandt=MANDT, versn="INT", ergsl=ergsl, ktopl=KTOPL,
                                             vonkt=vonkt, biskt=biskt, soll=soll, haben=haben))

        # --- Dunning procedure 0001 (four levels, 14-day interval, 3 grace days) ---
        s.merge(DunningProcedure(mandt=MANDT, mahna="0001", text1="Four-level dunning, every 14 days",
                                 rhytm=14, mstuf=4, gracp=3, minbt=Decimal("10.00")))
        for mahns, verzn, text, always, charge in [
            (1, 1, "Payment reminder", False, "0"),
            (2, 15, "Second reminder", False, "5.00"),
            (3, 29, "Final reminder", False, "10.00"),
            (4, 43, "Notice before legal action", True, "25.00"),
        ]:
            s.merge(DunningLevel(mandt=MANDT, mahna="0001", mahns=mahns, verzn=verzn, text1=text, xalwy=always))
            s.merge(DunningCharge(mandt=MANDT, mahna="0001", mahns=mahns, waers="EUR", mahng=Decimal(charge)))

        # Default tolerance group: differences up to 2.00 EUR and 1% are posted automatically.
        s.merge(CustomerVendorTolerance(mandt=MANDT, bukrs=BUKRS, togru="", betrh=Decimal("2.00"), prozh=Decimal("1.00"), betrs=Decimal("2.00"), prozs=Decimal("1.00")))

        # --- Demo customer & vendor ---
        s.merge(Customer(mandt=MANDT, kunnr="0000010000", ktokd="KUNA", name1="Alpha Retail GmbH", land1="DE", ort01="Berlin", spras="E"))
        s.merge(CustomerCompanyCode(mandt=MANDT, kunnr="0000010000", bukrs=BUKRS, akont="140000", zterm="0001", zuawa="001", zwels="E"))
        s.merge(CustomerBankDetails(mandt=MANDT, kunnr="0000010000", banks="DE", bankl="30000000", bankn="0555666777", koinh="Alpha Retail GmbH", iban="DE81300000000555666777"))
        # KNB5 holds runtime state (last dunning level/date): create only, never re-merge.
        if s.get(CustomerDunningData, (MANDT, "0000010000", BUKRS, "")) is None:
            s.add(CustomerDunningData(mandt=MANDT, kunnr="0000010000", bukrs=BUKRS, maber="", mahna="0001"))
        s.merge(SepaMandate(mandt=MANDT, mndid="MND-0000010000-001", snd_type="BUS3007", snd_id="0000010000",
                            snd_name1="Alpha Retail GmbH", snd_iban="DE81300000000555666777", snd_bic="BEDEDEBB",
                            rec_type="BUS0002", rec_id=BUKRS, rec_crdid="DE98ZZZ09999999999", rec_name1="Demo Company AG",
                            sign_date=date(2026, 1, 1), sign_city="Berlin", pay_type="RCUR", status="1"))
        s.merge(Vendor(mandt=MANDT, lifnr="0000020000", ktokk="LIEF", name1="Beta Supplies AG", land1="DE", ort01="Munich", spras="E"))
        s.merge(VendorCompanyCode(mandt=MANDT, lifnr="0000020000", bukrs=BUKRS, akont="160000", zterm="ZB01", zuawa="001", zwels="T"))
        s.merge(VendorBankDetails(mandt=MANDT, lifnr="0000020000", banks="DE", bankl="20000000", bankn="0987654321", koinh="Beta Supplies AG", iban="DE84200000000987654321"))
        # Second vendor without bank details: shows up as an F110 exception.
        s.merge(Vendor(mandt=MANDT, lifnr="0000020001", ktokk="LIEF", name1="Gamma Logistics GmbH", land1="DE", ort01="Hamburg", spras="E"))
        s.merge(VendorCompanyCode(mandt=MANDT, lifnr="0000020001", bukrs=BUKRS, akont="160000", zterm="0001", zuawa="001", zwels="T"))

        # --- Asset Accounting ---
        s.merge(DepreciationArea(mandt=MANDT, afaber="01", afbe_txt="Book depreciation", buhbkt="1"))
        s.merge(AssetClass(mandt=MANDT, anlkl="00003000", txk50="Machinery", ktogr="30000000", num_range="02"))
        s.merge(AssetAccountDetermination(
            mandt=MANDT, ktopl=KTOPL, ktogr="30000000", afaber="01",
            ktansw="011000", ktabg_dep="011010", ktaufw_dep="480000",
            ktvabg="113100", ktgewv="800000", ktverl="480000",
        ))
        for bwasl, txt, grp, anz in [
            ("100", "External asset acquisition", "10", "+"),
            ("200", "Asset retirement with revenue", "20", "-"),
            ("210", "Asset retirement without revenue", "20", "-"),
        ]:
            s.merge(AssetTransactionType(mandt=MANDT, bwasl=bwasl, bwatxt=txt, bwagrp=grp, xanz=anz))

        # --- Bank Accounting ---
        s.merge(Bank(mandt=MANDT, banks="DE", bankl="10000000", banka="Deutsche Demo Bank", ort01="Frankfurt", swift="DEMODEFF"))
        s.merge(HouseBank(mandt=MANDT, bukrs=BUKRS, hbkid="DB", banks="DE", bankl="10000000", swift="DEMODEFF"))
        s.merge(HouseBankAccount(mandt=MANDT, bukrs=BUKRS, hbkid="DB", hktid="GIRO", bankn="123456789", iban="DE91100000000123456789", waers="EUR", hkont="113100"))
        s.merge(Bank(mandt=MANDT, banks="DE", bankl="20000000", banka="Munich Demo Bank", ort01="Munich", swift="MUDEDEMM"))
        s.merge(Bank(mandt=MANDT, banks="DE", bankl="30000000", banka="Berlin Demo Bank", ort01="Berlin", swift="BEDEDEBB"))

        # --- Automatic payment program (F110) ---
        s.merge(PaymentMethod(mandt=MANDT, land1="DE", zlsch="T", text1="Bank transfer (SEPA)", xbkkt=True, blart="ZP", progn="SEPA_CT"))
        s.merge(PaymentMethod(mandt=MANDT, land1="DE", zlsch="E", text1="SEPA direct debit", xeinz=True, blart="ZP", progn="SEPA_DD"))
        for zlsch in ("T", "E"):
            s.merge(CompanyCodePaymentMethod(mandt=MANDT, zbukr=BUKRS, zlsch=zlsch, minbt=Decimal("1.00")))
            # F110 posts to the bank clearing account; the bank statement later clears it.
            s.merge(BankDetermination(mandt=MANDT, zbukr=BUKRS, zlsch=zlsch, waers="EUR", rangf=1, hbkid="DB", hktid="GIRO", ukont="113109"))

        s.commit()
        print("Seed complete: client 100, company code 1000, chart of accounts INT.")
    finally:
        s.close()


if __name__ == "__main__":
    seed()
