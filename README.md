# SAP Business One Clone

An ERP for small and midsize companies modelled on **SAP Business One**: financials,
business partners, sales (A/R), purchasing (A/P), inventory and banking. Database
tables and fields use B1's names (OACT, OJDT/JDT1, OCRD, OITM, ORDR/RDR1, OINV/INV1,
ORCT, ...). Independent clean-room implementation; "SAP" and "SAP Business One" are
trademarks of SAP SE.

| Module | Status |
|---|---|
| Administration — company, currencies, exchange rates, posting periods, numbering series, tax groups, payment terms | ✅ |
| Financials — chart of accounts (tree), journal entries, reversal, trial balance, balance sheet, P&L | ✅ |
| Business partners — master data, groups, contact persons, control accounts, balances and open items | ✅ |
| Sales A/R and purchasing A/P documents — quotation, order, delivery, return, invoice, credit memo (and purchasing equivalents), copy-from / copy-to, automatic journal entries, cancel / close | ✅ |
| Inventory — master data: items, item groups (G/L accounts), warehouses, stock per warehouse, price lists | ✅ |
| Inventory — goods receipt / issue / transfer, moving-average cost, inventory audit report (OINM) | ✅ |
| Foreign currency — documents and journal entries in foreign currencies, open FC amounts, realized exchange differences on payment and reconciliation | ✅ |
| India — INR company, GST (CGST / SGST / IGST by place of supply), GSTIN, HSN / SAC, GST tax report | ✅ |
| Printed documents — GST layout (tax invoice, credit note, delivery challan, orders ...) with HSN summary and amount in words, print / PDF | ✅ |
| Aging, account statements, cash flow | ✅ |
| Fixed assets — classes, capitalization, straight-line / WDV depreciation runs, retirement, asset register | ✅ |
| Period-end closing — P&L accounts of a year to retained earnings, periods locked, cancel | ✅ |
| Recurring postings — monthly / quarterly / ... journal entry templates with catch-up execution | ✅ |
| Budgets — scenarios, monthly account budgets, budget vs. actual, budget check of postings | ✅ |
| Cost accounting — dimensions, profit centers, distribution rules on journal and document lines, profit center report | ✅ |
| Inventory counting and posting, item groups maintenance | ✅ |
| Batches and serial numbers — on every stock move, automatic selection by expiry, transfers, returns, history | ✅ |
| Units of measure — documents in sales / purchase units (packs, reams ...), stock in inventory units | ✅ |
| Down payments — A/R and A/P down payment requests, paid by payments, drawn (fully or partly) on the final invoices | ✅ |
| Freight / additional expenses on documents (taxed, posted, in GST returns and e-invoices) and the credit / commitment limit check (warn or block) | ✅ |
| Withholding tax (TDS) — sections with thresholds, 206AA rate without PAN, deduction on A/P invoices, reversal on credit memos, TDS report with due dates | ✅ |
| E-invoicing and e-way bills — INV-01 JSON, IRN and QR code (test mode or import of the IRP response), e-way bill with validity and Part B, cancel within 24 hours | ✅ |
| GST returns — GSTR-1 (B2B, B2CL, B2CS, exports, credit notes, nil, HSN, documents issued) and GSTR-3B (with ITC set-off), JSON for the GST portal | ✅ |
| Print layouts — several per document type (classic / modern / compact, accent colour, options, footer), default layout, company logo | ✅ |
| Users and authorizations — login, users, superusers, full / read-only / no authorization per area, enforced on every API call | ✅ |
| Cockpit — KPI tiles, sales / purchase chart, aging, top 5, open documents, alerts, common functions, per-user layout | ✅ |
| Payment wizard — batch payment of due vendor items or collection from customers, transfer or check, cash discount, selection | ✅ |
| Dunning — dunning terms and levels, dunning wizard, interest on arrears and fees, printable letters | ✅ |
| Cash discount and installments — discount tiers on payment terms, discount on payment, installment invoices paid per installment | ✅ |
| Exchange rate differences — revaluation of open FC items (unrealized, auto-reversed) and FC G/L accounts | ✅ |
| Bank statements and reconciliation — house banks, statements (manual or CSV import), processing rows into payments / journal entries, automatic and manual external reconciliation, bank reconciliation statement | ✅ |
| Tax setup — tax types, tax authorities, tax codes with components, HSN / SAC codes, tax code determination rules | ✅ |
| Banking — incoming / outgoing payments (cash, bank transfer with charges, checks), partial payments, payments on account and reconciliation, account payments, foreign-currency payments, check and cash deposits, cancellation | ✅ |

## Run

```bash
docker compose up -d --build        # http://localhost:8000  (API docs: /docs)
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build   # on PostgreSQL
```

Log in as `manager` / `manager` (superuser; demo users `sales` / `sales2026` and `accountant` / `account2026`) and change the passwords under the user menu.

Field coverage against SAP Business One: [docs/field-coverage.md](docs/field-coverage.md).

Locally: `pip install -r requirements.txt`, `python -m app.seed`,
`python -m uvicorn app.main:app --reload`. Checks: `python -m app.verify_all`
(on a scratch database).
