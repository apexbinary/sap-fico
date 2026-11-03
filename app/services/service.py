"""Service: customer equipment cards (OINS), service contracts (OCTR / CTR1), service calls (OSCL).

Delivering a serial-number managed item to a customer (delivery or A/R invoice with stock) creates an
equipment card per serial number. A new service call looks for the customer's approved contract
valid on the day that covers it (customer contract: everything; item contract: the item; serial
contract: the serial number) and takes its response / resolution time as deadlines. Calls move
open -> pending -> closed (a resolution is required); activities link to a call (OCLG DocType 191).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inventory import Item
from app.models.partners import BusinessPartner
from app.models.service import CustomerEquipment, ServiceCall, ServiceContract, ServiceContractLine
from app.models.users import User
from app.services.admin import B1Error

STATUS = {-3: "Open", -2: "Pending", -1: "Closed"}
PRIORITY = {"L": "Low", "M": "Medium", "H": "High"}
EQ_STATUS = {"A": "Active", "R": "Returned", "T": "Terminated", "L": "Loaned", "I": "In repair lab"}
CT_STATUS = {"A": "Approved", "F": "On hold", "D": "Draft", "T": "Terminated"}
CT_TYPE = {"C": "Customer", "I": "Item group / items", "S": "Serial numbers"}


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _bp(session: Session, code: str | None) -> BusinessPartner:
    bp = session.get(BusinessPartner, code or "")
    if bp is None or bp.card_type == "S":
        raise B1Error("Choose a customer")
    return bp


# ------------------------------------------------------------- equipment
def register_from_document(session: Session, doc) -> int:
    """Equipment cards for the serial numbers a delivery / A/R invoice issued to a customer."""
    from app.models.batches import InventoryLog, SerialNumber

    if doc.obj_type not in {"15", "13"} or not doc.card_code:
        return 0
    bp = session.get(BusinessPartner, doc.card_code)
    if bp is None or bp.card_type != "C":
        return 0
    n = 0
    for log in session.scalars(select(InventoryLog).where(InventoryLog.doc_type == doc.obj_type, InventoryLog.doc_entry == doc.doc_entry,
                                                          InventoryLog.managed_by == "10000045", InventoryLog.stock_eff == -1)):
        for l in log.lines:
            sn = session.get(SerialNumber, l.md_abs_entry)
            if session.scalar(select(CustomerEquipment).where(CustomerEquipment.item_code == log.item_code,
                                                              CustomerEquipment.internal_sn == sn.dist_number)) is not None:
                continue
            item = session.get(Item, log.item_code)
            session.add(CustomerEquipment(ins_id=(session.scalar(select(func.max(CustomerEquipment.ins_id))) or 0) + 1, internal_sn=sn.dist_number,
                                          manuf_sn=sn.dist_number, item_code=log.item_code, item_name=item.item_name if item else None,
                                          customer=bp.card_code, status="A", dlv_date=doc.doc_date, dlv_type=doc.obj_type, dlv_entry=doc.doc_entry,
                                          street=bp.address, city=bp.city))
            session.flush()
            n += 1
    return n


def unregister_document(session: Session, obj: str, doc_entry: int) -> None:
    """Canceling the delivering document removes its equipment cards; a card with service calls is set to returned."""
    for eq in session.scalars(select(CustomerEquipment).where(CustomerEquipment.dlv_type == obj, CustomerEquipment.dlv_entry == doc_entry)).all():
        if session.scalar(select(ServiceCall.call_id).where(ServiceCall.ins_id == eq.ins_id).limit(1)) is None:
            session.delete(eq)
        else:
            eq.status = "R"
    session.flush()


def save_equipment(session: Session, data: dict, ins_id: int | None = None) -> CustomerEquipment:
    eq = session.get(CustomerEquipment, ins_id) if ins_id else None
    if ins_id and eq is None:
        raise B1Error(f"Equipment card {ins_id} does not exist")
    if eq is None:
        eq = CustomerEquipment(ins_id=(session.scalar(select(func.max(CustomerEquipment.ins_id))) or 0) + 1, status="A")
        session.add(eq)
    if data.get("customer"):
        eq.customer = _bp(session, data["customer"]).card_code
    if data.get("item_code"):
        it = session.get(Item, data["item_code"])
        if it is None:
            raise B1Error(f"Item {data['item_code']} does not exist")
        eq.item_code, eq.item_name = it.item_code, it.item_name
    for key in ("manuf_sn", "internal_sn", "street", "city"):
        if key in data:
            setattr(eq, key, (data[key] or "").strip() or None)
    if data.get("status"):
        if data["status"] not in EQ_STATUS:
            raise B1Error("Status: A active, R returned, T terminated, L loaned, I in repair lab")
        eq.status = data["status"]
    if not eq.customer or not eq.item_code or not (eq.internal_sn or eq.manuf_sn):
        raise B1Error("An equipment card needs the customer, the item and a serial number")
    session.commit()
    return eq


# ------------------------------------------------------------- contracts
def save_contract(session: Session, data: dict, cid: int | None = None) -> ServiceContract:
    ct = session.get(ServiceContract, cid) if cid else None
    if cid and ct is None:
        raise B1Error(f"Service contract {cid} does not exist")
    if ct is None:
        ct = ServiceContract(contract_id=(session.scalar(select(func.max(ServiceContract.contract_id))) or 0) + 1, status="A")
        session.add(ct)
    if data.get("cstmr_code"):
        ct.cstmr_code = _bp(session, data["cstmr_code"]).card_code
    if data.get("cntrc_type"):
        if data["cntrc_type"] not in CT_TYPE:
            raise B1Error("Contract type: C customer, I items, S serial numbers")
        ct.cntrc_type = data["cntrc_type"]
    for key in ("start_date", "end_date"):
        if data.get(key):
            v = data[key]
            setattr(ct, key, date.fromisoformat(v) if isinstance(v, str) else v)
    for key in ("rspns_time", "resol_time"):
        if key in data:
            setattr(ct, key, int(data[key]) if data[key] not in (None, "") else None)
    for key, col in (("incl_parts", "incl_parts"), ("incl_labor", "incl_labor"), ("incl_travel", "incl_travel")):
        if data.get(key) is not None:
            setattr(ct, col, "Y" if data[key] else "N")
    if data.get("status"):
        if data["status"] not in CT_STATUS:
            raise B1Error("Status: A approved, F on hold, D draft, T terminated")
        ct.status = data["status"]
    if "descriptio" in data:
        ct.descriptio = data["descriptio"]
    if data.get("lines") is not None:
        rows = []
        for n, l in enumerate(data["lines"]):
            if not (l.get("item_code") or l.get("internal_sn")):
                continue
            if l.get("item_code") and session.get(Item, l["item_code"]) is None:
                raise B1Error(f"Item {l['item_code']} does not exist")
            rows.append(ServiceContractLine(line=n, item_code=l.get("item_code") or None, internal_sn=l.get("internal_sn") or None))
        ct.lines = rows
    if not ct.cstmr_code or not ct.start_date or not ct.end_date:
        raise B1Error("Enter the customer and the contract period")
    if ct.end_date < ct.start_date:
        raise B1Error("The contract ends before it starts")
    if ct.cntrc_type in {"I", "S"} and not ct.lines:
        raise B1Error("An item / serial number contract needs the covered items or serial numbers")
    session.commit()
    return ct


def covering_contract(session: Session, customer: str, item_code: str | None, internal_sn: str | None, on: date) -> ServiceContract | None:
    rows = session.scalars(select(ServiceContract).where(ServiceContract.cstmr_code == customer, ServiceContract.status == "A",
                                                         ServiceContract.start_date <= on, ServiceContract.end_date >= on)
                           .order_by(ServiceContract.contract_id)).all()
    for wanted in ("S", "I", "C"):  # the most specific contract wins
        for ct in rows:
            if ct.cntrc_type != wanted:
                continue
            if wanted == "C":
                return ct
            if wanted == "I" and item_code and any(l.item_code == item_code for l in ct.lines):
                return ct
            if wanted == "S" and internal_sn and any(l.internal_sn == internal_sn and (not l.item_code or l.item_code == item_code) for l in ct.lines):
                return ct
    return None


# ------------------------------------------------------------- service calls
def create_call(session: Session, data: dict) -> ServiceCall:
    bp = _bp(session, data.get("customer"))
    if not (data.get("subject") or "").strip():
        raise B1Error("Enter the subject of the service call")
    item_code, sn, ins = data.get("item_code") or None, data.get("internal_sn") or None, None
    if data.get("ins_id"):
        ins = session.get(CustomerEquipment, int(data["ins_id"]))
        if ins is None or ins.customer != bp.card_code:
            raise B1Error("The equipment card does not belong to the customer")
        item_code, sn = ins.item_code, ins.internal_sn
    elif sn:
        ins = session.scalar(select(CustomerEquipment).where(CustomerEquipment.internal_sn == sn, CustomerEquipment.customer == bp.card_code))
    if item_code and session.get(Item, item_code) is None:
        raise B1Error(f"Item {item_code} does not exist")
    priority = data.get("priority") or "M"
    if priority not in PRIORITY:
        raise B1Error("Priority: L low, M medium, H high")
    if data.get("assignee") and session.get(User, int(data["assignee"])) is None:
        raise B1Error(f"User {data['assignee']} does not exist")
    now = _now()
    ct = covering_contract(session, bp.card_code, item_code, sn, now.date())
    call = ServiceCall(call_id=(session.scalar(select(func.max(ServiceCall.call_id))) or 0) + 1, customer=bp.card_code,
                       cntct_code=int(data["cntct_code"]) if data.get("cntct_code") else None, item_code=item_code, internal_sn=sn,
                       ins_id=ins.ins_id if ins else None, subject=data["subject"].strip()[:254], origin=data.get("origin"), call_type=data.get("call_type"),
                       problem_typ=data.get("problem_typ"), priority=priority, status=-3, assignee=int(data["assignee"]) if data.get("assignee") else None,
                       contract=ct.contract_id if ct else None, create_date=now, descrption=data.get("descrption"),
                       response_by=now + timedelta(hours=ct.rspns_time) if ct and ct.rspns_time else None,
                       resol_by=now + timedelta(hours=ct.resol_time) if ct and ct.resol_time else None)
    session.add(call)
    session.commit()
    return call


def update_call(session: Session, call_id: int, data: dict) -> ServiceCall:
    call = session.get(ServiceCall, call_id)
    if call is None:
        raise B1Error(f"Service call {call_id} does not exist")
    if call.status == -1 and data.get("status") != -3:
        raise B1Error(f"Service call {call_id} is closed")
    for key in ("subject", "origin", "call_type", "problem_typ", "descrption", "resolution"):
        if key in data and data[key] is not None:
            setattr(call, key, data[key])
    if data.get("priority"):
        if data["priority"] not in PRIORITY:
            raise B1Error("Priority: L low, M medium, H high")
        call.priority = data["priority"]
    if "assignee" in data:
        if data["assignee"] and session.get(User, int(data["assignee"])) is None:
            raise B1Error(f"User {data['assignee']} does not exist")
        call.assignee = int(data["assignee"]) if data["assignee"] else None
    if data.get("responded") and call.responded is None:
        call.responded = _now()
    if data.get("status") is not None:
        st = int(data["status"])
        if st not in STATUS:
            raise B1Error("Status: -3 open, -2 pending, -1 closed")
        if st == -1:
            if not (call.resolution or "").strip():
                raise B1Error("Enter the resolution before closing the call")
            call.close_date = _now()
            call.responded = call.responded or call.close_date
        elif call.status == -1:
            call.close_date = None  # reopened
        call.status = st
    session.commit()
    return call


def call_out(session: Session, c: ServiceCall) -> dict:
    bp = session.get(BusinessPartner, c.customer)
    u = session.get(User, c.assignee) if c.assignee else None
    now = _now()
    from app.models.crm import Activity
    from app.services.crm import activity_out

    acts = session.scalars(select(Activity).where(Activity.doc_type == "191", Activity.doc_entry == c.call_id).order_by(Activity.recontact)).all()
    return {"call_id": c.call_id, "customer": c.customer, "card_name": bp.card_name if bp else None, "item_code": c.item_code, "internal_sn": c.internal_sn,
            "ins_id": c.ins_id, "subject": c.subject, "origin": c.origin, "call_type": c.call_type, "problem_typ": c.problem_typ,
            "priority": c.priority, "priority_name": PRIORITY[c.priority], "status": c.status, "status_name": STATUS[c.status],
            "assignee": c.assignee, "assignee_code": u.user_code if u else None, "contract": c.contract, "create_date": c.create_date,
            "response_by": c.response_by, "resol_by": c.resol_by, "responded": c.responded, "close_date": c.close_date,
            "resolution": c.resolution, "descrption": c.descrption,
            "response_late": bool(c.response_by and (c.responded or now) > c.response_by),
            "resolution_late": bool(c.resol_by and (c.close_date or now) > c.resol_by),
            "activities": [activity_out(session, a) for a in acts]}


def report(session: Session) -> dict:
    calls = [call_out(session, c) for c in session.scalars(select(ServiceCall).order_by(ServiceCall.call_id.desc()))]
    open_ = [c for c in calls if c["status"] != -1]
    by_tech: dict = {}
    for c in open_:
        t = by_tech.setdefault(c["assignee_code"] or "-", {"technician": c["assignee_code"] or "unassigned", "open": 0, "late": 0})
        t["open"] += 1
        t["late"] += 1 if c["resolution_late"] else 0
    closed = [c for c in calls if c["status"] == -1]
    hours = [(c["close_date"] - c["create_date"]).total_seconds() / 3600 for c in closed]
    return {"open": len(open_), "pending": sum(1 for c in open_ if c["status"] == -2), "late": sum(1 for c in open_ if c["resolution_late"]),
            "closed": len(closed), "avg_hours": round(sum(hours) / len(hours), 1) if hours else None,
            "by_technician": sorted(by_tech.values(), key=lambda t: -t["open"])}
