"""REST endpoints: India e-documents (e-invoice IRN, e-way bill) of documents, settings and register."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import edocs

router = APIRouter()


@router.get("/documents/{obj}/{doc_entry}/edocs", tags=["E-documents"], summary="IRN / e-way bill status of a document")
def status(obj: str, doc_entry: int, s: Session = Depends(get_session)) -> dict:
    return run(lambda: edocs.status(s, obj, doc_entry))


@router.get("/documents/{obj}/{doc_entry}/einvoice/json", tags=["E-documents"], summary="E-invoice JSON (INV-01) for the IRP")
def einvoice_json(obj: str, doc_entry: int, s: Session = Depends(get_session)) -> JSONResponse:
    payload, issues = run(lambda: edocs.einvoice_payload(s, obj, doc_entry))
    return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="EINV_{payload["DocDtls"]["Typ"]}_{payload["DocDtls"]["No"]}.json"',
                                          "X-Issues": str(len(issues))})


@router.post("/documents/{obj}/{doc_entry}/einvoice", tags=["E-documents"], summary="Register the e-invoice (test mode: IRN made here)")
def generate_irn(obj: str, doc_entry: int, s: Session = Depends(get_session)) -> dict:
    run(lambda: edocs.generate_irn(s, obj, doc_entry))
    return edocs.status(s, obj, doc_entry)


@router.post("/documents/{obj}/{doc_entry}/einvoice/import", tags=["E-documents"], summary="Import the IRP response (live mode)")
def import_irn(obj: str, doc_entry: int, response: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    run(lambda: edocs.import_irn(s, obj, doc_entry, response))
    return edocs.status(s, obj, doc_entry)


class CancelIn(BaseModel):
    reason: str = Field(..., max_length=1)
    remark: str | None = Field(None, max_length=100)


@router.post("/documents/{obj}/{doc_entry}/einvoice/cancel", tags=["E-documents"], summary="Cancel the IRN (within 24 hours)")
def cancel_irn(obj: str, doc_entry: int, body: CancelIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: edocs.cancel_irn(s, obj, doc_entry, body.reason, body.remark))
    return edocs.status(s, obj, doc_entry)


class TransportIn(BaseModel):
    trans_mode: str | None = Field("1", max_length=1)
    distance: int | None = None
    vehicle_no: str | None = Field(None, max_length=20)
    vehicle_type: str | None = Field("R", max_length=1)
    transporter_id: str | None = Field(None, max_length=15)
    transporter_name: str | None = Field(None, max_length=100)
    trans_doc_no: str | None = Field(None, max_length=15)
    trans_doc_date: date | None = None


@router.post("/documents/{obj}/{doc_entry}/ewaybill/json", tags=["E-documents"], summary="E-way bill JSON for the portal")
def ewb_json(obj: str, doc_entry: int, body: TransportIn, s: Session = Depends(get_session)) -> JSONResponse:
    payload, _ = run(lambda: edocs.ewb_payload(s, obj, doc_entry, edocs._transport(body.model_dump())))
    return JSONResponse({"version": "1.0.0621", "billLists": [payload]},
                        headers={"Content-Disposition": f'attachment; filename="EWB_{payload["docType"]}_{payload["docNo"]}.json"'})


@router.post("/documents/{obj}/{doc_entry}/ewaybill", tags=["E-documents"], summary="Generate the e-way bill (test mode)")
def generate_ewb(obj: str, doc_entry: int, body: TransportIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: edocs.generate_ewb(s, obj, doc_entry, body.model_dump()))
    return edocs.status(s, obj, doc_entry)


class EwbImportIn(TransportIn):
    response: dict


@router.post("/documents/{obj}/{doc_entry}/ewaybill/import", tags=["E-documents"], summary="Import the e-way bill portal response")
def import_ewb(obj: str, doc_entry: int, body: EwbImportIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: edocs.import_ewb(s, obj, doc_entry, body.response, body.model_dump(exclude={"response"})))
    return edocs.status(s, obj, doc_entry)


@router.post("/documents/{obj}/{doc_entry}/ewaybill/vehicle", tags=["E-documents"], summary="Update Part B (vehicle)")
def update_vehicle(obj: str, doc_entry: int, body: TransportIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: edocs.update_vehicle(s, obj, doc_entry, body.model_dump(exclude_unset=True)))
    return edocs.status(s, obj, doc_entry)


@router.post("/documents/{obj}/{doc_entry}/ewaybill/cancel", tags=["E-documents"], summary="Cancel the e-way bill (within 24 hours)")
def cancel_ewb(obj: str, doc_entry: int, body: CancelIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: edocs.cancel_ewb(s, obj, doc_entry, body.reason, body.remark))
    return edocs.status(s, obj, doc_entry)


@router.get("/e-documents", tags=["E-documents"], summary="Register of IRNs and e-way bills, and documents still needing one")
def register(kind: str | None = None, since: date | None = None, s: Session = Depends(get_session)) -> dict:
    return {"settings": edocs.settings(s), "register": edocs.register(s, kind),
            "pending": edocs.pending(s, since or date.today() - timedelta(days=30))}


class SettingsIn(BaseModel):
    e_invoice: bool | None = None
    e_way_bill: bool | None = None
    mode: str | None = Field(None, max_length=1)
    street: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=20)


@router.put("/admin/e-documents", tags=["E-documents"], summary="E-document settings and company address (ADM1)")
def save_settings(body: SettingsIn, s: Session = Depends(get_session)) -> dict:
    return run(lambda: edocs.save_settings(s, body.model_dump(exclude_unset=True)))
