"""Seed the demo company "Demo Trading India Pvt Ltd" with a complete, postable B1 setup.

An Indian company in Bengaluru (Karnataka) with INR as local currency and USD, EUR,
GBP as foreign currencies: company details (OADM) with GSTIN and state, exchange
rates, monthly posting periods 2025-2027, numbering series, GST tax codes made of
CGST / SGST / IGST components (OVTG + STC1, tax authorities OSTA), payment terms,
an Indian chart of accounts, the G/L account determination, business partners with
GSTINs in several states, items with HSN / SAC codes and INR prices.

Run:  python -m app.seed   (runs on every start: data users maintain is created once and
never overwritten; reference data without an edit screen is merged)
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from app.database import SessionLocal, init_db
from app.models.admin import (CashDiscount, CashDiscountLine, DunningLevel, DunningTerm, Company, Country, Currency, ExchangeRate, HsnCode,
                              NumberingSeries, PaymentTerms, PaymentTermsInstallment, PostingPeriod, Project, SalesEmployee, State, TaxAuthority, TaxComponent, TaxDetermination,
                              TaxGroup, TaxType, TransactionCode)
from app.models.banking import Bank, HouseBankAccount
from app.models.finance import Account, AccountDetermination
from app.models.inventory import Item, ItemGroup, ItemPrice, ItemWarehouse, Manufacturer, PriceList, Warehouse
from app.models.partners import BusinessPartner, ContactPerson, PartnerAddress, PartnerGroup

LOCAL = "INR"

# Chart of accounts: (code, name, drawer, parent, postable, ActType, control account, cash account)
CHART = [
    ("1", "Assets", 1, None, "N", "N", "N", "N"),
    ("11", "Current Assets", 1, "1", "N", "N", "N", "N"),
    ("111000", "Cash-in-Hand", 1, "11", "Y", "N", "N", "Y"),
    ("112000", "Bank Account - HDFC Bank", 1, "11", "Y", "N", "N", "Y"),
    ("114000", "Sundry Debtors", 1, "11", "Y", "N", "Y", "N"),
    ("115000", "Stock-in-Trade", 1, "11", "Y", "N", "N", "N"),
    ("116000", "Input Tax (other)", 1, "11", "Y", "N", "N", "N"),
    ("116100", "Input CGST", 1, "11", "Y", "N", "N", "N"),
    ("116200", "Input SGST", 1, "11", "Y", "N", "N", "N"),
    ("116300", "Input IGST", 1, "11", "Y", "N", "N", "N"),
    ("117000", "Cheques Received", 1, "11", "Y", "N", "N", "N"),
    ("12", "Fixed Assets", 1, "1", "N", "N", "N", "N"),
    ("121000", "Office Equipment", 1, "12", "Y", "N", "N", "N"),
    ("2", "Liabilities", 2, None, "N", "N", "N", "N"),
    ("21", "Current Liabilities", 2, "2", "N", "N", "N", "N"),
    ("211000", "Sundry Creditors", 2, "21", "Y", "N", "Y", "N"),
    ("212000", "Goods Received Not Invoiced", 2, "21", "Y", "N", "N", "N"),
    ("216000", "Output Tax (other)", 2, "21", "Y", "N", "N", "N"),
    ("216100", "Output CGST", 2, "21", "Y", "N", "N", "N"),
    ("216200", "Output SGST", 2, "21", "Y", "N", "N", "N"),
    ("216300", "Output IGST", 2, "21", "Y", "N", "N", "N"),
    ("217000", "TDS Payable", 2, "21", "Y", "N", "N", "N"),
    ("3", "Capital and Reserves", 3, None, "N", "N", "N", "N"),
    ("31", "Shareholders' Funds", 3, "3", "N", "N", "N", "N"),
    ("311000", "Share Capital", 3, "31", "Y", "N", "N", "N"),
    ("312000", "Reserves and Surplus", 3, "31", "Y", "N", "N", "N"),
    ("313000", "Opening Balance Difference", 3, "31", "Y", "N", "N", "N"),
    ("4", "Revenue from Operations", 4, None, "N", "I", "N", "N"),
    ("41", "Sales", 4, "4", "N", "I", "N", "N"),
    ("411000", "Sales - Goods", 4, "41", "Y", "I", "N", "N"),
    ("412000", "Sales - Services", 4, "41", "Y", "I", "N", "N"),
    ("5", "Cost of Sales", 5, None, "N", "E", "N", "N"),
    ("51", "Cost of Goods Sold", 5, "5", "N", "E", "N", "N"),
    ("511000", "Cost of Goods Sold", 5, "51", "Y", "E", "N", "N"),
    ("512000", "Purchase Price Variance", 5, "51", "Y", "E", "N", "N"),
    ("513000", "Stock Adjustments", 5, "51", "Y", "E", "N", "N"),
    ("6", "Operating Expenses", 6, None, "N", "E", "N", "N"),
    ("61", "Administrative Expenses", 6, "6", "N", "E", "N", "N"),
    ("611000", "Office Expenses", 6, "61", "Y", "E", "N", "N"),
    ("612000", "Rent", 6, "61", "Y", "E", "N", "N"),
    ("613000", "Bank Charges", 6, "61", "Y", "E", "N", "N"),
    ("615000", "Cash Discount Allowed", 6, "61", "Y", "E", "N", "N"),
    ("7", "Other Income and Expenses", 7, None, "N", "N", "N", "N"),
    ("71", "Foreign Exchange", 7, "7", "N", "N", "N", "N"),
    ("711000", "Foreign Exchange Gain", 7, "71", "Y", "I", "N", "N"),
    ("712000", "Foreign Exchange Loss", 7, "71", "Y", "E", "N", "N"),
    ("713000", "Unrealized Exchange Gain", 7, "71", "Y", "I", "N", "N"),
    ("714000", "Unrealized Exchange Loss", 7, "71", "Y", "E", "N", "N"),
    ("72", "Other Income", 7, "7", "N", "I", "N", "N"),
    ("721000", "Interest Income", 7, "72", "Y", "I", "N", "N"),
    ("722000", "Cash Discount Received", 7, "72", "Y", "I", "N", "N"),
    ("723000", "Dunning Fees", 7, "72", "Y", "I", "N", "N"),
]

# GST tax authorities (OSTA): code, name, output account, input account
TAX_AUTHORITIES = [("CGST", "Central GST", "216100", "116100"), ("SGST", "State GST", "216200", "116200"),
                   ("IGST", "Integrated GST", "216300", "116300")]
GST_RATES = ["5", "12", "18", "28"]

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
    "25": ("Primary", 1),          # deposit (ODPS)
}


def _gst_tax_groups() -> list[tuple[str, str, str, Decimal, str, list[tuple[str, Decimal]]]]:
    """(code, name, category, rate, account, components): OCS18 = output CGST 9 % + SGST 9 %, OIG18 = IGST 18 % ..."""
    out = []
    for cat, prefix, label, other in (("O", "O", "Out", "216000"), ("I", "I", "In", "116000")):
        for r in GST_RATES:
            rate, half = Decimal(r), Decimal(r) / 2
            h = f"{half.normalize():f}"  # names fit OVTG.Name (30 characters)
            out.append((f"{prefix}CS{r}", f"{label} GST {r}% (CGST {h}+SGST {h})", cat,
                        rate, other, [("CGST", half), ("SGST", half)]))
            out.append((f"{prefix}IG{r}", f"{label} IGST {r}%", cat, rate, other, [("IGST", rate)]))
        out.append((f"{prefix}NIL", f"{label} GST nil / exempt", cat, Decimal("0"), other, []))
    return out


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
        for country, code, name, gst in STATES:
            put(State(country=country, code=code, name=name, gst_code=gst))
        put_new(Company(code=1, company_name="Demo Trading India Pvt Ltd", main_curncy=LOCAL, sys_curncy="USD",
                        country="IN", state="KA", tax_id="29AAACD1234E1Z5",
                        address="42 MG Road, Bengaluru 560001, Karnataka", phone="+91 80 4000 1234",
                        e_mail="accounts@demotrading.example.in", manager="Rahul Mehta"), 1)
        for code, name in [(LOCAL, "Indian Rupee"), ("USD", "US Dollar"), ("EUR", "Euro"), ("GBP", "Pound Sterling")]:
            put(Currency(curr_code=code, curr_name=name, iso=code, decimals=2))
        # Daily rates 2025-2027 (INR per unit): USD 83.00 -> 86.00, EUR 90.50 -> 93.00, GBP 105.20.
        # Rates are user data: only created when the currency has none yet.
        if s.get(ExchangeRate, (date(2025, 1, 1), "USD")) is None:
            day = date(2025, 1, 1)
            while day <= date(2027, 12, 31):
                share = Decimal((day - date(2025, 1, 1)).days) / Decimal(1095)
                s.add(ExchangeRate(rate_date=day, currency="USD", rate=(Decimal("83") + 3 * share).quantize(Decimal("0.0001"))))
                s.add(ExchangeRate(rate_date=day, currency="EUR", rate=(Decimal("90.5") + Decimal("2.5") * share).quantize(Decimal("0.0001"))))
                s.add(ExchangeRate(rate_date=day, currency="GBP", rate=Decimal("105.2")))
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

        # tax setup is maintained by users (Administration -> Tax setup): created once, never overwritten
        for code, name, _, _ in TAX_AUTHORITIES:
            put_new(TaxType(code=code, name=name), code)
        for code, name, sales, purch in TAX_AUTHORITIES:
            put_new(TaxAuthority(code=code, name=name, type=code, sales_tax=sales, purch_tax=purch), code)
        for code, name, category, rate, account, comps in _gst_tax_groups():
            if s.get(TaxGroup, code) is None:
                put(TaxGroup(code=code, name=name, category=category, rate=rate, account=account))
                for line, (authority, comp_rate) in enumerate(comps):
                    put(TaxComponent(stc_code=code, line=line, sta_code=authority, efctiv_rate=comp_rate))
        for n, (chapter, descr, kind) in enumerate(HSN_CODES, start=1):
            put_new(HsnCode(abs_entry=n, chapter_id=chapter, dscription=descr, item_type=kind), n)
        # example determination: paper (HSN 4802) is taxed at 12 % in sales and purchasing
        for n, area, code in [(1, "S", "OCS12"), (2, "P", "ICS12")]:
            put_new(TaxDetermination(abs_id=n, priority=10, doc_area=area, chapter_id="48025690", tax_code=code,
                                     descr="Paper: GST 12 %", active="Y"), n)
        for num, name, start, months, days in [(-1, "Cash Basic", "N", 0, 0), (1, "Net 30", "N", 0, 30),
                                               (2, "Net 60", "N", 0, 60), (3, "End of next month", "E", 1, 0)]:
            put_new(PaymentTerms(group_num=num, pymnt_group=name, bsline_date="P", pay_du_month=start,
                                 extra_month=months, extra_days=days), num)
        # cash discount 2 % within 10 days, 1 % within 20 days; terms with it and with 3 installments
        if s.get(CashDiscount, "2-10") is None:
            put(CashDiscount(code="2-10", name="2% 10 days, 1% 20 days", by_date="N"))
            put(CashDiscountLine(cdc_code="2-10", line_id=1, num_of_days=10, discount=Decimal("2")))
            put(CashDiscountLine(cdc_code="2-10", line_id=2, num_of_days=20, discount=Decimal("1")))
        put_new(PaymentTerms(group_num=4, pymnt_group="2% 10 / 1% 20, net 30", bsline_date="P", pay_du_month="N",
                             extra_month=0, extra_days=30, cdc_code="2-10"), 4)
        if s.get(PaymentTerms, 5) is None:
            put(PaymentTerms(group_num=5, pymnt_group="3 installments 30/60/90", bsline_date="P", pay_du_month="N",
                             extra_month=0, extra_days=30, inst_num=3))
            for n, (days, pct) in enumerate([(30, "33.33"), (60, "33.33"), (90, "33.34")], start=1):
                put(PaymentTermsInstallment(ctg_code=5, ints_no=n, inst_month=0, inst_days=days, inst_prcnt=Decimal(pct)))
        # dunning: friendly reminder after 7 days, 2nd after 30 days (fee 250), final after 60 days (fee 500)
        if s.get(DunningTerm, "STD") is None:
            put(DunningTerm(code="STD", name="Standard dunning", interest=Decimal("18"), highest="N", days_between=7))
            for lvl, days, fee, text in [
                    (1, 7, "0", "This is a friendly reminder that the items below are overdue. Please arrange payment."),
                    (2, 30, "250", "Despite our reminder the items below are still unpaid. Please pay within 7 days."),
                    (3, 60, "500", "Final notice: unless the items below are paid within 7 days we will take further steps.")]:
                put(DunningLevel(term_code="STD", level=lvl, days=days, fee=Decimal(fee), min_balance=Decimal("100"),
                                 letter_text=text))
        eom = s.get(PaymentTerms, 3)
        if eom.pymnt_group == "End of next month" and eom.pay_du_month == "N":  # before "start from" existed
            eom.pay_du_month = "E"
        for code, name in [(-1, "-No Sales Employee-"), (1, "Anita Desai"), (2, "Vikram Singh"), (3, "Neha Gupta")]:
            put_new(SalesEmployee(slp_code=code, slp_name=name, commission=Decimal("0"), active="Y"), code)
        for code, name in [("P001", "Website relaunch"), ("P002", "Mumbai outlet opening")]:
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
                opening_bal="313000", bank_charges="613000", checks_received="117000", unreal_gain="713000",
                unreal_loss="714000", cash_disc_allowed="615000", cash_disc_received="722000",
                dunning_interest="721000", dunning_fee="723000"))
        put_new(Bank(abs_entry=1, bank_code="HDFC", bank_name="HDFC Bank Ltd", country_cod="IN", swift_num="HDFCINBB"), 1)
        put_new(HouseBankAccount(abs_entry=1, bank_code="HDFC", account="50100123456789", branch="HDFC0000123",
                                 gl_account="112000", acct_name="HDFC current account", country="IN", currency=LOCAL), 1)
        _seed_users(s)
        _seed_print_layouts(s)
        _seed_withholding(s)
        from app.models.admin import CompanyAddress

        put_new(CompanyAddress(code=1, street="42 MG Road", city="Bengaluru", zip_code="560001"), 1)
        _seed_partners_and_items(s, put)
        s.commit()
        print("Seed complete: Demo Trading India Pvt Ltd (INR, GST), chart of accounts, periods 2025-2027, "
              "business partners, items and warehouses.")
    finally:
        s.close()


# Business partners: (code, name, type, group, payment terms, price list, tax group, city, contact,
#                     sales employee, street, zip, state, phone, GSTIN)
PARTNERS = [
    ("C10000", "Maxi Teq Retail Pvt Ltd", "C", 100, 1, 1, "OCS18", "Bengaluru", "Priya Sharma", 1,
     "12 Residency Road", "560025", "KA", "+91 80 2222 1234", "29AABCM1234F1Z1"),
    ("C20000", "Earthshaker Industries Ltd", "C", 100, 2, 2, "OCS18", "Mumbai", "Arjun Patel", 2,
     "Nariman Point 7", "400021", "MH", "+91 22 6666 5678", "27AACCE5678G1Z3"),
    ("C30000", "Northwind Wholesale", "C", 101, 1, 2, "OCS18", "Chennai", None, 1,
     "Anna Salai 88", "600002", "TN", "+91 44 4444 9012", "33AADCN9012H1Z7"),
    ("V10000", "Acme Supplies Pvt Ltd", "S", 102, 1, 3, "ICS18", "Bengaluru", "Kavita Rao", 3,
     "Peenya Industrial Area 4", "560058", "KA", "+91 80 3333 3456", "29AAECA3456J1Z2"),
    ("V20000", "Office World India", "S", 102, 3, 3, "ICS18", "New Delhi", None, 3,
     "Connaught Place 21", "110001", "DL", "+91 11 5555 7890", "07AAFCO7890K1Z9"),
]

# Items: (code, name, group, inventory item, unit, sales tax, purchase tax, base price, purchase price, vendor,
#         manufacturer, bar code, HSN / SAC)
ITEMS = [
    ("A00001", "J.B. Officeprint 1420", 100, True, "Each", "OCS18", "ICS18", "35000", "22000", "V10000", 1, "8901234500011", "84433210"),
    ("A00002", "J.B. Officeprint 1111", 100, True, "Each", "OCS18", "ICS18", "26000", "15500", "V10000", 1, "8901234500028", "84433210"),
    ("A00003", "J.B. Officeprint 1186", 100, True, "Each", "OCS18", "ICS18", "42000", "27000", "V10000", 1, "8901234500035", "84433210"),
    ("A00004", "Rainbow Color Printer 7.5", 100, True, "Each", "OCS18", "ICS18", "55000", "35000", "V10000", 2, "8901234500042", "84433100"),
    ("C00001", "Toner cartridge black", 101, True, "Box", "OCS18", "ICS18", "3800", "1900", "V20000", -1, None, "84439951"),
    ("C00002", "Paper A4, 500 sheets", 101, True, "Pack", "OCS12", "ICS12", "500", "300", "V20000", -1, None, "48025690"),
    ("S00001", "Installation service (hour)", 102, False, "Hour", "OCS18", "ICS18", "1500", None, None, -1, None, "998713"),
]


# HSN (goods) / SAC (services) codes: (code, description, I goods / S services)
HSN_CODES = [("84433210", "Printers, laser, connectable to a computer", "I"),
             ("84433100", "Multifunction printers (print, copy, scan)", "I"),
             ("84439951", "Toner cartridges", "I"),
             ("48025690", "Paper, uncoated, for writing / printing (A4)", "I"),
             ("998713", "Maintenance and repair of computers and peripherals", "S")]

COUNTRIES = [("AE", "United Arab Emirates"), ("AT", "Austria"), ("BE", "Belgium"), ("CH", "Switzerland"),
             ("DE", "Germany"), ("ES", "Spain"), ("FR", "France"), ("GB", "United Kingdom"), ("IN", "India"),
             ("IT", "Italy"), ("JP", "Japan"), ("NL", "Netherlands"), ("SG", "Singapore"), ("US", "United States")]
# (country, state code, name, GST state code)
STATES = [("IN", code, name, gst) for code, name, gst in [
    ("JK", "Jammu and Kashmir", "01"), ("HP", "Himachal Pradesh", "02"), ("PB", "Punjab", "03"),
    ("CH", "Chandigarh", "04"), ("UK", "Uttarakhand", "05"), ("HR", "Haryana", "06"), ("DL", "Delhi", "07"),
    ("RJ", "Rajasthan", "08"), ("UP", "Uttar Pradesh", "09"), ("BR", "Bihar", "10"), ("SK", "Sikkim", "11"),
    ("AR", "Arunachal Pradesh", "12"), ("NL", "Nagaland", "13"), ("MN", "Manipur", "14"), ("MZ", "Mizoram", "15"),
    ("TR", "Tripura", "16"), ("ML", "Meghalaya", "17"), ("AS", "Assam", "18"), ("WB", "West Bengal", "19"),
    ("JH", "Jharkhand", "20"), ("OD", "Odisha", "21"), ("CG", "Chhattisgarh", "22"), ("MP", "Madhya Pradesh", "23"),
    ("GJ", "Gujarat", "24"), ("DN", "Dadra and Nagar Haveli and Daman and Diu", "26"), ("MH", "Maharashtra", "27"),
    ("KA", "Karnataka", "29"), ("GA", "Goa", "30"), ("LD", "Lakshadweep", "31"), ("KL", "Kerala", "32"),
    ("TN", "Tamil Nadu", "33"), ("PY", "Puducherry", "34"), ("AN", "Andaman and Nicobar Islands", "35"),
    ("TS", "Telangana", "36"), ("AP", "Andhra Pradesh", "37"), ("LA", "Ladakh", "38")]] + [
    ("US", code, name, None) for code, name in [("CA", "California"), ("FL", "Florida"), ("IL", "Illinois"),
                                                ("NY", "New York"), ("TX", "Texas"), ("WA", "Washington")]] + [
    ("DE", code, name, None) for code, name in [("BE", "Berlin"), ("BY", "Bavaria"), ("HH", "Hamburg"),
                                                ("NW", "North Rhine-Westphalia")]]


def _seed_users(s) -> None:
    """manager (superuser) and two demo users; created once. Initial passwords from the
    environment (B1_MANAGER_PASSWORD, default "manager"); change them after the first login."""
    import os

    from app.models.users import User, UserPermission
    from app.services.auth import PERMISSIONS, hash_password

    users = [(1, "manager", "Manager", "Y", os.environ.get("B1_MANAGER_PASSWORD", "manager"), {}),
             (2, "sales", "Sales clerk", "N", os.environ.get("B1_DEMO_PASSWORD", "sales2026"),
              {"SALES": "F", "BP": "F", "ITEMS": "R", "INV": "R", "COCKPIT": "F", "DUNNING": "R"}),
             (3, "accountant", "Accountant", "N", os.environ.get("B1_DEMO_PASSWORD", "account2026"),
              {"COA": "F", "JE": "F", "FINRPT": "F", "BANK": "F", "FXREVAL": "F", "DUNNING": "F", "BP": "R",
               "SALES": "R", "PURCH": "R", "INV": "R", "ITEMS": "R", "COCKPIT": "F"})]
    for uid, code, name, sup, pwd, perms in users:
        if s.get(User, uid) is None:
            s.add(User(user_id=uid, user_code=code, u_name=name, superuser=sup, locked="N", password=hash_password(pwd)))
            s.flush()
            for perm in PERMISSIONS:
                s.add(UserPermission(user_link=uid, perm_id=perm, permission=perms.get(perm, "N") if sup == "N" else "F"))
            s.flush()


def _seed_withholding(s) -> None:
    """TDS sections (rates and thresholds of FY 2025-26) as withholding tax codes; created once."""
    from app.models.admin import WithholdingTax

    for code, name, section, rate, single, annual, typ in [
            ("C1", "Contractors - individual / HUF", "194C", "1", "30000", "100000", "A"),
            ("C2", "Contractors - others", "194C", "2", "30000", "100000", "A"),
            ("H", "Commission / brokerage", "194H", "2", "0", "20000", "A"),
            ("I1", "Rent - plant and machinery", "194I(a)", "2", "50000", "0", "A"),
            ("I2", "Rent - land, building, furniture", "194I(b)", "10", "50000", "0", "A"),
            ("J1", "Fees for technical services", "194J(a)", "2", "0", "50000", "A"),
            ("J2", "Fees for professional services", "194J(b)", "10", "0", "50000", "A"),
            ("Q", "Purchase of goods", "194Q", "0.1", "0", "5000000", "E")]:
        if s.get(WithholdingTax, code) is None:
            s.add(WithholdingTax(wt_code=code, wt_name=name, section=section, rate=Decimal(rate), thr_single=Decimal(single),
                                 thr_annual=Decimal(annual), thr_type=typ, rate_no_pan=Decimal("20"), account="217000",
                                 category="I", base_type="N", inactive="N"))
            s.flush()


def _seed_print_layouts(s) -> None:
    """A standard (classic GST) default layout per sales / purchasing document type; layouts are
    maintained by users (Administration -> Print layouts): created only for types without one."""
    from sqlalchemy import select

    from app.models.admin import PrintLayout
    from app.services.printing import TITLES

    for obj in TITLES:
        if s.scalar(select(PrintLayout).where(PrintLayout.type_code == obj).limit(1)) is None:
            s.add(PrintLayout(doc_code=f"STD-{obj}", doc_name="Standard (GST)", type_code=obj, style="classic",
                              color="#1f3b63", show_logo="Y", show_hsn="Y", show_bank="Y", show_sign="Y",
                              footer="Subject to local jurisdiction. E. & O.E." if obj == "13" else None, default="Y"))
            s.flush()


def _seed_partners_and_items(s, put) -> None:
    for code, name, kind in [(100, "Customers", "C"), (101, "Wholesale", "C"), (102, "Vendors", "S")]:
        put(PartnerGroup(group_code=code, group_name=name, group_type=kind))
    # price lists: 1 base price, 2 wholesale = 90 % of base, 3 purchase price (own list)
    put_new = lambda obj, key: (s.add(obj), s.flush()) if s.get(type(obj), key) is None else None  # noqa: E731
    for num, name, base, factor in [(1, "Base Price", 1, "1"), (2, "Wholesale", 1, "0.9"), (3, "Purchase Price", 3, "1")]:
        put_new(PriceList(list_num=num, list_name=name, base_num=base, factor=Decimal(factor), prim_curr=LOCAL,
                          valid_for="Y"), num)
    for code, name, street, zip_code, city, state in [
            ("01", "Bengaluru Main Warehouse", "Peenya Industrial Area, Phase 2", "560058", "Bengaluru", "KA"),
            ("02", "Mumbai Outlet", "Andheri East, MIDC", "400093", "Mumbai", "MH")]:
        put_new(Warehouse(whs_code=code, whs_name=name, street=street, zip_code=zip_code, city=city, state=state,
                          country="IN", drop_ship="N", nettable="Y", inactive="N"), code)
    for code, name, inv, cogs, rev, exp in [(100, "Printers", "115000", "511000", "411000", "611000"),
                                             (101, "Supplies", "115000", "511000", "411000", "611000"),
                                             (102, "Services", "115000", "511000", "412000", "611000")]:
        put(ItemGroup(itms_grp_cod=code, itms_grp_nam=name, bal_invnt_ac=inv, sale_cost_ac=cogs, revenues_ac=rev,
                      expenses_ac=exp, price_dif_ac="512000"))

    # partner balances, item stock and cost are runtime state: create only, never re-merge
    contact = 1
    for (code, name, kind, group, terms, plist, vat, city, person, slp, street, zip_code, state, phone,
         gstin) in PARTNERS:
        if s.get(BusinessPartner, code) is None:
            put(BusinessPartner(card_code=code, card_name=name, card_type=kind, group_code=group, currency="##",
                                deb_pay_acct="211000" if kind == "S" else "114000", group_num=terms, list_num=plist,
                                vat_group=vat, address=street, zip_code=zip_code, city=city, country="IN",
                                cntct_prsn=person, slp_code=slp, phone1=phone, lic_trad_num=gstin,
                                credit_line=Decimal("500000") if kind == "C" else Decimal("0"),
                                balance=Decimal("0"), dnotes_bal=Decimal("0"), orders_bal=Decimal("0"), frozen_for="N"))
            if person:
                first, last = person.split(" ", 1)
                put(ContactPerson(cntct_code=contact, card_code=code, name=person, first_name=first, last_name=last,
                                  position="Purchasing" if kind == "C" else "Sales", tel1=phone, active="Y"))
        contact += 1
        bp = s.get(BusinessPartner, code)
        for adres_type in ("B", "S"):  # bill-to and ship-to addresses (CRD1) with GSTIN, created once
            if s.get(PartnerAddress, (code, adres_type, "Main")) is None:
                s.add(PartnerAddress(card_code=code, adres_type=adres_type, address="Main", street=street,
                                     zip_code=zip_code, city=city, state=state, country="IN", gst_regn_no=gstin,
                                     gst_type="R"))
                s.flush()
        bp.bill_to_def = bp.bill_to_def or "Main"
        bp.ship_to_def = bp.ship_to_def or "Main"
        if bp.slp_code is None:
            bp.slp_code = slp
        if kind == "C" and bp.dun_term is None:
            bp.dun_term = "STD"
    for code, name, group, inv, uom, vat_sa, vat_pu, price, pur, vendor, firm, bars, hsn in ITEMS:
        if s.get(Item, code) is None:
            put(Item(item_code=code, item_name=name, itms_grp_cod=group, invnt_item="Y" if inv else "N",
                     sell_item="Y", prchse_item="Y" if inv else "N", eval_system="A", gl_method="C", invntry_uom=uom,
                     vat_gourp_sa=vat_sa, vat_group_pu=vat_pu, dflt_wh="01" if inv else None, card_code=vendor,
                     min_level=Decimal("5") if inv else Decimal("0"), on_hand=Decimal("0"), is_commited=Decimal("0"),
                     on_order=Decimal("0"), avg_price=Decimal("0"), stock_value=Decimal("0"), last_pur_prc=Decimal("0"),
                     frozen_for="N", item_type="I" if inv else "L", firm_code=firm, code_bars=bars, chapter_id=hsn,
                     buy_unit_msr=uom, sal_unit_msr=uom, max_level=Decimal("50") if inv else Decimal("0"),
                     reorder_qty=Decimal("10") if inv else Decimal("0"), lead_time=7 if inv else None))
        if inv:
            for whs in ("01", "02"):
                if s.get(ItemWarehouse, (code, whs)) is None:
                    put(ItemWarehouse(item_code=code, whs_code=whs))
        for plist, amount in [(1, price), (3, pur)]:  # prices are maintained by users: create only
            if amount and s.get(ItemPrice, (code, plist)) is None:
                put(ItemPrice(item_code=code, price_list=plist, price=Decimal(amount), currency=LOCAL))


if __name__ == "__main__":
    seed()
