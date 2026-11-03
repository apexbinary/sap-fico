"""Approval procedures (B1: Administration -> Approval Procedures) and the approval decisions.

When an originator of an active template adds a document of one of its types and a condition is met
(document total / discount % / gross profit % compared with a value; no condition = always), the
document is not added: it is fully validated (created and rolled back, so errors show at once and
the totals are exact) and held as an approval request (OWDD) with its stages. The authorizers of the
current stage approve or reject (WDD1); with the stage's required approvals the next stage starts,
after the last one the request is approved; the required rejections reject it. The originator then
adds the document from the approved request.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.approvals import (ApprovalDecision, ApprovalRequest, ApprovalStage, ApprovalStageUser, ApprovalTemplate,
                                  ApprovalTemplateCondition, ApprovalTemplateDocument, ApprovalTemplateStage, ApprovalTemplateUser)
from app.models.users import User
from app.services.admin import B1Error

ZERO = Decimal("0")
CONDITIONS = {"TOTAL": "Document total (LC)", "DISC": "Discount %", "GPPCT": "Gross profit %"}
OPS = {"GT": ">", "GE": ">=", "LT": "<", "LE": "<="}
STATUS = {"W": "Pending", "Y": "Approved", "N": "Rejected", "A": "Document added"}


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _cmp(a: Decimal, op: str, b: Decimal) -> bool:
    return {"GT": a > b, "GE": a >= b, "LT": a < b, "LE": a <= b}[op]


# ------------------------------------------------------------- setup
def save_stage(session: Session, data: dict, code: int | None = None) -> ApprovalStage:
    st = session.get(ApprovalStage, code) if code else None
    if code and st is None:
        raise B1Error(f"Approval stage {code} does not exist")
    if st is None:
        st = ApprovalStage(wst_code=(session.scalar(select(func.max(ApprovalStage.wst_code))) or 0) + 1)
        session.add(st)
    if data.get("name"):
        st.name = data["name"].strip()[:30]
    if "remarks" in data:
        st.remarks = data["remarks"]
    users = data.get("authorizers")
    if users is not None:
        for u in users:
            if session.get(User, int(u)) is None:
                raise B1Error(f"User {u} does not exist")
        st.authorizers = [ApprovalStageUser(user_id=int(u)) for u in dict.fromkeys(users)]
    st.max_reqr = int(data.get("max_reqr") or st.max_reqr or 1)
    st.max_rej_reqr = int(data.get("max_rej_reqr") or st.max_rej_reqr or 1)
    if not st.name:
        raise B1Error("Enter the stage name")
    if not st.authorizers:
        raise B1Error("A stage needs at least one authorizer")
    if st.max_reqr > len(st.authorizers) or st.max_rej_reqr > len(st.authorizers):
        raise B1Error("The required approvals / rejections cannot exceed the number of authorizers")
    session.commit()
    return st


def save_template(session: Session, data: dict, code: int | None = None) -> ApprovalTemplate:
    from app.services.documents import DEFS

    t = session.get(ApprovalTemplate, code) if code else None
    if code and t is None:
        raise B1Error(f"Approval template {code} does not exist")
    if t is None:
        t = ApprovalTemplate(wtm_code=(session.scalar(select(func.max(ApprovalTemplate.wtm_code))) or 0) + 1, active="Y")
        session.add(t)
    if data.get("name"):
        t.name = data["name"].strip()[:50]
    if "remarks" in data:
        t.remarks = data["remarks"]
    if data.get("active") is not None:
        t.active = "Y" if data["active"] else "N"
    if data.get("originators") is not None:
        for u in data["originators"]:
            if session.get(User, int(u)) is None:
                raise B1Error(f"User {u} does not exist")
        t.originators = [ApprovalTemplateUser(user_id=int(u)) for u in dict.fromkeys(data["originators"])]
    if data.get("stages") is not None:
        if len(set(map(int, data["stages"]))) != len(data["stages"]):
            raise B1Error("A stage can be used only once in a template")
        for s in data["stages"]:
            if session.get(ApprovalStage, int(s)) is None:
                raise B1Error(f"Approval stage {s} does not exist")
        t.stages = [ApprovalTemplateStage(sort_id=n + 1, wst_code=int(s)) for n, s in enumerate(data["stages"])]
    if data.get("documents") is not None:
        for o in data["documents"]:
            if o not in DEFS or DEFS[o].side == "I" and o not in {"59", "60", "67"}:
                raise B1Error(f"Unknown document type {o}")
        t.documents = [ApprovalTemplateDocument(trans_type=o) for o in dict.fromkeys(data["documents"])]
    if data.get("conditions") is not None:
        rows = []
        for n, c in enumerate(data["conditions"]):
            if c.get("cond_id") not in CONDITIONS or c.get("op_code") not in OPS:
                raise B1Error(f"Condition {n + 1}: choose the term and the operator")
            rows.append(ApprovalTemplateCondition(line_id=n, cond_id=c["cond_id"], op_code=c["op_code"], value=Decimal(str(c.get("value") or 0))))
        t.conditions = rows
    if not t.name:
        raise B1Error("Enter the template name")
    if not t.originators or not t.stages or not t.documents:
        raise B1Error("A template needs originators, stages and document types")
    session.commit()
    return t


def setup(session: Session) -> dict:
    users = {u.user_id: u.user_code for u in session.scalars(select(User))}
    return {
        "stages": [{"wst_code": s.wst_code, "name": s.name, "remarks": s.remarks, "max_reqr": s.max_reqr, "max_rej_reqr": s.max_rej_reqr,
                    "authorizers": [a.user_id for a in s.authorizers], "authorizer_codes": [users.get(a.user_id) for a in s.authorizers]}
                   for s in session.scalars(select(ApprovalStage).order_by(ApprovalStage.wst_code))],
        "templates": [{"wtm_code": t.wtm_code, "name": t.name, "remarks": t.remarks, "active": t.active == "Y",
                       "originators": [o.user_id for o in t.originators], "stages": [s.wst_code for s in t.stages],
                       "documents": [d.trans_type for d in t.documents],
                       "conditions": [{"cond_id": c.cond_id, "op_code": c.op_code, "value": c.value} for c in t.conditions]}
                      for t in session.scalars(select(ApprovalTemplate).order_by(ApprovalTemplate.wtm_code))],
        "users": [{"user_id": k, "user_code": v} for k, v in sorted(users.items())],
        "conditions": CONDITIONS, "ops": OPS,
    }


# ------------------------------------------------------------- requests
def _figures(doc) -> dict:
    disc = Decimal(str(doc.disc_prcnt or 0))
    net = sum((Decimal(str(l.line_total)) for l in doc.lines), ZERO) * (1 - disc / 100)
    gp = sum((Decimal(str(l.grss_profit or 0)) for l in doc.lines), ZERO)
    return {"TOTAL": Decimal(str(doc.doc_total)), "DISC": disc, "GPPCT": (gp / net * 100) if net else ZERO}


def check(session: Session, obj: str, payload: dict, build, user_id: int | None) -> ApprovalRequest | None:
    """Hold the document for approval when a template of the user applies; None = add it normally.
    build(payload) -> DocumentRequest."""
    if user_id is None:
        return None
    templates = session.scalars(select(ApprovalTemplate).join(ApprovalTemplateUser).join(ApprovalTemplateDocument).where(
        ApprovalTemplate.active == "Y", ApprovalTemplateUser.user_id == user_id, ApprovalTemplateDocument.trans_type == obj)
        .order_by(ApprovalTemplate.wtm_code)).unique().all()
    if not templates:
        return None
    from app.services import documents

    doc = documents.create_document(session, build(payload), commit=False)  # validates everything, exact totals
    figures, card, total = _figures(doc), doc.card_code, doc.doc_total
    session.rollback()  # the document is not added
    for t in templates:
        met = [c for c in t.conditions if _cmp(Decimal(figures[c.cond_id]), c.op_code, c.value)]
        if t.conditions and not met:
            continue
        reason = "; ".join(f"{CONDITIONS[c.cond_id]} {Decimal(figures[c.cond_id]).quantize(Decimal('0.01'))} {OPS[c.op_code]} {c.value.normalize():f}"
                           for c in met) or "always"
        req = ApprovalRequest(wdd_code=(session.scalar(select(func.max(ApprovalRequest.wdd_code))) or 0) + 1, wtm_code=t.wtm_code,
                              obj_type=obj, draft=json.dumps(payload, default=str), status="W", current_stage=1, owner_id=user_id,
                              card_code=card, doc_total=total, reason=f"{t.name}: {reason}"[:254], create_date=_now())
        session.add(req)
        session.commit()
        return req
    return None


def _stage(session: Session, req: ApprovalRequest) -> ApprovalStage | None:
    t = session.get(ApprovalTemplate, req.wtm_code)
    row = next((s for s in t.stages if s.sort_id == req.current_stage), None)
    return session.get(ApprovalStage, row.wst_code) if row else None


def decide(session: Session, wdd_code: int, user_id: int, approve: bool, remarks: str | None = None) -> ApprovalRequest:
    req = session.get(ApprovalRequest, wdd_code)
    if req is None:
        raise B1Error(f"Approval request {wdd_code} does not exist")
    if req.status != "W":
        raise B1Error(f"Approval request {wdd_code} is {STATUS[req.status].lower()}")
    st = _stage(session, req)
    if user_id not in [a.user_id for a in st.authorizers]:
        raise B1Error(f"You are not an authorizer of stage {st.name}")
    if any(d.step_code == st.wst_code and d.user_id == user_id for d in req.decisions):
        raise B1Error("You already decided at this stage")
    req.decisions.append(ApprovalDecision(line_id=len(req.decisions), step_code=st.wst_code, user_id=user_id, status="Y" if approve else "N",
                                          remarks=(remarks or None), update_date=_now()))
    here = [d for d in req.decisions if d.step_code == st.wst_code]
    if sum(1 for d in here if d.status == "N") >= st.max_rej_reqr:
        req.status = "N"
    elif sum(1 for d in here if d.status == "Y") >= st.max_reqr:
        t = session.get(ApprovalTemplate, req.wtm_code)
        if req.current_stage >= len(t.stages):
            req.status = "Y"
        else:
            req.current_stage += 1
    session.commit()
    return req


def generate(session: Session, wdd_code: int, user_id: int, superuser: bool, build) -> int:
    """Add the document of an approved request (the originator or a superuser); returns its DocEntry."""
    req = session.get(ApprovalRequest, wdd_code)
    if req is None:
        raise B1Error(f"Approval request {wdd_code} does not exist")
    if req.status != "Y":
        raise B1Error(f"Approval request {wdd_code} is {STATUS[req.status].lower()}, not approved")
    if req.owner_id != user_id and not superuser:
        raise B1Error("Only the originator adds the approved document")
    from app.services import documents

    doc = documents.create_document(session, build(json.loads(req.draft)), commit=False)
    req.status, req.doc_entry = "A", doc.doc_entry
    session.commit()
    return doc.doc_entry


def out(session: Session, req: ApprovalRequest) -> dict:
    from app.services.documents import DEFS

    users = {u.user_id: u.user_code for u in session.scalars(select(User))}
    st = _stage(session, req) if req.status == "W" else None
    return {"wdd_code": req.wdd_code, "obj_type": req.obj_type, "doc_name": DEFS[req.obj_type].name if req.obj_type in DEFS else req.obj_type,
            "status": req.status, "status_name": STATUS[req.status], "owner": users.get(req.owner_id), "owner_id": req.owner_id,
            "card_code": req.card_code, "doc_total": req.doc_total, "reason": req.reason, "create_date": req.create_date,
            "doc_entry": req.doc_entry, "stage": st.name if st else None, "stage_authorizers": [a.user_id for a in st.authorizers] if st else [],
            "template": session.get(ApprovalTemplate, req.wtm_code).name,
            "decisions": [{"stage": session.get(ApprovalStage, d.step_code).name, "user": users.get(d.user_id), "status": d.status,
                           "remarks": d.remarks, "date": d.update_date} for d in req.decisions]}


def requests_for(session: Session, user_id: int, superuser: bool) -> dict:
    rows = session.scalars(select(ApprovalRequest).order_by(ApprovalRequest.wdd_code.desc())).all()
    mine = [out(session, r) for r in rows if r.owner_id == user_id or superuser]
    to_decide = []
    for r in rows:
        if r.status != "W":
            continue
        st = _stage(session, r)
        if st and user_id in [a.user_id for a in st.authorizers] and not any(d.user_id == user_id and d.step_code == st.wst_code for d in r.decisions):
            to_decide.append(out(session, r))
    return {"mine": mine, "to_decide": to_decide}
