"""Production: bills of materials (OITT / ITT1) and production orders (OWOR / WOR1).

Issue for production = a goods issue of components against the work-in-progress account (OACP
WipAcct); receipt from production = backflush components are issued first, then a goods receipt of
the product valued at the order's component cost per unit (issued value per unit of each component,
or its item cost when nothing is issued yet) against the WIP account. Closing posts what is left in
WIP for the order (issued - received) to the production variance account (OACP WipVarAcct). The
stock movements are ordinary goods issues / receipts (Ref2 "WO<number>"), so stock, valuation,
batches and the journal follow the document rules.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import AccountDetermination
from app.models.inventory import Item, Warehouse
from app.models.production import BillOfMaterials, BomLine, ProductionOrder, ProductionOrderLine
from app.services import documents, journal
from app.services.admin import B1Error, next_number

ZERO = Decimal("0")
STATUS = {"P": "Planned", "R": "Released", "L": "Closed", "C": "Canceled"}


def _det(session: Session, on: date) -> AccountDetermination:
    det = session.get(AccountDetermination, str(on.year))
    if det is None:
        raise B1Error(f"No G/L account determination for {on.year}")
    return det


# ------------------------------------------------------------- bills of materials
def _components(session: Session, code: str, seen: set) -> None:
    """Refuse a BOM that contains its own parent (directly or through component BOMs)."""
    bom = session.get(BillOfMaterials, code)
    if bom is None:
        return
    for l in bom.lines:
        if l.code in seen:
            raise B1Error(f"Item {l.code} would be a component of itself")
        _components(session, l.code, seen | {l.code})


def save_bom(session: Session, code: str, data: dict) -> BillOfMaterials:
    parent = session.get(Item, code)
    if parent is None:
        raise B1Error(f"Item {code} does not exist")
    tree_type = data.get("tree_type") or "P"
    if tree_type not in {"P", "S", "A", "T"}:
        raise B1Error("BOM type: P production, S sales, A assembly, T template")
    if tree_type == "P" and parent.invnt_item != "Y":
        raise B1Error("The parent of a production BOM is an inventory item")
    qty = Decimal(str(data.get("qauntity") or 1))
    if qty <= 0:
        raise B1Error("The BOM quantity must be positive")
    lines = data.get("lines") or []
    if not lines:
        raise B1Error("A bill of materials needs components")
    bom = session.get(BillOfMaterials, code)
    if bom is None:
        bom = BillOfMaterials(code=code)
        session.add(bom)
    bom.tree_type, bom.qauntity = tree_type, qty
    bom.to_wh = data.get("to_wh") or parent.dflt_wh
    rows = []
    for n, l in enumerate(lines):
        comp = session.get(Item, l.get("code"))
        if comp is None:
            raise B1Error(f"Component {n + 1}: item {l.get('code')} does not exist")
        if comp.item_code == code:
            raise B1Error("An item cannot be its own component")
        q = Decimal(str(l.get("quantity") or 0))
        if q <= 0:
            raise B1Error(f"Component {comp.item_code}: the quantity must be positive")
        whs = l.get("warehouse") or comp.dflt_wh or bom.to_wh
        if whs and session.get(Warehouse, whs) is None:
            raise B1Error(f"Warehouse {whs} does not exist")
        mthd = l.get("issue_mthd") or "M"
        if mthd not in {"M", "B"}:
            raise B1Error("Issue method: M manual, B backflush")
        rows.append(BomLine(child_num=n, code=comp.item_code, quantity=q, warehouse=whs, issue_mthd=mthd))
    bom.lines = rows
    session.flush()
    _components(session, code, {code})
    session.commit()
    return bom


def bom_cost(session: Session, code: str) -> Decimal:
    bom = session.get(BillOfMaterials, code)
    if bom is None:
        return ZERO
    total = sum((l.quantity * (session.get(Item, l.code).avg_price or session.get(Item, l.code).last_pur_prc or ZERO) for l in bom.lines), ZERO)
    return (total / bom.qauntity).quantize(Decimal("0.0001"))


# ------------------------------------------------------------- production orders
def create_order(session: Session, item_code: str, planned_qty: Decimal, post_date: date, due_date: date | None = None,
                 warehouse: str | None = None, card_code: str | None = None, comments: str | None = None,
                 release: bool = False, origin_num: int | None = None, project: str | None = None, ocr_code: str | None = None,
                 line_whs: dict | None = None) -> ProductionOrder:
    bom = session.get(BillOfMaterials, item_code)
    if bom is None or bom.tree_type != "P":
        raise B1Error(f"Item {item_code} has no production bill of materials")
    planned_qty = Decimal(str(planned_qty))
    if planned_qty <= 0:
        raise B1Error("The planned quantity must be positive")
    item = session.get(Item, item_code)
    whs = warehouse or bom.to_wh or item.dflt_wh
    if not whs or session.get(Warehouse, whs) is None:
        raise B1Error(f"Warehouse {whs} does not exist")
    from app.models.partners import BusinessPartner
    from app.services.admin import check_project

    if card_code and (session.get(BusinessPartner, card_code) is None or session.get(BusinessPartner, card_code).card_type == "S"):
        raise B1Error(f"Customer {card_code} does not exist")
    check_project(session, project or None, post_date)
    if ocr_code:
        from app.services import costacct

        costacct.check_codes(session, (ocr_code,), post_date)
    entry = (session.scalar(select(func.max(ProductionOrder.doc_entry))) or 0) + 1
    po = ProductionOrder(doc_entry=entry, doc_num=next_number(session, "202"), type="S", status="R" if release else "P", item_code=item_code,
                         planned_qty=planned_qty, warehouse=whs, post_date=post_date, due_date=due_date or post_date, card_code=card_code,
                         comments=comments, issued_val=ZERO, rcpt_val=ZERO, origin_num=origin_num, project=project or None, ocr_code=ocr_code or None)
    for n, l in enumerate(bom.lines):
        base = l.quantity / bom.qauntity
        lw = (line_whs or {}).get(str(n)) or (line_whs or {}).get(n) or l.warehouse or whs
        if session.get(Warehouse, lw) is None:
            raise B1Error(f"Component {l.code}: warehouse {lw} does not exist")
        po.lines.append(ProductionOrderLine(line_num=n, item_code=l.code, base_qty=base, planned_qty=(base * planned_qty).quantize(Decimal("0.000001")),
                                            issued_qty=ZERO, issued_val=ZERO, warehouse=lw, issue_type=l.issue_mthd))
    session.add(po)
    session.commit()
    return po


def get(session: Session, entry: int) -> ProductionOrder:
    po = session.get(ProductionOrder, entry)
    if po is None:
        raise B1Error(f"Production order {entry} does not exist")
    return po


def release(session: Session, entry: int) -> ProductionOrder:
    po = get(session, entry)
    if po.status != "P":
        raise B1Error(f"Production order {po.doc_num} is {STATUS[po.status].lower()}")
    po.status = "R"
    session.commit()
    return po


def _issue(session: Session, po: ProductionOrder, on: date, items: list[tuple[ProductionOrderLine, Decimal, list | None]], memo: str) -> None:
    det = _det(session, on)
    lines = [documents.DocLineRequest(item_code=l.item_code, quantity=q, whs_code=l.warehouse, acct_code=det.wip_acct, project=po.project,
                                      batches=b if b and session.get(Item, l.item_code).man_btch_num == "Y" else None,
                                      serials=b if b and session.get(Item, l.item_code).man_ser_num == "Y" else None)
             for l, q, b in items if q > 0]
    if not lines:
        return
    doc = documents.create_document(session, documents.DocumentRequest(obj="60", doc_date=on, lines=lines, ref2=f"WO{po.doc_num}",
                                                                       comments=f"{memo} - production order {po.doc_num}"), commit=False)
    for (l, q, _), dl in zip([x for x in items if x[1] > 0], doc.lines):
        l.issued_qty += q
        l.issued_val += dl.line_total
        po.issued_val += dl.line_total


def issue(session: Session, entry: int, on: date, lines: list[dict] | None = None) -> ProductionOrder:
    """Issue for production: [{line_num, quantity, batches?}] or all remaining manual components."""
    po = get(session, entry)
    if po.status != "R":
        raise B1Error(f"Production order {po.doc_num} must be released")
    by_num = {l.line_num: l for l in po.lines}
    if lines:
        items = []
        for x in lines:
            l = by_num.get(int(x["line_num"]))
            if l is None:
                raise B1Error(f"Production order {po.doc_num} has no component line {x['line_num']}")
            q = Decimal(str(x.get("quantity") or 0))
            if q <= 0:
                raise B1Error(f"Component {l.item_code}: the quantity must be positive")
            items.append((l, q, x.get("batches")))
    else:
        items = [(l, max(ZERO, l.planned_qty - l.issued_qty), None) for l in po.lines if l.issue_type == "M"]
    try:
        _issue(session, po, on, items, "Issue for production")
        session.commit()
        return po
    except Exception:
        session.rollback()
        raise


def unit_cost(po: ProductionOrder, session: Session) -> Decimal:
    """Component cost per unit of the product: issued value per unit of each component (else its item cost)."""
    total = ZERO
    for l in po.lines:
        per = (l.issued_val / l.issued_qty) if l.issued_qty else (session.get(Item, l.item_code).avg_price or session.get(Item, l.item_code).last_pur_prc or ZERO)
        total += l.base_qty * per
    return total.quantize(Decimal("0.01"))


def receive(session: Session, entry: int, on: date, quantity: Decimal, batches: list | None = None) -> ProductionOrder:
    """Receipt from production: backflush components for the quantity, then the product at the component cost."""
    po = get(session, entry)
    if po.status != "R":
        raise B1Error(f"Production order {po.doc_num} must be released")
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise B1Error("The quantity must be positive")
    try:
        _issue(session, po, on, [(l, (l.base_qty * quantity).quantize(Decimal("0.000001")), None) for l in po.lines if l.issue_type == "B"],
               "Backflush")
        price = unit_cost(po, session)
        det = _det(session, on)
        item = session.get(Item, po.item_code)
        doc = documents.create_document(session, documents.DocumentRequest(
            obj="59", doc_date=on, ref2=f"WO{po.doc_num}", comments=f"Receipt from production order {po.doc_num}",
            lines=[documents.DocLineRequest(item_code=po.item_code, quantity=quantity, whs_code=po.warehouse, price=price, acct_code=det.wip_acct, project=po.project,
                                            batches=batches if item.man_btch_num == "Y" else None,
                                            serials=batches if item.man_ser_num == "Y" else None)]), commit=False)
        po.cmplt_qty += quantity
        po.rcpt_val += doc.lines[0].line_total
        session.commit()
        return po
    except Exception:
        session.rollback()
        raise


def close(session: Session, entry: int, on: date) -> ProductionOrder:
    """Close: what is left in WIP (issued - received) goes to the production variance account."""
    po = get(session, entry)
    if po.status != "R":
        raise B1Error(f"Production order {po.doc_num} must be released to be closed")
    det = _det(session, on)
    diff = po.issued_val - po.rcpt_val  # positive: more consumed than received (unfavourable)
    try:
        if diff:
            je = journal.post_entry(session, journal.JournalRequest(
                ref_date=on, memo=f"Production variance WO{po.doc_num}", ref3=f"WO{po.doc_num}", manual=False, trans_type="202", project=po.project, lines=[
                    journal.JournalLineRequest(account=det.wip_var_acct, debit=diff if diff > 0 else ZERO, credit=-diff if diff < 0 else ZERO,
                                               project=po.project, ocr_codes=(po.ocr_code, None, None, None, None) if po.ocr_code else None),
                    journal.JournalLineRequest(account=det.wip_acct, debit=-diff if diff < 0 else ZERO, credit=diff if diff > 0 else ZERO)]),
                commit=False)
            po.var_trans = je.trans_id
        po.status, po.close_date = "L", on
        session.commit()
        return po
    except Exception:
        session.rollback()
        raise


def cancel(session: Session, entry: int) -> ProductionOrder:
    po = get(session, entry)
    if po.status not in {"P", "R"}:
        raise B1Error(f"Production order {po.doc_num} is {STATUS[po.status].lower()}")
    if po.issued_val or po.cmplt_qty:
        raise B1Error("Components were issued or products received: close the order instead")
    po.status = "C"
    session.commit()
    return po


def out(session: Session, po: ProductionOrder) -> dict:
    item = session.get(Item, po.item_code)
    names = {i.item_code: i.item_name for i in session.scalars(select(Item).where(Item.item_code.in_([l.item_code for l in po.lines])))}
    return {"doc_entry": po.doc_entry, "doc_num": po.doc_num, "status": po.status, "status_name": STATUS[po.status], "item_code": po.item_code,
            "item_name": item.item_name if item else None, "planned_qty": po.planned_qty, "cmplt_qty": po.cmplt_qty, "warehouse": po.warehouse,
            "post_date": po.post_date, "due_date": po.due_date, "close_date": po.close_date, "card_code": po.card_code, "comments": po.comments,
            "origin_num": po.origin_num, "project": po.project, "ocr_code": po.ocr_code,
            "issued_val": po.issued_val, "rcpt_val": po.rcpt_val, "wip": po.issued_val - po.rcpt_val if po.status != "L" else ZERO,
            "unit_cost": unit_cost(po, session), "var_trans": po.var_trans,
            "lines": [{"line_num": l.line_num, "item_code": l.item_code, "item_name": names.get(l.item_code), "base_qty": l.base_qty,
                       "planned_qty": l.planned_qty, "issued_qty": l.issued_qty, "issued_val": l.issued_val, "warehouse": l.warehouse,
                       "issue_type": l.issue_type} for l in po.lines]}


def bom_out(session: Session, b: BillOfMaterials) -> dict:
    names = {i.item_code: i.item_name for i in session.scalars(select(Item).where(Item.item_code.in_([b.code] + [l.code for l in b.lines])))}
    return {"code": b.code, "item_name": names.get(b.code), "tree_type": b.tree_type, "qauntity": b.qauntity, "to_wh": b.to_wh,
            "cost": bom_cost(session, b.code),
            "lines": [{"code": l.code, "item_name": names.get(l.code), "quantity": l.quantity, "warehouse": l.warehouse, "issue_mthd": l.issue_mthd}
                      for l in b.lines]}
