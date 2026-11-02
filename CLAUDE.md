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
   copy-from. **Done** (BP master data and all 12 marketing documents). (quotation → order → delivery → invoice → credit memo, and the
   purchasing equivalents).
3. Inventory — items, warehouses, price lists, goods receipt/issue/transfer,
   moving-average cost, automatic stock postings. **Done.**
4. Banking — incoming/outgoing payments (cash, transfer, check), payments on
   account, BP balances. **Done** (plus check/cash deposits, account payments,
   foreign-currency payment means).

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
  models/admin.py     OADM OCRN ORTT OFPR NNM1 OVTG OCTG, OSLP OPRJ OTRC OCRY OCST
  models/finance.py   OACT OJDT JDT1 OACP (G/L account determination)
  models/partners.py  OCRG OCRD OCPR CRD1
  models/inventory.py OITB OITM OMRC OWHS OITW OPLN ITM1
  models/banking.py   ORCT/OVPM (+RCT1/2/4, VPM1/2/4), OCHH checks for receipt, ODPS deposits
  models/documents.py the 15 document header/line pairs (OQUT/QUT1 ... OWTR/WTR1, built from
                      shared DocumentHeader/DocumentLine columns) and OINM warehouse journal
  services/admin.py   B1Error, numbering (NNM1), posting periods, exchange rates, due dates
  services/journal.py THE posting engine: post_entry / reverse_entry (OJDT/JDT1)
  services/reports.py trial balance, balance sheet, P&L (account tree)
  services/masterdata.py  create BP / item / warehouse (validation, OITW rows), price lookup
                      (own ITM1 price, else base list x factor; BP price = its price list)
  api_finance.py      /api/admin/*, /api/accounts, /api/journal-entries, /api/reports/*
  services/documents.py  document engine: DEFS (object types, copy-from bases), create /
                      cancel / close, stock moves (receive/issue/revalue -> OINM), automatic JEs
  api_documents.py    /api/documents/{obj}*, /api/documents/types, /api/inventory/journal
  services/banking.py payments (open items, apply / on account / reconcile, FC means, cancel), deposits
  api_banking.py      /api/payments/{incoming|outgoing}*, /api/payments/open-items, /api/checks, /api/deposits
  api_masterdata.py   /api/partners*, /api/partner-groups, /api/items*, /api/item-groups,
                      /api/warehouses, /api/price-lists
  seed.py             demo company "Demo Trading Ltd" (EUR), chart of accounts, periods 2025-2027
  verify_*.py         end-to-end checks; verify_all runs them all
web/                  index.html, styles.css, app.js (shell, typed field builder, journal entries,
                      documents, reports), masterdata.js (accounts, BPs, items, warehouses, setup),
                      banking.js (payments, deposits)
docs/field-coverage.md  B1 field register: every form, column, input type, status
```

### Fields and UI (keep invariant)
- **No standard B1 field of a built feature is silently missing.** Every form is
  listed in `docs/field-coverage.md` (column, input type, status); a field is either
  implemented or listed as excluded with the reason. Update the register with
  every feature.
- **The UI keeps B1's field types**: numbers are numeric inputs, B1 dropdowns are
  dropdowns (fed by their tables: OCRY/OCST, OSLP, OPRJ, OTRC, OMRC, OCTG, OPLN,
  OVTG, OWHS, OCRN), checkboxes are checkboxes, dates are date pickers, BP / item /
  G/L account are selection lists. Forms declare fields with `fieldsHtml` /
  `readFields` (typed values) in app.js; do not hand-build inputs.
- PATCH endpoints use `apply_changes` (an empty value never overwrites a NOT NULL
  column).
- OJDT AutoStorno/StornoDate = B1's "Reverse" checkbox (reversal posted on that
  date); a reversal entry is recognised by StornoToTr (`is_reversal` in the API).
- The seed runs on every start: data users maintain (company, periods and their
  lock, accounts, payment terms, price lists, warehouses, BPs, items, prices,
  lookup tables) is created once and never overwritten; only reference data
  without an edit screen is merged.

### Posting rules (keep invariant)
- Every posting is one OJDT/JDT1 journal entry via `journal.post_entry`.
- A business partner line posts to the partner's control account and keeps the
  partner code in ShortName; its open amount is BalDueDeb/BalDueCred.
- Only active (Postable Y), unfrozen accounts; manual entries never post a
  control account directly.
- Balanced in local currency; posting date in an unlocked period (OFPR); due date
  and document date inside the period's due / document date ranges.
- OACT-CurrTotal (and OCRD-Balance) are updated with each entry.
- Document numbers come from the default NNM1 series of the object type;
  NNM1-NextNumber and exchange rates are runtime data: the seed creates them
  once and never resets them.
- Seed inserts flush one by one, parents first (PostgreSQL enforces FKs).
  The seed runs on every container start: OCRD (Balance), OITM/OITW (stock,
  cost) and ITM1 prices are created once and never re-merged.
- An inventory item has an OITW row in every warehouse (created with the item
  or the warehouse). G/L accounts for item postings come from the item group
  (OITB, GLMethod C); valuation is moving average (OITM-AvgPrice).

### Documents (keep invariant)
- Copy-from: a line references BaseType/BaseEntry/BaseLine; the base line's OpenQty
  drops, LineStatus C at zero, DocStatus C when all lines are closed (invoices close
  when paid instead). Orders commit stock (IsCommited), purchase orders OnOrder.
- Moving average: OITM-StockValue is the exact value, AvgPrice = StockValue/OnHand;
  issues at average (the last unit takes the remaining value); every change writes
  an OINM row. Invariant (checked in verify_documents): inventory account balance =
  sum of StockValue; OITW quantities = OITM; OINM net quantity = OnHand.
- A/P invoice price differences revalue stock still on hand, else price differences.
- A credit memo copied from one invoice is reconciled with it (PaidToDate, BalDue).
- Cancel: only without target documents / payments; reverses stock at original
  values and the JE (B1 creates a separate cancellation document; we mark the
  original CANCELED=Y and link the reversal JE).
- Document currency is the local currency for now (DocCur/DocRate kept).

### Banking (keep invariant)
- A payment pays open partner lines (JDT1 with BalDue) of its BP in LC; the means are
  in the payment currency (LC = FC x ORTT rate); a small FC mismatch (<= 0.5 %) is an
  exchange difference, otherwise the rest must be "payment on account".
- Applied amounts reduce BalDueDeb/BalDueCred of the item and the payment's own
  line by the same amount, plus the item document's PaidToDate (closes at 100 %) or
  the paid payment's OpenBal. Invariant (verify_banking): every BP balance = sum of
  its open items.
- A payment with items but no means posts no JE (pure reconciliation).
- Cancel: refused if a check is deposited or the amount on account was used; items
  reopen, the JE is reversed. Documents used in an active payment cannot be canceled.

### Chart of accounts
Drawers (GroupMask) 1 assets, 2 liabilities, 3 capital and reserves, 4 turnover,
5 cost of sales, 6 operating costs, 7 non-operating, 8 taxation, 9 other. Title
accounts (Postable N) form the tree via FatherNum/Levels. Demo accounts: 112000 bank,
114000 A/R control, 115000 inventory, 116000 input VAT, 211000 A/P control, 212000
goods received not invoiced, 216000 output VAT, 411000 sales revenue, 511000 COGS,
512000 price differences, 513000 inventory adjustments, 6xxxxx expenses, 711000/
712000 exchange gains/losses. Tax groups O1/O2/O0 (output) and I1/I2/I0 (input);
payment terms -1 cash, 1 net 30, 2 net 60, 3 end of next month.
BP groups 100 Customers, 101 Wholesale, 102 Vendors; customers C10000-C30000,
vendors V10000/V20000. Price lists 1 Base Price, 2 Wholesale (= base x 0.9),
3 Purchase Price. Warehouses 01 General, 02 Outlet Berlin. Item groups 100
Printers, 101 Supplies, 102 Services; items A00001-A00004, C00001/C00002,
S00001 (non-inventory service).

### Not B1-verified
OACP column names are descriptive (B1's OACP has many more columns with other
names); everything else uses B1's documented table and field names.
