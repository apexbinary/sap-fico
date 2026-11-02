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
| Sales A/R and purchasing A/P documents | planned |
| Inventory — master data: items, item groups (G/L accounts), warehouses, stock per warehouse, price lists | ✅ |
| Inventory — goods receipt / issue / transfer, moving-average cost | planned |
| Banking | planned |

## Run

```bash
docker compose up -d --build        # http://localhost:8000  (API docs: /docs)
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build   # on PostgreSQL
```

Locally: `pip install -r requirements.txt`, `python -m app.seed`,
`python -m uvicorn app.main:app --reload`. Checks: `python -m app.verify_all`
(on a scratch database).
