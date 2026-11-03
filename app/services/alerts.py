"""Alerts (B1: Alerts Management, system alerts), evaluated when a recipient asks for them.

    MINSTOCK  items below their minimum stock in a warehouse (OITW MinStock) or in total (OITM MinLevel)
    OVERDUE   customer items overdue more than Param days
    CREDIT    customers over their credit limit (balance + open deliveries + open orders)
    EXPIRY    batches in stock expiring within Param days
    APPROVAL  approval requests waiting for my decision, my approved requests waiting to be added
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approvals import Alert, AlertRecipient
from app.models.finance import JournalLine
from app.models.inventory import Item, ItemWarehouse
from app.models.partners import BusinessPartner
from app.models.users import User
from app.services.admin import B1Error

TYPES = {"MINSTOCK": "Items below minimum stock", "OVERDUE": "Overdue customer items", "CREDIT": "Customers over the credit limit",
         "EXPIRY": "Batches expiring soon", "APPROVAL": "Approval requests", "ACTIVITY": "My activities due",
         "SERVICE": "My open service calls"}


def setup(session: Session) -> dict:
    users = {u.user_id: u.user_code for u in session.scalars(select(User))}
    return {"alerts": [{"code": a.code, "name": a.name, "type": a.alert_type, "type_name": TYPES.get(a.alert_type), "param": a.param,
                        "active": a.active == "Y", "recipients": [r.user_id for r in a.recipients]}
                       for a in session.scalars(select(Alert).order_by(Alert.code))],
            "users": [{"user_id": k, "user_code": v} for k, v in sorted(users.items())], "types": TYPES}


def save(session: Session, code: int, data: dict) -> Alert:
    a = session.get(Alert, code)
    if a is None:
        raise B1Error(f"Alert {code} does not exist")
    if data.get("active") is not None:
        a.active = "Y" if data["active"] else "N"
    if "param" in data:
        a.param = int(data["param"]) if data["param"] not in (None, "") else None
        if a.param is not None and a.param < 0:
            raise B1Error("The days cannot be negative")
    if data.get("recipients") is not None:
        for u in data["recipients"]:
            if session.get(User, int(u)) is None:
                raise B1Error(f"User {u} does not exist")
        a.recipients = [AlertRecipient(user_id=int(u)) for u in dict.fromkeys(data["recipients"])]
    session.commit()
    return a


def _evaluate(session: Session, a: Alert, user_id: int, on: date) -> list[dict]:
    if a.alert_type == "MINSTOCK":
        out = []
        for w, i in session.execute(select(ItemWarehouse, Item).join(Item, Item.item_code == ItemWarehouse.item_code).where(
                Item.invnt_item == "Y", ItemWarehouse.min_stock > 0, ItemWarehouse.on_hand < ItemWarehouse.min_stock)):
            out.append({"text": f"{i.item_code} {i.item_name}: {w.on_hand.normalize()} in {w.whs_code}, minimum {w.min_stock.normalize()}",
                        "link": f"#/items?code={i.item_code}"})
        for i in session.scalars(select(Item).where(Item.invnt_item == "Y", Item.min_level > 0, Item.on_hand < Item.min_level)):
            out.append({"text": f"{i.item_code} {i.item_name}: {i.on_hand.normalize()} in stock, minimum level {i.min_level.normalize()}",
                        "link": f"#/items?code={i.item_code}"})
        return out
    if a.alert_type == "OVERDUE":
        limit = on - timedelta(days=a.param or 0)
        customers = {b.card_code: b.card_name for b in session.scalars(select(BusinessPartner).where(BusinessPartner.card_type == "C"))}
        return [{"text": f"{l.short_name} {customers[l.short_name]}: {l.base_ref or l.trans_id} due {l.due_date} ({(on - l.due_date).days} days), "
                         f"open {l.bal_due_deb:,.2f}", "link": f"#/statement?code={l.short_name}&to={on}"}
                for l in session.scalars(select(JournalLine).where(JournalLine.short_name.in_(list(customers)), JournalLine.bal_due_deb > 0,
                                                                   JournalLine.short_name != JournalLine.account, JournalLine.due_date < limit)
                                         .order_by(JournalLine.due_date))]
    if a.alert_type == "CREDIT":
        from app.services.credit import exposure

        return [{"text": f"{b.card_code} {b.card_name}: exposure {exposure(b):,.2f} > credit limit {b.credit_line:,.2f}",
                 "link": f"#/partners?code={b.card_code}"}
                for b in session.scalars(select(BusinessPartner).where(BusinessPartner.card_type == "C", BusinessPartner.credit_line > 0))
                if exposure(b) > b.credit_line]
    if a.alert_type == "EXPIRY":
        from app.services.batches import numbers

        until = on + timedelta(days=a.param or 30)
        return [{"text": f"{r['item_code']} batch {r['number']}: {r['quantity'].normalize()} in {r['whs_code']}, expires {r['exp_date']}",
                 "link": f"#/batches?item={r['item_code']}&number={r['number']}"}
                for r in numbers(session) if r["type"] == "batch" and r["exp_date"] and r["exp_date"] <= until]
    if a.alert_type == "ACTIVITY":
        from app.services.crm import ACTIONS, activities

        return [{"text": f"{ACTIONS[x.action]} {x.recontact}{' ' + x.begin_time if x.begin_time else ''}: {x.details}"
                         f"{' (' + x.card_code + ')' if x.card_code else ''}{' — overdue' if x.recontact < on else ''}", "link": f"#/activities?id={x.clg_code}"}
                for x in activities(session, None, on, user_id, None, True)]
    if a.alert_type == "SERVICE":
        from app.models.service import ServiceCall
        from app.services.service import PRIORITY

        now = datetime.now()
        return [{"text": f"Service call {c.call_id} ({c.customer}, {PRIORITY[c.priority].lower()}): {c.subject}"
                         f"{' — resolution overdue' if c.resol_by and c.resol_by < now else ''}", "link": f"#/service-calls?id={c.call_id}"}
                for c in session.scalars(select(ServiceCall).where(ServiceCall.assignee == user_id, ServiceCall.status != -1).order_by(ServiceCall.call_id))]
    if a.alert_type == "APPROVAL":
        from app.services.approvals import requests_for

        u = session.get(User, user_id)
        r = requests_for(session, user_id, False)
        items = [{"text": f"Decide: {x['doc_name']} of {x['card_code'] or '-'} {x['doc_total']:,.2f} by {x['owner']} ({x['reason']})",
                  "link": "#/approvals"} for x in r["to_decide"]]
        items += [{"text": f"Approved: add {x['doc_name']} of {x['card_code'] or '-'} {x['doc_total']:,.2f}", "link": "#/approvals"}
                  for x in r["mine"] if x["status"] == "Y" and x["owner_id"] == user_id]
        return items if u else []
    return []


def for_user(session: Session, user_id: int | None, on: date | None = None) -> dict:
    on = on or date.today()
    out = []
    for a in session.scalars(select(Alert).where(Alert.active == "Y").order_by(Alert.code)):
        if a.alert_type not in {"APPROVAL", "ACTIVITY", "SERVICE"} and user_id not in [r.user_id for r in a.recipients]:
            continue
        if user_id is None:
            continue
        items = _evaluate(session, a, user_id, on)
        if items:
            out.append({"code": a.code, "name": a.name, "type": a.alert_type, "count": len(items), "items": items[:50]})
    return {"alerts": out, "total": sum(x["count"] for x in out)}
