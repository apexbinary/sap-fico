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

python -m uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs   |   Web UI: http://localhost:8000/
```

The venv Python on Windows is `.venv/Scripts/python.exe`; on macOS/Linux
`.venv/bin/python`. Re-running `app.seed` is idempotent (merge by primary key),
but if you change a model's columns on SQLite, delete `sapfico.db` first
(SQLAlchemy `create_all` does not ALTER existing tables).

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
    partners.py        KNA1 KNB1 LFA1 LFB1
    controlling.py     CSKS CSKA CSKB AUFK CEPC COEP
    assets.py          ANKA T093 T095 TABW ANLA ANLB ANLZ ANLC ANEK ANEP ANLP
    bank.py            BNKA T012 T012K FEBKO FEBEP
  services/          business logic (the "application layer")
    fiscal.py          period determination (T009B), open-period check (T001B), PostingError
    tax.py             tax calc + account determination
    posting.py         THE posting engine — post_document(); account types S/D/K/A,
                       balancing, posting keys, number ranges, GLT0, real-time CO (COEP),
                       asset value updates (ANEP/ANLC)
    asset_accounting.py  create_asset, post_acquisition, run_depreciation (straight-line)
    bank.py            import_statement, post_statement (+ open-item clearing via AUGBL)
    reporting.py       trial_balance, account_balance, open_items
  api.py             /api/documents, /api/reports/*
  masterdata.py      /api/master/* (company codes, GL accounts, partners, posting keys, ...)
  api_assets_bank.py /api/assets*, /api/bank*, /api/master/house-banks
  main.py            FastAPI app; mounts routers under /api and the web UI at /
  seed.py            demo customizing + master data
  verify.py / verify_assets.py   runnable end-to-end checks
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

## Demo configuration (from seed)

Client **100**, company code **1000** (Germany, EUR), chart of accounts **INT**,
fiscal year variant **K4** (calendar, 12+4 periods), controlling area **1000**,
cost center 0000001000. Tax procedure TAXD: **A1** output VAT 19%, **V1** input VAT
19%. Customer 0000010000, vendor 0000020000. Asset class 00003000 (machinery).
House bank DB / account GIRO → G/L 113100. Posting keys 40/50 (G/L), 01/11/15
(customer), 21/25/31 (vendor), 70/75 (asset). Document types SA/DR/DZ/KR/KZ/AA/AF.

## Status — all 9 initial modules complete and verified

Enterprise structure, G/L master, posting engine, taxes, AR/AP, Controlling,
Asset Accounting (acquisition + depreciation), Bank Accounting (statements +
clearing), reporting, REST API, and web UI are all done and pass the two verify
scripts.

## Roadmap / likely next tasks

1. **Payments & clearing**: manual clearing (F-03/F-32/F-44), the automatic
   payment program (F110), partial/residual clearing, cash discount.
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
