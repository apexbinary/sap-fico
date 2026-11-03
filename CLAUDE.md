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

## Localization

The demo company is **Demo Trading India Pvt Ltd** (Bengaluru, Karnataka, GSTIN 29...):
local currency **INR**, USD / EUR / GBP as foreign currencies, Indian chart of accounts,
**GST**. (Before commit d50ddc0 the demo was a German EUR company.)

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
  models/admin.py     OADM OCRN ORTT OFPR NNM1 OVTG OCTG, OSLP OPRJ OTRC OCRY OCST,
                      tax setup: OSTT OSTA STC1 OCHP OTCD
  models/finance.py   OACT OJDT JDT1 OACP (G/L account determination)
  models/users.py     OUSR users, USR3 general authorizations, OUSS sessions
  services/auth.py    password hashing, login / sessions, areas (PERMISSIONS), path -> area (ROUTES),
                      authorize(); app/main.py middleware checks every /api call; app/context.py
                      holds the logged-in user (journal UserSign, document UserSign, cockpit layout)
  api_users.py        /api/auth/login|logout|me|password, /api/users
  models/partners.py  OCRG OCRD OCPR CRD1
  models/inventory.py OITB OITM OMRC OWHS OITW OPLN ITM1
  models/banking.py   ORCT/OVPM (+RCT1/2/4, VPM1/2/4), OCHH checks for receipt, ODPS deposits,
                      ODSC/DSC1 house banks, OBNH/OBNK bank statements, OMTH/MTH1 external reconciliation
  models/documents.py the 15 document header/line pairs (OQUT/QUT1 ... OWTR/WTR1, built from
                      shared DocumentHeader/DocumentLine columns) and OINM warehouse journal
  services/admin.py   B1Error, numbering (NNM1), posting periods, exchange rates, due dates
  services/fxreval.py exchange rate differences: preview / run (BP open items unrealized + reversed,
                      FC G/L accounts permanent), OEXR/EXR1 runs (models/finance.py)
  services/cockpit.py cockpit data (KPIs, 12-month chart, aging, top 5, open documents, alerts);
                      api_cockpit.py with the per-user widget layout (OCPT)
  services/printing.py print data of sales / purchasing documents (GST layout, amount in words);
                      GET /api/documents/{obj}/{entry}/print?layout=; web/print.js renders the A4 page.
                      Print layouts RDOC (style classic / modern / compact, colour, options, one default
                      per type; seed creates STD-{obj} once), company logo OADM LogoImage (PNG / JPEG /
                      GIF data URL, magic bytes checked, 512 KB); api_printing.py /api/print-layouts,
                      /api/admin/company/logo; web view #/print-layouts
  services/gst_returns.py GSTR-1 / GSTR-3B of a month from OINV / ORIN / OPCH / ORPC (lines taken
                      again as posted: net after header discount, components rounded in the document
                      currency x rate); set_off (IGST credit first); JSON in the GSTN offline tool layout;
                      api_gst.py /api/gst-returns/gstr1|gstr3b[/json] (area FINRPT); web/gst.js
  services/paywiz.py  payment wizard: recommendation (OPWZ / PWZ1), selection, execution
  services/dunning.py dunning terms, preview / run, letters (models/banking.py ODWZ DWZ1 DWZ2)
  services/journal.py THE posting engine: post_entry / reverse_entry (OJDT/JDT1)
  services/reports.py trial balance, balance sheet, P&L (account tree)
  services/masterdata.py  create BP / item / warehouse (validation, OITW rows), price lookup
                      (own ITM1 price, else base list x factor; BP price = its price list)
  api_finance.py      /api/admin/*, /api/accounts, /api/journal-entries, /api/reports/*
  services/documents.py  document engine: DEFS (object types, copy-from bases), create /
                      cancel / close, stock moves (receive/issue/revalue -> OINM), automatic JEs
  api_documents.py    /api/documents/{obj}*, /api/documents/types, /api/inventory/journal
  services/tax.py     tax components (split), GST kind, place of supply, tax setup maintenance,
                      tax code determination (OTCD)
  api_tax.py          /api/tax/setup, /api/tax/types|authorities|codes|hsn|determination
  services/banking.py payments (open items, apply / on account / reconcile, FC means, cancel), deposits
  api_banking.py      /api/payments/{incoming|outgoing}*, /api/payments/open-items, /api/checks, /api/deposits
  services/bankrec.py bank statements (entry, CSV import), row processing, external reconciliation
                      (manual / automatic / cancel), bank reconciliation report
  api_bankrec.py      /api/house-banks, /api/banks, /api/bank-statements*, /api/bank-reconciliation*
  api_masterdata.py   /api/partners*, /api/partner-groups, /api/items*, /api/item-groups,
                      /api/warehouses, /api/price-lists
  seed.py             demo company "Demo Trading India Pvt Ltd" (INR, GST), chart of accounts, periods 2025-2027
  verify_*.py         end-to-end checks; verify_all runs them all
web/                  index.html, styles.css, app.js (shell, typed field builder, journal entries,
                      documents, reports), masterdata.js (accounts, BPs, items, warehouses, setup),
                      banking.js (payments, deposits), tax.js (tax setup),
                      bankrec.js (bank statements, bank reconciliation), fxreval.js (exchange rate differences),
                      dunning.js (dunning wizard, letters), paywiz.js (payment wizard),
                      cockpit.js (home screen; SVG charts, no chart library),
                      users.js (login, user menu, nav by authorization, users),
                      print.js (print preview, Print Layouts screen with the company logo)
                      Router: a link to the current hash re-renders; list + form screens (FORM_VIEWS)
                      scroll to the form and focus its first field on ?new / ?id / ?code / ?rule
                      index.html loads scripts / styles with ?v=N: raise N when they change
docs/field-coverage.md  B1 field register: every form, column, input type, status
```

### Users and authorizations (keep invariant)
- Every /api path needs a session except /api/auth/login|logout; the web client (/), /health
  and /docs stay public. Add every new API prefix to auth.ROUTES (unknown paths need ADMIN);
  documents map by object type to SALES / PURCH / INV.
- GET of shared reference data (auth.SHARED_READS) is allowed to every logged-in user.
- Seeded users (created once): manager (superuser, password B1_MANAGER_PASSWORD, default
  "manager"), sales and accountant (demo, password B1_DEMO_PASSWORD or sales2026 /
  account2026). Change them after the first login.
- Checks that call services directly need no login; verify_users tests the HTTP layer.

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
- Foreign currency: a document has DocCur / DocRate (rate of the posting date); line
  prices and totals are in the document currency, LC = FC x rate per line (net and
  VAT rounded separately); the partner line carries the FC total and its open FC
  amount (JDT1 BalFcDeb/BalFcCred). Copied lines keep the base currency; inventory
  documents are LC only; a BP with a fixed currency takes that currency or LC.
- An FC item paid in its currency (or an FC credit memo reconciled with its invoice)
  is matched by FC amount; each side's LC reduces proportionally and the LC
  difference is a realized exchange difference (gain / loss account).

### Tax (keep invariant)
- A tax code (OVTG) posts either its own rate to its account, or its components (STC1):
  each component's tax authority (OSTA) gives the output / input account; every
  component is rounded on its own and the line tax is their sum.
- Line tax code: entered > base line > first matching OTCD rule > item default > BP default.
- GST: company state (OADM State) vs ship-to (sales) / bill-to (purchasing) state decides
  intra (CGST + SGST) or inter (IGST); a code of the wrong kind is switched to the one of
  the same rate, except when the deciding OTCD rule has its own supply condition.
- A tax code used in postings keeps its category, rate and components.
- Tax setup data is maintained by users: the seed creates it once.

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

### Payment wizard (keep invariant)
- Recommendation = open partner lines due up to a date: vendors' credits are paid (+1),
  their debits offset (-1) (customers the other way); discount = allowed on the payment date.
- Execute creates one payment per BP with a positive net, in one transaction; an item whose
  open amount changed since the recommendation makes the run fail (create a new run).

### Dunning (keep invariant)
- Open customer items carry JDT1 DunnLevel / DunDate. A run on a date raises an item to the
  highest DUT1 level whose days <= days overdue — one step per run unless "highest"; items
  dunned within ODUT DaysBtwn are skipped; a letter needs the level's minimum balance.
- Interest = open x rate x days / 365 since the last dunning (since the due date first);
  optional posting: customer open item vs OACP DunIntrstAcct (721000) / DunFeeAcct (723000).

### Cash discount and installments (keep invariant)
- Invoices (13 / 18) on terms with installments (OCTG InstNum + CTG1) get INV6 / PCH6 rows and
  one partner JDT1 line per installment (same order); the last installment takes the rest.
  `documents.installment_for_line` maps a partner line to its installment.
- Cash discount (OCDC / CDC1 via OCTG CdcCode): allowed % by days from the document date;
  a discount settles the item completely (sum applied + discount = open); the partner line
  is posted with paid + discount, the discount on OACP CashDiscAlwAcct / CashDiscRcvAcct.
- Credit memos copied from installment invoices are not auto-reconciled (use a payment).

### GST returns (keep invariant)
- Registered = GSTIN on the bill-to address (else OCRD LicTradNum) and GstType not U; export =
  bill-to country not the company country (POS 96). B2CL above 1,00,000 (inter-state, unregistered).
- Documents with only nil-rated lines go to Table 8 only; exports keep their 0 % lines.
- GSTR-3B liability / ITC must equal the output / input tax of the journal for the month
  (checked in verify_gstreturns).

### Exchange rate differences (keep invariant)
- BP open FC items: difference (open FC x rate of the date - open LC) posted on the control
  account against unrealized gain / loss (OACP UnrlzGainAcct / UnrlzLossAcct), reversed on the
  reversal date; partner lines and balances are not touched, so payments still realize the
  full difference. One BP run per date.
- G/L accounts with ActCurr in FC: FC balance x rate - LC balance, posted permanently against
  the realized gain / loss accounts.

### Bank reconciliation (keep invariant)
- A statement's opening balance is the previous closing balance; closing = opening + in - out.
- An external reconciliation matches statement rows (in - out) with journal lines of the same
  G/L bank account (debit - credit) when the sums agree; JDT1 ExtrMatch / OBNK BankMatch
  hold its number, canceling clears them.
- Report: balance per bank + in transit - outstanding = balance per books + bank credits -
  bank debits not booked (difference 0 when the opening balances agree).

### Chart of accounts
Drawers (GroupMask) 1 assets, 2 liabilities, 3 capital and reserves, 4 turnover,
5 cost of sales, 6 operating costs, 7 non-operating, 8 taxation, 9 other. Title
accounts (Postable N) form the tree via FatherNum/Levels. Demo accounts: 112000 bank,
114000 sundry debtors (A/R control), 115000 stock-in-trade, 116100/116200/116300 input
CGST/SGST/IGST (116000 other input tax), 211000 sundry creditors (A/P control), 212000
goods received not invoiced, 216100/216200/216300 output CGST/SGST/IGST (216000 other),
411000 sales, 511000 COGS, 512000 price variance, 513000 stock adjustments, 6xxxxx
expenses, 711000/712000 exchange gain/loss, 713000/714000 unrealized exchange gain/loss,
721000 interest income, 615000 cash discount allowed, 722000 cash discount received,
723000 dunning fees. Dunning term STD (7 / 30 / 60 days, fees 0 / 250 / 500, 18 % p.a.).
Payment terms 4 = 2 % 10 days / 1 % 20 days, net 30; 5 = 3 installments 30/60/90. Tax codes OCS5/12/18/28 (output CGST + SGST),
OIG5/12/18/28 (output IGST), ONIL, and the input equivalents ICS.., IIG.., INIL;
payment terms -1 cash, 1 net 30, 2 net 60, 3 end of next month.
BP groups 100 Customers, 101 Wholesale, 102 Vendors; customers C10000-C30000,
vendors V10000/V20000. Price lists 1 Base Price, 2 Wholesale (= base x 0.9),
3 Purchase Price. Warehouses 01 General, 02 Outlet Berlin. Item groups 100
Printers, 101 Supplies, 102 Services; items A00001-A00004, C00001/C00002,
S00001 (non-inventory service).

### Not B1-verified
OACP column names are descriptive (B1's OACP has many more columns with other
names). RDOC keeps template options in descriptive columns (Style, Color, Show*, Footer,
Default) instead of B1's Print Layout Designer template; OADM LogoImage, OCPT and OUSS are
not B1-verified either. Everything else uses B1's documented table and field names.
