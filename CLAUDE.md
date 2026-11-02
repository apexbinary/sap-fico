# CLAUDE.md — project context for Claude Code

## What this is

A clone of **SAP Business One (B1)** — the ERP for small and midsize companies —
built from scratch in Python. The defining requirement: **B1's own table and field
names** (OACT, OJDT/JDT1, OCRD, OITM, ORDR/RDR1, OINV/INV1, ORCT, ...) are used as
the database names, with readable Python attribute names mapped onto them. It is a
clean-room implementation and contains no SAP code.

History: the user asked for "the B1 of SAP" at the start. An earlier session built
the full SAP ERP **FI/CO** suite instead; that work lives on the branch
`feature/payments-clearing` (its Docker data volume `cloned_system_sapfico-data` is
kept). **This branch, `feature/sap-b1`, is the B1 product.** Do not bring FI/CO
concepts (company codes, posting keys, CO, F110, FSV ...) into it.

## Scope (agreed with the user)

1. Core financials — chart of accounts, journal entries, financial reports. **Done.**
2. Business partners + sales (A/R) and purchasing (A/P) document chains with
   copy-from (quotation → order → delivery → invoice → credit memo, and the
   purchasing equivalents).
3. Inventory — items, warehouses, price lists, goods receipt/issue/transfer,
   moving-average cost, automatic stock postings.
4. Banking — incoming/outgoing payments (cash, transfer, check), payments on
   account, BP balances.

## Stack and running

Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic; SQLite by default,
PostgreSQL via `DATABASE_URL` or `docker-compose.postgres.yml`. Web client: vanilla
JS SPA in `web/`.

```bash
docker compose up -d --build                 # http://localhost:8000  (container sap-b1, volume b1-data)
docker run --rm -e DATABASE_URL=sqlite:////tmp/v.db cloned_system-app \
  sh -c "python -m app.seed && python -m app.verify_all"   # checks on a scratch DB
```

Never run checks or smoke tests against the live database (volume `b1-data`).
Schema changes need an Alembic revision (`migrations/`); `init_db()` runs
`alembic upgrade head` on startup and in `app.seed`.

## Architecture

```
app/
  models/admin.py     OADM OCRN ORTT OFPR NNM1 OVTG OCTG
  models/finance.py   OACT OJDT JDT1 OACP (G/L account determination)
  services/admin.py   B1Error, numbering (NNM1), posting periods, exchange rates, due dates
  services/journal.py THE posting engine: post_entry / reverse_entry (OJDT/JDT1)
  services/reports.py trial balance, balance sheet, P&L (account tree)
  api_finance.py      /api/admin/*, /api/accounts, /api/journal-entries, /api/reports/*
  seed.py             demo company "Demo Trading Ltd" (EUR), chart of accounts, periods 2025-2027
  verify_*.py         end-to-end checks; verify_all runs them all
web/                  index.html, styles.css, app.js
```

### Posting rules (keep invariant)
- Every posting is one OJDT/JDT1 journal entry via `journal.post_entry`.
- A business partner line posts to the partner's control account and keeps the
  partner code in ShortName; its open amount is BalDueDeb/BalDueCred.
- Only active (Postable Y), unfrozen accounts; manual entries never post a
  control account directly.
- Balanced in local currency; posting date in an unlocked period (OFPR).
- OACT-CurrTotal (and OCRD-Balance) are updated with each entry.
- Document numbers come from the default NNM1 series of the object type;
  NNM1-NextNumber and exchange rates are runtime data: the seed creates them
  once and never resets them.
- Seed inserts flush one by one, parents first (PostgreSQL enforces FKs).

### Chart of accounts
Drawers (GroupMask) 1 assets, 2 liabilities, 3 capital and reserves, 4 turnover,
5 cost of sales, 6 operating costs, 7 non-operating, 8 taxation, 9 other. Title
accounts (Postable N) form the tree via FatherNum/Levels. Demo accounts: 112000 bank,
114000 A/R control, 115000 inventory, 116000 input VAT, 211000 A/P control, 212000
goods received not invoiced, 216000 output VAT, 411000 sales revenue, 511000 COGS,
512000 price differences, 513000 inventory adjustments, 6xxxxx expenses, 711000/
712000 exchange gains/losses. Tax groups O1/O2/O0 (output) and I1/I2/I0 (input);
payment terms -1 cash, 1 net 30, 2 net 60, 3 end of next month.

### Not B1-verified
OACP column names are descriptive (B1's OACP has many more columns with other
names); everything else uses B1's documented table and field names.
