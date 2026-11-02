"""REST API routers for FI/CO."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.models.documents import AccountingDocumentHeader
from app.schemas import DocumentIn, DocumentOut
from app.services import fsv, reporting, reversal
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, LineRequest, delete_parked, post_document, post_parked

router = APIRouter()


def _request(doc: DocumentIn, mandt: str | None, bstat: str = " ", belnr: str | None = None) -> DocumentRequest:
    return DocumentRequest(
        bstat=bstat, belnr=belnr,
        mandt=mandt or settings.default_client,
        bukrs=doc.bukrs, blart=doc.blart, bldat=doc.bldat, budat=doc.budat,
        waers=doc.waers, kursf=doc.kursf, xblnr=doc.xblnr, bktxt=doc.bktxt,
        usnam=doc.usnam, tcode=doc.tcode, kokrs=doc.kokrs,
        lines=[
            LineRequest(
                bschl=l.bschl, account=l.account, wrbtr=l.wrbtr, mwskz=l.mwskz,
                calculate_tax=l.calculate_tax, sgtxt=l.sgtxt, zuonr=l.zuonr,
                gsber=l.gsber, kostl=l.kostl, aufnr=l.aufnr, prctr=l.prctr,
                zterm=l.zterm, umskz=l.umskz, zlsch=l.zlsch, zlspr=l.zlspr,
            )
            for l in doc.lines
        ],
    )


@router.post("/documents", response_model=DocumentOut, tags=["Postings"], summary="Post a FI document (FB01)")
def create_document(
    doc: DocumentIn,
    mandt: str = Query(default=None),
    session: Session = Depends(get_session),
) -> AccountingDocumentHeader:
    try:
        return post_document(session, _request(doc, mandt))
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/documents/park", response_model=DocumentOut, tags=["Postings"], summary="Park a document (FV50 / F-65)")
def park_document(
    doc: DocumentIn,
    mandt: str = Query(default=None),
    session: Session = Depends(get_session),
) -> AccountingDocumentHeader:
    try:
        return post_document(session, _request(doc, mandt, bstat="V"))
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _m(mandt: str | None) -> str:
    return mandt or settings.default_client


@router.post("/documents/{bukrs}/{gjahr}/{belnr}/post", response_model=DocumentOut, tags=["Postings"],
             summary="Post a parked document (FBV0)")
def post_parked_document(
    bukrs: str, gjahr: int, belnr: str, mandt: str = Query(default=None), session: Session = Depends(get_session),
) -> AccountingDocumentHeader:
    try:
        return post_parked(session, _m(mandt), bukrs, belnr, gjahr)
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/documents/{bukrs}/{gjahr}/{belnr}", response_model=DocumentOut, tags=["Postings"],
            summary="Change a parked document (FBV2)")
def change_parked_document(
    bukrs: str, gjahr: int, belnr: str, doc: DocumentIn,
    mandt: str = Query(default=None), session: Session = Depends(get_session),
) -> AccountingDocumentHeader:
    if doc.bukrs != bukrs:
        raise HTTPException(status_code=422, detail="The company code cannot be changed")
    try:
        return post_document(session, _request(doc, mandt, bstat="V", belnr=belnr))
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class MassReverseIn(BaseModel):
    documents: list[str] = Field(..., description="Documents as 'BELNR/GJAHR'")
    budat: date | None = None
    stgrd: str = "01"


@router.post("/documents/{bukrs}/mass-reverse", tags=["Postings"], summary="Mass reversal (F.80)")
def mass_reverse(
    bukrs: str, body: MassReverseIn, mandt: str = Query(default=None), session: Session = Depends(get_session),
) -> list[dict]:
    docs = []
    for ref in body.documents:
        belnr, _, gjahr = ref.partition("/")
        if not gjahr.isdigit():
            raise HTTPException(status_code=422, detail=f"Use BELNR/GJAHR, not {ref!r}")
        docs.append((belnr, int(gjahr)))
    return reversal.mass_reverse(session, _m(mandt), bukrs, docs, budat=body.budat, stgrd=body.stgrd)


@router.delete("/documents/{bukrs}/{gjahr}/{belnr}", tags=["Postings"], summary="Delete a parked document (FBV0)")
def delete_parked_document(
    bukrs: str, gjahr: int, belnr: str, mandt: str = Query(default=None), session: Session = Depends(get_session),
) -> dict:
    try:
        delete_parked(session, _m(mandt), bukrs, belnr, gjahr)
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"deleted": f"{belnr.zfill(10)}/{gjahr}"}


class ReverseIn(BaseModel):
    budat: date | None = Field(None, description="Posting date of the reversal (default: original)")
    stgrd: str = Field("01", description="Reversal reason: 01 current period, 02 closed period")


@router.post("/documents/{bukrs}/{gjahr}/{belnr}/reverse", response_model=DocumentOut, tags=["Postings"],
             summary="Reverse a document (FB08)")
def reverse(
    bukrs: str, gjahr: int, belnr: str, body: ReverseIn,
    mandt: str = Query(default=None), session: Session = Depends(get_session),
) -> AccountingDocumentHeader:
    try:
        return reversal.reverse_document(session, _m(mandt), bukrs, belnr, gjahr, budat=body.budat, stgrd=body.stgrd)
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ResetClearingIn(BaseModel):
    reverse: bool = Field(False, description="Also reverse the clearing document")
    budat: date | None = None
    stgrd: str = "01"


@router.post("/documents/{bukrs}/{gjahr}/{belnr}/reset-clearing", tags=["Postings"],
             summary="Reset cleared items, optionally reverse (FBRA)")
def reset_clearing(
    bukrs: str, gjahr: int, belnr: str, body: ResetClearingIn,
    mandt: str = Query(default=None), session: Session = Depends(get_session),
) -> dict:
    try:
        return reversal.reset_clearing(session, _m(mandt), bukrs, belnr, gjahr,
                                       reverse=body.reverse, budat=body.budat, stgrd=body.stgrd)
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
        session, mandt or settings.default_client, bukrs, gjahr, saknr, period_to
    )


@router.get("/reports/open-items", tags=["Reports"], summary="Open items (FBL5N/FBL1N/FBL3N)")
def open_items(
    bukrs: str, koart: str, account: str, only_open: bool = True,
    mandt: str = Query(default=None),
    session: Session = Depends(get_session),
) -> list[dict]:
    if koart not in ("D", "K", "S"):
        raise HTTPException(status_code=400, detail="koart must be 'D' (customer), 'K' (vendor) or 'S' (G/L)")
    return reporting.open_items(
        session, mandt or settings.default_client, bukrs, koart,
        account if koart == "S" else account.zfill(10), only_open,
    )


@router.get("/reports/financial-statement", tags=["Reports"],
            summary="Balance sheet / P&L by financial statement version (RFBILA00 / F.01)")
def financial_statement(
    bukrs: str, gjahr: int, period_to: int = 16, versn: str | None = None,
    compare_gjahr: int | None = None,
    mandt: str = Query(default=None),
    session: Session = Depends(get_session),
) -> dict:
    try:
        return fsv.financial_statement(
            session, mandt or settings.default_client, bukrs, gjahr,
            versn=versn, period_to=period_to, compare_gjahr=compare_gjahr,
        )
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reports/partner-balances", tags=["Reports"],
            summary="Customer / vendor balances with G/L reconciliation (FD10N / FK10N)")
def partner_balances(
    bukrs: str, koart: str, gjahr: int, period_to: int = 16,
    mandt: str = Query(default=None), session: Session = Depends(get_session),
) -> dict:
    if koart not in ("D", "K"):
        raise HTTPException(status_code=400, detail="koart must be 'D' (customer) or 'K' (vendor)")
    return reporting.partner_balances(session, _m(mandt), bukrs, koart, gjahr, period_to)


@router.get("/reports/pl-functional-area", tags=["Reports"], summary="P&L by functional area (cost of sales)")
def pl_functional_area(
    bukrs: str, gjahr: int, period_from: int = 1, period_to: int = 16,
    mandt: str = Query(default=None), session: Session = Depends(get_session),
) -> dict:
    try:
        return fsv.pl_by_functional_area(session, _m(mandt), bukrs, gjahr, period_from=period_from, period_to=period_to)
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class FSVNodeIn(BaseModel):
    parent: int
    txt45: str = Field(..., max_length=45)
    ergsl: str | None = Field(None, max_length=10)
    sign: int = 1


class FSVNodeChange(BaseModel):
    txt45: str | None = Field(None, max_length=45)
    seqno: int | None = None
    sign: int | None = None


class FSVRangeIn(BaseModel):
    vonkt: str
    biskt: str
    soll: bool = True
    haben: bool = True


def _fsv(fn):
    try:
        return fn()
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/fsv/{versn}", tags=["Financial statement version"], summary="FSV items and account ranges (OB58)")
def fsv_structure(versn: str, mandt: str = Query(default=None), session: Session = Depends(get_session)) -> list[dict]:
    return fsv.structure(session, _m(mandt), versn)


@router.post("/fsv/{versn}/nodes", tags=["Financial statement version"], summary="Add an FSV item")
def fsv_add_node(versn: str, body: FSVNodeIn, mandt: str = Query(default=None), session: Session = Depends(get_session)) -> dict:
    node = _fsv(lambda: fsv.add_node(session, _m(mandt), versn, parent=body.parent, txt45=body.txt45,
                                     ergsl=body.ergsl, sign=body.sign))
    return {"id": node.id, "ergsl": node.ergsl}


@router.patch("/fsv/{versn}/nodes/{node_id}", tags=["Financial statement version"], summary="Change an FSV item")
def fsv_change_node(versn: str, node_id: int, body: FSVNodeChange, mandt: str = Query(default=None),
                    session: Session = Depends(get_session)) -> dict:
    node = _fsv(lambda: fsv.update_node(session, _m(mandt), versn, node_id, txt45=body.txt45, seqno=body.seqno,
                                        sign=body.sign))
    return {"id": node.id, "txt45": node.txt45}


@router.delete("/fsv/{versn}/nodes/{node_id}", tags=["Financial statement version"], summary="Delete an FSV item")
def fsv_delete_node(versn: str, node_id: int, mandt: str = Query(default=None), session: Session = Depends(get_session)) -> dict:
    _fsv(lambda: fsv.delete_node(session, _m(mandt), versn, node_id))
    return {"deleted": node_id}


@router.post("/fsv/{versn}/nodes/{node_id}/ranges", tags=["Financial statement version"], summary="Assign an account range")
def fsv_add_range(versn: str, node_id: int, body: FSVRangeIn, mandt: str = Query(default=None),
                  session: Session = Depends(get_session)) -> dict:
    _fsv(lambda: fsv.add_assignment(session, _m(mandt), versn, node_id, vonkt=body.vonkt, biskt=body.biskt,
                                    soll=body.soll, haben=body.haben))
    return body.model_dump()


@router.delete("/fsv/{versn}/nodes/{node_id}/ranges/{vonkt}", tags=["Financial statement version"],
               summary="Remove an account range")
def fsv_delete_range(versn: str, node_id: int, vonkt: str, mandt: str = Query(default=None),
                     session: Session = Depends(get_session)) -> dict:
    _fsv(lambda: fsv.delete_assignment(session, _m(mandt), versn, node_id, vonkt))
    return {"deleted": vonkt}


class CarryForwardIn(BaseModel):
    bukrs: str
    gjahr: int = Field(..., description="Fiscal year to carry forward from")


@router.post("/closing/carry-forward", tags=["Closing"], summary="Balance carryforward (FAGLGVTR / F.16)")
def carry_forward(
    body: CarryForwardIn, mandt: str = Query(default=None), session: Session = Depends(get_session),
) -> dict:
    try:
        return fsv.carry_forward(session, mandt or settings.default_client, body.bukrs, body.gjahr)
    except PostingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
