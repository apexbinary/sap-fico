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
