# CLAUDE.md — project context for Claude Code

This file is read automatically by Claude Code at the start of a session. It
orients a fresh session on this repository. Keep it current when the project
changes.

## What this is

A from-scratch ERP **Financial Accounting (FI)** and **Controlling (CO)** engine,
modeled on **SAP ECC / S/4HANA** conventions. It is an independent, clean-room
implementation — it contains **no SAP source code**. The defining requirement:
**table and field names mirror the real SAP data dictionary** (e.g. `BUKRS`,
`BKPF`/`BSEG`, `SKA1`/`SKB1`, `HKONT`, `KOSTL`, `ANLA`) and **no SAP field the
module needs should be omitted**. When adding fields/tables, use the authentic
SAP technical name with the English data-element meaning in a comment.

Origin: the user asked to "build the B1 of SAP" and then specified the full
**FI/CO** finance suite (not the simpler Business One model), Python backend,
authentic SAP fields.

## Stack

- Python 3.12, **FastAPI** (REST), **SQLAlchemy 2.0** ORM (`Mapped`/`mapped_column`),
  Pydantic v2, Uvicorn.
- **SQLite by default** (zero config, `sapfico.db`), **PostgreSQL** via `DATABASE_URL`.
- Web UI: **vanilla JS SPA** in `web/` (no build step), SAP Fiori-inspired, served
  by FastAPI `StaticFiles` at `/`.

## How to run (Windows paths shown; adjust for your OS)

```bash
cd sap-fico
python -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m app.seed                     # build schema + demo client 100 / company 1000
python -m app.verify                   # end-to-end FI smoke test (posts docs, trial balance)
python -m app.verify_assets            # end-to-end asset + bank smoke test
python -m app.verify_payments          # payments, cash discount, partial/residual, clearing
python -m app.verify_payment_run       # F110 proposal, payment run, SEPA file

python -m uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs   |   Web UI: http://localhost:8000/
```

The venv Python on Windows is `.venv/Scripts/python.exe`; on macOS/Linux
`.venv/bin/python`. Re-running `app.seed` is idempotent (merge by primary key).
`create_all()` also adds new *nullable* model columns to existing tables
(`database._add_missing_columns`); any other schema change (new NOT NULL
column, type change, rename) still needs `sapfico.db` deleted or a migration.

### Docker

`docker compose up -d --build` builds the image, seeds on every start
(idempotent) and serves on http://localhost:8000. SQLite lives in the
`sapfico-data` volume (`/data/sapfico.db`). Run the verify scripts against a
scratch DB so they don't post test documents into it:

```bash
docker run --rm -e DATABASE_URL=sqlite:////tmp/v.db cloned_system-app \
  sh -c "python -m app.seed && python -m app.verify && python -m app.verify_assets && python -m app.verify_payments && python -m app.verify_payment_run"
```

## Architecture (dependencies flow inward)

```
app/
  config.py          Settings (reads .env: DATABASE_URL, DEFAULT_CLIENT, SQL_ECHO)
  database.py        engine, SessionLocal, Base, create_all()
  models/            ORM tables — authentic SAP names; MANDT (client) is CHAR(3) key
    organizational.py  T000 T001 T004 T009/T009B TKA01/02 TGSB T014 TCURC/TCURR T001B
    gl_master.py       SKA1 SKAT SKB1 T077S T004V/T004G
    documents.py       T003 TBSL NRIV BKPF BSEG GLT0
    tax.py             T005 T007A TAXRATE T030K T059P/Z
    partners.py        KNA1 KNB1 LFA1 LFB1 LFBK
    controlling.py     CSKS CSKA CSKB AUFK CEPC COEP
    assets.py          ANKA T093 T095 TABW ANLA ANLB ANLZ ANLC ANEK ANEP ANLP
    bank.py            BNKA T012 T012K FEBKO FEBEP
    payments.py        T052 (terms of payment) T030 (automatic accounts: SKT/SKE)
                       T042Z T042E T042I (F110 payment methods, limits, bank ranking)
                       T043G (customer/vendor payment-difference tolerances)
    payment_run.py     REGUV REGUH REGUP (F110 run control, payees, paid items)
  services/          business logic (the "application layer")
    fiscal.py          period determination (T009B), open-period check (T001B), PostingError
    tax.py             tax calc + account determination
    posting.py         THE posting engine — post_document(); account types S/D/K/A,
                       balancing, posting keys, number ranges, GLT0, real-time CO (COEP),
                       asset value updates (ANEP/ANLC)
    asset_accounting.py  create_asset, post_acquisition, run_depreciation (straight-line)
    payment_terms.py   T052 -> BSEG terms fields, net due date, cash discount
    clearing.py        post_payment(): F-28/F-53 payments + F-32/F-44/F-03 clearing;
                       modes clear / residual / partial / on_account; tolerances,
                       discount tax adjustment; proposal()
    payment_run.py     F110: create_proposal / execute / sepa_credit_transfer (pain.001)
    bank.py            import_statement, post_statement (auto-match + clear via clearing.py)
    reporting.py       trial_balance, account_balance, open_items
  api.py             /api/documents, /api/reports/*
  masterdata.py      /api/master/* (company codes, GL accounts, partners, posting keys, ...)
  api_assets_bank.py /api/assets*, /api/bank*, /api/master/house-banks
  api_payments.py    /api/payments/open-items, /api/payments, /api/clearing
  api_payment_run.py /api/payment-runs (proposal, execute, sepa, delete)
  main.py            FastAPI app; mounts routers under /api and the web UI at /
  seed.py            demo customizing + master data
  verify*.py         runnable end-to-end checks (FI, assets/bank, payments, F110)
web/                 index.html, styles.css, app.js (SPA)
scripts/             setup_postgres.sql
```

### Posting engine rules (the core of FI — keep these invariant)
- Each line's **debit/credit (SHKZG)** and **account type (KOART)** come from its
  **posting key (TBSL)**; never infer them elsewhere.
- A document must **balance** (sum debits == sum credits) in **document currency
  and local currency**.
- Posting period must be **open** (T001B) for each account type used.
- Sub-ledger lines (customer D / vendor K) post to their **reconciliation account**
  (`AKONT` from KNB1/LFB1) in the G/L; asset lines (A) post to the **APC account**
  from account determination (T095).
- Document numbers come from the **number range (NRIV)** of the document type.
- Primary cost-element lines with a CO object mirror into **COEP** (real-time FI→CO).
- Errors use `PostingError` and surface as HTTP 422 with SAP-style messages.
- Invoice lines (sales-related keys, TBSL-XUMSW) copy their terms of payment
  (entered ZTERM, else KNB1/LFB1) into BSEG ZTERM/ZBD*T/ZBD*P/SKFBT; discount
  and due dates are always read from the line, never from T052.
- Clearing posts one document via `post_document(..., commit=False)` and stamps
  AUGBL/AUGGJ/AUGDT on the settled items and their offsetting lines in the
  same transaction. Open items = BSEG lines with XOPVW set (all D/K lines, G/L
  lines of SKB1-XOPVW accounts) and empty AUGBL. A zero-balance clearing posts
  a BKPF header without line items (`DocumentRequest.xclear`).
- F110 never posts by itself: `payment_run.execute` calls `clearing.post_payment`
  once per REGUH group; groups with an `exception` are skipped.
- Seed merges must set every primary-key column explicitly (column defaults
  only apply on INSERT, so a missing key makes `merge` insert a duplicate).

## Demo configuration (from seed)

Client **100**, company code **1000** (Germany, EUR), chart of accounts **INT**,
fiscal year variant **K4** (calendar, 12+4 periods), controlling area **1000**,
cost center 0000001000. Tax procedure TAXD: **A1** output VAT 19%, **V1** input VAT
19%. Customer 0000010000, vendor 0000020000. Asset class 00003000 (machinery).
House bank DB / account GIRO → G/L 113100. Posting keys 40/50 (G/L), 01/11/15
(customer), 21/25/31 (vendor), 70/75 (asset), plus clearing keys 05/06/07/16/17
(customer) and 26/27/35/36/37 (vendor). Document types SA/DR/DZ/KR/KZ/AA/AF/AB.
Terms of payment 0001 (net), NT30, ZB01 (14d 3% / 30d 2% / 45d net); customer
0000010000 is on 0001, vendor 0000020000 on ZB01. Cash discount accounts
(T030): SKT granted 880000, SKE received 276000. F110: payment method T (SEPA
transfer, needs payee IBAN), min 1.00 EUR, bank ranking DB/GIRO -> G/L 113100,
document type ZP. Vendor 0000020000 has LFBK bank details and ZWELS T; vendor
0000020001 (Gamma Logistics) has none, so it shows up as an F110 exception.
Tolerance group '' (T043G): gain and loss up to 2.00 EUR and 1%, posted via
T030 ZDI to 880100 (loss) / 880200 (gain). G/L 113109 is open-item managed.

## Status

Enterprise structure, G/L master, posting engine, taxes, AR/AP, Controlling,
Asset Accounting (acquisition + depreciation), Bank Accounting (statements +
clearing), reporting, REST API, and web UI are done and pass the verify scripts.

**Payments & clearing (roadmap 1, first part) — done:** terms of payment,
incoming/outgoing payments with clearing (F-28/F-53), clearing without payment
(F-32/F-44), cash discount, partial payments and residual items, bank statement
auto-matching through the same service, "Payments & Clearing" UI screen.
Also done: G/L open-item clearing (F-03), payment-difference tolerances
(T043G -> ZDI), tax adjustment on cash discount (proportional to the
invoice's tax lines), header-only zero-balance clearing documents.
Known gaps: local currency only; T043G column names need checking against
the SAP DDIC; tolerances per employee (T043T) and reason codes are missing.

**Automatic payment program F110 — done (vendors):** parameters, proposal
(due / cash-discount rule, credit-memo offset, payment method and house bank
determination, exception list), payment run, SEPA pain.001 file, UI screen.
Known gaps: customers (direct debit, pain.008), editing a proposal item by item,
available amounts per bank (T042Y), checks, bank clearing sub-accounts.

## Roadmap / likely next tasks

1. **Payments (rest)**: F110 for customers (direct debit, pain.008), bank
   clearing sub-account flow (F110 -> 113109 -> bank statement -> F-03).
2. **Financial Statement Version (FSV)**: balance sheet & P&L hierarchy over the
   trial balance.
3. **Dunning** (FBMP/F150), **foreign-currency valuation**, **recurring entries**,
   **document reversal** (FB08) and **parked documents** (BSTAT='V').
4. **PostgreSQL cutover** (see HANDOFF.md) and Alembic migrations.
5. More CO: assessments/distributions, internal order settlement, CO-PA.

## Conventions when extending

- Match SAP names and keep `MANDT` in the primary key of client-dependent tables.
- Put new interpretation/ownership at the producing boundary; don't re-parse raw
  values downstream. Keep engine/provider specifics out of `models/`.
- Add a runnable check (extend `verify*.py`) for new posting behavior, and keep
  the trial balance balanced as the invariant test.
- Conventional Commit messages. End commit messages with the Co-Authored-By line.

## GitHub

Remote `origin` → `https://github.com/apexbinary/sap-fico` (private, branch `main`).
