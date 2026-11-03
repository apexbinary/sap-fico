"""Batch and serial numbers of managed items (OITM ManBtchNum / ManSerNum).

Every stock move of a managed item (the warehouse journal rows a document writes) is allocated to
batches / serial numbers and logged (OITL / ITL1); OBTQ / OSRQ keep the quantity per warehouse.

  receipts   the line names them (new batches / serial numbers are created, with expiry and
             manufacturing date); a line copied from a document that issued them (a return of a
             delivery) takes the base line's numbers by default
  issues     the line names them, else the base line's (a return to the vendor of a receipt), else
             they are selected automatically: earliest expiry first, then oldest; expired batches
             are not selected automatically
  transfers  the same numbers leave the source warehouse and enter the target warehouse
  cancel     the logs of the document are reversed
A serial number holds one unit: it must be new (not in stock) when received and in stock in the
warehouse when issued; quantities of serial numbers are whole.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batches import Batch, BatchQuantity, InventoryLog, InventoryLogLine, SerialNumber, SerialQuantity
from app.models.inventory import Item
from app.services.admin import B1Error

ZERO = Decimal("0")
BATCH, SERIAL = "10000044", "10000045"  # OITL ManagedBy


def kind(item: Item | None) -> str | None:
    if item is None:
        return None
    if item.man_btch_num == "Y":
        return BATCH
    if item.man_ser_num == "Y":
        return SERIAL
    return None


def _classes(managed: str):
    return (Batch, BatchQuantity) if managed == BATCH else (SerialNumber, SerialQuantity)


def _number(session: Session, managed: str, item_code: str, dist: str):
    master, _ = _classes(managed)
    return session.scalar(select(master).where(master.item_code == item_code, master.dist_number == dist))


def _qty_row(session: Session, managed: str, number, whs: str, create: bool = False):
    _, qcls = _classes(managed)
    row = session.scalar(select(qcls).where(qcls.md_abs_entry == number.abs_entry, qcls.whs_code == whs))
    if row is None and create:
        row = qcls(abs_entry=(session.scalar(select(func.max(qcls.abs_entry))) or 0) + 1, item_code=number.item_code,
                   sys_number=number.sys_number, whs_code=whs, quantity=ZERO, md_abs_entry=number.abs_entry)
        session.add(row)
        session.flush()
    return row


def _new_number(session: Session, managed: str, item_code: str, a: dict, on: date):
    master, _ = _classes(managed)
    sys_no = (session.scalar(select(func.max(master.sys_number)).where(master.item_code == item_code)) or 0) + 1
    n = master(abs_entry=(session.scalar(select(func.max(master.abs_entry))) or 0) + 1, item_code=item_code, sys_number=sys_no,
               dist_number=a["number"], exp_date=a.get("exp_date"), mnf_date=a.get("mnf_date"), in_date=on, notes=a.get("notes"))
    session.add(n)
    session.flush()
    return n


def _requested(managed: str, lr) -> list[dict]:
    """Allocations named on the request line: batches [{number, quantity, exp_date, mnf_date}] or serials [{number, ...}]."""
    rows = (lr.batches if managed == BATCH else lr.serials) if lr is not None else None
    out = []
    for r in rows or []:
        number = str(r.get("number") or r.get("batch") or r.get("serial") or "").strip()
        if not number:
            raise B1Error("Enter the batch / serial number")
        if len(number) > 36:
            raise B1Error(f"{number}: at most 36 characters")
        exp = r.get("exp_date")
        mnf = r.get("mnf_date")
        out.append({"number": number, "quantity": Decimal(str(r.get("quantity", 1) if managed == BATCH else 1)),
                    "exp_date": date.fromisoformat(exp) if isinstance(exp, str) and exp else exp or None,
                    "mnf_date": date.fromisoformat(mnf) if isinstance(mnf, str) and mnf else mnf or None, "notes": r.get("notes")})
    return out


def _base_allocations(session: Session, managed: str, base_type: str | None, base_entry: int | None, base_line: int | None,
                      item_code: str) -> list[dict]:
    """Numbers the base document line moved (net of its reversals), largest first."""
    if not base_type:
        return []
    master, _ = _classes(managed)
    totals: dict[int, Decimal] = {}
    for log in session.scalars(select(InventoryLog).where(InventoryLog.doc_type == base_type, InventoryLog.doc_entry == base_entry,
                                                          InventoryLog.doc_line == base_line, InventoryLog.item_code == item_code,
                                                          InventoryLog.reversed == "N")):
        for l in log.lines:
            totals[l.md_abs_entry] = totals.get(l.md_abs_entry, ZERO) + abs(l.quantity)
    rows = [{"number": session.get(master, k).dist_number, "quantity": v} for k, v in totals.items() if v > 0]
    return sorted(rows, key=lambda r: -r["quantity"])


def _auto(session: Session, managed: str, item_code: str, whs: str, qty: Decimal, on: date) -> list[dict]:
    """Automatic selection for an issue: earliest expiry first (no expiry last), then oldest; not expired."""
    master, qcls = _classes(managed)
    rows = session.execute(select(master, qcls).join(qcls, qcls.md_abs_entry == master.abs_entry).where(
        master.item_code == item_code, qcls.whs_code == whs, qcls.quantity > 0)).all()
    rows.sort(key=lambda r: (r[0].exp_date is None, r[0].exp_date or date.max, r[0].in_date or date.min, r[0].sys_number))
    out, rest = [], qty
    for number, q in rows:
        if rest <= 0:
            break
        if number.exp_date and number.exp_date < on:
            continue
        take = min(rest, q.quantity)
        out.append({"number": number.dist_number, "quantity": take})
        rest -= take
    if rest > 0:
        raise B1Error(f"Item {item_code}: only {(qty - rest).normalize()} available in batches / serial numbers of warehouse {whs} "
                      f"that are not expired; {qty.normalize()} needed")
    return out


def allocate(ctx, req) -> None:
    """Allocate the warehouse journal rows of a new document (ctx.oinm) to batches / serial numbers."""
    session, doc = ctx.session, ctx.doc
    lines = {l.line_num: l for l in doc.lines}
    log_no = session.scalar(select(func.max(InventoryLog.log_entry))) or 0
    for row in ctx.oinm:
        qty = row.in_qty or row.out_qty
        if not qty:
            continue  # revaluation
        item = session.get(Item, row.item_code)
        managed = kind(item)
        if managed is None:
            continue
        line = lines[row.doc_line_num]
        lr = req.lines[row.doc_line_num] if row.doc_line_num < len(req.lines) else None
        incoming = bool(row.in_qty)
        if managed == SERIAL and qty != qty.to_integral_value():
            raise B1Error(f"Line {row.doc_line_num + 1}: serial numbers are counted in whole units ({qty.normalize()})")
        allocs = _requested(managed, lr) or _base_allocations(session, managed, line.base_type, line.base_entry, line.base_line,
                                                              item.item_code)
        if not allocs:
            if incoming:
                raise B1Error(f"Line {row.doc_line_num + 1}: enter the {'batches' if managed == BATCH else 'serial numbers'} "
                              f"received of item {item.item_code} ({qty.normalize()} {item.invntry_uom or ''})")
            allocs = _auto(session, managed, item.item_code, row.warehouse, qty, doc.doc_date)
        total = sum((a["quantity"] for a in allocs), ZERO)
        if total != qty:
            if line.base_type and not _requested(managed, lr):  # partial copy: take the base numbers in order
                allocs, rest = [], qty
                for a in _base_allocations(session, managed, line.base_type, line.base_entry, line.base_line, item.item_code):
                    take = min(rest, a["quantity"])
                    if take > 0:
                        allocs.append({**a, "quantity": take})
                        rest -= take
                total = qty - rest
            if total != qty:
                raise B1Error(f"Line {row.doc_line_num + 1}: the {'batch' if managed == BATCH else 'serial number'} quantities "
                              f"({total.normalize()}) must equal the quantity in inventory units ({qty.normalize()})")
        seen = set()
        log_no += 1
        log = InventoryLog(log_entry=log_no, item_code=item.item_code, doc_type=doc.obj_type, doc_entry=doc.doc_entry,
                           doc_line=row.doc_line_num, doc_num=doc.doc_num, doc_date=doc.doc_date, loc_code=row.warehouse,
                           stock_eff=1 if incoming else -1, doc_qty=qty, managed_by=managed, reversed="N")
        merged: dict[int, InventoryLogLine] = {}
        for a in allocs:
            if a["number"] in seen and managed == SERIAL:
                raise B1Error(f"Serial number {a['number']} is entered twice")
            seen.add(a["number"])
            if a["quantity"] <= 0:
                raise B1Error(f"{a['number']}: the quantity must be positive")
            number = _number(session, managed, item.item_code, a["number"])
            if incoming:
                if number is None:
                    number = _new_number(session, managed, item.item_code, a, doc.doc_date)
                elif managed == SERIAL and session.scalar(select(func.coalesce(func.sum(SerialQuantity.quantity), 0)).where(
                        SerialQuantity.md_abs_entry == number.abs_entry)) > 0:
                    raise B1Error(f"Serial number {a['number']} of {item.item_code} is already in stock")
                elif a.get("exp_date") and number.exp_date and a["exp_date"] != number.exp_date:
                    raise B1Error(f"Batch {a['number']} has the expiry date {number.exp_date.isoformat()}")
                q = _qty_row(session, managed, number, row.warehouse, create=True)
                q.quantity += a["quantity"]
            else:
                q = _qty_row(session, managed, number, row.warehouse) if number is not None else None
                if q is None or q.quantity < a["quantity"]:
                    raise B1Error(f"{'Batch' if managed == BATCH else 'Serial number'} {a['number']} of {item.item_code}: "
                                  f"{(q.quantity if q is not None else ZERO).normalize()} in warehouse {row.warehouse}, "
                                  f"{a['quantity'].normalize()} needed")
                q.quantity -= a["quantity"]
            signed = a["quantity"] if incoming else -a["quantity"]
            if number.abs_entry in merged:
                merged[number.abs_entry].quantity += signed
            else:
                merged[number.abs_entry] = InventoryLogLine(md_abs_entry=number.abs_entry, item_code=item.item_code,
                                                            sys_number=number.sys_number, quantity=signed)
        log.lines = list(merged.values())
        session.add(log)
    session.flush()


def reverse(session: Session, obj: str, doc_entry: int) -> None:
    """Cancel: undo the batch / serial quantities of the document's logs (the logs are marked reversed)."""
    for log in session.scalars(select(InventoryLog).where(InventoryLog.doc_type == obj, InventoryLog.doc_entry == doc_entry,
                                                          InventoryLog.reversed == "N").order_by(InventoryLog.log_entry.desc())):
        master, _ = _classes(log.managed_by)
        for l in log.lines:
            number = session.get(master, l.md_abs_entry)
            q = _qty_row(session, log.managed_by, number, log.loc_code, create=True)
            if q.quantity - l.quantity < 0:
                raise B1Error(f"{'Batch' if log.managed_by == BATCH else 'Serial number'} {number.dist_number} of {log.item_code} "
                              f"is no longer in warehouse {log.loc_code}; it cannot be reversed")
            q.quantity -= l.quantity
        log.reversed = "Y"
    session.flush()


def check_item_change(item: Item, data: dict) -> None:
    """Batch / serial management can only change while the item has no stock; not both at once."""
    bt = data.get("man_btch_num")
    sr = data.get("man_ser_num")
    new_b = (item.man_btch_num == "Y") if bt is None else bool(bt)
    new_s = (item.man_ser_num == "Y") if sr is None else bool(sr)
    if new_b and new_s:
        raise B1Error("An item is managed by batches or by serial numbers, not both")
    if (new_b != (item.man_btch_num == "Y") or new_s != (item.man_ser_num == "Y")) and item.on_hand:
        raise B1Error(f"Item {item.item_code} has stock: batch / serial management can only change without stock")
    if (new_b or new_s) and item.invnt_item != "Y":
        raise B1Error("Only inventory items are managed by batches / serial numbers")


# ------------------------------------------------------------- reports
def numbers(session: Session, item_code: str | None = None, with_stock: bool = True) -> list[dict]:
    out = []
    for managed in (BATCH, SERIAL):
        master, qcls = _classes(managed)
        q = select(master, qcls).join(qcls, qcls.md_abs_entry == master.abs_entry)
        if item_code:
            q = q.where(master.item_code == item_code)
        if with_stock:
            q = q.where(qcls.quantity > 0)
        for n, row in session.execute(q.order_by(master.item_code, master.exp_date, master.sys_number)):
            out.append({"type": "batch" if managed == BATCH else "serial", "item_code": n.item_code, "number": n.dist_number,
                        "sys_number": n.sys_number, "abs_entry": n.abs_entry, "whs_code": row.whs_code, "quantity": row.quantity,
                        "exp_date": n.exp_date, "mnf_date": n.mnf_date, "in_date": n.in_date,
                        "expired": bool(n.exp_date and n.exp_date < date.today())})
    return out


def history(session: Session, item_code: str, number: str) -> list[dict]:
    """Transactions of one batch / serial number (traceability)."""
    item = session.get(Item, item_code)
    managed = kind(item)
    if managed is None:
        raise B1Error(f"Item {item_code} is not managed by batches / serial numbers")
    n = _number(session, managed, item_code, number)
    if n is None:
        raise B1Error(f"{number} is not a batch / serial number of {item_code}")
    rows = session.execute(select(InventoryLog, InventoryLogLine).join(InventoryLogLine, InventoryLogLine.log_entry == InventoryLog.log_entry)
                           .where(InventoryLogLine.md_abs_entry == n.abs_entry, InventoryLog.managed_by == managed)
                           .order_by(InventoryLog.log_entry)).all()
    return [{"log_entry": log.log_entry, "doc_type": log.doc_type, "doc_entry": log.doc_entry, "doc_num": log.doc_num,
             "doc_date": log.doc_date, "whs_code": log.loc_code, "quantity": line.quantity, "reversed": log.reversed == "Y"}
            for log, line in rows]
