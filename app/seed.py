"""Seed the demo company "Demo Trading Ltd" with a complete, postable B1 setup.

Creates company details (OADM), currencies and exchange rates, monthly posting
periods 2025-2027, numbering series for every document type, tax groups,
payment terms, a chart of accounts tree and the G/L account determination.

Run:  python -m app.seed   (idempotent: master data is merged; runtime state such
as next numbers in NNM1 is created once and never reset)
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from app.database import SessionLocal, init_db
from app.models.admin import (Company, Country, Currency, ExchangeRate, NumberingSeries, PaymentTerms, PostingPeriod,
                              Project, SalesEmployee, State, TaxGroup, TransactionCode)
from app.models.finance import Account, AccountDetermination
from app.models.inventory import Item, ItemGroup, ItemPrice, ItemWarehouse, Manufacturer, PriceList, Warehouse
from app.models.partners import BusinessPartner, ContactPerson, PartnerAddress, PartnerGroup

# Chart of accounts: (code, name, drawer, parent, postable, ActType, control account, cash account)
CHART = [
    ("1", "Assets", 1, None, "N", "N", "N", "N"),
    ("11", "Current Assets", 1, "1", "N", "N", "N", "N"),
    ("111000", "Cash on Hand", 1, "11", "Y", "N", "N", "Y"),
    ("112000", "Bank Account", 1, "11", "Y", "N", "N", "Y"),
    ("114000", "Accounts Receivable", 1, "11", "Y", "N", "Y", "N"),
    ("115000", "Inventory", 1, "11", "Y", "N", "N", "N"),
    ("116000", "Input VAT", 1, "11", "Y", "N", "N", "N"),
    ("117000", "Checks Received", 1, "11", "Y", "N", "N", "N"),
    ("12", "Fixed Assets", 1, "1", "N", "N", "N", "N"),
    ("121000", "Office Equipment", 1, "12", "Y", "N", "N", "N"),
    ("2", "Liabilities", 2, None, "N", "N", "N", "N"),
    ("21", "Current Liabilities", 2, "2", "N", "N", "N", "N"),
    ("211000", "Accounts Payable", 2, "21", "Y", "N", "Y", "N"),
    ("212000", "Goods Received Not Invoiced", 2, "21", "Y", "N", "N", "N"),
    ("216000", "Output VAT", 2, "21", "Y", "N", "N", "N"),
    ("3", "Capital and Reserves", 3, None, "N", "N", "N", "N"),
    ("31", "Equity", 3, "3", "N", "N", "N", "N"),
    ("311000", "Share Capital", 3, "31", "Y", "N", "N", "N"),
    ("312000", "Retained Earnings", 3, "31", "Y", "N", "N", "N"),
    ("313000", "Opening Balances", 3, "31", "Y", "N", "N", "N"),
    ("4", "Turnover", 4, None, "N", "I", "N", "N"),
    ("41", "Sales", 4, "4", "N", "I", "N", "N"),
    ("411000", "Sales Revenue", 4, "41", "Y", "I", "N", "N"),
    ("412000", "Service Revenue", 4, "41", "Y", "I", "N", "N"),
    ("5", "Cost of Sales", 5, None, "N", "E", "N", "N"),
    ("51", "Cost of Goods Sold", 5, "5", "N", "E", "N", "N"),
    ("511000", "Cost of Goods Sold", 5, "51", "Y", "E", "N", "N"),
    ("512000", "Price Differences", 5, "51", "Y", "E", "N", "N"),
    ("513000", "Inventory Adjustments", 5, "51", "Y", "E", "N", "N"),
    ("6", "Operating Costs", 6, None, "N", "E", "N", "N"),
    ("61", "Administrative Expenses", 6, "6", "N", "E", "N", "N"),
    ("611000", "Office Supplies", 6, "61", "Y", "E", "N", "N"),
    ("612000", "Rent", 6, "61", "Y", "E", "N", "N"),
    ("613000", "Bank Charges", 6, "61", "Y", "E", "N", "N"),
    ("7", "Non-Operating Income and Expenditure", 7, None, "N", "N", "N", "N"),
    ("71", "Exchange Differences", 7, "7", "N", "N", "N", "N"),
    ("711000", "Exchange Rate Gains", 7, "71", "Y", "I", "N", "N"),
    ("712000", "Exchange Rate Losses", 7, "71", "Y", "E", "N", "N"),
]

# Object types with their document numbering start (NNM1)
SERIES = {
    "30": ("Primary", 1),          # journal entry
    "23": ("Primary", 1),          # sales quotation (OQUT)
    "17": ("Primary", 1),          # sales order (ORDR)
    "15": ("Primary", 1),          # delivery (ODLN)
    "16": ("Primary", 1),          # sales return (ORDN)
    "13": ("Primary", 1),          # A/R invoice (OINV)
    "14": ("Primary", 1),          # A/R credit memo (ORIN)
    "540000006": ("Primary", 1),   # purchase quotation (OPQT)
    "22": ("Primary", 1),          # purchase order (OPOR)
    "20": ("Primary", 1),          # goods receipt PO (OPDN)
    "21": ("Primary", 1),          # goods return (ORPD)
    "18": ("Primary", 1),          # A/P invoice (OPCH)
    "19": ("Primary", 1),          # A/P credit memo (ORPC)
    "59": ("Primary", 1),          # goods receipt (OIGN)
    "60": ("Primary", 1),          # goods issue (OIGE)
    "67": ("Primary", 1),          # inventory transfer (OWTR)
    "24": ("Primary", 1),          # incoming payment (ORCT)
    "46": ("Primary", 1),          # outgoing payment (OVPM)
}


def seed() -> None:
    init_db()
    s = SessionLocal()

    def put(obj) -> None:
        # reference data without an edit screen: merged on every run. Flush record by record in
        # code order (parents first; PostgreSQL enforces foreign keys)
        s.merge(obj)
        s.flush()

    def put_new(obj, key) -> None:
        # master data users maintain (and runtime state): created once, never overwritten
        if s.get(type(obj), key) is None:
            s.add(obj)
            s.flush()

    try:
        for code, name in COUNTRIES:
            put(Country(code=code, name=name))
        for country, code, name in STATES:
            put(State(country=country, code=code, name=name))
        put_new(Company(code=1, company_name="Demo Trading Ltd", main_curncy="EUR", sys_curncy="USD", country="DE",
                        tax_id="DE123456789", address="Hauptstrasse 1, 69190 Walldorf", phone="+49 6227 0",
                        e_mail="info@demo-trading.example", manager="Max Mustermann"), 1)
        for code, name in [("EUR", "Euro"), ("USD", "US Dollar"), ("GBP", "Pound Sterling")]:
            put(Currency(curr_code=code, curr_name=name, iso=code, decimals=2))
        # Daily rates 2025-2027 (EUR per unit): USD drifts from 0.92 to 0.88, GBP 1.17.
        # Rates are user data: only created when the currency has none yet.
        if s.get(ExchangeRate, (date(2025, 1, 1), "USD")) is None:
            day = date(2025, 1, 1)
            while day <= date(2027, 12, 31):
                usd = Decimal("0.92") - Decimal("0.04") * Decimal((day - date(2025, 1, 1)).days) / Decimal(1095)
                s.add(ExchangeRate(rate_date=day, currency="USD", rate=usd.quantize(Decimal("0.0001"))))
                s.add(ExchangeRate(rate_date=day, currency="GBP", rate=Decimal("1.17")))
                day += timedelta(days=1)
            s.flush()

        entry = 1
        for year in (2025, 2026, 2027):
            for month in range(1, 13):
                last = calendar.monthrange(year, month)[1]
                # the status (lock) is user data: periods are created once, never reset
                put_new(PostingPeriod(abs_entry=entry, code=f"{year}-{month:02d}", name=f"{year}-{month:02d}",
                                      f_ref_date=date(year, month, 1), t_ref_date=date(year, month, last),
                                      f_due_date=date(year, 1, 1), t_due_date=date(year + 1, 12, 31),
                                      f_tax_date=date(year - 1, 1, 1), t_tax_date=date(year, 12, 31),
                                      category=str(year), period_stat="N"), entry)
                period = s.get(PostingPeriod, entry)
                if period.f_due_date is None:  # databases from before the due / document date ranges
                    period.f_due_date, period.t_due_date = date(year, 1, 1), date(year + 1, 12, 31)
                    period.f_tax_date, period.t_tax_date = date(year - 1, 1, 1), date(year, 12, 31)
                entry += 1

        for obj, (name, start) in SERIES.items():  # next numbers are live counters: create only
            if s.get(NumberingSeries, (obj, 1)) is None:
                put(NumberingSeries(object_code=obj, series=1, series_name=name, initial_num=start,
                                    next_number=start, last_num=None, is_default=True))

        for code, name, parent_drawer, parent, postable, act_type, control, cash in CHART:
            put_new(Account(acct_code=code, acct_name=name, group_mask=parent_drawer, father_num=parent,
                            levels=1 if parent is None else (2 if len(parent) == 1 else 3), postable=postable,
                            act_type=act_type, loc_man_tran=control, finanse=cash), code)

        for code, name, category, rate, account in [
            ("O1", "Output VAT 19%", "O", "19", "216000"), ("O2", "Output VAT 7%", "O", "7", "216000"),
            ("O0", "Output VAT exempt", "O", "0", "216000"),
            ("I1", "Input VAT 19%", "I", "19", "116000"), ("I2", "Input VAT 7%", "I", "7", "116000"),
            ("I0", "Input VAT exempt", "I", "0", "116000"),
        ]:
            put(TaxGroup(code=code, name=name, category=category, rate=Decimal(rate), account=account))
        for num, name, start, months, days in [(-1, "Cash Basic", "N", 0, 0), (1, "Net 30", "N", 0, 30),
                                               (2, "Net 60", "N", 0, 60), (3, "End of next month", "E", 1, 0)]:
            put_new(PaymentTerms(group_num=num, pymnt_group=name, bsline_date="P", pay_du_month=start,
                                 extra_month=months, extra_days=days), num)
        eom = s.get(PaymentTerms, 3)
        if eom.pymnt_group == "End of next month" and eom.pay_du_month == "N":  # before "start from" existed
            eom.pay_du_month = "E"
        for code, name in [(-1, "-No Sales Employee-"), (1, "Jane Miller"), (2, "Tom Baker"), (3, "Lisa Wong")]:
            put_new(SalesEmployee(slp_code=code, slp_name=name, commission=Decimal("0"), active="Y"), code)
        for code, name in [("P001", "Website relaunch"), ("P002", "Berlin outlet opening")]:
            put_new(Project(prj_code=code, prj_name=name, active="Y"), code)
        for code, name in [("OB", "Opening balance"), ("AD", "Adjustment"), ("AC", "Accrual")]:
            put_new(TransactionCode(trns_code=code, trns_cod_dsc=name), code)
        for code, name in [(-1, "- No Manufacturer -"), (1, "J.B. Printing Systems"), (2, "Rainbow Imaging")]:
            put_new(Manufacturer(firm_code=code, firm_name=name), code)
        for year in ("2025", "2026", "2027"):
            put(AccountDetermination(
                period_cat=year, ar_control="114000", ap_control="211000", revenue="411000", cogs="511000",
                inventory="115000", allocation="212000", price_diff="512000", expense="611000",
                inv_offset_inc="513000", inv_offset_dec="513000", exch_gain="711000", exch_loss="712000",
                opening_bal="313000"))
        _seed_partners_and_items(s, put)
        s.commit()
        print("Seed complete: Demo Trading Ltd (EUR), chart of accounts, periods 2025-2027, "
              "business partners, items and warehouses.")
    finally:
        s.close()


# Business partners: (code, name, type, group, payment terms, price list, tax group, city, contact,
#                     sales employee, street, zip, state, phone)
PARTNERS = [
    ("C10000", "Maxi Teq Retail GmbH", "C", 100, 1, 1, "O1", "Berlin", "Anna Schmidt", 1, "Friedrichstrasse 20", "10117", "BE", "+49 30 1234"),
    ("C20000", "Earthshaker Corporation", "C", 100, 2, 2, "O1", "Hamburg", "Tom Becker", 2, "Jungfernstieg 4", "20354", "HH", "+49 40 5678"),
    ("C30000", "Northwind Wholesale", "C", 101, 1, 2, "O1", "Munich", None, 1, "Leopoldstrasse 8", "80802", "BY", "+49 89 9012"),
    ("V10000", "Acme Supplies AG", "S", 102, 1, 3, "I1", "Frankfurt", "Lena Fischer", 3, "Zeil 100", "60313", "HE", "+49 69 3456"),
    ("V20000", "Office World Ltd", "S", 102, 3, 3, "I1", "Cologne", None, 3, "Hohe Strasse 50", "50667", "NW", "+49 221 7890"),
]

# Items: (code, name, group, inventory item, unit, sales tax, purchase tax, base price, purchase price, vendor,
#         manufacturer, bar code)
ITEMS = [
    ("A00001", "J.B. Officeprint 1420", 100, True, "Each", "O1", "I1", "400", "250", "V10000", 1, "4006381333931"),
    ("A00002", "J.B. Officeprint 1111", 100, True, "Each", "O1", "I1", "300", "180", "V10000", 1, "4006381333948"),
    ("A00003", "J.B. Officeprint 1186", 100, True, "Each", "O1", "I1", "500", "320", "V10000", 1, "4006381333955"),
    ("A00004", "Rainbow Color Printer 7.5", 100, True, "Each", "O1", "I1", "650", "410", "V10000", 2, "4006381333962"),
    ("C00001", "Toner cartridge black", 101, True, "Box", "O1", "I1", "45", "22", "V20000", -1, None),
    ("C00002", "Paper A4, 500 sheets", 101, True, "Pack", "O2", "I2", "6", "3.5", "V20000", -1, None),
    ("S00001", "Installation service (hour)", 102, False, "Hour", "O1", "I1", "90", None, None, -1, None),
]


COUNTRIES = [("AT", "Austria"), ("BE", "Belgium"), ("CH", "Switzerland"), ("DE", "Germany"), ("DK", "Denmark"),
             ("ES", "Spain"), ("FR", "France"), ("GB", "United Kingdom"), ("IN", "India"), ("IT", "Italy"),
             ("NL", "Netherlands"), ("PL", "Poland"), ("SE", "Sweden"), ("US", "United States")]
STATES = [("DE", code, name) for code, name in [
    ("BW", "Baden-Wuerttemberg"), ("BY", "Bavaria"), ("BE", "Berlin"), ("BB", "Brandenburg"), ("HB", "Bremen"),
    ("HH", "Hamburg"), ("HE", "Hesse"), ("MV", "Mecklenburg-Western Pomerania"), ("NI", "Lower Saxony"),
    ("NW", "North Rhine-Westphalia"), ("RP", "Rhineland-Palatinate"), ("SL", "Saarland"), ("SN", "Saxony"),
    ("ST", "Saxony-Anhalt"), ("SH", "Schleswig-Holstein"), ("TH", "Thuringia")]] + [
    ("US", code, name) for code, name in [("CA", "California"), ("FL", "Florida"), ("IL", "Illinois"),
                                          ("NY", "New York"), ("TX", "Texas"), ("WA", "Washington")]]


def _seed_partners_and_items(s, put) -> None:
    for code, name, kind in [(100, "Customers", "C"), (101, "Wholesale", "C"), (102, "Vendors", "S")]:
        put(PartnerGroup(group_code=code, group_name=name, group_type=kind))
    # price lists: 1 base price, 2 wholesale = 90 % of base, 3 purchase price (own list)
    put_new = lambda obj, key: (s.add(obj), s.flush()) if s.get(type(obj), key) is None else None  # noqa: E731
    for num, name, base, factor in [(1, "Base Price", 1, "1"), (2, "Wholesale", 1, "0.9"), (3, "Purchase Price", 3, "1")]:
        put_new(PriceList(list_num=num, list_name=name, base_num=base, factor=Decimal(factor), prim_curr="EUR",
                          valid_for="Y"), num)
    for code, name, street, zip_code, city, state in [
            ("01", "General Warehouse", "Industriestrasse 5", "69190", "Walldorf", "BW"),
            ("02", "Outlet Berlin", "Unter den Linden 10", "10117", "Berlin", "BE")]:
        put_new(Warehouse(whs_code=code, whs_name=name, street=street, zip_code=zip_code, city=city, state=state,
                          country="DE", drop_ship="N", nettable="Y", inactive="N"), code)
    for code, name, inv, cogs, rev, exp in [(100, "Printers", "115000", "511000", "411000", "611000"),
                                             (101, "Supplies", "115000", "511000", "411000", "611000"),
                                             (102, "Services", "115000", "511000", "412000", "611000")]:
        put(ItemGroup(itms_grp_cod=code, itms_grp_nam=name, bal_invnt_ac=inv, sale_cost_ac=cogs, revenues_ac=rev,
                      expenses_ac=exp, price_dif_ac="512000"))

    # partner balances, item stock and cost are runtime state: create only, never re-merge
    contact = 1
    for code, name, kind, group, terms, plist, vat, city, person, slp, street, zip_code, state, phone in PARTNERS:
        if s.get(BusinessPartner, code) is None:
            put(BusinessPartner(card_code=code, card_name=name, card_type=kind, group_code=group, currency="##",
                                deb_pay_acct="211000" if kind == "S" else "114000", group_num=terms, list_num=plist,
                                vat_group=vat, address=street, zip_code=zip_code, city=city, country="DE",
                                cntct_prsn=person, slp_code=slp, phone1=phone,
                                credit_line=Decimal("20000") if kind == "C" else Decimal("0"),
                                balance=Decimal("0"), dnotes_bal=Decimal("0"), orders_bal=Decimal("0"), frozen_for="N"))
            if person:
                first, last = person.split(" ", 1)
                put(ContactPerson(cntct_code=contact, card_code=code, name=person, first_name=first, last_name=last,
                                  position="Purchasing" if kind == "C" else "Sales", tel1=phone, active="Y"))
        contact += 1
        bp = s.get(BusinessPartner, code)
        for adres_type in ("B", "S"):  # bill-to and ship-to addresses (CRD1), created once
            if s.get(PartnerAddress, (code, adres_type, "Main")) is None:
                s.add(PartnerAddress(card_code=code, adres_type=adres_type, address="Main", street=street,
                                     zip_code=zip_code, city=city, state=state, country="DE"))
                s.flush()
        bp.bill_to_def = bp.bill_to_def or "Main"
        bp.ship_to_def = bp.ship_to_def or "Main"
        if bp.slp_code is None:
            bp.slp_code = slp
    for code, name, group, inv, uom, vat_sa, vat_pu, price, pur, vendor, firm, bars in ITEMS:
        if s.get(Item, code) is None:
            put(Item(item_code=code, item_name=name, itms_grp_cod=group, invnt_item="Y" if inv else "N",
                     sell_item="Y", prchse_item="Y" if inv else "N", eval_system="A", gl_method="C", invntry_uom=uom,
                     vat_gourp_sa=vat_sa, vat_group_pu=vat_pu, dflt_wh="01" if inv else None, card_code=vendor,
                     min_level=Decimal("5") if inv else Decimal("0"), on_hand=Decimal("0"), is_commited=Decimal("0"),
                     on_order=Decimal("0"), avg_price=Decimal("0"), stock_value=Decimal("0"), last_pur_prc=Decimal("0"),
                     frozen_for="N", item_type="I" if inv else "L", firm_code=firm, code_bars=bars,
                     buy_unit_msr=uom, sal_unit_msr=uom, max_level=Decimal("50") if inv else Decimal("0"),
                     reorder_qty=Decimal("10") if inv else Decimal("0"), lead_time=7 if inv else None))
        if inv:
            for whs in ("01", "02"):
                if s.get(ItemWarehouse, (code, whs)) is None:
                    put(ItemWarehouse(item_code=code, whs_code=whs))
        for plist, amount in [(1, price), (3, pur)]:  # prices are maintained by users: create only
            if amount and s.get(ItemPrice, (code, plist)) is None:
                put(ItemPrice(item_code=code, price_list=plist, price=Decimal(amount), currency="EUR"))


if __name__ == "__main__":
    seed()
