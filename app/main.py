"""FastAPI application entry point (API + web UI)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import router
from app.api_assets_bank import router as aa_bank_router
from app.api_payments import router as payments_router
from app.config import settings
from app.database import create_all
from app.masterdata import router as master_router

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="A from-scratch SAP FI/CO finance core (General Ledger, sub-ledgers, "
    "taxes, Controlling) with authentic SAP table/field names.",
)
app.include_router(router, prefix="/api")
app.include_router(master_router, prefix="/api")
app.include_router(aa_bank_router, prefix="/api")
app.include_router(payments_router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    create_all()


@app.get("/health", tags=["System"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": __version__, "db": settings.database_url.split("://")[0]}


# Serve the single-page web UI at the root. Mounted last so /api and /health win.
if _WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
