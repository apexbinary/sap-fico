"""REST API routers for FI/CO."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.models.documents import AccountingDocumentHeader
from app.schemas import DocumentIn, DocumentOut
from app.services import reporting
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, LineRequest, post_document

router = APIRouter()


@router.post("/documents", response_model=DocumentOut, tags=["Postings"], summary="Post a FI document (FB01)")
def create_document(
    doc: DocumentIn,
    mandt: str = Query(default=None),
    session: Session = Depends(get_session),
) -> AccountingDocumentHeader:
    req = DocumentRequest(
        mandt=mandt or settings.default_client,
        bukrs=doc.bukrs, blart=doc.blart, bldat=doc.bldat, budat=doc.budat,
        waers=doc.waers, kursf=doc.kursf, xblnr=doc.xblnr, bktxt=doc.bktxt,
        usnam=doc.usnam, tcode=doc.tcode, kokrs=doc.kokrs,
        lines=[
            LineRequest(
                bschl=l.bschl, account=l.account, wrbtr=l.wrbtr, mwskz=l.mwskz,
                calculate_tax=l.calculate_tax, sgtxt=l.sgtxt, zuonr=l.zuonr,
                gsber=l.gsber, kostl=l.kostl, aufnr=l.aufnr, prctr=l.prctr,
                zterm=l.zterm, umskz=l.umskz,
            )
            for l in doc.lines
        ],
    )
    try:
        return post_document(session, req)
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/documents/{bukrs}/{gjahr}/{belnr}", response_model=DocumentOut, tags=["Postings"], summary="Display document (FB03)")
def get_document(
    bukrs: str, gjahr: int, belnr: str,
    mandt: str = Query(default=None),
    session: Session = Depends(get_session),
) -> AccountingDocumentHeader:
    key = (mandt or settings.default_client, bukrs, belnr.zfill(10), gjahr)
    header = session.get(AccountingDocumentHeader, key)
    if header is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return header


@router.get("/reports/trial-balance", tags=["Reports"], summary="Trial balance (S_ALR_87012277)")
def trial_balance(
    bukrs: str, gjahr: int, period_to: int = 16,
    mandt: str = Query(default=None),
    session: Session = Depends(get_session),
) -> dict:
    return reporting.trial_balance(session, mandt or settings.default_client, bukrs, gjahr, period_to)


@router.get("/reports/account-balance", tags=["Reports"], summary="G/L account balance (FAGLB03/FS10N)")
def account_balance(
    bukrs: str, gjahr: int, saknr: str, period_to: int = 16,
    mandt: str = Query(default=None),
    session: Session = Depends(get_session),
) -> dict:
    return reporting.account_balance(
        session, mandt or settings.default_client, bukrs, gjahr, saknr.zfill(10), period_to
    )


@router.get("/reports/open-items", tags=["Reports"], summary="Open items (FBL5N/FBL1N)")
def open_items(
    bukrs: str, koart: str, account: str, only_open: bool = True,
    mandt: str = Query(default=None),
    session: Session = Depends(get_session),
) -> list[dict]:
    if koart not in ("D", "K"):
        raise HTTPException(status_code=400, detail="koart must be 'D' (customer) or 'K' (vendor)")
    return reporting.open_items(
        session, mandt or settings.default_client, bukrs, koart, account.zfill(10), only_open
    )
