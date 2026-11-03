"""MRP (B1: MRP Wizard / Order Recommendation): net requirements and recommendations.

Demand up to the horizon: open sales order lines (by delivery date), remaining components of open
production orders, and the minimum level of the item (OITM MinLevel). Supply: stock on hand, open
purchase orders (OnOrder) and the open quantity of production orders of the item. Items are planned
level by level through the production BOMs, so a recommended production order adds demand for its
components. The net requirement (at least the minimum order quantity) is recommended as a production
order (items with a production BOM) or a purchase order (preferred vendor, ordered lead time days
before it is needed). Recommendations are computed when asked; the selected ones become documents.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import DOCUMENT_CLASSES
from app.models.inventory import Item
from app.models.production import BillOfMaterials, ProductionOrder
from app.services.admin import B1Error

ZERO = Decimal("0")


def _levels(session: Session) -> dict[str, int]:
    """Low-level code: a component is planned after all its parents."""
    boms = {b.code: b for b in session.scalars(select(BillOfMaterials).where(BillOfMaterials.tree_type == "P"))}
    level: dict[str, int] = defaultdict(int)
    changed = True
    while changed:
        changed = False
        for code, b in boms.items():
            for l in b.lines:
                if level[l.code] < level[code] + 1:
                    level[l.code] = level[code] + 1
                    changed = True
                    if level[l.code] > 50:
                        raise B1Error("Bills of materials contain a cycle")
    return level


def run(session: Session, horizon: date, today: date | None = None) -> dict:
    today = today or date.today()
    if horizon < today:
        raise B1Error("The horizon lies before today")
    demand: dict[str, list[tuple[date, Decimal, str]]] = defaultdict(list)  # item -> [(need date, qty, source)]
    so_cls = DOCUMENT_CLASSES["17"][0]
    for so in session.scalars(select(so_cls).where(so_cls.doc_status == "O", so_cls.canceled == "N")):
        for l in so.lines:
            if l.item_code and l.open_qty > 0 and l.line_status == "O":
                need = l.ship_date or so.doc_due_date
                if need <= horizon:
                    demand[l.item_code].append((max(need, today), l.open_qty * (l.num_per_msr or 1), f"Sales order {so.doc_num}"))
    open_prod: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for po in session.scalars(select(ProductionOrder).where(ProductionOrder.status.in_(["P", "R"]))):
        open_prod[po.item_code] += max(ZERO, po.planned_qty - po.cmplt_qty)
        for l in po.lines:
            rest = max(ZERO, l.planned_qty - l.issued_qty)
            if rest:
                demand[l.item_code].append((max(po.post_date, today), rest, f"Production order {po.doc_num}"))
    level = _levels(session)
    items = {i.item_code: i for i in session.scalars(select(Item).where(Item.invnt_item == "Y", Item.frozen_for == "N"))}
    for code, i in items.items():
        if i.min_level and i.min_level > 0:
            demand[code].append((today, ZERO, "minimum level"))  # the minimum level is added to the requirement below
    recs, details = [], []
    planned = sorted({c for c in demand if c in items}, key=lambda c: (level.get(c, 0), c))
    queue = list(planned)
    done = set()
    while queue:
        queue.sort(key=lambda c: (level.get(c, 0), c))
        code = queue.pop(0)
        if code in done or code not in items:
            continue
        done.add(code)
        it = items[code]
        rows = demand.get(code, [])
        gross = sum((q for _, q, _ in rows), ZERO) + (it.min_level or ZERO)
        supply = it.on_hand + it.on_order + open_prod.get(code, ZERO)
        net = gross - supply
        need = min((d for d, _, _ in rows), default=today)
        details.append({"item_code": code, "item_name": it.item_name, "level": level.get(code, 0), "gross": gross, "on_hand": it.on_hand,
                        "on_order": it.on_order, "in_production": open_prod.get(code, ZERO), "net": max(net, ZERO),
                        "sources": [s for _, q, s in rows if q] + (["minimum level"] if it.min_level else [])})
        if net <= 0:
            continue
        qty = max(net, it.min_ordr_qty or ZERO)
        bom = session.get(BillOfMaterials, code)
        if bom is not None and bom.tree_type == "P":
            recs.append({"type": "production", "item_code": code, "item_name": it.item_name, "quantity": qty, "due_date": need,
                         "order_date": need, "card_code": None, "warehouse": bom.to_wh or it.dflt_wh})
            for l in bom.lines:  # dependent demand of the components
                demand[l.code].append((need, (l.quantity / bom.qauntity * qty).quantize(Decimal("0.000001")), f"Recommended production of {code}"))
                if l.code not in done and l.code not in queue:
                    queue.append(l.code)
                elif l.code in done:  # already planned at a lower level (should not happen with low-level codes)
                    done.discard(l.code)
                    queue.append(l.code)
        else:
            lead = it.lead_time or 0
            recs.append({"type": "purchase", "item_code": code, "item_name": it.item_name, "quantity": qty, "due_date": need,
                         "order_date": max(today, need - timedelta(days=lead)), "card_code": it.card_code, "warehouse": it.dflt_wh})
    return {"horizon": horizon, "today": today, "recommendations": recs, "items": details}


def create_documents(session: Session, recs: list[dict], on: date, default_vendor: str | None = None) -> dict:
    """Selected recommendations -> purchase orders (one per vendor) and planned production orders."""
    from app.services import documents, production

    by_vendor: dict[str, list[dict]] = defaultdict(list)
    made = {"purchase_orders": [], "production_orders": []}
    for r in recs:
        if Decimal(str(r.get("quantity") or 0)) <= 0:
            raise B1Error(f"{r.get('item_code')}: the quantity must be positive")
        if r["type"] == "purchase":
            vendor = r.get("card_code") or default_vendor
            if not vendor:
                raise B1Error(f"{r['item_code']} has no preferred vendor: choose a vendor for the purchase orders")
            by_vendor[vendor].append(r)
        elif r["type"] != "production":
            raise B1Error("Recommendation type: purchase or production")
    try:
        for vendor, rows in by_vendor.items():
            doc = documents.create_document(session, documents.DocumentRequest(
                obj="22", doc_date=on, card_code=vendor, comments="MRP recommendation",
                lines=[documents.DocLineRequest(item_code=r["item_code"], quantity=Decimal(str(r["quantity"])), whs_code=r.get("warehouse"),
                                                ship_date=date.fromisoformat(str(r["due_date"])) if r.get("due_date") else None) for r in rows]),
                commit=False)
            made["purchase_orders"].append(doc.doc_num)
        session.commit()
    except Exception:
        session.rollback()
        raise
    for r in recs:
        if r["type"] == "production":
            po = production.create_order(session, r["item_code"], Decimal(str(r["quantity"])), on,
                                         date.fromisoformat(str(r["due_date"])) if r.get("due_date") else on, r.get("warehouse"),
                                         comments="MRP recommendation")
            made["production_orders"].append(po.doc_num)
    return made
