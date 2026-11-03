"""REST endpoints: Service — customer equipment cards, service contracts, service calls."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.service import CustomerEquipment, ServiceCall, ServiceContract
from app.services import service
from app.services.admin import B1Error

router = APIRouter()


def _eq(s: Session, e: CustomerEquipment) -> dict:
    from app.models.partners import BusinessPartner

    bp = s.get(BusinessPartner, e.customer)
    ct = service.covering_contract(s, e.customer, e.item_code, e.internal_sn, date.today())
    calls = s.scalars(select(ServiceCall).where(ServiceCall.ins_id == e.ins_id).order_by(ServiceCall.call_id.desc())).all()
    return {"ins_id": e.ins_id, "manuf_sn": e.manuf_sn, "internal_sn": e.internal_sn, "item_code": e.item_code, "item_name": e.item_name,
            "customer": e.customer, "card_name": bp.card_name if bp else None, "status": e.status, "status_name": service.EQ_STATUS[e.status],
            "dlv_date": e.dlv_date, "dlv_type": e.dlv_type, "dlv_entry": e.dlv_entry, "street": e.street, "city": e.city,
            "contract": ct.contract_id if ct else None, "contract_end": ct.end_date if ct else None,
            "calls": [{"call_id": c.call_id, "subject": c.subject, "status_name": service.STATUS[c.status], "create_date": c.create_date} for c in calls]}


def _ct(s: Session, c: ServiceContract) -> dict:
    from app.models.partners import BusinessPartner

    bp = s.get(BusinessPartner, c.cstmr_code)
    return {"contract_id": c.contract_id, "cstmr_code": c.cstmr_code, "card_name": bp.card_name if bp else None, "cntrc_type": c.cntrc_type,
            "type_name": service.CT_TYPE[c.cntrc_type], "start_date": c.start_date, "end_date": c.end_date, "status": c.status,
            "status_name": service.CT_STATUS[c.status], "rspns_time": c.rspns_time, "resol_time": c.resol_time,
            "incl_parts": c.incl_parts == "Y", "incl_labor": c.incl_labor == "Y", "incl_travel": c.incl_travel == "Y", "descriptio": c.descriptio,
            "lines": [{"item_code": l.item_code, "internal_sn": l.internal_sn} for l in c.lines]}


# ------------------------------------------------------------- equipment cards
@router.get("/service/equipment", tags=["Service"], summary="Customer equipment cards")
def list_equipment(customer: str | None = None, s: Session = Depends(get_session)) -> list[dict]:
    q = select(CustomerEquipment).order_by(CustomerEquipment.ins_id.desc())
    if customer:
        q = q.where(CustomerEquipment.customer == customer)
    return [_eq(s, e) for e in s.scalars(q)]


@router.post("/service/equipment", tags=["Service"], summary="Add a customer equipment card")
def add_equipment(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return _eq(s, run(lambda: service.save_equipment(s, body)))


@router.patch("/service/equipment/{ins_id}", tags=["Service"], summary="Change a customer equipment card")
def change_equipment(ins_id: int, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return _eq(s, run(lambda: service.save_equipment(s, body, ins_id)))


# ------------------------------------------------------------- contracts
@router.get("/service/contracts", tags=["Service"], summary="Service contracts")
def list_contracts(customer: str | None = None, s: Session = Depends(get_session)) -> list[dict]:
    q = select(ServiceContract).order_by(ServiceContract.contract_id.desc())
    if customer:
        q = q.where(ServiceContract.cstmr_code == customer)
    return [_ct(s, c) for c in s.scalars(q)]


@router.post("/service/contracts", tags=["Service"], summary="Add a service contract")
def add_contract(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return _ct(s, run(lambda: service.save_contract(s, body)))


@router.patch("/service/contracts/{cid}", tags=["Service"], summary="Change a service contract")
def change_contract(cid: int, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return _ct(s, run(lambda: service.save_contract(s, body, cid)))


# ------------------------------------------------------------- service calls
@router.get("/service/calls", tags=["Service"], summary="Service calls")
def list_calls(status: int | None = None, customer: str | None = None, s: Session = Depends(get_session)) -> list[dict]:
    q = select(ServiceCall).order_by(ServiceCall.call_id.desc())
    if status is not None:
        q = q.where(ServiceCall.status == status)
    if customer:
        q = q.where(ServiceCall.customer == customer)
    return [service.call_out(s, c) for c in s.scalars(q)]


@router.post("/service/calls", tags=["Service"], summary="Add a service call")
def add_call(body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return service.call_out(s, run(lambda: service.create_call(s, body)))


@router.get("/service/calls/{call_id}", tags=["Service"], summary="A service call")
def get_call(call_id: int, s: Session = Depends(get_session)) -> dict:
    def get():
        c = s.get(ServiceCall, call_id)
        if c is None:
            raise B1Error(f"Service call {call_id} does not exist")
        return c
    return service.call_out(s, run(get))


@router.patch("/service/calls/{call_id}", tags=["Service"], summary="Change, respond to, close or reopen a service call")
def change_call(call_id: int, body: dict = Body(...), s: Session = Depends(get_session)) -> dict:
    return service.call_out(s, run(lambda: service.update_call(s, call_id, body)))


@router.get("/service/report", tags=["Service"], summary="Service call overview (open, late, by technician)")
def call_report(s: Session = Depends(get_session)) -> dict:
    return service.report(s)


@router.get("/service/technicians", tags=["Service"], summary="Users who can be assigned to service calls")
def technicians(s: Session = Depends(get_session)) -> list[dict]:
    from app.models.users import User

    return [{"user_id": u.user_id, "user_code": u.user_code, "u_name": u.u_name}
            for u in s.scalars(select(User).where(User.locked == "N").order_by(User.user_code))]
