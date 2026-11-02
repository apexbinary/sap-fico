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
from app.models.admin import Company, Currency, ExchangeRate, NumberingSeries, PaymentTerms, PostingPeriod, TaxGroup
from app.models.finance import Account, AccountDetermination

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
        # flush record by record in code order (parents first; PostgreSQL enforces foreign keys)
        s.merge(obj)
        s.flush()

    try:
        put(Company(code=1, company_name="Demo Trading Ltd", main_curncy="EUR", sys_curncy="USD", country="DE",
                    tax_id="DE123456789", address="Hauptstrasse 1, 69190 Walldorf", phone="+49 6227 0"))
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
                put(PostingPeriod(abs_entry=entry, code=f"{year}-{month:02d}", name=f"{year}-{month:02d}",
                                  f_ref_date=date(year, month, 1), t_ref_date=date(year, month, last),
                                  category=str(year), period_stat="N"))
                entry += 1

        for obj, (name, start) in SERIES.items():  # next numbers are live counters: create only
            if s.get(NumberingSeries, (obj, 1)) is None:
                put(NumberingSeries(object_code=obj, series=1, series_name=name, initial_num=start,
                                    next_number=start, last_num=None, is_default=True))

        for code, name, parent_drawer, parent, postable, act_type, control, cash in CHART:
            put(Account(acct_code=code, acct_name=name, group_mask=parent_drawer, father_num=parent,
                        levels=1 if parent is None else (2 if len(parent) == 1 else 3), postable=postable,
                        act_type=act_type, loc_man_tran=control, finanse=cash))

        for code, name, category, rate, account in [
            ("O1", "Output VAT 19%", "O", "19", "216000"), ("O2", "Output VAT 7%", "O", "7", "216000"),
            ("O0", "Output VAT exempt", "O", "0", "216000"),
            ("I1", "Input VAT 19%", "I", "19", "116000"), ("I2", "Input VAT 7%", "I", "7", "116000"),
            ("I0", "Input VAT exempt", "I", "0", "116000"),
        ]:
            put(TaxGroup(code=code, name=name, category=category, rate=Decimal(rate), account=account))
        for num, name, months, days in [(-1, "Cash Basic", 0, 0), (1, "Net 30", 0, 30), (2, "Net 60", 0, 60),
                                        (3, "End of next month", 1, 0)]:
            put(PaymentTerms(group_num=num, pymnt_group=name, extra_month=months, extra_days=days))
        for year in ("2025", "2026", "2027"):
            put(AccountDetermination(
                period_cat=year, ar_control="114000", ap_control="211000", revenue="411000", cogs="511000",
                inventory="115000", allocation="212000", price_diff="512000", expense="611000",
                inv_offset_inc="513000", inv_offset_dec="513000", exch_gain="711000", exch_loss="712000",
                opening_bal="313000"))
        s.commit()
        print("Seed complete: Demo Trading Ltd (EUR), chart of accounts, periods 2025-2027.")
    finally:
        s.close()


if __name__ == "__main__":
    seed()
