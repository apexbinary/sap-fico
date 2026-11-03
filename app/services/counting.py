"""Inventory counting (OINC / INC1) and inventory posting (OIQR / IQR1).

A counting lists items per warehouse with the quantity in the warehouse when it was created
(InWhsQty); counted quantities are entered (Counted Y). Posting books the differences of the
counted lines (counted - InWhsQty): surpluses through one goods receipt, shortages through one
goods issue, at the item cost against the inventory offset accounts (OACP) — so stock, value,
batches / serial numbers and the journal follow the document rules. The counting is closed.
A line of an item that moved after the counting was created must be recounted (the system
quantity changed), as B1 warns; a counting can hold an item / warehouse only once and an item
/ warehouse can be in only one open counting.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.counting import InventoryCounting, InventoryCountingLine, InventoryPosting, InventoryPostingLine
from app.models.inventory import Item, ItemWarehouse, Warehouse
from app.services import batches
from app.services import documents as docs
from app.services.admin import B1Error, next_number, posting_period

ZERO = Decimal("0")


def _user() -> str | None:
    from app.context import current_user_code

    return current_user_code.get()


def _row(session: Session, item_code: str, whs: str) -> ItemWarehouse:
    row = session.get(ItemWarehouse, (item_code, whs))
    if row is None:
        raise B1Error(f"Item {item_code} has no stock row in warehouse {whs}")
    return row


def create(session: Session, count_date: date, lines: list[dict] | None = None, whs_code: str | None = None,
           item_group: int | None = None, remarks: str | None = None) -> InventoryCounting:
    """New counting: the given item / warehouse lines, or all inventory items of a warehouse (and group)."""
    if not lines:
        if not whs_code:
            raise B1Error("Choose items or a warehouse to count")
        if session.get(Warehouse, whs_code) is None:
            raise B1Error(f"Warehouse {whs_code} does not exist")
        q = select(Item).where(Item.invnt_item == "Y", Item.frozen_for == "N")
        if item_group is not None:
            q = q.where(Item.itms_grp_cod == item_group)
        lines = [{"item_code": i.item_code, "whs_code": whs_code} for i in session.scalars(q.order_by(Item.item_code))]
        if not lines:
            raise B1Error("No inventory items to count")
    entry = (session.scalar(select(func.max(InventoryCounting.doc_entry))) or 0) + 1
    cnt = InventoryCounting(doc_entry=entry, doc_num=next_number(session, "1470000065"), count_date=count_date, status="O",
                            remarks=remarks, user_sign=_user())
    seen = set()
    for n, l in enumerate(lines):
        item = session.get(Item, l.get("item_code"))
        whs = l.get("whs_code")
        if item is None or item.invnt_item != "Y":
            raise B1Error(f"Line {n + 1}: {l.get('item_code')} is not an inventory item")
        if (item.item_code, whs) in seen:
            raise B1Error(f"Line {n + 1}: {item.item_code} / {whs} is counted twice")
        seen.add((item.item_code, whs))
        other = session.scalar(select(InventoryCounting.doc_num).join(InventoryCountingLine).where(
            InventoryCounting.status == "O", InventoryCountingLine.item_code == item.item_code, InventoryCountingLine.whs_code == whs))
        if other is not None:
            raise B1Error(f"Line {n + 1}: {item.item_code} / {whs} is already in open counting {other}")
        cnt.lines.append(InventoryCountingLine(line_num=n, item_code=item.item_code, whs_code=whs,
                                               in_whs_qty=_row(session, item.item_code, whs).on_hand, counted="N",
                                               count_qty=ZERO, difference=ZERO))
    session.add(cnt)
    session.commit()
    return cnt


def get(session: Session, entry: int) -> InventoryCounting:
    cnt = session.get(InventoryCounting, entry)
    if cnt is None:
        raise B1Error(f"Inventory counting {entry} does not exist")
    return cnt


def record(session: Session, entry: int, counts: list[dict]) -> InventoryCounting:
    """Counted quantities: [{line_num, count_qty, batches?, remarks?}] (count_qty None = not counted)."""
    cnt = get(session, entry)
    if cnt.status != "O":
        raise B1Error(f"Counting {cnt.doc_num} is closed")
    by_line = {l.line_num: l for l in cnt.lines}
    for c in counts:
        line = by_line.get(int(c["line_num"]))
        if line is None:
            raise B1Error(f"Counting {cnt.doc_num} has no line {c['line_num']}")
        if c.get("count_qty") is None:
            line.counted, line.count_qty, line.difference = "N", ZERO, ZERO
            continue
        qty = Decimal(str(c["count_qty"]))
        if qty < 0:
            raise B1Error(f"{line.item_code}: the counted quantity cannot be negative")
        item = session.get(Item, line.item_code)
        if batches.kind(item) == batches.SERIAL and qty != qty.to_integral_value():
            raise B1Error(f"{line.item_code}: serial numbers are counted in whole units")
        line.counted, line.count_qty, line.difference = "Y", qty, qty - line.in_whs_qty
        if "batches" in c:
            line.batches = json.dumps(c["batches"]) if c["batches"] else None
        if "remarks" in c:
            line.remarks = c["remarks"]
    session.commit()
    return cnt


def post(session: Session, entry: int, doc_date: date) -> InventoryPosting:
    """Post the differences of the counted lines; the counting is closed."""
    cnt = get(session, entry)
    if cnt.status != "O":
        raise B1Error(f"Counting {cnt.doc_num} is already posted")
    posting_period(session, doc_date)
    counted = [l for l in cnt.lines if l.counted == "Y"]
    if not counted:
        raise B1Error("Nothing counted yet")
    for l in counted:
        now = _row(session, l.item_code, l.whs_code).on_hand
        if now != l.in_whs_qty:
            raise B1Error(f"{l.item_code} / {l.whs_code}: the quantity in the warehouse changed since the counting was created "
                          f"({l.in_whs_qty.normalize()} -> {now.normalize()}); create a new counting")
    surplus = [l for l in counted if l.difference > 0]
    shortage = [l for l in counted if l.difference < 0]

    def cost(item: Item) -> Decimal:
        """Item cost; without one the last purchase price, the preferred vendor's price, else the lowest list price
        (a surplus is never valued above what it would cost to buy)."""
        from app.models.inventory import ItemPrice
        from app.services.masterdata import partner_price

        price = item.avg_price or item.last_pur_prc
        if not price and item.card_code:
            price = partner_price(session, item.card_code, item.item_code)
        price = price or session.scalar(select(func.min(ItemPrice.price)).where(ItemPrice.item_code == item.item_code, ItemPrice.price > 0))
        if not price:
            raise B1Error(f"{item.item_code} has no item cost, purchase price or list price to value the surplus; enter a price first")
        return price

    try:
        gr = gi = None
        if surplus:
            req_lines = []
            for l in surplus:
                item = session.get(Item, l.item_code)
                numbers = json.loads(l.batches) if l.batches else None
                req_lines.append(docs.DocLineRequest(
                    item_code=l.item_code, quantity=l.difference, whs_code=l.whs_code, price=cost(item),
                    batches=numbers if batches.kind(item) == batches.BATCH else None,
                    serials=numbers if batches.kind(item) == batches.SERIAL else None))
            gr = docs.create_document(session, docs.DocumentRequest(obj="59", doc_date=doc_date, lines=req_lines, ref2=f"IC{cnt.doc_num}",
                                                                    comments=f"Inventory posting of counting {cnt.doc_num}"), commit=False)
        if shortage:
            gi = docs.create_document(session, docs.DocumentRequest(obj="60", doc_date=doc_date, ref2=f"IC{cnt.doc_num}",
                                                                    comments=f"Inventory posting of counting {cnt.doc_num}", lines=[
                docs.DocLineRequest(item_code=l.item_code, quantity=-l.difference, whs_code=l.whs_code,
                                    batches=json.loads(l.batches) if l.batches and batches.kind(session.get(Item, l.item_code)) == batches.BATCH else None,
                                    serials=json.loads(l.batches) if l.batches and batches.kind(session.get(Item, l.item_code)) == batches.SERIAL else None)
                for l in shortage]), commit=False)
        p_entry = (session.scalar(select(func.max(InventoryPosting.doc_entry))) or 0) + 1
        posting = InventoryPosting(doc_entry=p_entry, doc_num=next_number(session, "10000071"), doc_date=doc_date, base_entry=cnt.doc_entry,
                                   gr_entry=gr.doc_entry if gr else None, gi_entry=gi.doc_entry if gi else None,
                                   value_in=gr.doc_total if gr else ZERO, value_out=gi.doc_total if gi else ZERO, user_sign=_user())
        lines_by_item = {}
        for doc, sign in ((gr, 1), (gi, -1)):
            for dl in (doc.lines if doc else []):
                lines_by_item[(dl.item_code, dl.whs_code)] = (sign * dl.quantity, dl.stock_price, sign * dl.line_total)
        for n, l in enumerate(counted):
            qty, price, total = lines_by_item.get((l.item_code, l.whs_code), (ZERO, session.get(Item, l.item_code).avg_price, ZERO))
            posting.lines.append(InventoryPostingLine(line_num=n, item_code=l.item_code, whs_code=l.whs_code, in_whs_qty=l.in_whs_qty,
                                                      count_qty=l.count_qty, quantity=qty, price=price, line_total=total, base_line=l.line_num))
        session.add(posting)
        cnt.status = "C"
        session.commit()
        return posting
    except Exception:
        session.rollback()
        raise


def close(session: Session, entry: int) -> InventoryCounting:
    """Close a counting without posting."""
    cnt = get(session, entry)
    if cnt.status != "O":
        raise B1Error(f"Counting {cnt.doc_num} is already closed")
    cnt.status = "C"
    session.commit()
    return cnt


def out(session: Session, cnt: InventoryCounting) -> dict:
    posting = session.scalar(select(InventoryPosting).where(InventoryPosting.base_entry == cnt.doc_entry))
    names = {i.item_code: i.item_name for i in session.scalars(select(Item).where(Item.item_code.in_([l.item_code for l in cnt.lines])))}
    return {"doc_entry": cnt.doc_entry, "doc_num": cnt.doc_num, "count_date": cnt.count_date, "status": cnt.status, "remarks": cnt.remarks,
            "lines": [{"line_num": l.line_num, "item_code": l.item_code, "item_name": names.get(l.item_code), "whs_code": l.whs_code,
                       "in_whs_qty": l.in_whs_qty, "counted": l.counted == "Y", "count_qty": l.count_qty, "difference": l.difference,
                       "batches": json.loads(l.batches) if l.batches else None, "remarks": l.remarks,
                       "managed": batches.kind(session.get(Item, l.item_code))} for l in cnt.lines],
            "posting": {"doc_num": posting.doc_num, "doc_date": posting.doc_date, "gr_entry": posting.gr_entry, "gi_entry": posting.gi_entry,
                        "value_in": posting.value_in, "value_out": posting.value_out} if posting else None}
