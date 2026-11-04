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
  models/documents.py the 17 document header/line pairs (OQUT/QUT1 ... OWTR/WTR1, built from
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
  services/gst_itc.py ITC reversals / reclaims (journal entries), GSTR-2B JSON reconciliation with A/P documents;
                      /api/gst-itc/reversals (area JE), POST /api/gst-returns/gstr2b/reconcile; web/gst.js (#/itc-reversals)
  services/gst_filing.py filing status OGSR (snapshot of the filed return), lock checks, amend(); GSTR-1 tables
                      9A / 9C / 10 in gst_returns._amendments; /api/gst-returns/{ret}/file|unfile, /api/documents/{obj}/{entry}/amend
  services/edocs.py   e-invoice (INV-01 JSON, IRN = SHA-256 of GSTIN+FY+type+no., QR via segno) and
                      e-way bill (validity, Part B); test mode makes IRN / EWB here, live mode imports
                      the portal response; models/edocs.py EDOC register, ADM1 company address;
                      api_edocs.py /api/documents/{obj}/{entry}/edocs|einvoice*|ewaybill*, /api/e-documents,
                      /api/admin/e-documents; web/edocs.js (document panel, #/e-documents)
  services/withholding.py TDS on A/P invoices / credit memos: OWHT codes, CRD4 per vendor, PCH5 / RPC5
                      rows, thresholds per financial year, report; api_withholding.py /api/withholding-tax,
                      /api/reports/tds; web/tds.js (#/withholding-tax, #/tds-report)
                      TCS on A/R (INV5 / RIN5), TDS on advances (VPM5), challans OTCH, 26Q / 27EQ, 16A / 27D;
                      web/tds.js #/tds-challans, #/tds-returns, #/tds-certificate
  services/credit.py  credit / commitment limit check of customers (OADM CrdLmtChk / CmtLmtChk /
                      CrdLmtDocs); documents.create_document compares the exposure before / after
  api_freight.py      freight / additional expenses OEXD (web/freight.js); document freight QUT3 ... RPC3
  down payments       documents.DEFS 203 / 204 (kind downpayment, not posted); banking.DownPaymentPay
                      (RCT2 / VPM2 InvType 203 / 204, amount on account); documents._draw_down_payments
                      (INV9 / PCH9) and _undraw_down_payments; GET /api/documents/{203|204}/open-down-payments
  services/batches.py batch / serial numbers (models/batches.py OBTN OSRN OBTQ OSRQ OITL ITL1): allocate()
                      runs on the document's warehouse journal rows before the journal is posted;
                      reverse() on cancel; api_batches.py /api/batches[/history]; web/batches.js
  services/counting.py inventory counting OINC / INC1 and inventory posting OIQR / IQR1 (models/counting.py):
                      differences post through a goods receipt (surplus) / goods issue (shortage);
                      api_counting.py /api/inventory/counting*; web/counting.js; item groups:
                      POST / PATCH /api/item-groups, web/itemgroups.js
  services/costacct.py cost accounting (models/costacct.py ODIM OPRC OOCR OCR1): JDT1 ProfitCode / OcrCode2-5,
                      document lines OcrCode-5; _Ctx.post keeps a line's rules on revenue / expense
                      accounts; profit center report; api_costacct.py; web/costacct.js
  services/budgets.py budgets OBGS / OBGT / BGT1 (models/budgets.py), budget vs. actual, budget check called by
                      journal.post_entry (OADM BgtCheck B: expense account over the year's main budget);
                      api_budgets.py /api/budgets*, /api/admin/budget-check; web/budgets.js
  services/recurring.py recurring postings ORCR / RCR1 (models/recurring.py): due(), execute() posts journal
                      entries per due date (catch-up, Day = posting day, 31 = month end); api_recurring.py;
                      web/recurring.js
  services/closing.py period-end closing: TransType -3 entry on 31-12 (P&L accounts to the closing account),
                      lock / cancel; reports.profit_and_loss excludes -3 unless include_closing (the
                      balance sheet includes it); api_closing.py; web/closing.js
  services/assets.py  fixed assets (models/assets.py OACS OFAS FAS1, not B1-verified): capitalize, monthly
                      depreciation run (SL / WDV) / reverse, retire; api_assets.py; web/assets.js
  services/bp_reports.py aging (customers / vendors), account statement, cash flow (Finanse accounts);
                      /api/reports/aging|statement|cash-flow; web/bpreports.js
  services/approvals.py approval procedures OWST / OWTM (WTM1-4) / OWDD / WDD1 (models/approvals.py): the
                      document API (api_documents.create_document) asks approvals.check, which validates
                      the document (create + rollback) and holds it; build_request replays it on add
  services/alerts.py  system alerts OALT / ALT1, evaluated per user; /api/alerts; web/approvals.js (bell)
  services/dataimport.py data import (partners, items, prices, opening balances, opening stock) in one outer
                      transaction with a savepoint per row (own engine: SQLite BEGIN / SAVEPOINT fix);
                      api_import.py /api/import/*, /api/export/xlsx (openpyxl); web/dataimport.js adds
                      the "Export to Excel" button to every page with tables (route() -> addExportButton)
  services/production.py BOMs OITT / ITT1 and production orders OWOR / WOR1 (models/production.py): issue /
                      receipt via goods issues / receipts against OACP WipAcct, close -> WipVarAcct
  services/mrp.py     MRP: net requirements level by level through production BOMs, recommendations ->
                      purchase / production orders; api_production.py; web/production.js
  services/crm.py     CRM: OOST stages, OOPR / OPR1 opportunities, OCLG activities (models/crm.py), pipeline;
                      api_crm.py /api/crm/*; web/crm.js (opportunities, activities, calendar, pipeline)
  services/service.py service: OINS equipment cards (from deliveries of serial numbers), OCTR / CTR1 contracts,
                      OSCL service calls with contract deadlines (models/service.py); api_service.py /api/service/*
                      (area SERVICE); web/service.js (service calls, contracts, equipment cards)
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
- Reverse charge (OVTG RevCharge Y) / import of goods (I): input codes only; the vendor is not charged the
  tax (not in VatSum / DocTotal); each component posts Dr input account / Cr OSTA RvsChrgAct (import: Cr OACP
  ImpTaxAcct without tax group). Import IGST is on BoEValue (LC) when given. GSTR-3B: 3.1(d) and liability
  include reverse charge (paid in cash, never from ITC); ITC 4A(1) imports, 4A(2) foreign RCM, 4A(3) RCM.
- Non-deductible input tax (OVTG NonDedct %): the vendor charges the full tax; per component the
  non-deductible part posts to NonDedAcc. GSTR-3B 4(A) has the full tax, 4(B)(1) the blocked part.
- ITC reversals are journal entries with Ref3 ITC:B1 / ITC:B2 / ITC:D1 on the input tax accounts
  (services/gst_itc.py); reports.tax_report counts their input tax lines, so 4(C) net ITC = journal
  input tax. A reclaim (D1) cannot exceed the temporary reversals (B2) still open.
- Filed GST months (OGSR, services/gst_filing.py) are locked: no A/R document in a month with GSTR-1 or
  GSTR-3B filed, no A/P document / ITC entry in a GSTR-3B month. A/R documents of a GSTR-1 month are amended
  (replacement in an open month with AmndEntry, original canceled on that date); A/P documents are canceled
  with a CancelDate in an open month. A document belongs to its month unless canceled in that month; earlier
  documents canceled in a month are negative in its GSTR-3B (journal invariant holds).
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

### Freight and credit limit (keep invariant)
- Freight lines have no header discount and their own tax code (GST kind switched like lines);
  DocTotal / VatSum include them; invoices / credit memos post them on OEXD RevAcct / ExpnsAcct.
  GST returns and e-invoices take freight as a service with the OEXD SAC code.
- Credit check: exposure = balance + DNotesBal + OrdersBal; a document is checked only when it
  raises the exposure (copied lines do not). Warn mode needs confirm_credit; block refuses.

### Batches and serial numbers (keep invariant)
- Every stock move (OINM row with quantity) of a managed item writes one OITL log with ITL1 lines;
  OBTQ / OSRQ per warehouse always add up to OITW OnHand (checked in verify_batches).
- Receipts need the numbers (or take the base line's); issues take named, base or automatic
  (earliest expiry, not expired) numbers; serial numbers are unique units.

### Cost accounting (keep invariant)
- A rule code belongs to one dimension (position 1-5 in ocr_codes); only active dimensions / rules.
  Documents keep the line's rules only on revenue / expense accounts (ActType I / E); reversals
  carry the rules. Each profit center has a direct rule with its code (100 %).

### Units of measure (keep invariant)
- A line's Quantity / OpenQty / price are in its unit (unitMsr); NumPerMsr = inventory units per
  unit (OITM NumInSale on sales, NumInBuy on purchasing, 1 on inventory documents; copied lines
  keep the base line's). Stock moves, commitments, StockPrice and LastPurPrc are per inventory unit.

### Down payments (keep invariant)
- A request is not posted. A payment that pays it keeps the amount on account (OpenBal) and raises
  the request's PaidToDate; drawing on an invoice reconciles the invoice's partner line(s) with
  that open payment line (oldest payment first) via banking._apply_to_item — no journal entry, so
  every BP balance still equals its open items. Canceling the invoice releases the draws; a payment
  whose amount on account was drawn cannot be canceled.

- A down payment invoice (DpmType I) posts: partner (gross) / OACP DpmClrSal 219000 or DpmClrPur 119000 (net) /
  tax; it is paid as an open item (banking.INVOICE_TYPES has 203 / 204; it stays open until drawn). Drawing it
  (in full, when paid) on an invoice reverses its non-partner JE lines in the invoice's JE, lowers the
  invoice's partner line by the gross and adds it to PaidToDate / DpmAmnt (INV9 row without PayTrans).
  GSTR-1 11A / 11B and GSTR-3B take the advance and, negative, its adjustment.

### Withholding tax / TDS (keep invariant)
- A/P invoice of a vendor with WTLiable Y: base = net LC excl. GST, TDS in whole rupees; vendor
  line = DocTotal = gross - WTSum; the code's account (217000 TDS payable) credited. Every invoice
  of such a vendor writes PCH5 rows (also with 0 TDS) so the year's base counts for thresholds.
- Threshold type A: once the year's base crosses ThrAnnual, TDS = rate x year's base - TDS so far.
- A credit memo copied from an A/P invoice reverses that invoice's TDS in proportion (RPC5).
- TCS (OWHT WTKind C, customers): A/R DocTotal = gross + TCS (INV5 / RIN5), base gross incl. GST (BaseType G);
  GSTR-1 invoice value excludes it. TDS on advances (VPM5): cash on account grossed up, vendor debited before
  TDS; A/P invoices deduct their TDS less withholding.advance_open (AdvAdj); year-to-date TDS = WTAmnt + AdvAdj.
- Challans (OTCH): Dr payable (+ 619000 interest / fee) / Cr bank, rows get ChallanAbs; deposited rows block
  canceling their document / payment. 26Q / 27EQ list rows with tax only.

### E-documents (keep invariant)
- A document with an active IRN or e-way bill cannot be canceled (documents._cancel asks
  edocs.blocks_cancel); an IRN is canceled only after its e-way bill, within 24 hours.
- An imported IRP response must carry the IRN computed for the document.

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
Default) instead of B1's Print Layout Designer template; OADM LogoImage / EInvoice /
EWayBill / EDocMode, EDOC, OCPT, OUSS, OCRD PANNo and the OWHT India columns (Section, Thr*,
RateNoPAN), OEXD SACCode, the OADM credit check columns, OVTG RevCharge / NonDedAcc usage, OSTA RvsChrgAct and the bill of entry
columns (BoENum / BoEDate / BoEValue / PortCode), OGSR, AmndEntry, DpmType, OWHT WTKind, VPM5, AdvAdj, OTCH and
OADM TANNo are not B1-verified either. Everything else uses B1's documented table and field names.
