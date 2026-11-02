"""Seed a demo client with a complete, postable FI/CO configuration.

Creates:
  * Client 100, Company code 1000 (Germany, EUR), Chart of accounts INT
  * Fiscal year variant K4 (calendar year) + open posting periods (T001B)
  * Controlling area 1000 with cost centers 1000/2000/3000, internal order 400001,
    primary cost elements and the CO document number range (RK_BELEG)
  * Allocation cycles ADMIN-ASM (assessment), SALES-DST (distribution), SALES-PA (KEU5)
  * Activity type 1000 (labour hours, 50 EUR at production), admin office plan 12000 EUR/year
  * Settlement rule of order 400001 (60% cost center 2000, 40% G/L 477000)
  * Operating concern IDEA (account-based CO-PA) assigned to controlling area 1000
  * Document types, posting keys, document number ranges
  * A small chart of accounts (bank, receivables, payables, tax, revenue, expense)
  * German tax procedure TAXD with input (V1) and output (A1) VAT at 19%
  * Terms of payment 0001 / NT30 / ZB01 and cash discount accounts (SKT/SKE)
  * F110: methods T (SEPA transfer) / E (SEPA direct debit), bank determination,
    vendor/customer bank details, a SEPA mandate for the demo customer
  * Payment-difference tolerances (T043G, key ZDI) and open-item G/L account 113109
  * Employee tolerances (T043T, user JDOE in group JUNI), reason codes 01/02 (T053R),
    check payment method C with check lot 100001-100500, T042Y available amount
  * Financial statement version INT and retained earnings 109000 (T030 BIL)
  * Functional areas 0100/0300/0400/0500 on cost centers and P&L accounts
  * Dunning procedure 0001 (four levels, interest from level 2), dunning areas 01/02,
    interest indicator 01 (8%), dunning data for the demo customer and vendor
  * USD exchange rates M/G/B (TCURR), valuation methods (T044A), exchange rate
    difference accounts (T030H), group currency USD (T001A), USD bank account 113200
  * One demo customer and one demo vendor (vendor on ZB01 cash discount terms)

Run:  python -m app.seed
Re-running is idempotent (records are merged by primary key).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal, init_db
from app.models.assets import (
    AssetAccountDetermination,
    AssetClass,
    AssetTransactionType,
    DepreciationArea,
)
from app.models.bank import Bank, HouseBank, HouseBankAccount
from app.models.controlling import (
    ActivityPrice,
    ActivityType,
    AllocationCycle,
    AllocationReceiver,
    AllocationSegment,
    CostCenter,
    CostElement,
    COTotals,
    CostElementCO,
    FunctionalArea,
    InternalOrder,
    OperatingConcern,
    SettlementDistribution,
    SettlementRule,
)
from app.models.documents import DocumentType, NumberRange, PostingKey
from app.models.dunning import (
    DunningArea,
    DunningCharge,
    DunningLevel,
    DunningProcedure,
    InterestIndicator,
    InterestRate,
)
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
    AdditionalLocalCurrencies,
    Currency,
    ExchangeRate,
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
    VendorDunningData,
)
from app.models.payments import (
    AutomaticAccountDetermination,
    AvailableAmount,
    BankDetermination,
    CheckLot,
    CompanyCodePaymentMethod,
    CustomerVendorTolerance,
    EmployeeTolerance,
    ExchangeDifferenceAccounts,
    PaymentDifferenceReason,
    PaymentMethod,
    PaymentTerms,
    UserToleranceGroup,
    ValuationMethod,
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
        ("113200", "Bank USD account", True, "GL00", None, None),
        ("113209", "Bank USD - valuation adjustment", True, "GL00", None, None),
        ("140000", "Trade receivables - domestic", True, "RECN", "D", None),
        ("140099", "Receivables - FX valuation adjustment", True, "GL00", None, None),
        ("154000", "Input tax (VST)", True, "GL00", None, "<"),
        ("160000", "Trade payables - domestic", True, "RECN", "K", None),
        ("160099", "Payables - FX valuation adjustment", True, "GL00", None, None),
        ("230000", "Realized exchange rate losses", False, "GL00", None, None),
        ("230010", "Exchange rate valuation losses", False, "GL00", None, None),
        ("280000", "Realized exchange rate gains", False, "GL00", None, None),
        ("280010", "Exchange rate valuation gains", False, "GL00", None, None),
        ("175000", "Output tax (MWS)", True, "GL00", None, ">"),
        ("400000", "Consumption of raw materials", False, "PL00", None, "V1"),
        ("476000", "Office supplies expense", False, "PL00", None, "V1"),
        ("479000", "Bank charges", False, "PL00", None, None),
        ("477000", "Marketing expenses", False, "PL00", None, None),
        ("960000", "Internal order settlement", False, "PL00", None, None),
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
    (33, 3, "33", "Other operating income", "", 1, [("270000", "279999", True, True), ("280000", "289999", True, True)]),
    (34, 3, "34", "Cost of materials", "", 1, [("400000", "409999", True, True)]),
    (35, 3, "35", "Other operating expenses", "", 1, [("410000", "479999", True, True), ("230000", "239999", True, True),
                                                       ("960000", "969999", True, True)]),
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


# G/L accounts kept in a foreign currency (SKB1-WAERS); valued by balance on the key date
ACCOUNT_CURRENCY = {"113200": "USD"}

# Functional area of P&L accounts posted without a cost center (cost-of-sales P&L)
ACCOUNT_FUNCTIONAL_AREAS = {
    "400000": "0100", "480000": "0100", "476000": "0400", "477000": "0300", "479000": "0400",
    "880000": "0300", "880100": "0400", "880200": "0400", "230000": "0400", "230010": "0400",
    "280000": "0400", "280010": "0400", "276000": "0400", "960000": "0400",
}


def seed() -> None:
    init_db()
    s = SessionLocal()

    def put(obj) -> None:
        # Flush record by record, in code order (parents first): SQLAlchemy only
        # orders inserts by relationships, and PostgreSQL enforces every foreign key.
        s.merge(obj)
        s.flush()

    try:
        # --- Client & currency ---
        put(Client(mandt=MANDT, mtext="Demo Group", ort01="Walldorf", mwaer="EUR", cccategory="C"))
        for cur, name, iso in [("EUR", "Euro", "EUR"), ("USD", "US Dollar", "USD")]:
            put(Currency(mandt=MANDT, waers=cur, isocd=iso, ltext=name, currdec=2))

        # Exchange rates (type M): value of 1 USD in EUR, valid from GDATU
        for gdatu, ukurs in [(date(2025, 1, 1), "0.93"), (date(2026, 1, 1), "0.92"), (date(2026, 6, 1), "0.90"),
                             (date(2026, 9, 1), "0.95"), (date(2026, 12, 1), "0.88")]:
            put(ExchangeRate(mandt=MANDT, kurst="M", fcurr="USD", tcurr="EUR", gdatu=gdatu,
                                 ukurs=Decimal(ukurs), ffact=1, tfact=1))
            # bank buying (G) and selling (B) rates, 1% around the middle rate
            for kurst, factor in (("G", Decimal("0.99")), ("B", Decimal("1.01"))):
                put(ExchangeRate(mandt=MANDT, kurst=kurst, fcurr="USD", tcurr="EUR", gdatu=gdatu,
                                 ukurs=(Decimal(ukurs) * factor).quantize(Decimal("0.00001")), ffact=1, tfact=1))
        # Valuation methods (T044A): middle rate, or lower-of-cost with buying / selling rates
        put(ValuationMethod(mandt=MANDT, bwmet="KTO", txt="Middle rate for all balances", kurst_s="M", kurst_h="M"))
        put(ValuationMethod(mandt=MANDT, bwmet="BG", txt="Buying rate debit, selling rate credit",
                            kurst_s="G", kurst_h="B"))

        # --- Country & tax procedure ---
        put(Country(mandt=MANDT, land1="DE", landx="Germany", kalsm="TAXD", intca="DE", waers="EUR", xegld=True))

        # --- Chart of accounts & account groups ---
        put(ChartOfAccounts(mandt=MANDT, ktopl=KTOPL, ktplt="Chart of accounts - international", seona=6, spras="E"))
        for grp, txt, lo, hi in [
            ("GL00", "General G/L accounts", "0", "399999"),
            ("PL00", "P&L accounts", "400000", "899999"),
            ("RECN", "Reconciliation accounts", "100000", "199999"),
        ]:
            put(GLAccountGroup(mandt=MANDT, ktopl=KTOPL, ktoks=grp, txt30=txt, vonkt=lo, biskt=hi))

        # --- Fiscal year variant K4 (calendar) + open periods ---
        put(FiscalYearVariant(mandt=MANDT, periv=PERIV, xmon=True, anzbp=12, anzsp=4, beztx="Calendar year, 4 spec. periods"))

        # --- Company code 1000 ---  (group currency USD as 2nd local currency, see T001A below)
        put(CompanyCode(
            mandt=MANDT, bukrs=BUKRS, butxt="Demo Company AG", ort01="Walldorf", land1="DE",
            waers="EUR", spras="E", ktopl=KTOPL, periv=PERIV, kokfi="1", stceg="DE123456789",
            land1_iso="DE", waers_iso="EUR",
        ))

        put(AdditionalLocalCurrencies(mandt=MANDT, bukrs=BUKRS, curtp2="30", waers2="USD", kurst2="M"))

        # Open posting periods for all account types ('+')
        put(PostingPeriodControl(
            mandt=MANDT, bukrs=BUKRS, koart="+", konti_von="",
            frpe1=1, frgj1=0, tope1=12, tagj1=9999, frpe2=13, frgj2=0, tope2=16, tagj2=9999,
        ))

        # --- Controlling area 1000 ---
        put(OperatingConcern(mandt=MANDT, erkrs="IDEA", erkrs_txt="Demo operating concern", waers="EUR", xkontb=True))
        put(ControllingArea(mandt=MANDT, kokrs=KOKRS, bezei="Controlling area 1000", waers="EUR", ctyp="10", ktopl=KTOPL, lmona=PERIV, bukrs=BUKRS, khinr="H1000", erkrs="IDEA"))
        put(ControllingAreaAssignment(mandt=MANDT, kokrs=KOKRS, bukrs=BUKRS))
        for kostl, ktext, ltext, kosar, fkber in [
            ("0000001000", "Admin", "Administration cost center", "1", "0400"),
            ("0000002000", "Sales", "Sales cost center", "3", "0300"),
            ("0000003000", "Production", "Production cost center", "4", "0100"),
        ]:
            put(CostCenter(mandt=MANDT, kokrs=KOKRS, kostl=kostl, datbi=HIGH, datab=LOW, ktext=ktext, ltext=ltext,
                           bukrs=BUKRS, prctr="0000001000", waers="EUR", kosar=kosar, fkber=fkber))
        # Secondary cost elements: assessments (category 42) and activity allocation (category 43)
        for kstar, katyp, ktext, ltext in [
            ("943000", "42", "Assessment admin", "Assessment of administration costs"),
            ("944000", "42", "Assessment CO-PA", "Assessment of sales costs to CO-PA"),
            ("943100", "43", "Labour allocation", "Activity allocation: labour hours"),
        ]:
            put(CostElement(mandt=MANDT, ktopl=KTOPL, kstar=kstar, erdat="20260101"))
            put(CostElementCO(mandt=MANDT, kokrs=KOKRS, kstar=kstar, datbi=HIGH, datab=LOW, katyp=katyp,
                              ktext=ktext, ltext=ltext))
        # Activity type 1000 (labour hours) provided by production at 50 EUR per hour in 2026
        put(ActivityType(mandt=MANDT, kokrs=KOKRS, lstar="1000", datbi=HIGH, datab=LOW, ktext="Labour hours",
                         leinh="H", vksta="943100", latyp="1"))
        # Plan data and activity prices are user data: create only, never re-merge
        if s.get(ActivityPrice, (MANDT, f"LT{KOKRS}00000030001000", 2026, "01", "000")) is None:
            put(ActivityPrice(mandt=MANDT, objnr=f"LT{KOKRS}00000030001000", gjahr=2026, wrttp="01", versn="000",
                              kokrs=KOKRS, **{f"tkg{p:03d}": Decimal("50.00") for p in range(1, 17)}))
        if s.get(COTotals, (MANDT, f"KS{KOKRS}0000001000", 2026, "01", "000", "476000")) is None:
            put(COTotals(mandt=MANDT, objnr=f"KS{KOKRS}0000001000", gjahr=2026, wrttp="01", versn="000",
                         kstar="476000", kokrs=KOKRS, twaer="EUR",
                         **{f"wkg{p:03d}": Decimal("1000.00") if p <= 12 else Decimal("0") for p in range(1, 17)}))
        # Cycles: admin costs are assessed to sales/production (60:40); sales distributes office costs to production
        for cycle, ttype, txt, segs in [
            ("ADMIN-ASM", "A", "Assess administration to sales and production",
             [(1, "Admin costs", "0000001000", "0000001000", "400000", "499999", "943000",
               [("0000002000", "60"), ("0000003000", "40")])]),
            ("SALES-DST", "D", "Distribute sales office costs to production",
             [(1, "Office supplies", "0000002000", "0000002000", "476000", "476000", None,
               [("0000003000", "1")])]),
            # KEU5: receivers are the profitability segments, weighted by their net revenue
            ("SALES-PA", "P", "Assess sales costs to profitability segments",
             [(1, "Sales costs", "0000002000", "0000002000", "400000", "999999", "944000", [])]),
        ]:
            put(AllocationCycle(mandt=MANDT, kokrs=KOKRS, cycle=cycle, sdate=date(2026, 1, 1), edate=HIGH,
                                txt=txt, ttype=ttype))
            for seg, stxt, kvon, kbis, evon, ebis, askst, receivers in segs:
                put(AllocationSegment(mandt=MANDT, kokrs=KOKRS, cycle=cycle, sdate=date(2026, 1, 1), seg=seg,
                                      txt=stxt, kostl_von=kvon, kostl_bis=kbis, kstar_von=evon, kstar_bis=ebis,
                                      askst=askst))
                for kostl, factor in receivers:
                    put(AllocationReceiver(mandt=MANDT, kokrs=KOKRS, cycle=cycle, sdate=date(2026, 1, 1), seg=seg,
                                           kostl=kostl, faktor=Decimal(factor)))
        put(InternalOrder(mandt=MANDT, aufnr="000000400001", auart="0100", autyp="01", ktext="Trade fair 2026",
                          bukrs=BUKRS, kokrs=KOKRS, kostv="0000002000", waers="EUR", phas0=True, phas1=True))
        # Settlement: internal element 950000 (cat. 21, CO only), external 960000 (cat. 22, G/L account)
        put(CostElement(mandt=MANDT, ktopl=KTOPL, kstar="950000", erdat="20260101"))
        put(CostElementCO(mandt=MANDT, kokrs=KOKRS, kstar="950000", datbi=HIGH, datab=LOW, katyp="21",
                          ktext="Order settlement", ltext="Internal order settlement (internal)"))
        put(CostElement(mandt=MANDT, ktopl=KTOPL, kstar="960000", erdat="20260101"))
        put(CostElementCO(mandt=MANDT, kokrs=KOKRS, kstar="960000", datbi=HIGH, datab=LOW, katyp="22",
                          ktext="Ext. settlement", ltext="Internal order settlement (external)"))
        # Trade fair order: 60% to the sales cost center, 40% to marketing expenses
        put(SettlementRule(mandt=MANDT, objnr="OR000000400001", aprof="20", kokrs=KOKRS))
        put(SettlementDistribution(mandt=MANDT, objnr="OR000000400001", bureg=1, lfdnr=1, konty="KS",
                                   kostl="0000002000", prozs=Decimal("60"), perbz="PER", gabja=2026, gabpe=1))
        put(SettlementDistribution(mandt=MANDT, objnr="OR000000400001", bureg=2, lfdnr=1, konty="SK",
                                   hkont="477000", prozs=Decimal("40"), perbz="PER", gabja=2026, gabpe=1))

        # --- G/L accounts ---
        for fkber, fkbtx in [("0100", "Production"), ("0300", "Sales and distribution"),
                             ("0400", "Administration"), ("0500", "Research and development")]:
            put(FunctionalArea(mandt=MANDT, fkber=fkber, fkbtx=fkbtx))
        for saknr, name, is_bs, grp, recon, taxcat in _gl_accounts():
            put(GLAccountCOA(mandt=MANDT, ktopl=KTOPL, saknr=saknr, xbilk=is_bs, gvtyp=None if is_bs else "X", ktoks=grp,
                             func_area=None if is_bs else ACCOUNT_FUNCTIONAL_AREAS.get(saknr), erdat="20260101", ernam="SEED"))
            put(GLAccountText(mandt=MANDT, spras="E", ktopl=KTOPL, saknr=saknr, txt20=name[:20], txt50=name, mcod1=name[:25].upper()))
            put(GLAccountCompanyCode(
                mandt=MANDT, bukrs=BUKRS, saknr=saknr, waers=ACCOUNT_CURRENCY.get(saknr, "EUR"), xkres=True,
                mwskz=taxcat, mitkz=recon, xopvw=recon is not None or saknr in OPEN_ITEM_GL,
                fstag="G001", zuawa="001", erdat="20260101", ernam="SEED",
            ))

        # --- Cost elements for P&L accounts ---
        for kstar, katyp in [("400000", "1"), ("476000", "1"), ("480000", "1"), ("800000", "11"), ("880000", "12")]:
            put(CostElement(mandt=MANDT, ktopl=KTOPL, kstar=kstar, erdat="20260101"))
            put(CostElementCO(mandt=MANDT, kokrs=KOKRS, kstar=kstar, datbi=HIGH, datab=LOW, katyp=katyp, ktext=kstar))

        # --- Tax codes (TAXD) ---
        put(TaxCode(mandt=MANDT, kalsm="TAXD", mwskz="A1", mwart="A", text1="Output VAT 19%"))
        put(TaxCode(mandt=MANDT, kalsm="TAXD", mwskz="V1", mwart="V", text1="Input VAT 19%"))
        put(TaxRate(mandt=MANDT, kalsm="TAXD", mwskz="A1", ktosl="MWS", kschl="MWAS", kbetr=Decimal("19.000")))
        put(TaxRate(mandt=MANDT, kalsm="TAXD", mwskz="V1", ktosl="VST", kschl="MWVS", kbetr=Decimal("19.000")))
        put(TaxAccount(mandt=MANDT, ktopl=KTOPL, ktosl="MWS", mwskz="A1", bukrs="", konts="175000", shkzg="H"))
        put(TaxAccount(mandt=MANDT, ktopl=KTOPL, ktosl="VST", mwskz="V1", bukrs="", konts="154000", shkzg="S"))

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
            put(DocumentType(mandt=MANDT, blart=blart, ltext=txt, numkr=numkr, **flags))

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
                put(NumberRange(mandt=MANDT, object="RF_BELEG", subobject=BUKRS, nrrangenr=numkr, toyear=0, fromnumber=str(lo), tonumber=str(hi), nrlevel=str(lo - 1)))

        # CO document numbers (object RK_BELEG per controlling area); live counter: create only
        if s.get(NumberRange, (MANDT, "RK_BELEG", KOKRS, "01", 0)) is None:
            put(NumberRange(mandt=MANDT, object="RK_BELEG", subobject=KOKRS, nrrangenr="01", toyear=0,
                            fromnumber="2000000000", tonumber="2999999999", nrlevel="1999999999"))

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
            put(PostingKey(mandt=MANDT, bschl=bschl, ltext=txt, shkzg=shkzg, koart=koart,
                               stbsl=REVERSAL_KEYS[bschl], **extra))

        # --- Terms of payment (T052) & cash discount accounts (T030) ---
        for zterm, text, t1, p1, t2, p2, t3 in [
            ("0001", "Payable immediately, due net", 0, "0", 0, "0", 0),
            ("NT30", "30 days due net", 0, "0", 0, "0", 30),
            ("ZB01", "14 days 3%, 30 days 2%, 45 days due net", 14, "3", 30, "2", 45),
        ]:
            put(PaymentTerms(
                mandt=MANDT, zterm=zterm, ztagg=0, text1=text, zdart="B",
                ztag1=t1, zprz1=Decimal(p1), ztag2=t2, zprz2=Decimal(p2), ztag3=t3,
            ))
        put(AutomaticAccountDetermination(mandt=MANDT, ktopl=KTOPL, ktosl="SKT", bwmod="", komok="", bklas="", konts="880000"))
        put(AutomaticAccountDetermination(mandt=MANDT, ktopl=KTOPL, ktosl="SKE", bwmod="", komok="", bklas="", konts="276000"))
        put(AutomaticAccountDetermination(mandt=MANDT, ktopl=KTOPL, ktosl="ZDI", bwmod="", komok="", bklas="", konts="880100", konth="880200"))
        # Retained earnings for the balance carryforward (P&L statement account type X)
        put(AutomaticAccountDetermination(mandt=MANDT, ktopl=KTOPL, ktosl="BIL", bwmod="", komok="X", bklas="", konts="109000"))

        # --- Financial statement version INT ---
        put(FinancialStatementVersion(mandt=MANDT, versn="INT", vstxt="Balance sheet / P&L (international)", ktopl=KTOPL))
        for seqno, (node_id, parent, ergsl, text, kind, sign, ranges) in enumerate(FSV_ITEMS):
            put(FSVNode(mandt=MANDT, versn="INT", id=node_id, parent=parent, ergsl=ergsl, txt45=text,
                            seqno=seqno, kind=kind, sign=sign))
            for vonkt, biskt, soll, haben in ranges:
                put(FSVAccountAssignment(mandt=MANDT, versn="INT", ergsl=ergsl, ktopl=KTOPL,
                                             vonkt=vonkt, biskt=biskt, soll=soll, haben=haben))

        # --- Dunning procedure 0001 (four levels, 14-day interval, 3 grace days) ---
        put(DunningProcedure(mandt=MANDT, mahna="0001", text1="4-level dunning, every 14 days",
                                 rhytm=14, mstuf=4, gracp=3, minbt=Decimal("10.00")))
        for mahns, verzn, text, always, charge in [
            (1, 1, "Payment reminder", False, "0"),
            (2, 15, "Second reminder", False, "5.00"),
            (3, 29, "Final reminder", False, "10.00"),
            (4, 43, "Notice before legal action", True, "25.00"),
        ]:
            put(DunningLevel(mandt=MANDT, mahna="0001", mahns=mahns, verzn=verzn, text1=text, xalwy=always,
                             xzins=mahns >= 2))
            put(DunningCharge(mandt=MANDT, mahna="0001", mahns=mahns, waers="EUR", mahng=Decimal(charge)))

        # Exchange rate differences per open-item / reconciliation account (T030H)
        for hkont, korr in [("140000", "140099"), ("160000", "160099"), ("113109", "140099"), ("113200", "113209")]:
            put(ExchangeDifferenceAccounts(mandt=MANDT, ktopl=KTOPL, hkont=hkont, lsrea="230000", lhrea="280000",
                                               lsbew="230010", lhbew="280010", lkorr=korr))

        # Employee tolerances (T043T): default group and a junior clerk group; user JDOE is a junior
        for togru, betrh, betrp, sktpr, zubet, zuprz in [
            ("", "1000000.00", "500000.00", "5.00", "5.00", "2.00"),
            ("JUNI", "1000.00", "1000.00", "3.00", "1.00", "1.00"),
        ]:
            put(EmployeeTolerance(mandt=MANDT, bukrs=BUKRS, togru=togru, waers="EUR", betrh=Decimal(betrh),
                                  betrp=Decimal(betrp), sktpr=Decimal(sktpr), zubet=Decimal(zubet), zuprz=Decimal(zuprz)))
        put(UserToleranceGroup(mandt=MANDT, usnam="JDOE", bukrs=BUKRS, togru="JUNI"))
        # Reason codes for payment differences; 01 is charged off to bank charges (T030 ZDI, modifier 01)
        put(PaymentDifferenceReason(mandt=MANDT, bukrs=BUKRS, rstgr="01", txt40="Bank charges deducted", xausb=True))
        put(PaymentDifferenceReason(mandt=MANDT, bukrs=BUKRS, rstgr="02", txt40="Price difference", xausb=False))
        put(AutomaticAccountDetermination(mandt=MANDT, ktopl=KTOPL, ktosl="ZDI", bwmod="", komok="01", bklas="",
                                          konts="479000", konth="479000"))

        # Dunning areas and dunning interest (8% p.a., 360 days) for interest indicator 01
        for maber, text in [("01", "Domestic"), ("02", "Export")]:
            put(DunningArea(mandt=MANDT, bukrs=BUKRS, maber=maber, text1=text))
        put(InterestIndicator(mandt=MANDT, vzskz="01", text1="Dunning interest 8%", zbase=360))
        put(InterestRate(mandt=MANDT, vzskz="01", waers="EUR", datab=date(2020, 1, 1), zsoll=Decimal("8.0000")))

        # Default tolerance group: differences up to 2.00 EUR and 1% are posted automatically.
        put(CustomerVendorTolerance(mandt=MANDT, bukrs=BUKRS, togru="", betrh=Decimal("2.00"), prozh=Decimal("1.00"), betrs=Decimal("2.00"), prozs=Decimal("1.00")))

        # --- Demo customer & vendor ---
        put(Customer(mandt=MANDT, kunnr="0000010000", ktokd="KUNA", name1="Alpha Retail GmbH", land1="DE", ort01="Berlin", spras="E", brsch="RETL", kukla="01"))
        put(CustomerCompanyCode(mandt=MANDT, kunnr="0000010000", bukrs=BUKRS, akont="140000", zterm="0001", zuawa="001", zwels="E", vzskz="01"))
        put(CustomerBankDetails(mandt=MANDT, kunnr="0000010000", banks="DE", bankl="30000000", bankn="0555666777", koinh="Alpha Retail GmbH", iban="DE81300000000555666777"))
        # KNB5 holds runtime state (last dunning level/date): create only, never re-merge.
        if s.get(CustomerDunningData, (MANDT, "0000010000", BUKRS, "")) is None:
            put(CustomerDunningData(mandt=MANDT, kunnr="0000010000", bukrs=BUKRS, maber="", mahna="0001"))
        put(SepaMandate(mandt=MANDT, mndid="MND-0000010000-001", snd_type="BUS3007", snd_id="0000010000",
                            snd_name1="Alpha Retail GmbH", snd_iban="DE81300000000555666777", snd_bic="BEDEDEBB",
                            rec_type="BUS0002", rec_id=BUKRS, rec_crdid="DE98ZZZ09999999999", rec_name1="Demo Company AG",
                            sign_date=date(2026, 1, 1), sign_city="Berlin", pay_type="RCUR", status="1"))
        put(Vendor(mandt=MANDT, lifnr="0000020000", ktokk="LIEF", name1="Beta Supplies AG", land1="DE", ort01="Munich", spras="E"))
        put(VendorCompanyCode(mandt=MANDT, lifnr="0000020000", bukrs=BUKRS, akont="160000", zterm="ZB01", zuawa="001", zwels="T"))
        # LFB5 holds runtime state (last dunning level/date): create only, never re-merge.
        if s.get(VendorDunningData, (MANDT, "0000020000", BUKRS, "")) is None:
            put(VendorDunningData(mandt=MANDT, lifnr="0000020000", bukrs=BUKRS, maber="", mahna="0001"))
        put(VendorBankDetails(mandt=MANDT, lifnr="0000020000", banks="DE", bankl="20000000", bankn="0987654321", koinh="Beta Supplies AG", iban="DE84200000000987654321"))
        # Second vendor without bank details: shows up as an F110 exception.
        put(Vendor(mandt=MANDT, lifnr="0000020001", ktokk="LIEF", name1="Gamma Logistics GmbH", land1="DE", ort01="Hamburg", spras="E"))
        put(VendorCompanyCode(mandt=MANDT, lifnr="0000020001", bukrs=BUKRS, akont="160000", zterm="0001", zuawa="001", zwels="TC"))

        # --- Asset Accounting ---
        put(DepreciationArea(mandt=MANDT, afaber="01", afbe_txt="Book depreciation", buhbkt="1"))
        put(AssetClass(mandt=MANDT, anlkl="00003000", txk50="Machinery", ktogr="30000000", num_range="02"))
        put(AssetAccountDetermination(
            mandt=MANDT, ktopl=KTOPL, ktogr="30000000", afaber="01",
            ktansw="011000", ktabg_dep="011010", ktaufw_dep="480000",
            ktvabg="113100", ktgewv="800000", ktverl="480000",
        ))
        for bwasl, txt, grp, anz in [
            ("100", "External asset acquisition", "10", "+"),
            ("200", "Asset retirement with revenue", "20", "-"),
            ("210", "Asset retirement without revenue", "20", "-"),
        ]:
            put(AssetTransactionType(mandt=MANDT, bwasl=bwasl, bwatxt=txt, bwagrp=grp, xanz=anz))

        # --- Bank Accounting ---
        put(Bank(mandt=MANDT, banks="DE", bankl="10000000", banka="Deutsche Demo Bank", ort01="Frankfurt", swift="DEMODEFF"))
        put(HouseBank(mandt=MANDT, bukrs=BUKRS, hbkid="DB", banks="DE", bankl="10000000", swift="DEMODEFF"))
        put(HouseBankAccount(mandt=MANDT, bukrs=BUKRS, hbkid="DB", hktid="GIRO", bankn="123456789", iban="DE91100000000123456789", waers="EUR", hkont="113100"))
        put(Bank(mandt=MANDT, banks="DE", bankl="20000000", banka="Munich Demo Bank", ort01="Munich", swift="MUDEDEMM"))
        put(Bank(mandt=MANDT, banks="DE", bankl="30000000", banka="Berlin Demo Bank", ort01="Berlin", swift="BEDEDEBB"))

        # --- Automatic payment program (F110) ---
        put(PaymentMethod(mandt=MANDT, land1="DE", zlsch="T", text1="Bank transfer (SEPA)", xbkkt=True, blart="ZP", progn="SEPA_CT"))
        put(PaymentMethod(mandt=MANDT, land1="DE", zlsch="E", text1="SEPA direct debit", xeinz=True, blart="ZP", progn="SEPA_DD"))
        put(PaymentMethod(mandt=MANDT, land1="DE", zlsch="C", text1="Check", xschk=True, blart="ZP", progn="CHECK"))
        # Checks: one lot of prenumbered checks; live counter (CHECL) is created, never re-merged
        if s.get(CheckLot, (MANDT, BUKRS, "DB", "GIRO", "0001")) is None:
            put(CheckLot(mandt=MANDT, zbukr=BUKRS, hbkid="DB", hktid="GIRO", stapl="0001",
                         fstap="100001", lstap="100500"))
        put(AvailableAmount(mandt=MANDT, zbukr=BUKRS, hbkid="DB", hktid="GIRO", waers="EUR", bfbet=Decimal("1000000.00")))
        for zlsch in ("T", "E", "C"):
            put(CompanyCodePaymentMethod(mandt=MANDT, zbukr=BUKRS, zlsch=zlsch, minbt=Decimal("1.00")))
            # F110 posts to the bank clearing account; the bank statement later clears it.
            put(BankDetermination(mandt=MANDT, zbukr=BUKRS, zlsch=zlsch, waers="EUR", rangf=1, hbkid="DB", hktid="GIRO", ukont="113109"))

        s.commit()
        print("Seed complete: client 100, company code 1000, chart of accounts INT.")
    finally:
        s.close()


if __name__ == "__main__":
    seed()
