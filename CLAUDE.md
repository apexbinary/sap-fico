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
python -m app.verify_payment_run       # F110 proposal, payment run, SEPA files, bank clearing
python -m app.verify_fsv               # balance sheet / P&L by FSV, balance carryforward
python -m app.verify_documents         # park / post parked / delete, reversal, reset clearing
python -m app.verify_recurring         # recurring entry original + F.14 runs
python -m app.verify_dunning           # dunning levels, interval, charges, notices
python -m app.verify_fx                # FX translation, rounding, valuation, realized differences
python -m app.verify_controlling       # CO documents, reports, allocations, settlement, CO-PA
python -m app.verify_all               # all of the above in order

python -m uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs   |   Web UI: http://localhost:8000/
```

The venv Python on Windows is `.venv/Scripts/python.exe`; on macOS/Linux
`.venv/bin/python`. Re-running `app.seed` is idempotent (merge by primary key).

### Schema changes: Alembic

The schema is owned by Alembic (`alembic.ini`, `migrations/`). `init_db()` (run
by the app on startup and by `app.seed`) does `alembic upgrade head`; a database
created before Alembic (tables but no `alembic_version`) is synced once by the
legacy helpers and stamped. After changing a model, add a revision and commit it:

```bash
alembic revision --autogenerate -m "describe the change"   # review the file!
docker run --rm -v "$PWD/migrations:/app/migrations" -e DATABASE_URL=sqlite:////tmp/e.db   cloned_system-app sh -c "python -m app.seed >/dev/null; alembic revision --autogenerate -m 'x'"
```

### PostgreSQL

`docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build`
runs the app on PostgreSQL 16 (service `db`, volume `sapfico-pg`). PostgreSQL
enforces VARCHAR lengths and every foreign key: `python -m scripts.check_lengths`
lists values that SQLite accepted but PostgreSQL would reject.

### Docker

`docker compose up -d --build` builds the image, seeds on every start
(idempotent) and serves on http://localhost:8000. SQLite lives in the
`sapfico-data` volume (`/data/sapfico.db`). Run the verify scripts against a
scratch DB so they don't post test documents into it:

```bash
docker run --rm -e DATABASE_URL=sqlite:////tmp/v.db cloned_system-app \
  sh -c "python -m app.seed && python -m app.verify_all"
```

## Architecture (dependencies flow inward)

```
app/
  config.py          Settings (reads .env: DATABASE_URL, DEFAULT_CLIENT, SQL_ECHO)
  database.py        engine, SessionLocal, Base, init_db() (Alembic upgrade / legacy stamp)
  models/            ORM tables — authentic SAP names; MANDT (client) is CHAR(3) key
    organizational.py  T000 T001 T004 T009/T009B TKA01/02 TGSB T014 TCURC/TCURR T001B
    gl_master.py       SKA1 SKAT SKB1 T077S T004V/T004G
    documents.py       T003 TBSL NRIV BKPF BSEG GLT0 BKDF
    tax.py             T005 T007A TAXRATE T030K T059P/Z
    partners.py        KNA1 KNB1 LFA1 LFB1 LFBK KNBK SEPA_MANDATE KNB5
    dunning.py         T047A T047B T047C (procedure, levels, charges) MAHNV MHNK MHND
    controlling.py     CSKS CSKA CSKB AUFK CEPC COEP COBK, T811C/S/K (cycles),
                       COBRA/COBRB (settlement rules), TKEB CE4IDEA (CO-PA)
    assets.py          ANKA T093 T095 TABW ANLA ANLB ANLZ ANLC ANEK ANEP ANLP
    bank.py            BNKA T012 T012K FEBKO FEBEP
    payments.py        T052 (terms of payment) T030 (automatic accounts: SKT/SKE)
                       T042Z T042E T042I (F110 payment methods, limits, bank ranking)
                       T043G (customer/vendor payment-difference tolerances)
                       T030H (exchange rate difference accounts)
    payment_run.py     REGUV REGUH REGUP (F110 run control, payees, paid items)
    fsv.py             T011 FAGL_011PC FAGL_011ZC (financial statement version)
  services/          business logic (the "application layer")
    fiscal.py          period determination (T009B), open-period check (T001B), PostingError
    tax.py             tax calc + account determination
    posting.py         THE posting engine — post_document(); account types S/D/K/A,
                       balancing, posting keys, number ranges, GLT0, real-time CO (COEP),
                       asset value updates (ANEP/ANLC); parked documents (bstat V,
                       post_parked / delete_parked)
    reversal.py        reverse_document (FB08, TBSL-STBSL keys), reset_clearing (FBRA)
    recurring.py       create_recurring (FBD1, BSTAT D, interval X1) / run_recurring (F.14)
    dunning.py         F150: create_proposal / execute (BSEG-MANST, KNB5) / notice_html
    fx.py              rate (TCURR), valuate (FAGL_FCV with next-day reversal)
    asset_accounting.py  create_asset, post_acquisition, run_depreciation (straight-line)
    payment_terms.py   T052 -> BSEG terms fields, net due date, cash discount
    clearing.py        post_payment(): F-28/F-53 payments + F-32/F-44/F-03 clearing;
                       modes clear / residual / partial / on_account; tolerances,
                       discount tax adjustment; proposal()
    payment_run.py     F110 vendors + customers: create_proposal / execute /
                       sepa_credit_transfer (pain.001) / sepa_direct_debit (pain.008)
    bank.py            import_statement, post_statement (partner items: auto-match +
                       clear; partner-less items: clear the T042I clearing account)
    reporting.py       trial_balance, account_balance, open_items
    controlling.py     CO documents (COBK, RK_BELEG numbers), object balances, actuals
    allocation.py      assessment (KSU5, RKIU) / distribution (KSV5, RKIV), reverse_run
    settlement.py      internal order settlement (KO88, KOAO; KS in CO, SK via FI)
    copa.py            CO-PA segment derivation from the customer, contribution report
    fsv.py             financial_statement (balance sheet / P&L by FSV),
                       carry_forward (FAGLGVTR: GLT0-HSLVT, P&L -> retained earnings)
  api.py             /api/documents (+ park, post, delete, reverse, reset-clearing),
                     /api/reports/* (incl. financial-statement),
                     /api/closing/carry-forward
  masterdata.py      /api/master/* (company codes, GL accounts, partners, posting keys, ...)
  api_assets_bank.py /api/assets*, /api/bank*, /api/master/house-banks
  api_payments.py    /api/payments/open-items, /api/payments, /api/clearing
  api_payment_run.py /api/payment-runs (proposal, execute, sepa, sepa-dd, delete)
  api_controlling.py /api/co/actuals, documents, cycles, orders/{aufnr}/settle, pa/contribution
  api_periodic.py    /api/recurring (+ run), /api/dunning-runs (+ execute, notice),
                     /api/exchange-rates, /api/fx-valuation
  main.py            FastAPI app; mounts routers under /api and the web UI at /
  seed.py            demo customizing + master data
  verify*.py         runnable end-to-end checks (FI, assets/bank, payments, F110, FSV,
                     document lifecycle)
web/                 index.html, styles.css, app.js (SPA)
migrations/          Alembic env + revisions (0001 baseline, 0002 COBK, 0003 cycles,
                     0004 settlement rules, 0005 CO-PA)
scripts/             setup_postgres.sql, check_lengths.py
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
- Primary cost-element lines with a CO object mirror into **COEP** (real-time FI→CO),
  in a CO document of their own (COBK, RK_BELEG) that references the FI document.
  Revenue / sales deduction lines (categories 11/12) without a CO object go to the
  CO-PA segment derived from the document's customer (BSEG-PAOBJNR, object EO).
- Errors use `PostingError` and surface as HTTP 422 with SAP-style messages.
- Invoice lines (sales-related keys, TBSL-XUMSW) copy their terms of payment
  (entered ZTERM, else KNB1/LFB1) into BSEG ZTERM/ZBD*T/ZBD*P/SKFBT; discount
  and due dates are always read from the line, never from T052.
- Clearing posts one document via `post_document(..., commit=False)` and stamps
  AUGBL/AUGGJ/AUGDT on the settled items and their offsetting lines in the
  same transaction. Open items = BSEG lines with XOPVW set (all D/K lines, G/L
  lines of SKB1-XOPVW accounts) and empty AUGBL. A zero-balance clearing posts
  a BKPF header without line items (`DocumentRequest.xclear`).
- Parked documents (BKPF-BSTAT 'V') are numbered and stored but update nothing,
  and their items have XOPVW off, so every open-item query (which filters on
  XOPVW) ignores them. Deleted parked documents get BSTAT 'Z'.
- A reversal uses each posting key's TBSL-STBSL, links both documents via
  STBLG/STJAH and clears their open items against each other; cleared items
  block a reversal until reset_clearing reopens them.
- F110 never posts by itself: `payment_run.execute` calls `clearing.post_payment`
  once per REGUH group; groups with an `exception` are skipped.
- Seed merges must set every primary-key column explicitly (column defaults
  only apply on INSERT, so a missing key makes `merge` insert a duplicate).
  Runtime state (NRIV-NRLEVEL counters, KNB5 dunning level/date) is only
  created, never re-merged.
- Auto-tax lines take the debit/credit side of their base line (so credit
  memos reduce output/input tax).
- Foreign-currency documents translate at the TCURR rate (type M) of the
  posting date unless KURSF is given; cent differences go to the largest
  translated line. `LineRequest.dmbtr` fixes a line's local amount (clearing
  offsets each item at its historical rate; the rest is realized FX, T030H).
- Every model change needs an Alembic revision. The pre-Alembic helpers
  (`_legacy_create_all`) only run once for databases without `alembic_version`.
- The controlling area of a company code comes from TKA02
  (`fiscal.controlling_area`); T001-KOKFI is only the 1-character indicator.
- Seed inserts are flushed one by one in code order (parents first) because
  PostgreSQL enforces foreign keys that SQLAlchemy does not order by.
- The engine rejects header/line texts longer than their columns (BKTXT 25,
  XBLNR 16, SGTXT 50, ZUONR 18).

## Demo configuration (from seed)

Client **100**, company code **1000** (Germany, EUR), chart of accounts **INT**,
fiscal year variant **K4** (calendar, 12+4 periods), controlling area **1000**,
cost centers 0000001000 (admin) / 0000002000 (sales) / 0000003000
(production), internal order 000000400001 (trade fair). Tax procedure TAXD: **A1** output VAT 19%, **V1** input VAT
19%. Customer 0000010000, vendor 0000020000. Asset class 00003000 (machinery).
House bank DB / account GIRO → G/L 113100. Posting keys 40/50 (G/L), 01/11/15
(customer), 21/25/31 (vendor), 70/75 (asset), plus clearing keys 05/06/07/16/17
(customer) and 26/27/35/36/37 (vendor). Document types SA/DR/DZ/KR/KZ/AA/AF/AB.
Terms of payment 0001 (net), NT30, ZB01 (14d 3% / 30d 2% / 45d net); customer
0000010000 is on 0001, vendor 0000020000 on ZB01. Cash discount accounts
(T030): SKT granted 880000, SKE received 276000. F110: payment method T (SEPA
transfer, needs payee IBAN) and E (SEPA direct debit, needs an active mandate),
min 1.00 EUR, bank ranking DB/GIRO -> clearing account 113109, document type
ZP. Customer 0000010000 pays by E (KNBK + mandate MND-0000010000-001, creditor
ID DE98ZZZ09999999999). FSV INT (items: assets / liabilities & equity with
net result / P&L / not assigned; 113xxx is a bank asset when in debit and an
overdraft when in credit). Retained earnings 109000 (T030 BIL, modifier X). Vendor 0000020000 has LFBK bank details and ZWELS T; vendor
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
Also done: employee tolerances (T043/T043T: document, item, cash discount and
payment-difference limits per user group), reason codes (T053R, BSEG-RSTGR,
charge-off via T030 ZDI with the reason as modifier). Still to verify in SAP:
the non-key column names of T043G and T043T.

**Automatic payment program F110 — done:** vendors (SEPA transfer, pain.001)
and customers (SEPA direct debit with mandates, pain.008); proposal with the
due / cash-discount rule, credit-memo offset, method and house bank
determination, exception list; payment run posting to the bank clearing
account 113109, which the bank statement clears automatically.
Also done: blocking/releasing single proposal items, available amounts per
house bank account (T042Y), check payments (method C, check lots PCEC, check
register PAYR, printable checks, void with payment reversal), SEPA sequence
FRST/RCUR/OOFF from SEPA_MANDATE-FIRSTUSE_DATE/DOCID.

**Financial Statement Version — done:** FSV tables, balance sheet / P&L report
with comparison year, debit/credit-dependent assignment, net result in equity,
unassigned-account check, balance carryforward to the next year, UI screen.
Also done: FSV maintenance (items, order, account ranges; special items
protected), functional areas (TFKB; BSEG-FUNC_AREA from CSKS-FKBER, else
SKA1-FUNC_AREA) with a cost-of-sales P&L, customer/vendor transaction figures
KNC1/LFC1 (posting engine + carryforward of UMSAV) with a balances report
reconciled against the reconciliation accounts; revision 0007 backfills them.

**Foreign currency — done:** automatic translation with rounding absorption,
clearing in foreign currency with realized gains/losses (T030H LHREA/LSREA),
FX valuation of open items with test run, posting against LKORR/LHBEW/LSBEW
and reversal on the next day, exchange rate maintenance, UI.
Known gaps: valuation of foreign-currency G/L balances (non open item),
second/third local currencies, rate types other than M.

**Dunning — done:** procedure 0001 (4 levels, 14-day interval, 3 grace days,
charges from level 2), proposal with level rise of at most one per run,
credit offset, interval/block/minimum checks, run updating BSEG-MANST/MADAT
and KNB5, printable HTML notices, UI. Known gaps: dunning interest, dunning
areas, vendors with debit balances; T047A/B/C and MAHNV/MHNK/MHND non-key
column names need checking against the SAP DDIC.

**Recurring entries — done:** originals (BSTAT 'D', interval X1) with BKDF schedule,
F.14 run with month-end clamping and no double posting, deletion, UI.

**Document lifecycle — done:** parking (FV50) with post (FBV0) and delete,
reversal (FB08) with reasons 01/02, reset clearing with optional reversal
(FBRA), UI actions on the document view.
Also done: changing a parked document (FBV2, keeps its number), asset
reversal (AB08: ANEP/ANLC and ANLP depreciation are taken back), mass reversal (F.80).

**Controlling — done:** CO documents (COBK) for every CO posting; actual cost
reports per cost center / internal order; assessment and distribution cycles
(ADMIN-ASM, SALES-DST) with test run, one run per period and reversal;
internal order settlement to cost centers (CO) and G/L accounts (FI); account-
based CO-PA (operating concern IDEA) with a contribution report; UI screens.
Known gaps: plan data, activity types and internal activity allocation,
settlement reversal, CO-PA assessment, costing-based CO-PA; cycle tables are
an explicit version of SAP's generic T811* storage.

**PostgreSQL + Alembic — done:** baseline revision 0001, upgrade on startup,
legacy databases stamped, PostgreSQL compose override; the full verify suite
passes on SQLite and PostgreSQL 16. Fixed on the way: length overflows and
KOKFI misuse, seed FK order, duplicate GLT0 rows for repeated accounts.

## Roadmap / likely next tasks

1. ~~Payments~~ — complete (see Status).
2. ~~Financial Statement Version~~ — done (see Status).
3. ~~Dunning, FX valuation, recurring entries, reversal, parking~~ — done.
4. ~~PostgreSQL cutover and Alembic migrations~~ — done.
5. ~~Assessments/distributions, internal order settlement, CO-PA~~ — done.

All five original roadmap items are complete. Candidates next: CO planning
(plan versions, plan/actual comparison), activity allocation (KB21N), asset
retirement and AB08, customer/vendor clearing (KNB1-XVERR), user management
and authorizations, PDF output for notices and payment advices.

## Conventions when extending

- Match SAP names and keep `MANDT` in the primary key of client-dependent tables.
- Put new interpretation/ownership at the producing boundary; don't re-parse raw
  values downstream. Keep engine/provider specifics out of `models/`.
- Add a runnable check (extend `verify*.py`) for new posting behavior, and keep
  the trial balance balanced as the invariant test.
- Conventional Commit messages. End commit messages with the Co-Authored-By line.

## GitHub

Remote `origin` → `https://github.com/apexbinary/sap-fico` (private, branch `main`).
