"""Read-only master-data endpoints that back the web UI dropdowns and lists."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.models.documents import AccountingDocumentHeader, DocumentType, PostingKey
from app.models.gl_master import GLAccountCompanyCode, GLAccountText
from app.models.organizational import CompanyCode
from app.models.partners import Customer, CustomerCompanyCode, Vendor, VendorCompanyCode
from app.models.tax import TaxCode

router = APIRouter(prefix="/master", tags=["Master data"])


def _mandt(mandt: str | None) -> str:
    return mandt or settings.default_client


@router.get("/company-codes")
def company_codes(mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    rows = s.scalars(select(CompanyCode).where(CompanyCode.mandt == _mandt(mandt))).all()
    return [{"bukrs": r.bukrs, "butxt": r.butxt, "waers": r.waers, "land1": r.land1, "ktopl": r.ktopl} for r in rows]


@router.get("/document-types")
def document_types(mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    rows = s.scalars(select(DocumentType).where(DocumentType.mandt == _mandt(mandt))).all()
    return [
        {"blart": r.blart, "ltext": r.ltext, "xsach": r.xsach, "xkund": r.xkund, "xlief": r.xlief}
        for r in rows
    ]


@router.get("/posting-keys")
def posting_keys(mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    rows = s.scalars(select(PostingKey).where(PostingKey.mandt == _mandt(mandt)).order_by(PostingKey.bschl)).all()
    return [{"bschl": r.bschl, "ltext": r.ltext, "shkzg": r.shkzg, "koart": r.koart} for r in rows]


@router.get("/tax-codes")
def tax_codes(mandt: str = Query(default=None), s: Session = Depends(get_session)) -> list[dict]:
    rows = s.scalars(select(TaxCode).where(TaxCode.mandt == _mandt(mandt))).all()
    return [{"mwskz": r.mwskz, "text1": r.text1, "mwart": r.mwart, "kalsm": r.kalsm} for r in rows]


@router.get("/gl-accounts")
def gl_accounts(
    bukrs: str, mandt: str = Query(default=None), s: Session = Depends(get_session)
) -> list[dict]:
    m = _mandt(mandt)
    rows = s.scalars(
        select(GLAccountCompanyCode).where(
            GLAccountCompanyCode.mandt == m, GLAccountCompanyCode.bukrs == bukrs
        )
    ).all()
    out = []
    for r in rows:
        name = s.scalars(
            select(GLAccountText.txt50).where(
                GLAccountText.mandt == m, GLAccountText.saknr == r.saknr
            )
        ).first()
        out.append(
            {"saknr": r.saknr, "name": name, "mitkz": r.mitkz, "mwskz": r.mwskz, "xopvw": r.xopvw}
        )
    return sorted(out, key=lambda a: a["saknr"])


@router.get("/customers")
def customers(
    bukrs: str | None = None, mandt: str = Query(default=None), s: Session = Depends(get_session)
) -> list[dict]:
    m = _mandt(mandt)
    rows = s.scalars(select(Customer).where(Customer.mandt == m)).all()
    out = []
    for r in rows:
        akont = None
        if bukrs:
            cc = s.get(CustomerCompanyCode, (m, r.kunnr, bukrs))
            akont = cc.akont if cc else None
        out.append({"kunnr": r.kunnr, "name1": r.name1, "land1": r.land1, "ort01": r.ort01, "akont": akont})
    return out


@router.get("/vendors")
def vendors(
    bukrs: str | None = None, mandt: str = Query(default=None), s: Session = Depends(get_session)
) -> list[dict]:
    m = _mandt(mandt)
    rows = s.scalars(select(Vendor).where(Vendor.mandt == m)).all()
    out = []
    for r in rows:
        akont = None
        if bukrs:
            cc = s.get(VendorCompanyCode, (m, r.lifnr, bukrs))
            akont = cc.akont if cc else None
        out.append({"lifnr": r.lifnr, "name1": r.name1, "land1": r.land1, "ort01": r.ort01, "akont": akont})
    return out


@router.get("/documents")
def recent_documents(
    bukrs: str, gjahr: int | None = None, limit: int = 50,
    mandt: str = Query(default=None), s: Session = Depends(get_session),
) -> list[dict]:
    m = _mandt(mandt)
    stmt = select(AccountingDocumentHeader).where(
        AccountingDocumentHeader.mandt == m, AccountingDocumentHeader.bukrs == bukrs
    )
    if gjahr:
        stmt = stmt.where(AccountingDocumentHeader.gjahr == gjahr)
    stmt = stmt.order_by(
        AccountingDocumentHeader.gjahr.desc(), AccountingDocumentHeader.belnr.desc()
    ).limit(limit)
    rows = s.scalars(stmt).all()
    out = []
    for h in rows:
        total = sum((i.dmbtr for i in h.items if i.shkzg == "S"), 0)
        out.append({
            "belnr": h.belnr, "gjahr": h.gjahr, "blart": h.blart, "budat": h.budat.isoformat(),
            "bldat": h.bldat.isoformat(), "waers": h.waers, "bktxt": h.bktxt,
            "monat": h.monat, "amount": str(total), "items": len(h.items),
            "bstat": h.bstat, "stblg": h.stblg, "stjah": h.stjah, "tcode": h.tcode, "xblnr": h.xblnr,
        })
    return out
