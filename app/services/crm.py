"""CRM: sales stages (OOST), sales opportunities (OOPR / OPR1), activities (OCLG), pipeline and calendar.

An opportunity starts in a stage; moving it on closes the current stage line and opens the next with
the new amount and closing %; the weighted amount is potential x closing %. Won (optionally linked to
a quotation / order of the partner) closes at 100 %, lost at 0 % with a reason. Activities belong to
a user (AttendUser) and may be linked to a partner, an opportunity or a document; closing marks them
done. The pipeline sums open opportunities by stage and sales employee.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crm import Activity, Opportunity, OpportunityStage, SalesStage
from app.models.partners import BusinessPartner, ContactPerson
from app.models.users import User
from app.services.admin import B1Error

ZERO = Decimal("0")
ACTIONS = {"C": "Phone call", "M": "Meeting", "T": "Task", "N": "Note", "E": "E-mail", "O": "Other"}
PRIORITIES = {"0": "Low", "1": "Normal", "2": "High"}
STATUS = {"O": "Open", "W": "Won", "L": "Lost"}


def _today() -> date:
    return date.today()


def _user() -> tuple[int | None, str | None]:
    from app.context import current_user_code, current_user_id

    return current_user_id.get(), current_user_code.get()


def stages(session: Session) -> list[SalesStage]:
    return list(session.scalars(select(SalesStage).where(SalesStage.canceled == "N").order_by(SalesStage.step_id)))


def save_stage(session: Session, data: dict, num: int | None = None) -> SalesStage:
    st = session.get(SalesStage, num) if num else None
    if num and st is None:
        raise B1Error(f"Sales stage {num} does not exist")
    if st is None:
        st = SalesStage(num=(session.scalar(select(func.max(SalesStage.num))) or 0) + 1, canceled="N")
        session.add(st)
    if data.get("descript"):
        st.descript = data["descript"].strip()[:30]
    if data.get("clo_prcnt") is not None:
        st.clo_prcnt = Decimal(str(data["clo_prcnt"]))
    if data.get("step_id") is not None:
        st.step_id = int(data["step_id"])
    if data.get("canceled") is not None:
        st.canceled = "Y" if data["canceled"] else "N"
    if not st.descript or st.clo_prcnt is None or not (0 <= st.clo_prcnt <= 100):
        raise B1Error("Enter the description and a closing % between 0 and 100")
    st.step_id = st.step_id or st.num
    session.commit()
    return st


def _stage_line(o: Opportunity, st: SalesStage, on: date, amount: Decimal, memo: str | None = None, obj_type=None, doc=None):
    for l in o.lines:
        if l.close_date is None:
            l.close_date = on
    o.lines.append(OpportunityStage(line=len(o.lines), step_id=st.num, open_date=on, max_sum_loc=amount, close_prcnt=st.clo_prcnt,
                                    memo=memo, obj_type=obj_type, doc_number=doc))
    o.step_last, o.max_sum_loc, o.clo_prcnt = st.num, amount, st.clo_prcnt
    o.wt_sum_loc = (amount * st.clo_prcnt / 100).quantize(Decimal("0.01"))


def create_opportunity(session: Session, data: dict) -> Opportunity:
    bp = session.get(BusinessPartner, data.get("card_code") or "")
    if bp is None:
        raise B1Error("Choose a business partner (customer or lead)")
    if bp.card_type == "S":
        raise B1Error("Sales opportunities belong to customers or leads")
    if not (data.get("name") or "").strip():
        raise B1Error("Enter the opportunity name")
    sts = stages(session)
    st = session.get(SalesStage, int(data["stage"])) if data.get("stage") else (sts[0] if sts else None)
    if st is None:
        raise B1Error("Define the sales stages first")
    amount = Decimal(str(data.get("max_sum_loc") or 0))
    if amount < 0:
        raise B1Error("The potential amount cannot be negative")
    on = data.get("open_date") or _today()
    on = date.fromisoformat(on) if isinstance(on, str) else on
    pred = data.get("pred_date")
    o = Opportunity(oppr_id=(session.scalar(select(func.max(Opportunity.oppr_id))) or 0) + 1, name=data["name"].strip()[:100], card_code=bp.card_code,
                    cpr_code=int(data["cpr_code"]) if data.get("cpr_code") else None, slp_code=int(data["slp_code"]) if data.get("slp_code") is not None else bp.slp_code,
                    open_date=on, pred_date=date.fromisoformat(pred) if isinstance(pred, str) and pred else pred, status="O", memo=data.get("memo"))
    if o.cpr_code is not None:
        cp = session.get(ContactPerson, o.cpr_code)
        if cp is None or cp.card_code != bp.card_code:
            raise B1Error("The contact person does not belong to the partner")
    _stage_line(o, st, on, amount)
    session.add(o)
    session.commit()
    return o


def get(session: Session, oppr_id: int) -> Opportunity:
    o = session.get(Opportunity, oppr_id)
    if o is None:
        raise B1Error(f"Opportunity {oppr_id} does not exist")
    return o


def advance(session: Session, oppr_id: int, stage: int, amount: Decimal | None = None, on: date | None = None, memo: str | None = None,
            obj_type: str | None = None, doc_entry: int | None = None) -> Opportunity:
    o = get(session, oppr_id)
    if o.status != "O":
        raise B1Error(f"Opportunity {o.oppr_id} is {STATUS[o.status].lower()}")
    st = session.get(SalesStage, int(stage))
    if st is None or st.canceled == "Y":
        raise B1Error(f"Sales stage {stage} does not exist")
    if obj_type:
        _check_doc(session, o, obj_type, doc_entry)
    _stage_line(o, st, on or _today(), Decimal(str(amount)) if amount is not None else o.max_sum_loc, memo, obj_type, doc_entry)
    session.commit()
    return o


def _check_doc(session: Session, o: Opportunity, obj_type: str, doc_entry: int | None) -> None:
    from app.models.documents import DOCUMENT_CLASSES

    if obj_type not in {"23", "17", "15", "13"} or not doc_entry:
        raise B1Error("Link a sales quotation, order, delivery or A/R invoice")
    d = session.get(DOCUMENT_CLASSES[obj_type][0], int(doc_entry))
    if d is None or d.card_code != o.card_code:
        raise B1Error("The linked document does not belong to the opportunity's partner")


def close(session: Session, oppr_id: int, won: bool, on: date | None = None, reason: str | None = None,
          obj_type: str | None = None, doc_entry: int | None = None) -> Opportunity:
    o = get(session, oppr_id)
    if o.status != "O":
        raise B1Error(f"Opportunity {o.oppr_id} is already {STATUS[o.status].lower()}")
    if not won and not (reason or "").strip():
        raise B1Error("Enter the reason why the opportunity was lost")
    if obj_type:
        _check_doc(session, o, obj_type, doc_entry)
    on = on or _today()
    for l in o.lines:
        if l.close_date is None:
            l.close_date = on
            if obj_type:
                l.obj_type, l.doc_number = obj_type, int(doc_entry)
    o.status, o.close_date, o.reason = ("W" if won else "L"), on, (reason or None)
    o.clo_prcnt = Decimal(100) if won else ZERO
    o.wt_sum_loc = o.max_sum_loc if won else ZERO
    session.commit()
    return o


def pipeline(session: Session, slp_code: int | None = None) -> dict:
    sts = {s.num: s for s in session.scalars(select(SalesStage))}
    q = select(Opportunity).where(Opportunity.status == "O")
    if slp_code is not None:
        q = q.where(Opportunity.slp_code == slp_code)
    by_stage: dict[int, dict] = {}
    by_slp: dict = defaultdict(lambda: {"count": 0, "potential": ZERO, "weighted": ZERO})
    for o in session.scalars(q):
        st = sts.get(o.step_last)
        row = by_stage.setdefault(o.step_last, {"stage": st.descript if st else "-", "step_id": st.step_id if st else 0, "clo_prcnt": st.clo_prcnt if st else 0,
                                                "count": 0, "potential": ZERO, "weighted": ZERO})
        row["count"] += 1
        row["potential"] += o.max_sum_loc
        row["weighted"] += o.wt_sum_loc
        s = by_slp[o.slp_code]
        s["count"] += 1
        s["potential"] += o.max_sum_loc
        s["weighted"] += o.wt_sum_loc
    won = session.execute(select(func.count(), func.coalesce(func.sum(Opportunity.max_sum_loc), 0)).where(Opportunity.status == "W")).one()
    lost = session.execute(select(func.count(), func.coalesce(func.sum(Opportunity.max_sum_loc), 0)).where(Opportunity.status == "L")).one()
    stages_ = sorted(by_stage.values(), key=lambda r: r["step_id"])
    return {"stages": stages_, "by_employee": [{"slp_code": k, **v} for k, v in by_slp.items()],
            "open": {"count": sum(r["count"] for r in stages_), "potential": sum((r["potential"] for r in stages_), ZERO),
                     "weighted": sum((r["weighted"] for r in stages_), ZERO)},
            "won": {"count": won[0], "amount": Decimal(won[1])}, "lost": {"count": lost[0], "amount": Decimal(lost[1])},
            "win_rate": (Decimal(won[0]) / (won[0] + lost[0]) * 100).quantize(Decimal("0.1")) if (won[0] + lost[0]) else None}


# ------------------------------------------------------------- activities
def save_activity(session: Session, data: dict, code: int | None = None) -> Activity:
    a = session.get(Activity, code) if code else None
    if code and a is None:
        raise B1Error(f"Activity {code} does not exist")
    uid, ucode = _user()
    if a is None:
        a = Activity(clg_code=(session.scalar(select(func.max(Activity.clg_code))) or 0) + 1, closed="N", user_sign=ucode,
                     create_date=datetime.now().replace(microsecond=0), attend_user=uid, priority="1")
        session.add(a)
    if a.closed == "Y" and data.get("closed") is not False:
        raise B1Error(f"Activity {a.clg_code} is closed")
    if data.get("action"):
        if data["action"] not in ACTIONS:
            raise B1Error("Activity: C call, M meeting, T task, N note, E e-mail, O other")
        a.action = data["action"]
    if data.get("details") is not None:
        a.details = data["details"].strip()[:100]
    for key in ("notes", "location"):
        if key in data:
            setattr(a, key, data[key] or None)
    if "card_code" in data:
        if data["card_code"] and session.get(BusinessPartner, data["card_code"]) is None:
            raise B1Error(f"Business partner {data['card_code']} does not exist")
        a.card_code = data["card_code"] or None
    if "cntct_code" in data:
        a.cntct_code = int(data["cntct_code"]) if data["cntct_code"] else None
        if a.cntct_code:
            cp = session.get(ContactPerson, a.cntct_code)
            if cp is None or cp.card_code != a.card_code:
                raise B1Error("The contact person does not belong to the partner")
    if "attend_user" in data and data["attend_user"]:
        if session.get(User, int(data["attend_user"])) is None:
            raise B1Error(f"User {data['attend_user']} does not exist")
        a.attend_user = int(data["attend_user"])
    for key in ("recontact", "end_date"):
        if key in data:
            v = data[key]
            setattr(a, key, date.fromisoformat(v) if isinstance(v, str) and v else (v or None))
    for key in ("begin_time", "end_time"):
        if key in data:
            v = (data[key] or "").strip()
            if v and not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
                raise B1Error(f"Time {v}: HH:MM")
            setattr(a, key, v or None)
    if data.get("priority") is not None:
        if str(data["priority"]) not in PRIORITIES:
            raise B1Error("Priority: 0 low, 1 normal, 2 high")
        a.priority = str(data["priority"])
    if "opr_id" in data:
        a.opr_id = int(data["opr_id"]) if data["opr_id"] else None
        if a.opr_id:
            o = get(session, a.opr_id)
            a.card_code = a.card_code or o.card_code
    if "doc_type" in data:
        a.doc_type, a.doc_entry = (data.get("doc_type") or None), (int(data["doc_entry"]) if data.get("doc_entry") else None)
    if a.begin_time and a.end_time and (a.end_date or a.recontact) == a.recontact:
        h1, m1 = map(int, a.begin_time.split(":"))
        h2, m2 = map(int, a.end_time.split(":"))
        if h2 * 60 + m2 < h1 * 60 + m1:
            raise B1Error("The end time lies before the start time")
        a.duration = h2 * 60 + m2 - (h1 * 60 + m1)
    if data.get("closed"):
        a.closed, a.close_date = "Y", _today()
    elif data.get("closed") is False:
        a.closed, a.close_date = "N", None
    if not a.action or not a.details or not a.recontact:
        raise B1Error("Enter the activity type, subject and date")
    session.commit()
    return a


def activities(session: Session, date_from: date | None = None, date_to: date | None = None, user_id: int | None = None,
               card_code: str | None = None, open_only: bool = False) -> list[Activity]:
    q = select(Activity)
    if date_from:
        q = q.where(Activity.recontact >= date_from)
    if date_to:
        q = q.where(Activity.recontact <= date_to)
    if user_id:
        q = q.where(Activity.attend_user == user_id)
    if card_code:
        q = q.where(Activity.card_code == card_code)
    if open_only:
        q = q.where(Activity.closed == "N")
    return list(session.scalars(q.order_by(Activity.recontact, Activity.begin_time)))


def activity_out(session: Session, a: Activity) -> dict:
    u = session.get(User, a.attend_user) if a.attend_user else None
    bp = session.get(BusinessPartner, a.card_code) if a.card_code else None
    return {"clg_code": a.clg_code, "action": a.action, "action_name": ACTIONS[a.action], "details": a.details, "notes": a.notes,
            "card_code": a.card_code, "card_name": bp.card_name if bp else None, "cntct_code": a.cntct_code, "attend_user": a.attend_user,
            "attend_code": u.user_code if u else None, "recontact": a.recontact, "begin_time": a.begin_time, "end_date": a.end_date,
            "end_time": a.end_time, "duration": a.duration, "priority": a.priority, "location": a.location, "opr_id": a.opr_id,
            "doc_type": a.doc_type, "doc_entry": a.doc_entry, "closed": a.closed == "Y", "close_date": a.close_date,
            "overdue": a.closed == "N" and a.recontact < _today()}


def opportunity_out(session: Session, o: Opportunity) -> dict:
    sts = {s.num: s for s in session.scalars(select(SalesStage))}
    bp = session.get(BusinessPartner, o.card_code)
    return {"oppr_id": o.oppr_id, "name": o.name, "card_code": o.card_code, "card_name": bp.card_name if bp else None, "cpr_code": o.cpr_code,
            "slp_code": o.slp_code, "open_date": o.open_date, "pred_date": o.pred_date, "close_date": o.close_date, "max_sum_loc": o.max_sum_loc,
            "wt_sum_loc": o.wt_sum_loc, "clo_prcnt": o.clo_prcnt, "stage": o.step_last, "stage_name": sts[o.step_last].descript if o.step_last in sts else None,
            "status": o.status, "status_name": STATUS[o.status], "reason": o.reason, "memo": o.memo,
            "lines": [{"line": l.line, "stage": sts[l.step_id].descript if l.step_id in sts else l.step_id, "open_date": l.open_date, "close_date": l.close_date,
                       "max_sum_loc": l.max_sum_loc, "close_prcnt": l.close_prcnt, "obj_type": l.obj_type, "doc_number": l.doc_number, "memo": l.memo}
                      for l in o.lines],
            "activities": [activity_out(session, a) for a in session.scalars(select(Activity).where(Activity.opr_id == o.oppr_id).order_by(Activity.recontact))]}
