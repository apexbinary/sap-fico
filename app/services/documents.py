"""Marketing and inventory documents: copy-from chains, stock, automatic journal entries.

Postings per document (perpetual inventory, moving average, accounts from the item group):

    Sales order 17        commits stock (IsCommited)
    Delivery 15           stock out at item cost         Dr COGS / Cr inventory
    A/R invoice 13        Dr BP (gross) / Cr revenue, output VAT; when not based on a
                          delivery also stock out        Dr COGS / Cr inventory
    Return 16             stock in at delivery cost      Dr inventory / Cr COGS
    A/R credit memo 14    Dr revenue, VAT / Cr BP; when not based on a return also stock
                          in at invoice cost; reconciled with the base invoice
    Purchase order 22     stock on order (OnOrder)
    Goods receipt PO 20   stock in at net price          Dr inventory / Cr GRNI (allocation)
    A/P invoice 18        Dr GRNI (base value) or inventory / Cr BP, Dr input VAT; a price
                          difference revalues the stock, or goes to price differences when
                          the stock is gone
    Goods return 21       stock out at item cost         Dr GRNI / Cr inventory (+ difference)
    A/P credit memo 19    Dr BP / Cr VAT, GRNI (based on goods return) or inventory
    Goods receipt 59      Dr inventory / Cr inventory offset (increase)
    Goods issue 60        Dr inventory offset (decrease) / Cr inventory
    Inventory transfer 67 moves stock between warehouses (no posting: company-wide cost)

Issues are valued at the moving average (OITM StockValue / OnHand); every stock change
writes an OINM row, so the inventory account always equals the sum of StockValue.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.documents import DOCUMENT_CLASSES, WarehouseJournal
from app.models.finance import Account, AccountDetermination, JournalLine
from app.models.inventory import Item, ItemGroup, ItemWarehouse, Warehouse
from app.models.partners import BusinessPartner
from app.models.admin import TaxGroup
from app.services import journal, masterdata
from app.services.admin import (B1Error, check_project, check_sales_employee, company, default_series, due_date,
                                next_number, posting_period)
from app.services.journal import JournalLineRequest, JournalRequest

ZERO = Decimal("0")
CENT = Decimal("0.01")
UNIT = Decimal("0.000001")


def money(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def unit(v) -> Decimal:
    return Decimal(v).quantize(UNIT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DocDef:
    obj: str
    name: str
    side: str  # S sales, P purchasing, I inventory
    kind: str  # quotation, order, delivery, return, invoice, credit, receipt, issue, transfer
    bases: tuple[str, ...] = ()

    @property
    def stock(self) -> bool:  # document moves stock (items only)
        return self.kind in {"delivery", "return", "receipt", "issue", "transfer"}


DEFS: dict[str, DocDef] = {d.obj: d for d in [
    DocDef("23", "Sales Quotation", "S", "quotation"),
    DocDef("17", "Sales Order", "S", "order", ("23",)),
    DocDef("15", "Delivery", "S", "delivery", ("23", "17")),
    DocDef("16", "Return", "S", "return", ("15",)),
    DocDef("13", "A/R Invoice", "S", "invoice", ("23", "17", "15")),
    DocDef("14", "A/R Credit Memo", "S", "credit", ("13", "16")),
    DocDef("540000006", "Purchase Quotation", "P", "quotation"),
    DocDef("22", "Purchase Order", "P", "order", ("540000006",)),
    DocDef("20", "Goods Receipt PO", "P", "delivery", ("540000006", "22")),
    DocDef("21", "Goods Return", "P", "return", ("20",)),
    DocDef("18", "A/P Invoice", "P", "invoice", ("540000006", "22", "20")),
    DocDef("19", "A/P Credit Memo", "P", "credit", ("18", "21")),
    DocDef("59", "Goods Receipt", "I", "receipt"),
    DocDef("60", "Goods Issue", "I", "issue"),
    DocDef("67", "Inventory Transfer", "I", "transfer"),
]}


def doc_def(obj: str) -> DocDef:
    if obj not in DEFS:
        raise B1Error(f"Unknown document type {obj}")
    return DEFS[obj]


def get_document(session: Session, obj: str, doc_entry: int):
    header_cls, _ = DOCUMENT_CLASSES[doc_def(obj).obj]
    doc = session.get(header_cls, doc_entry)
    if doc is None:
        raise B1Error(f"{DEFS[obj].name} {doc_entry} does not exist")
    return doc


# ------------------------------------------------------------- requests
@dataclass
class DocLineRequest:
    item_code: str | None = None
    quantity: Decimal = Decimal("1")
    price: Decimal | None = None  # unit price before discount; default from base line / price list
    disc_prcnt: Decimal | None = None
    vat_group: str | None = None
    whs_code: str | None = None
    from_whs_cod: str | None = None  # transfers
    acct_code: str | None = None  # service lines; offset account of goods receipts / issues
    dscription: str | None = None
    base_type: str | None = None
    base_entry: int | None = None
    base_line: int | None = None
    ship_date: date | None = None  # line delivery date
    free_txt: str | None = None
    project: str | None = None
    slp_code: int | None = None


@dataclass
class DocumentRequest:
    obj: str
    doc_date: date
    lines: list[DocLineRequest]
    card_code: str | None = None
    doc_type: str = "I"  # I items, S service
    doc_due_date: date | None = None
    tax_date: date | None = None
    disc_prcnt: Decimal | None = None  # default: base document, else the BP's total discount
    num_at_card: str | None = None
    comments: str | None = None
    from_whs: str | None = None  # transfers: header from / to warehouse
    to_whs: str | None = None
    cntct_code: int | None = None  # defaults: base document, else the business partner
    slp_code: int | None = None
    project: str | None = None
    pay_to_code: str | None = None  # bill-to address ID (CRD1)
    ship_to_code: str | None = None  # ship-to address ID (CRD1)
    jrnl_memo: str | None = None
    ref2: str | None = None


# ------------------------------------------------------------- stock movements
@dataclass
class _Ctx:
    """Document being posted: collects journal lines and warehouse journal rows."""

    session: Session
    d: DocDef
    doc: object
    det: AccountDetermination
    je: dict = field(default_factory=lambda: defaultdict(lambda: ZERO))  # (account | ("BP", code)) -> debit - credit
    vat: dict = field(default_factory=lambda: defaultdict(lambda: ZERO))  # account -> (debit - credit), by tax group
    vat_groups: dict = field(default_factory=dict)
    oinm: list = field(default_factory=list)

    def post(self, account: str, amount: Decimal) -> None:
        """Debit (positive) or credit (negative) a G/L account."""
        if amount:
            self.je[account] += amount


def _warehouse_row(session: Session, item_code: str, whs_code: str) -> ItemWarehouse:
    row = session.get(ItemWarehouse, (item_code, whs_code))
    if row is None:
        if session.get(Warehouse, whs_code) is None:
            raise B1Error(f"Warehouse {whs_code} does not exist")
        row = ItemWarehouse(item_code=item_code, whs_code=whs_code, on_hand=ZERO, is_commited=ZERO, on_order=ZERO,
                            min_stock=ZERO)
        session.add(row)
    return row


def _journal_row(ctx: _Ctx, item: Item, whs: str, line_num: int, in_qty: Decimal, out_qty: Decimal,
                 value: Decimal, memo: str | None = None) -> None:
    qty = in_qty or out_qty
    ctx.oinm.append(WarehouseJournal(
        doc_date=ctx.doc.doc_date, trans_type=ctx.d.obj, created_by=ctx.doc.doc_entry, base_ref=str(ctx.doc.doc_num),
        doc_line_num=line_num, item_code=item.item_code, warehouse=whs, in_qty=in_qty, out_qty=out_qty,
        price=unit(abs(value) / qty) if qty else ZERO, trans_value=value, calc_price=item.avg_price,
        card_code=ctx.doc.card_code, jrnl_memo=memo or ctx.doc.jrnl_memo,
    ))


def _set_avg(item: Item) -> None:
    if item.on_hand > 0:
        item.avg_price = unit(item.stock_value / item.on_hand)


def receive(ctx: _Ctx, item: Item, whs: str, qty: Decimal, value: Decimal, line_num: int, memo: str | None = None) -> None:
    """Stock in: quantity and value (already rounded to cents)."""
    if item.on_hand < 0:
        raise B1Error(f"Item {item.item_code} has negative stock")
    item.on_hand += qty
    item.stock_value += value
    _set_avg(item)
    _warehouse_row(ctx.session, item.item_code, whs).on_hand += qty
    _journal_row(ctx, item, whs, line_num, qty, ZERO, value, memo)


def issue(ctx: _Ctx, item: Item, whs: str, qty: Decimal, line_num: int, value: Decimal | None = None,
          memo: str | None = None) -> Decimal:
    """Stock out at the moving average (or at an exact value, for cancellations); returns the value."""
    row = _warehouse_row(ctx.session, item.item_code, whs)
    if row.on_hand < qty:
        raise B1Error(f"Not enough stock of {item.item_code} in warehouse {whs}: {row.on_hand.normalize()} "
                      f"available, {qty.normalize()} needed")
    if value is None:
        value = item.stock_value if qty == item.on_hand else money(qty * item.avg_price)
    elif qty == item.on_hand and value != item.stock_value:
        raise B1Error(f"Item {item.item_code} was revalued or consumed since; it cannot be reversed at its "
                      f"original value - post a return document instead")
    item.on_hand -= qty
    item.stock_value -= value
    _set_avg(item)
    row.on_hand -= qty
    _journal_row(ctx, item, whs, line_num, ZERO, qty, -value, memo)
    return value


def revalue(ctx: _Ctx, item: Item, whs: str, amount: Decimal, line_num: int, memo: str | None = None) -> None:
    """Change the stock value without quantity (price differences)."""
    if item.on_hand <= 0:
        raise B1Error(f"Item {item.item_code} has no stock to revalue")
    item.stock_value += amount
    _set_avg(item)
    _journal_row(ctx, item, whs, line_num, ZERO, ZERO, amount, memo or "Revaluation")


# ------------------------------------------------------------- create
def _determination(session: Session, on: date) -> AccountDetermination:
    det = session.get(AccountDetermination, str(on.year))
    if det is None:
        raise B1Error(f"No G/L account determination for {on.year}")
    return det


def _partner(session: Session, d: DocDef, card_code: str | None) -> BusinessPartner | None:
    if d.side == "I":
        return None
    if not card_code:
        raise B1Error("Enter a business partner")
    bp = session.get(BusinessPartner, card_code)
    if bp is None:
        raise B1Error(f"Business partner {card_code} does not exist")
    allowed = {"C", "L"} if (d.side == "S" and d.kind == "quotation") else ({"C"} if d.side == "S" else {"S"})
    if bp.card_type not in allowed:
        raise B1Error(f"{bp.card_code} is not a {'customer' if d.side == 'S' else 'vendor'}")
    if bp.frozen_for == "Y":
        raise B1Error(f"Business partner {card_code} is inactive")
    return bp


def _base(session: Session, d: DocDef, req: DocumentRequest, lr: DocLineRequest):
    if lr.base_type not in d.bases:
        raise B1Error(f"A {d.name} cannot be copied from a {DEFS.get(lr.base_type, DocDef('', lr.base_type or '?', '', '')).name}")
    base = get_document(session, lr.base_type, lr.base_entry)
    bd = DEFS[lr.base_type]
    if base.card_code != req.card_code:
        raise B1Error(f"{bd.name} {base.doc_num} belongs to another business partner")
    if base.canceled == "Y" or (bd.kind != "invoice" and base.doc_status != "O"):
        raise B1Error(f"{bd.name} {base.doc_num} is closed or canceled")
    if base.doc_type != req.doc_type:
        raise B1Error(f"{bd.name} {base.doc_num} is a {'service' if base.doc_type == 'S' else 'item'} document")
    line = next((l for l in base.lines if l.line_num == lr.base_line), None)
    if line is None or line.line_status != "O":
        raise B1Error(f"Line {lr.base_line} of {bd.name} {base.doc_num} is not open")
    return base, line


def _tax(session: Session, d: DocDef, code: str | None) -> TaxGroup | None:
    if d.side == "I" or code is None:
        return None
    tg = session.get(TaxGroup, code)
    category = "O" if d.side == "S" else "I"
    if tg is None or tg.category != category or tg.inactive == "Y":
        raise B1Error(f"Tax group {code} is not {'an output' if category == 'O' else 'an input'} tax group")
    return tg


def create_document(session: Session, req: DocumentRequest, *, commit: bool = True):
    try:
        doc = _create(session, req)
        if commit:
            session.commit()
        else:
            session.flush()
        return doc
    except Exception:
        session.rollback()
        raise


def _create(session: Session, req: DocumentRequest):
    d = doc_def(req.obj)
    header_cls, line_cls = DOCUMENT_CLASSES[d.obj]
    posting_period(session, req.doc_date, req.doc_due_date, req.tax_date)
    if req.doc_type not in {"I", "S"}:
        raise B1Error("Document type must be I (items) or S (service)")
    if req.doc_type == "S" and (d.side == "I" or d.kind in {"delivery", "return"}):
        raise B1Error(f"A {d.name} is always an item document")
    if not req.lines:
        raise B1Error("Enter at least one line")
    bp = _partner(session, d, req.card_code)
    # header defaults: the (first) base document, else the business partner master data
    hb = next((get_document(session, l.base_type, l.base_entry) for l in req.lines
               if l.base_type in d.bases and l.base_entry is not None), None)
    pick = lambda value, attr, fallback=None: value if value is not None else (getattr(hb, attr) if hb is not None else fallback)  # noqa: E731
    hdisc = Decimal(pick(req.disc_prcnt, "disc_prcnt", bp.discount if bp else 0) or 0)
    header = _header_defaults(session, d, req, bp, pick)
    if not (0 <= hdisc < 100):
        raise B1Error("The document discount must be between 0 and 100 %")

    lines = []
    for n, lr in enumerate(req.lines):
        qty = Decimal(lr.quantity if req.doc_type == "I" else 1)
        if qty <= 0:
            raise B1Error(f"Line {n + 1}: the quantity must be positive")
        base = base_line = None
        if lr.base_type:
            base, base_line = _base(session, d, req, lr)
            if qty > base_line.open_qty:
                raise B1Error(f"Line {n + 1}: only {base_line.open_qty.normalize()} open on "
                              f"{DEFS[lr.base_type].name} {base.doc_num}")
            if lr.item_code and lr.item_code != base_line.item_code:
                raise B1Error(f"Line {n + 1}: the item differs from the base line")
        item_code = lr.item_code or (base_line.item_code if base_line else None)
        item = None
        if req.doc_type == "I":
            item = session.get(Item, item_code) if item_code else None
            if item is None:
                raise B1Error(f"Line {n + 1}: item {item_code or ''} does not exist")
            if item.frozen_for == "Y":
                raise B1Error(f"Item {item.item_code} is inactive")
            if d.side == "S" and item.sell_item != "Y":
                raise B1Error(f"Item {item.item_code} is not a sales item")
            if d.side == "P" and item.prchse_item != "Y":
                raise B1Error(f"Item {item.item_code} is not a purchase item")
            if (d.stock or d.side == "I") and item.invnt_item != "Y":
                raise B1Error(f"Item {item.item_code} is not an inventory item")
            acct = lr.acct_code
        else:
            acct = lr.acct_code or (base_line.acct_code if base_line else None)
            a = session.get(Account, acct) if acct else None
            if a is None or a.postable != "Y" or a.loc_man_tran == "Y" or a.frozen == "Y":
                raise B1Error(f"Line {n + 1}: enter an active G/L account that is not a control account")

        # price, discount, tax group, warehouse: request, else base line, else defaults
        if lr.price is not None:
            price = Decimal(lr.price)
        elif base_line is not None:
            price = base_line.price_bef_di
        elif d.side == "I":
            price = item.avg_price if d.kind != "receipt" else (item.avg_price or item.last_pur_prc)
        elif item is not None:
            price = masterdata.partner_price(session, bp.card_code, item.item_code)
            if d.side == "P" and not price:
                price = item.last_pur_prc
        else:
            raise B1Error(f"Line {n + 1}: enter an amount")
        if price < 0:
            raise B1Error(f"Line {n + 1}: the price cannot be negative")
        disc = Decimal(lr.disc_prcnt if lr.disc_prcnt is not None else (base_line.disc_prcnt if base_line else 0))
        vat_code = lr.vat_group or (base_line.vat_group if base_line else None)
        if vat_code is None and d.side != "I":
            vat_code = (item.vat_gourp_sa if d.side == "S" else item.vat_group_pu) if item else None
            vat_code = vat_code or bp.vat_group
        tg = _tax(session, d, vat_code)
        whs = None
        if item is not None and item.invnt_item == "Y":
            whs = lr.whs_code or (base_line.whs_code if base_line else None) or req.to_whs or item.dflt_wh
            whs = whs or session.scalar(select(Warehouse.whs_code).order_by(Warehouse.whs_code))
            if session.get(Warehouse, whs) is None:
                raise B1Error(f"Warehouse {whs} does not exist")
        price_after = unit(price * (1 - disc / 100))
        project = lr.project or (base_line.project if base_line else None) or header.get("project")
        check_project(session, project, req.doc_date)
        check_sales_employee(session, lr.slp_code)
        line_total = money(qty * price_after)
        lines.append(dict(lr=lr, item=item, base=base, base_line=base_line, qty=qty, price=price, disc=disc,
                          price_after=price_after, line_total=line_total, tg=tg, whs=whs, acct=acct,
                          project=project))

    # header discount and tax per line (document-level amounts used for postings)
    for x in lines:
        x["net"] = money(x["line_total"] * (1 - hdisc / 100))
        x["vat"] = money(x["net"] * (x["tg"].rate if x["tg"] else 0) / 100)
    total_before = sum((x["line_total"] for x in lines), ZERO)
    net_total = sum((x["net"] for x in lines), ZERO)
    vat_total = sum((x["vat"] for x in lines), ZERO)

    entry = (session.scalar(select(func.max(header_cls.doc_entry))) or 0) + 1
    main = company(session).main_curncy
    doc = header_cls(
        doc_entry=entry, doc_num=next_number(session, d.obj), doc_type=req.doc_type, canceled="N", doc_status="O",
        obj_type=d.obj, doc_date=req.doc_date, tax_date=req.tax_date or req.doc_date,
        doc_due_date=req.doc_due_date or (due_date(session, bp.group_num, req.doc_date, req.tax_date)
                                          if bp and d.kind in {"invoice", "credit"} else req.doc_date),
        card_code=bp.card_code if bp else None, card_name=bp.card_name if bp else None, num_at_card=req.num_at_card,
        doc_cur=main, doc_rate=Decimal("1"), group_num=bp.group_num if bp else None, disc_prcnt=hdisc,
        disc_sum=total_before - net_total, vat_sum=vat_total,
        doc_total=net_total + vat_total if d.side != "I" else net_total, paid_to_date=ZERO,
        filler=req.from_whs, to_whs_code=req.to_whs, comments=req.comments,
        jrnl_memo=(req.jrnl_memo or (f"{d.name} - {bp.card_code}" if bp else d.name))[:50],
        series=default_series(session, d.obj), ref2=req.ref2, **header,
    )
    for n, x in enumerate(lines):
        lr, item = x["lr"], x["item"]
        doc.lines.append(line_cls(
            line_num=n, line_status="O", item_code=item.item_code if item else None,
            dscription=lr.dscription or (x["base_line"].dscription if x["base_line"] else None) or (item.item_name if item else None),
            quantity=x["qty"], open_qty=x["qty"], price_bef_di=x["price"], disc_prcnt=x["disc"], price=x["price_after"],
            line_total=x["line_total"], vat_group=x["tg"].code if x["tg"] else None,
            vat_prcnt=x["tg"].rate if x["tg"] else ZERO, vat_sum=x["vat"], gtotal=x["net"] + x["vat"],
            whs_code=x["whs"], from_whs_cod=lr.from_whs_cod or req.from_whs if d.kind == "transfer" else None,
            acct_code=x["acct"], unit_msr=item.invntry_uom if item else None,
            stock_price=x["base_line"].stock_price if x["base_line"] else ZERO,
            base_type=lr.base_type, base_entry=x["base"].doc_entry if x["base"] else None,
            base_line=lr.base_line if x["base"] else None, base_ref=str(x["base"].doc_num) if x["base"] else None,
            ship_date=lr.ship_date or (x["base_line"].ship_date if x["base_line"] else None) or doc.doc_due_date,
            free_txt=lr.free_txt if lr.free_txt is not None else (x["base_line"].free_txt if x["base_line"] else None),
            project=x["project"], slp_code=lr.slp_code if lr.slp_code is not None else header.get("slp_code"),
            price_af_vat=unit(x["price_after"] * (1 + (x["tg"].rate if x["tg"] else ZERO) / 100)),
        ))
    session.add(doc)
    session.flush()

    ctx = _Ctx(session=session, d=d, doc=doc, det=_determination(session, req.doc_date))
    for line, x in zip(doc.lines, lines):
        _post_line(ctx, line, x)
    _copy_effects(ctx, lines)
    _commitments(session, d, doc, +1)
    if d.side != "I" and d.kind in {"invoice", "credit"}:
        sign = 1 if (d.side, d.kind) in {("S", "invoice"), ("P", "credit")} else -1
        ctx.je[("BP", doc.card_code)] += sign * doc.doc_total
    _post_journal(ctx)
    if d.kind == "credit":
        _reconcile_with_invoice(ctx, lines)
    if d.side == "I":
        doc.doc_status = "C"  # inventory documents have nothing to copy
        for line in doc.lines:
            line.line_status, line.open_qty = "C", ZERO
    if bp is not None:
        refresh_partner(session, bp)
    session.flush()
    return doc


def _address_text(a) -> str:
    return ", ".join(filter(None, [a.street, a.block, " ".join(filter(None, [a.zip_code, a.city])), a.county,
                                   a.state, a.country]))


def _header_defaults(session: Session, d: DocDef, req: DocumentRequest, bp, pick) -> dict:
    """Contact person, sales employee, project and addresses of a new document."""
    from app.models.partners import ContactPerson, PartnerAddress

    if bp is None:
        project = pick(req.project, "project")
        check_project(session, project, req.doc_date)
        return {"project": project, "slp_code": None}
    slp = pick(req.slp_code, "slp_code", bp.slp_code)
    check_sales_employee(session, slp)
    default_contact = session.scalar(select(ContactPerson.cntct_code).where(
        ContactPerson.card_code == bp.card_code, ContactPerson.name == bp.cntct_prsn)) if bp.cntct_prsn else None
    contact = pick(req.cntct_code, "cntct_code", default_contact)
    if contact is not None:
        cp = session.get(ContactPerson, contact)
        if cp is None or cp.card_code != bp.card_code:
            raise B1Error(f"Contact person {contact} does not belong to {bp.card_code}")
    project = pick(req.project, "project", bp.project_cod)
    check_project(session, project, req.doc_date)
    out = {"card_code": bp.card_code, "cntct_code": contact, "slp_code": slp, "project": project,
           "lic_trad_num": bp.lic_trad_num}
    for kind, code, field_code, field_text, default in [
            ("B", req.pay_to_code, "pay_to_code", "address", bp.bill_to_def),
            ("S", req.ship_to_code, "ship_to_code", "address2", bp.ship_to_def)]:
        addr_id = pick(code, field_code, default)
        if addr_id:
            a = session.get(PartnerAddress, (bp.card_code, kind, addr_id))
            if a is None:
                raise B1Error(f"{'Bill-to' if kind == 'B' else 'Ship-to'} address {addr_id} of {bp.card_code} does not exist")
            out[field_code], out[field_text] = addr_id, _address_text(a)
        elif kind == "B":  # no address master data: the general address of the partner
            out[field_text] = ", ".join(filter(None, [bp.address, " ".join(filter(None, [bp.zip_code, bp.city])), bp.country]))
    out.pop("card_code")
    return out


def _post_line(ctx: _Ctx, line, x: dict) -> None:
    """Stock movement and G/L amounts of one line."""
    d, item, qty, net = ctx.d, x["item"], line.quantity, x["net"]
    group = ctx.session.get(ItemGroup, item.itms_grp_cod) if item else None
    inventory = item is not None and item.invnt_item == "Y"
    base_kind = DEFS[line.base_type].kind if line.base_type else None
    n, whs = line.line_num, line.whs_code

    if d.side in {"S", "P"} and d.kind in {"invoice", "credit"} and x["vat"]:
        sign = -1 if (d.side, d.kind) in {("S", "invoice"), ("P", "credit")} else 1
        ctx.vat[x["tg"].account] += sign * x["vat"]
        ctx.vat_groups[x["tg"].account] = x["tg"].code

    if d.side == "S":
        revenue = group.revenues_ac if group else line.acct_code
        if d.kind == "delivery" or (d.kind == "invoice" and inventory and base_kind != "delivery"):
            cost = issue(ctx, item, whs, qty, n)
            line.stock_price = unit(cost / qty)
            ctx.post(group.sale_cost_ac, cost)
            ctx.post(group.bal_invnt_ac, -cost)
        if d.kind == "return" or (d.kind == "credit" and inventory and base_kind != "return"):
            cost = money(qty * line.stock_price) if line.base_type else money(qty * item.avg_price)
            receive(ctx, item, whs, qty, cost, n)
            if not line.base_type:  # copied lines keep the base line's unit cost
                line.stock_price = unit(cost / qty)
            ctx.post(group.bal_invnt_ac, cost)
            ctx.post(group.sale_cost_ac, -cost)
        if d.kind == "invoice":
            ctx.post(revenue, -net)
        elif d.kind == "credit":
            ctx.post(revenue, net)
        if d.kind in {"delivery", "invoice"} and item is not None:
            line.grss_profit = net - money(qty * line.stock_price)

    elif d.side == "P":
        expense = (group.expenses_ac if group else line.acct_code)
        grni = ctx.det.allocation
        if d.kind == "delivery":  # goods receipt PO
            if inventory:
                receive(ctx, item, whs, qty, net, n)
                ctx.post(group.bal_invnt_ac, net)
                ctx.post(grni, -net)
            line.stock_price = unit(net / qty)
            item.last_pur_prc = line.price
        elif d.kind == "invoice":
            if base_kind == "delivery" and inventory:
                base_value = money(qty * x["base_line"].stock_price)
                ctx.post(grni, base_value)
                _price_difference(ctx, item, group, whs, qty, net - base_value, n)
            elif inventory:
                receive(ctx, item, whs, qty, net, n)
                ctx.post(group.bal_invnt_ac, net)
            else:
                ctx.post(expense, net)
            line.stock_price = unit(net / qty)
            if item is not None:
                item.last_pur_prc = line.price
        elif d.kind == "return":  # goods return
            base_value = money(qty * line.stock_price) if line.base_type else net
            cost = issue(ctx, item, whs, qty, n)
            ctx.post(grni, base_value)
            ctx.post(group.bal_invnt_ac, -cost)
            ctx.post(group.price_dif_ac, cost - base_value)
            line.stock_price = unit(base_value / qty)
        elif d.kind == "credit":
            if base_kind == "return" and inventory:
                base_value = money(qty * x["base_line"].stock_price)
                ctx.post(grni, -base_value)
                ctx.post(group.price_dif_ac, base_value - net)
            elif inventory:
                cost = issue(ctx, item, whs, qty, n)
                ctx.post(group.bal_invnt_ac, -cost)
                ctx.post(group.price_dif_ac, cost - net)
            else:
                ctx.post(expense, -net)
            line.stock_price = unit(net / qty)

    else:  # inventory documents
        if d.kind == "receipt":
            value = money(qty * line.price)
            receive(ctx, item, whs, qty, value, n)
            line.stock_price = line.price
            ctx.post(group.bal_invnt_ac, value)
            ctx.post(line.acct_code or ctx.det.inv_offset_inc, -value)
        elif d.kind == "issue":
            value = issue(ctx, item, whs, qty, n)
            line.stock_price = unit(value / qty)
            ctx.post(line.acct_code or ctx.det.inv_offset_dec, value)
            ctx.post(group.bal_invnt_ac, -value)
        elif d.kind == "transfer":
            src = line.from_whs_cod
            if not src or ctx.session.get(Warehouse, src) is None:
                raise B1Error(f"Line {n + 1}: enter the warehouse to transfer from")
            if src == whs:
                raise B1Error(f"Line {n + 1}: from and to warehouse are the same")
            value = issue(ctx, item, src, qty, n)
            receive(ctx, item, whs, qty, value, n)
            line.stock_price = unit(value / qty)
        line.line_total = money(qty * line.stock_price)
    if d.side == "I":
        ctx.doc.doc_total = sum((l.line_total for l in ctx.doc.lines), ZERO)


def _price_difference(ctx: _Ctx, item: Item, group: ItemGroup, whs: str, qty: Decimal, diff: Decimal, n: int) -> None:
    """Invoice price differs from the receipt: revalue stock that is still on hand, else price differences."""
    if not diff:
        return
    if item.on_hand >= qty:
        revalue(ctx, item, whs, diff, n, "Price difference")
        ctx.post(group.bal_invnt_ac, diff)
    else:
        ctx.post(group.price_dif_ac, diff)


def _copy_effects(ctx: _Ctx, lines: list[dict]) -> None:
    """Reduce the open quantity of base lines; release commitments; close fully copied documents."""
    touched = {}
    for line, x in zip(ctx.doc.lines, lines):
        base, bl = x["base"], x["base_line"]
        if bl is None:
            continue
        bl.open_qty -= line.quantity
        bl.target_type, bl.trget_entry = ctx.d.obj, ctx.doc.doc_entry
        if bl.open_qty <= 0:
            bl.open_qty, bl.line_status = ZERO, "C"
        _commit_line(ctx.session, base.obj_type, bl, -line.quantity)
        touched[(base.obj_type, base.doc_entry)] = base
    for base in touched.values():
        if DEFS[base.obj_type].kind != "invoice" and all(l.line_status == "C" for l in base.lines):
            base.doc_status = "C"


def _commit_line(session: Session, obj: str, line, qty: Decimal) -> None:
    """Orders commit stock (IsCommited), purchase orders put it on order (OnOrder)."""
    if obj not in {"17", "22"} or not line.item_code or not line.whs_code:
        return
    item = session.get(Item, line.item_code)
    if item.invnt_item != "Y":
        return
    row = _warehouse_row(session, item.item_code, line.whs_code)
    if obj == "17":
        item.is_commited += qty
        row.is_commited += qty
    else:
        item.on_order += qty
        row.on_order += qty


def _commitments(session: Session, d: DocDef, doc, sign: int) -> None:
    for line in doc.lines:
        _commit_line(session, d.obj, line, sign * line.open_qty)


def _post_journal(ctx: _Ctx) -> None:
    amounts = dict(ctx.je)
    for acct, amount in ctx.vat.items():
        amounts[("VAT", acct)] = amounts.get(("VAT", acct), ZERO) + amount
    lines = []
    for key, amount in amounts.items():
        amount = money(amount)
        if not amount:
            continue
        debit, credit = (amount, ZERO) if amount > 0 else (ZERO, -amount)
        if isinstance(key, tuple) and key[0] == "BP":
            lines.append(JournalLineRequest(card_code=key[1], debit=debit, credit=credit, due_date=ctx.doc.doc_due_date))
        elif isinstance(key, tuple):
            lines.append(JournalLineRequest(account=key[1], debit=debit, credit=credit, vat_group=ctx.vat_groups.get(key[1])))
        else:
            lines.append(JournalLineRequest(account=key, debit=debit, credit=credit))
    doc = ctx.doc
    if lines:
        entry = journal.post_entry(ctx.session, JournalRequest(
            ref_date=doc.doc_date, tax_date=doc.tax_date, due_date=doc.doc_due_date, memo=doc.jrnl_memo,
            ref1=str(doc.doc_num), ref2=doc.num_at_card or doc.ref2, trans_type=ctx.d.obj, base_ref=str(doc.doc_num),
            project=doc.project,
            created_by=doc.doc_entry, manual=False, lines=lines), commit=False)
        doc.trans_id = entry.trans_id
    trans_num = ctx.session.scalar(select(func.max(WarehouseJournal.trans_num))) or 0
    for row in ctx.oinm:
        trans_num += 1
        row.trans_num, row.trans_id = trans_num, doc.trans_id
        ctx.session.add(row)
    ctx.oinm.clear()


def _bp_line(session: Session, doc) -> JournalLine | None:
    if not doc.trans_id:
        return None
    return session.scalars(select(JournalLine).where(
        JournalLine.trans_id == doc.trans_id, JournalLine.short_name == doc.card_code)).first()


def _reconcile_with_invoice(ctx: _Ctx, lines: list[dict]) -> None:
    """A credit memo copied from one invoice reduces that invoice's open amount (B1 reconciles them)."""
    invoices = {x["base"].doc_entry: x["base"] for x in lines if x["base"] is not None and DEFS[x["base"].obj_type].kind == "invoice"}
    if len(invoices) != 1:
        return
    inv = next(iter(invoices.values()))
    cm = ctx.doc
    amount = min(cm.doc_total, inv.doc_total - inv.paid_to_date)
    inv_line, cm_line = _bp_line(ctx.session, inv), _bp_line(ctx.session, cm)
    if amount <= 0 or inv_line is None or cm_line is None:
        return
    if ctx.d.side == "S":
        inv_line.bal_due_deb -= amount
        cm_line.bal_due_cred -= amount
    else:
        inv_line.bal_due_cred -= amount
        cm_line.bal_due_deb -= amount
    inv.paid_to_date += amount
    cm.paid_to_date += amount
    if inv.paid_to_date >= inv.doc_total:
        inv.doc_status = "C"
    if cm.paid_to_date >= cm.doc_total:
        cm.doc_status = "C"


# ------------------------------------------------------------- partner totals
def refresh_partner(session: Session, bp: BusinessPartner) -> None:
    """OCRD OrdersBal / DNotesBal: gross value of open orders and open deliveries (GRPOs)."""
    session.flush()
    orders, dnotes = ("17", "15") if bp.card_type != "S" else ("22", "20")

    def open_value(obj: str) -> Decimal:
        header_cls, _ = DOCUMENT_CLASSES[obj]
        total = ZERO
        for doc in session.scalars(select(header_cls).where(header_cls.card_code == bp.card_code,
                                                            header_cls.doc_status == "O", header_cls.canceled == "N")):
            for l in doc.lines:
                if l.open_qty > 0 and l.quantity:
                    total += (l.line_total * (1 - doc.disc_prcnt / 100) * (1 + l.vat_prcnt / 100)) * l.open_qty / l.quantity
        return money(total)

    bp.orders_bal = open_value(orders)
    bp.dnotes_bal = open_value(dnotes)


# ------------------------------------------------------------- close / cancel
def close_document(session: Session, obj: str, doc_entry: int):
    """Close a quotation or order manually: open quantities are released."""
    d = doc_def(obj)
    doc = get_document(session, obj, doc_entry)
    if d.kind not in {"quotation", "order"}:
        raise B1Error(f"A {d.name} cannot be closed manually")
    if doc.doc_status != "O":
        raise B1Error(f"{d.name} {doc.doc_num} is already closed")
    _commitments(session, d, doc, -1)
    for line in doc.lines:
        line.line_status = "C"
    doc.doc_status = "C"
    if doc.card_code:
        refresh_partner(session, session.get(BusinessPartner, doc.card_code))
    session.commit()
    return doc


def cancel_document(session: Session, obj: str, doc_entry: int, cancel_date: date | None = None):
    try:
        doc = _cancel(session, obj, doc_entry, cancel_date)
        session.commit()
        return doc
    except Exception:
        session.rollback()
        raise


def _cancel(session: Session, obj: str, doc_entry: int, cancel_date: date | None):
    d = doc_def(obj)
    doc = get_document(session, obj, doc_entry)
    if doc.canceled == "Y":
        raise B1Error(f"{d.name} {doc.doc_num} is already canceled")
    if d.side != "I" and any(l.open_qty < l.quantity for l in doc.lines):
        raise B1Error(f"{d.name} {doc.doc_num} was copied to a target document; cancel that document first")
    if d.kind == "credit":
        _unreconcile(session, d, doc)
    elif doc.paid_to_date:
        raise B1Error(f"{d.name} {doc.doc_num} is paid or reconciled; cancel the payment or credit memo first")

    ctx = _Ctx(session=session, d=d, doc=doc, det=_determination(session, doc.doc_date))
    rows = session.scalars(select(WarehouseJournal).where(WarehouseJournal.trans_type == d.obj,
                                                          WarehouseJournal.created_by == doc.doc_entry)
                           .order_by(WarehouseJournal.trans_num.desc())).all()
    for r in rows:  # undo stock movements in reverse order, at their original values
        item = session.get(Item, r.item_code)
        memo = f"Cancellation {d.name} {doc.doc_num}"[:50]
        if r.in_qty:
            issue(ctx, item, r.warehouse, r.in_qty, r.doc_line_num, value=r.trans_value, memo=memo)
        elif r.out_qty:
            receive(ctx, item, r.warehouse, r.out_qty, -r.trans_value, r.doc_line_num, memo)
        elif r.trans_value:
            revalue(ctx, item, r.warehouse, -r.trans_value, r.doc_line_num, memo)
    if doc.trans_id:
        rev = journal.reverse_entry(session, doc.trans_id, ref_date=cancel_date or doc.doc_date, commit=False)
        session.flush()
        trans_id = rev.trans_id
    else:
        trans_id = None
    trans_num = session.scalar(select(func.max(WarehouseJournal.trans_num))) or 0
    for row in ctx.oinm:
        trans_num += 1
        row.trans_num, row.trans_id = trans_num, trans_id
        session.add(row)

    _commitments(session, d, doc, -1)
    for line in doc.lines:  # reopen the base lines
        if line.base_type:
            base = get_document(session, line.base_type, line.base_entry)
            bl = next(l for l in base.lines if l.line_num == line.base_line)
            bl.open_qty += line.quantity
            bl.line_status = "O"
            if base.canceled == "N":
                paid = DEFS[base.obj_type].kind == "invoice" and base.paid_to_date >= base.doc_total
                base.doc_status = "C" if paid else "O"
            _commit_line(session, base.obj_type, bl, line.quantity)
        line.line_status = "C"
    doc.canceled, doc.doc_status = "Y", "C"
    if doc.card_code:
        refresh_partner(session, session.get(BusinessPartner, doc.card_code))
    session.flush()
    return doc


def _unreconcile(session: Session, d: DocDef, cm) -> None:
    if not cm.paid_to_date:
        return
    base = next((l for l in cm.lines if l.base_type and DEFS[l.base_type].kind == "invoice"), None)
    if base is None:
        raise B1Error(f"{d.name} {cm.doc_num} is paid; cancel the payment first")
    inv = get_document(session, base.base_type, base.base_entry)
    amount = cm.paid_to_date
    inv_line, cm_line = _bp_line(session, inv), _bp_line(session, cm)
    if d.side == "S":
        inv_line.bal_due_deb += amount
        cm_line.bal_due_cred += amount
    else:
        inv_line.bal_due_cred += amount
        cm_line.bal_due_deb += amount
    inv.paid_to_date -= amount
    cm.paid_to_date = ZERO
    if inv.canceled == "N":
        inv.doc_status = "O"


# ------------------------------------------------------------- copy-from sources
def copy_sources(session: Session, obj: str, card_code: str) -> list[dict]:
    """Open documents of the BP that the target type can be copied from, with their open lines."""
    d = doc_def(obj)
    out = []
    for base_obj in d.bases:
        header_cls, _ = DOCUMENT_CLASSES[base_obj]
        q = select(header_cls).where(header_cls.card_code == card_code, header_cls.canceled == "N")
        if DEFS[base_obj].kind != "invoice":
            q = q.where(header_cls.doc_status == "O")
        for doc in session.scalars(q.order_by(header_cls.doc_entry)):
            open_lines = [l for l in doc.lines if l.line_status == "O" and l.open_qty > 0]
            if open_lines:
                out.append({"obj": base_obj, "name": DEFS[base_obj].name, "doc_entry": doc.doc_entry,
                            "doc_num": doc.doc_num, "doc_date": doc.doc_date, "doc_type": doc.doc_type,
                            "doc_total": doc.doc_total, "disc_prcnt": doc.disc_prcnt,
                            "lines": [{"line_num": l.line_num, "item_code": l.item_code, "dscription": l.dscription,
                                       "open_qty": l.open_qty, "price": l.price_bef_di, "disc_prcnt": l.disc_prcnt,
                                       "vat_group": l.vat_group, "whs_code": l.whs_code, "acct_code": l.acct_code}
                                      for l in open_lines]})
    return out
