"""FastAPI application entry point (REST API + web client)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api_bankrec import router as bankrec_router
from app.api_banking import router as banking_router
from app.api_documents import router as documents_router
from app.api_finance import router as finance_router
from app.api_fxreval import router as fxreval_router
from app.api_masterdata import router as masterdata_router
from app.api_tax import router as tax_router
from app.config import settings
from app.database import init_db

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title=settings.app_name, version=__version__,
              description="An SAP Business One style ERP: financials, business partners, sales, purchasing, "
                          "inventory and banking, with B1 table and field names.")
app.include_router(finance_router, prefix="/api")
app.include_router(masterdata_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(banking_router, prefix="/api")
app.include_router(bankrec_router, prefix="/api")
app.include_router(fxreval_router, prefix="/api")
app.include_router(tax_router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health", tags=["System"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": __version__, "db": settings.database_url.split("://")[0]}


if _WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
