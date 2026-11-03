"""FastAPI application entry point (REST API + web client)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api_bankrec import router as bankrec_router
from app.api_banking import router as banking_router
from app.api_cockpit import router as cockpit_router
from app.api_printing import router as printing_router
from app.api_gst import router as gst_router
from app.api_documents import router as documents_router
from app.api_dunning import router as dunning_router
from app.api_finance import router as finance_router
from app.api_fxreval import router as fxreval_router
from app.api_masterdata import router as masterdata_router
from app.api_paywiz import router as paywiz_router
from app.api_tax import router as tax_router
from app.api_users import router as users_router
from app.api_users import token_of
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
app.include_router(dunning_router, prefix="/api")
app.include_router(paywiz_router, prefix="/api")
app.include_router(cockpit_router, prefix="/api")
app.include_router(printing_router, prefix="/api")
app.include_router(gst_router, prefix="/api")
app.include_router(tax_router, prefix="/api")
app.include_router(users_router, prefix="/api")

PUBLIC_API = {"/api/auth/login", "/api/auth/logout"}


@app.middleware("http")
async def _authorize(request: Request, call_next):
    """Every /api call needs a logged-in user (B1SESSION cookie or bearer token) with the
    general authorization of the area; the user is kept in the request context."""
    path = request.url.path
    if not path.startswith("/api/") or path in PUBLIC_API:
        return await call_next(request)
    from app import context
    from app.database import SessionLocal
    from app.services import auth

    s = SessionLocal()
    try:
        user = auth.user_for_token(s, token_of(request))
        if user is None:
            return JSONResponse({"detail": "Not logged in"}, status_code=401)
        try:
            auth.authorize(s, user, request.method, path)
        except auth.B1Error as exc:
            return JSONResponse({"detail": str(exc)}, status_code=403)
        code_token, id_token = context.current_user_code.set(user.user_code), context.current_user_id.set(user.user_id)
    finally:
        s.close()
    try:
        return await call_next(request)
    finally:
        context.current_user_code.reset(code_token)
        context.current_user_id.reset(id_token)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health", tags=["System"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": __version__, "db": settings.database_url.split("://")[0]}


if _WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
