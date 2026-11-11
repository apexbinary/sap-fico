"""REST endpoints: sales, purchasing and inventory documents; warehouse journal."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.documents import DOCUMENT_CLASSES, WarehouseJournal
from app.services import documents
from app.services.admin import B1Error

router = APIRouter()


def _doc_out(doc, detail: bool = False) -> dict:
    d = documents.DEFS[doc.obj_type]
    out = {"obj": doc.obj_type, "name": d.name, "doc_entry": doc.doc_entry, "doc_num": doc.doc_num,
           "doc_type": doc.doc_type, "doc_status": doc.doc_status, "canceled": doc.canceled == "Y",
           "doc_date": doc.doc_date, "doc_due_date": doc.doc_due_date, "tax_date": doc.tax_date,
           "card_code": doc.card_code, "card_name": doc.card_name, "num_at_card": doc.num_at_card,
           "doc_cur": doc.doc_cur, "doc_rate": doc.doc_rate, "doc_total_fc": doc.doc_total_fc, "vat_sum_fc": doc.vat_sum_fc,
           "disc_sum_fc": doc.disc_sum_fc, "paid_fc": doc.paid_fc, "disc_prcnt": doc.disc_prcnt, "disc_sum": doc.disc_sum, "vat_sum": doc.vat_sum,
           "doc_total": doc.doc_total, "paid_to_date": doc.paid_to_date, "trans_id": doc.trans_id,
           "wt_sum": doc.wt_sum, "wt_sum_fc": doc.wt_sum_fc, "total_expns": doc.total_expns, "total_exp_fc": doc.total_exp_fc,
           "dpm_amnt": doc.dpm_amnt, "dpm_appl": doc.dpm_appl,
           "boe_num": doc.boe_num, "boe_date": doc.boe_date, "boe_value": doc.boe_value, "port_code": doc.port_code,
           "cancel_date": doc.cancel_date, "amnd_entry": doc.amnd_entry, "dpm_type": doc.dpm_type,
           "comments": doc.comments, "filler": doc.filler, "to_whs_code": doc.to_whs_code, "series": doc.series,
           "cntct_code": doc.cntct_code, "slp_code": doc.slp_code, "project": doc.project,
           "lic_trad_num": doc.lic_trad_num, "jrnl_memo": doc.jrnl_memo, "ref2": doc.ref2, "group_num": doc.group_num}
    if detail:
        from app.models.documents import DOCUMENT_INSTALLMENTS
        from sqlalchemy.orm import object_session

        cls = DOCUMENT_INSTALLMENTS.get(doc.obj_type)
        out["installments"] = [{"instlmnt_id": i.instlmnt_id, "due_date": i.due_date, "ins_total": i.ins_total,
                                "ins_total_fc": i.ins_total_fc, "paid_to_date": i.paid_to_date, "paid_fc": i.paid_fc,
                                "status": i.status, "inst_prcnt": i.inst_prcnt}
                               for i in object_session(doc).scalars(select(cls).where(cls.doc_entry == doc.doc_entry)
                                                                    .order_by(cls.instlmnt_id))] if cls else []
        from app.services import withholding

        out["withholding"] = withholding.rows_of(object_session(doc), doc.obj_type, doc.doc_entry)
        from app.services import gst_filing

        ret = gst_filing.filed_for(object_session(doc), doc.obj_type, doc.doc_date)  # filed GST month: amend / cancel later
        out["gst_filed"] = gst_filing.RETURNS[ret] if ret else None
        out["gst_amend"] = bool(ret) and doc.obj_type in gst_filing.SALES and             gst_filing.get(object_session(doc), "GSTR1", doc.doc_date.year, doc.doc_date.month) is not None
        from app.models.batches import Batch, InventoryLog, SerialNumber

        alloc: dict[int, list] = {}
        for log in object_session(doc).scalars(select(InventoryLog).where(InventoryLog.doc_type == doc.obj_type,
                                                                          InventoryLog.doc_entry == doc.doc_entry)):
            master = Batch if log.managed_by == "10000044" else SerialNumber
            for l in log.lines:
                alloc.setdefault(log.doc_line, []).append({"number": object_session(doc).get(master, l.md_abs_entry).dist_number,
                                                           "quantity": l.quantity, "whs_code": log.loc_code, "reversed": log.reversed == "Y"})
        out["batch_allocations"] = alloc
        from app.models.documents import DOCUMENT_DOWN_PAYMENTS

        dcls = DOCUMENT_DOWN_PAYMENTS.get(doc.obj_type)
        dp_cls = DOCUMENT_CLASSES["203" if doc.obj_type == "13" else "204"][0] if dcls else None
        out["down_payments"] = [{"dp_entry": r.base_abs, "dp_num": object_session(doc).get(dp_cls, r.base_abs).doc_num,
                                 "drawn_sum": r.drawn_sum, "pay_type": r.pay_type, "pay_entry": r.pay_entry}
                                for r in object_session(doc).scalars(select(dcls).where(dcls.doc_entry == doc.doc_entry))] if dcls else []
        from app.models.admin import AdditionalExpense

        out["expenses"] = [{"expns_code": e.expns_code, "expns_name": (object_session(doc).get(AdditionalExpense, e.expns_code).expns_name
                                                                       if object_session(doc).get(AdditionalExpense, e.expns_code) else ""),
                            "line_total": e.line_total, "total_frgn": e.total_frgn, "vat_group": e.vat_group, "vat_prcnt": e.vat_prcnt,
                            "vat_sum": e.vat_sum, "grs_amount": e.grs_amount,
                            "ocr_codes": [e.ocr_code, e.ocr_code2, e.ocr_code3, e.ocr_code4, e.ocr_code5]} for e in getattr(doc, "expenses", [])]
        out.update(address=doc.address, address2=doc.address2, pay_to_code=doc.pay_to_code,
                   ship_to_code=doc.ship_to_code)
        out["lines"] = [{"line_num": l.line_num, "line_status": l.line_status, "item_code": l.item_code,
                         "dscription": l.dscription, "quantity": l.quantity, "open_qty": l.open_qty,
                         "price_bef_di": l.price_bef_di, "disc_prcnt": l.disc_prcnt, "price": l.price,
                         "line_total": l.line_total, "vat_group": l.vat_group, "vat_prcnt": l.vat_prcnt,
                         "vat_sum": l.vat_sum, "gtotal": l.gtotal, "whs_code": l.whs_code,
                         "from_whs_cod": l.from_whs_cod, "acct_code": l.acct_code, "unit_msr": l.unit_msr,
                         "stock_price": l.stock_price, "grss_profit": l.grss_profit, "base_type": l.base_type,
                         "base_entry": l.base_entry, "base_line": l.base_line, "base_ref": l.base_ref,
                         "target_type": l.target_type, "trget_entry": l.trget_entry, "ship_date": l.ship_date,
                         "free_txt": l.free_txt, "project": l.project, "slp_code": l.slp_code,
                         "ocr_codes": [l.ocr_code, l.ocr_code2, l.ocr_code3, l.ocr_code4, l.ocr_code5],
                         "price_af_vat": l.price_af_vat, "total_frgn": l.total_frgn, "vat_sum_frgn": l.vat_sum_frgn,
                         "gtotal_fc": l.gtotal_fc, "currency": l.currency, "rate": l.rate} for l in doc.lines]
    return out


def _check(obj: str) -> None:
    if obj not in documents.DEFS:
        raise HTTPException(status_code=404, detail=f"Unknown document type {obj}")


@router.get("/documents/types", tags=["Documents"], summary="Document types and their copy-from bases")
def types() -> list[dict]:
    return [{"obj": d.obj, "name": d.name, "side": d.side, "kind": d.kind, "bases": list(d.bases),
             "targets": [t.obj for t in documents.DEFS.values() if d.obj in t.bases]}
            for d in documents.DEFS.values()]


@router.get("/documents/{obj}", tags=["Documents"], summary="Documents of a type (newest first)")
def list_documents(obj: str, card_code: str | None = None, status: str | None = None, limit: int = 100,
                   s: Session = Depends(get_session)) -> list[dict]:
    _check(obj)
    header_cls, _ = DOCUMENT_CLASSES[obj]
    q = select(header_cls).order_by(header_cls.doc_entry.desc()).limit(limit)
    if card_code:
        q = q.where(header_cls.card_code == card_code)
    if status:
        q = q.where(header_cls.doc_status == status.upper())
    return [_doc_out(doc) for doc in s.scalars(q)]


class DocLineIn(BaseModel):
    item_code: str | None = None
    quantity: Decimal = Field(Decimal("1"), gt=0)
    price: Decimal | None = Field(None, ge=0)
    disc_prcnt: Decimal | None = Field(None, ge=0, le=100)
    vat_group: str | None = None
    whs_code: str | None = None
    from_whs_cod: str | None = None
    acct_code: str | None = None
    dscription: str | None = Field(None, max_length=100)
    base_type: str | None = None
    base_entry: int | None = None
    base_line: int | None = None
    ship_date: date | None = None
    free_txt: str | None = Field(None, max_length=100)
    project: str | None = Field(None, max_length=20)
    slp_code: int | None = None
    batches: list[dict] | None = None  # [{number, quantity, exp_date, mnf_date}]
    serials: list[dict] | None = None  # [{number, exp_date, mnf_date}]
    ocr_codes: list[str | None] | None = None  # distribution rules of dimensions 1 - 5


class DocumentIn(BaseModel):
    doc_date: date
    card_code: str | None = None
    doc_type: str = Field("I", pattern="^[IS]$")
    doc_due_date: date | None = None
    tax_date: date | None = None
    disc_prcnt: Decimal | None = Field(None, ge=0, lt=100)
    num_at_card: str | None = Field(None, max_length=100)
    comments: str | None = Field(None, max_length=254)
    from_whs: str | None = None
    to_whs: str | None = None
    cntct_code: int | None = None
    slp_code: int | None = None
    project: str | None = Field(None, max_length=20)
    pay_to_code: str | None = Field(None, max_length=50)
    ship_to_code: str | None = Field(None, max_length=50)
    jrnl_memo: str | None = Field(None, max_length=50)
    ref2: str | None = Field(None, max_length=11)
    doc_cur: str | None = Field(None, max_length=3)
    wt_codes: list[str] | None = None
    confirm_credit: bool = False
    expenses: list[dict] | None = None  # [{expns_code, amount, vat_group, ocr_codes}]
    down_payments: list[dict] | None = None  # invoices: [{dp_entry, amount}] paid down payments to draw
    dpm_type: str = Field("R", pattern="^[RI]$")  # down payments: R request / I invoice (posted with tax)
    boe_num: str | None = Field(None, max_length=20)  # import of goods: bill of entry
    boe_date: date | None = None
    boe_value: Decimal | None = Field(None, gt=0)
    port_code: str | None = Field(None, max_length=6)
    lines: list[DocLineIn]


def build_request(obj: str, payload: dict) -> documents.DocumentRequest:
    """DocumentRequest from the JSON body of a document (also replayed by approved approval requests)."""
    data = DocumentIn(**payload).model_dump()
    lines = [documents.DocLineRequest(**l) for l in data.pop("lines")]
    try:
        expenses = [documents.ExpenseRequest(**e) for e in (data.pop("expenses") or [])]
    except TypeError as exc:
        raise HTTPException(status_code=422, detail="Freight: expns_code, amount and vat_group are expected") from exc
    try:
        draws = [documents.DownPaymentDraw(**x) for x in (data.pop("down_payments") or [])]
    except TypeError as exc:
        raise HTTPException(status_code=422, detail="Down payments: dp_entry and amount are expected") from exc
    return documents.DocumentRequest(obj=obj, lines=lines, expenses=expenses, down_payments=draws, **data)


@router.post("/documents/{obj}", tags=["Documents"], summary="Add a document (posts stock and journal entry)")
def create_document(obj: str, body: DocumentIn, s: Session = Depends(get_session)) -> dict:
    _check(obj)
    payload = body.model_dump(mode="json")
    from app.context import current_user_id
    from app.services import approvals

    held = run(lambda: approvals.check(s, obj, payload, lambda p: build_request(obj, p), current_user_id.get()))
    if held is not None:  # approval procedure: the document waits for the authorizers
        return {"pending_approval": approvals.out(s, held)}
    doc = run(lambda: documents.create_document(s, build_request(obj, payload)))
    return _doc_out(doc, detail=True)


@router.get("/documents/{obj}/open-down-payments", tags=["Documents"], summary="Down payments of a partner: unpaid (to pay) or paid and not drawn (to draw)")
def open_down_payments(obj: str, card_code: str, s: Session = Depends(get_session)) -> list[dict]:
    if obj not in {"203", "204"}:
        raise HTTPException(status_code=404, detail="Down payments are object 203 (A/R) or 204 (A/P)")
    cls = DOCUMENT_CLASSES[obj][0]
    rows = s.scalars(select(cls).where(cls.card_code == card_code, cls.canceled == "N").order_by(cls.doc_entry))
    return [{"obj": obj, "doc_entry": d.doc_entry, "doc_num": d.doc_num, "doc_date": d.doc_date, "doc_total": d.doc_total,
             "paid": d.paid_to_date, "drawn": d.dpm_appl, "to_pay": d.doc_total - d.paid_to_date, "to_draw": d.paid_to_date - d.dpm_appl,
             "comments": d.comments, "dpm_type": d.dpm_type} for d in rows if d.doc_total - d.paid_to_date > 0 or d.paid_to_date - d.dpm_appl > 0]


@router.get("/documents/{obj}/copy-sources", tags=["Documents"], summary="Open base documents to copy from")
def copy_sources(obj: str, card_code: str, s: Session = Depends(get_session)) -> list[dict]:
    _check(obj)
    return documents.copy_sources(s, obj, card_code)


@router.get("/documents/{obj}/{doc_entry}", tags=["Documents"])
def get_document(obj: str, doc_entry: int, s: Session = Depends(get_session)) -> dict:
    _check(obj)
    try:
        return _doc_out(documents.get_document(s, obj, doc_entry), detail=True)
    except B1Error as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CancelIn(BaseModel):
    cancel_date: date | None = None


@router.get("/documents/{obj}/{doc_entry}/print", tags=["Documents"], summary="Print data (GST layout) of a document")
def print_document(obj: str, doc_entry: int, layout: str | None = None, s: Session = Depends(get_session)) -> dict:
    from app.services import printing

    _check(obj)
    return run(lambda: printing.print_data(s, obj, doc_entry, layout))


@router.post("/documents/{obj}/{doc_entry}/amend", tags=["Documents"],
             summary="Amend an A/R invoice / credit memo of a GSTR-1-filed month: replacement + cancellation of the original")
def amend_document(obj: str, doc_entry: int, body: DocumentIn, s: Session = Depends(get_session)) -> dict:
    _check(obj)
    from app.services import gst_filing

    doc = run(lambda: gst_filing.amend(s, obj, doc_entry, build_request(obj, body.model_dump(mode="json"))))
    return _doc_out(doc, detail=True)


@router.post("/documents/{obj}/{doc_entry}/cancel", tags=["Documents"], summary="Cancel a document")
def cancel_document(obj: str, doc_entry: int, body: CancelIn, s: Session = Depends(get_session)) -> dict:
    _check(obj)
    return _doc_out(run(lambda: documents.cancel_document(s, obj, doc_entry, body.cancel_date)), detail=True)


@router.post("/documents/{obj}/{doc_entry}/close", tags=["Documents"], summary="Close a quotation or order")
def close_document(obj: str, doc_entry: int, s: Session = Depends(get_session)) -> dict:
    _check(obj)
    return _doc_out(run(lambda: documents.close_document(s, obj, doc_entry)), detail=True)


@router.get("/inventory/journal", tags=["Inventory"], summary="Warehouse journal / inventory audit (OINM)")
def warehouse_journal(item_code: str | None = None, warehouse: str | None = None, limit: int = 200,
                      s: Session = Depends(get_session)) -> list[dict]:
    q = select(WarehouseJournal).order_by(WarehouseJournal.trans_num.desc()).limit(limit)
    if item_code:
        q = q.where(WarehouseJournal.item_code == item_code)
    if warehouse:
        q = q.where(WarehouseJournal.warehouse == warehouse)
    return [{"trans_num": r.trans_num, "doc_date": r.doc_date, "trans_type": r.trans_type,
             "name": documents.DEFS[r.trans_type].name, "doc_entry": r.created_by, "doc_num": r.base_ref,
             "line": r.doc_line_num, "item_code": r.item_code, "warehouse": r.warehouse, "in_qty": r.in_qty,
             "out_qty": r.out_qty, "price": r.price, "trans_value": r.trans_value, "calc_price": r.calc_price,
             "card_code": r.card_code, "jrnl_memo": r.jrnl_memo, "trans_id": r.trans_id} for r in s.scalars(q)]
