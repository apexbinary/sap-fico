# SAP FI/CO Clone — Finance Core

A from-scratch ERP **Financial Accounting (FI)** and **Controlling (CO)** engine,
modeled closely on SAP ECC / S/4HANA conventions. Table and field names mirror the
real SAP data dictionary (e.g. `BUKRS`, `BKPF`, `BSEG`, `SKA1`, `HKONT`, `KOSTL`)
so the model is recognizable to anyone who knows SAP FICO.

> This is an independent, clean-room implementation inspired by SAP's published
> data-model conventions. It contains **no SAP source code**. "SAP", "FI", "CO",
> "S/4HANA" are trademarks of SAP SE, used here only for interoperability/reference.

## Stack

- **Python 3.12**, **FastAPI** (REST API), **SQLAlchemy 2.0** (ORM)
- **SQLite** by default (zero-setup dev); switch to **PostgreSQL** via `DATABASE_URL`

## Modules (SAP terminology)

| Area | SAP component | Status |
|------|---------------|--------|
| Enterprise structure | Client, Company Code, Chart of Accounts, Fiscal Year Variant, Controlling Area | ✅ |
| General Ledger | G/L master (SKA1/SKB1/SKAT), posting, GLT0 totals | ✅ |
| Accounting documents | BKPF / BSEG, document types, posting keys | ✅ |
| Taxes | Tax codes (T007A), account determination (T030K) | 🚧 |
| Accounts Receivable | Customer master (KNA1/KNB1), open items | 🚧 |
| Accounts Payable | Vendor master (LFA1/LFB1), open items | 🚧 |
| Controlling | Cost centers, cost elements, internal orders, profit centers (real-time FI→CO) | ✅ |
| Asset Accounting | Asset master (ANLA/ANLB/ANLC), acquisition, straight-line depreciation run | ✅ |
| Bank Accounting | House banks (T012/T012K), electronic statements (FEBKO/FEBEP), auto-reconcile | ✅ |
| Payments & clearing | Terms of payment (T052), F-28/F-53 payments, F-32/F-44/F-03 clearing, cash discount with tax adjustment, tolerances (T043G), partial/residual items | ✅ |
| Automatic payment program | F110 parameters (REGUV), proposal and payment run (REGUH/REGUP), SEPA transfers (pain.001) and direct debits with mandates (pain.008), bank clearing account flow | ✅ |
| Reporting | Trial balance, account balances, open items (net due date) | ✅ |
| Document lifecycle | Parked documents (park / post / delete), reversal FB08, reset clearing FBRA | ✅ |
| Financial statements | FSV (T011/FAGL_011PC/FAGL_011ZC), balance sheet / P&L with comparison year, balance carryforward | ✅ |

### Web UI

A SAP Fiori-style single-page app (`web/`, vanilla JS, no build step) is served by
the same FastAPI process at `/`: Dashboard, Post Document (live balance + auto-tax),
Documents, Payments & Clearing, Payment Run (F110), Trial Balance, Balance Sheet / P&L, Open Items, Fixed Assets, Bank Statements, and master-data
browsers. Open http://localhost:8000/ after starting the server.

## Run

### Docker

```bash
docker compose up -d --build     # http://localhost:8000/  (data in volume sapfico-data)
```

### Local Python

```bash
cd sap-fico
python -m venv .venv
. .venv/Scripts/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# seed the demo client/company code/chart of accounts
python -m app.seed

# start the API
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive OpenAPI UI.

## Key SAP concepts implemented

- **Double-entry posting** enforced at the document level (sum of debits = sum of
  credits per currency), mirroring SAP's `BKPF`/`BSEG` structure.
- **Posting keys** (`TBSL`) drive debit/credit indicator and account type.
- **Posting periods** validated against the fiscal year variant and open-period table.
- **Reconciliation accounts** link sub-ledgers (AR/AP) to the G/L.
- **Document / line item numbering** via SAP-style number ranges (`BELNR` per
  company code + fiscal year).
