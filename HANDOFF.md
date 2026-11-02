# HANDOFF — continue this project on a new machine

This guide gets the **SAP FI/CO clone** running on a fresh system and resumes
development with Claude Code. (Technical project context for Claude lives in
[CLAUDE.md](CLAUDE.md), which a new Claude Code session reads automatically.)

---

## 1. Prerequisites

Install these first:

- **Python 3.12** (3.11+ works) — `python --version`
- **Git** — `git --version`
- **PostgreSQL 16+** (optional — SQLite works with zero setup) — `psql --version`
- **Claude Code** CLI/IDE extension, signed in
- A Chrome-family browser (only if you want Claude to screenshot the UI; the
  extension needs a one-time permission grant for `localhost`)

## 2. Clone the repository

```bash
git clone https://github.com/apexbinary/sap-fico.git
cd sap-fico
```

The repo is **private**. On the new machine, authenticate to GitHub when prompted
(Git Credential Manager opens a browser), or use a Personal Access Token / SSH.

## 3. Create the environment and install

```bash
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (Git Bash):   source .venv/Scripts/activate
# macOS / Linux:        source .venv/bin/activate

pip install -r requirements.txt
```

## 4. Create the database and demo data

### Option A — SQLite (fastest, zero config)
Nothing to install. Just seed:

```bash
python -m app.seed
```

This creates `sapfico.db` with client 100, company code 1000, chart of accounts
INT, and all customizing + demo master data.

### Option B — PostgreSQL
1. Create the role and database (one time; enter your `postgres` password when asked):
   ```bash
   psql -U postgres -f scripts/setup_postgres.sql
   ```
2. Copy the env template and point it at Postgres:
   ```bash
   cp .env.example .env
   # .env already contains:
   # DATABASE_URL=postgresql+psycopg://sapfico:sapfico@localhost:5432/sapfico
   ```
3. Build schema + demo data in Postgres:
   ```bash
   python -m app.seed
   ```

> `.env` is gitignored, so it won't exist after cloning — create it from
> `.env.example` only if you use Postgres. Without `.env`, the app uses SQLite.

## 5. Verify it works

```bash
python -m app.verify           # posts customer/vendor/GL documents, prints a balanced trial balance
python -m app.verify_assets    # asset acquisition + depreciation + bank statement + clearing
python -m app.verify_payments  # payments, cash discount, partial/residual items, F-32 clearing
python -m app.verify_payment_run  # F110 proposal, payment run, SEPA files, bank clearing
python -m app.verify_fsv       # balance sheet / P&L by FSV, balance carryforward
python -m app.verify_documents # park / post parked, reversal FB08, reset clearing FBRA
python -m app.verify_recurring # recurring entries (FBD1 + F.14 run)
python -m app.verify_dunning   # dunning run (F150) and notices
python -m app.verify_fx        # FX translation, valuation, realized differences
python -m app.verify_controlling  # CO documents, allocations, settlement, CO-PA
python -m app.verify_all       # all checks in order
```

Each should end with "OK ... the ledger balances."

## 6. Run the app

**With Docker** (needs Docker Desktop, and CPU virtualization enabled in the BIOS):

```bash
docker compose up -d --build
```

**Or locally:**

```bash
python -m uvicorn app.main:app --reload --port 8000
```

- Web UI: **http://localhost:8000/**
- API docs (OpenAPI/Swagger): **http://localhost:8000/docs**

## 7. Resume development with Claude Code

1. Open the `sap-fico` folder in Claude Code (or `cd sap-fico` and start the CLI).
2. Claude automatically reads **CLAUDE.md** for full project context.
3. Kick off with something like:

   > Read CLAUDE.md and HANDOFF.md. The FI/CO core is complete and verified.
   > Continue with the next roadmap item: payments & clearing (F110), then the
   > Financial Statement Version (balance sheet / P&L). Run `python -m app.seed`
   > and the verify scripts first to confirm the environment, then proceed.

Claude will have the architecture, conventions, demo config, and roadmap from
CLAUDE.md.

## What's already built (all verified)

Enterprise structure · G/L master · double-entry posting engine (BKPF/BSEG) ·
taxes (input/output VAT) · AR/AP sub-ledgers · Controlling (real-time FI→CO) ·
Asset Accounting (acquisition + straight-line depreciation) · Bank Accounting
(electronic statements + auto open-item clearing) · payments & clearing
(F-28/F-53/F-32/F-44/F-03, cash discount, tolerances, partial/residual) · automatic payment
program F110 (SEPA transfers + direct debits) · reporting (trial balance,
account balances, open items) · REST API · web UI.

## Roadmap (what to build next)

1. Payments: complete.
2. Financial Statement Version: done.
3. Done (reversal, parking, recurring entries, dunning, FX).
4. PostgreSQL + Alembic: done (compose override, migrations/).
5. Controlling (allocations, settlement, CO-PA): done. See CLAUDE.md for next candidates.

## Troubleshooting

- **`ModuleNotFoundError`** → activate the venv and `pip install -r requirements.txt`.
- **Schema looks stale (SQLite)** → stop the server, delete `sapfico.db`, re-run
  `python -m app.seed`. `create_all` does not ALTER existing tables.
- **Port 8000 busy** → run uvicorn with `--port 8001`.
- **Postgres connection refused** → ensure the service is running and the DSN in
  `.env` matches your host/port/credentials.
- **Can't push to GitHub** → re-authenticate Git (the credential manager will
  prompt in a browser), or set up an SSH remote.
