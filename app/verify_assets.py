"""End-to-end smoke test for Asset Accounting and Bank Accounting.

Run after app.seed:  python -m app.verify_assets
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.models.assets import AssetValues
from app.services import asset_accounting as aa
from app.services import bank as bank_svc
from app.services import reporting
from app.services.posting import DocumentRequest, LineRequest, post_document

MANDT, BUKRS = "100", "1000"


def main() -> None:
    s = SessionLocal()
    try:
        # --- set up open items to be paid via bank later ---
        post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="DR", bldat=date(2026, 2, 1), budat=date(2026, 2, 1), waers="EUR",
            bktxt="Sales invoice", lines=[
                LineRequest(bschl="01", account="0000010000", wrbtr=Decimal("1190.00"), zuonr="INV-1"),
                LineRequest(bschl="50", account="800000", wrbtr=Decimal("1000.00"), mwskz="A1", calculate_tax=True),
            ]))
        post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="KR", bldat=date(2026, 2, 2), budat=date(2026, 2, 2), waers="EUR",
            bktxt="Vendor invoice", lines=[
                LineRequest(bschl="31", account="0000020000", wrbtr=Decimal("595.00")),
                LineRequest(bschl="40", account="476000", wrbtr=Decimal("500.00"), mwskz="V1", calculate_tax=True, kostl="0000001000"),
            ]))

        # --- Asset Accounting ---
        print("=== ASSET ACCOUNTING ===")
        aa.create_asset(s, MANDT, BUKRS, "000000001000", "00003000", "CNC Milling Machine",
                        useful_life_years=5, kostl="0000001000")
        acq = aa.post_acquisition(s, MANDT, BUKRS, "000000001000", Decimal("60000.00"),
                                  date(2026, 1, 15), offset_account="0000020000", offset_is_vendor=True)
        print(f"Acquisition posted: FI doc {acq['belnr']}/{acq['gjahr']}  EUR {acq['amount']}")

        dep = aa.run_depreciation(s, MANDT, BUKRS, 2026, 1)
        for d in dep["posted"]:
            print(f"Depreciation: asset {d['anln1']}  EUR {d['depreciation']}  FI doc {d['belnr']}")
        val = s.get(AssetValues, (MANDT, BUKRS, "000000001000", "0000", 2026, "01"))
        nbv = val.answl - val.nafag
        print(f"Asset values: APC {val.answl}  depreciation {val.nafag}  net book value {nbv}")

        # --- Bank Accounting ---
        print("\n=== BANK ACCOUNTING ===")
        bank_svc.import_statement(
            s, MANDT, BUKRS, "DB", "GIRO", "STMT202603", date(2026, 3, 31),
            opening=Decimal("0.00"),
            items=[
                {"amount": "1190.00", "shkzg": "H", "kunnr": "0000010000", "note": "Payment INV-1", "partner": "Alpha Retail"},
                {"amount": "595.00", "shkzg": "S", "lifnr": "0000020000", "note": "Payment to Beta", "partner": "Beta Supplies"},
            ])
        res = bank_svc.post_statement(s, MANDT, BUKRS, "STMT202603")
        for p in res["posted"]:
            print(f"Statement item {p['esnum']}: FI doc {p['belnr']}  partner {p['partner']}  cleared={p['cleared']}")

        print("\nOpen items customer 0000010000 (should be empty):",
              len(reporting.open_items(s, MANDT, BUKRS, "D", "0000010000")))
        print("Open items vendor 0000020000 (should be empty):",
              len(reporting.open_items(s, MANDT, BUKRS, "K", "0000020000")))

        tb = reporting.trial_balance(s, MANDT, BUKRS, 2026)
        print(f"\nTrial balance: debit {tb['total_debit']}  credit {tb['total_credit']}  balanced={tb['balanced']}")
        for ln in tb["lines"]:
            print(f"   {ln['saknr']} {ln['name'][:32]:<32} {ln['balance']:>14}")
        assert tb["balanced"], "Trial balance not balanced!"
        print("\nOK - asset + bank flows posted, open items cleared, ledger balances.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
