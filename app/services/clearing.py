"""Payments and open-item clearing (F-28 / F-53 / F-32 / F-44 / F-03).

A payment or clearing transaction posts ONE document through the posting engine
and, in the same database transaction, stamps the clearing document
(AUGBL / AUGGJ / AUGDT) on every open item it settles and on the offsetting
lines it generated. Modes:

  clear       the selected items are settled in full; payment + cash discount
              must equal their open balance, except for a difference within
              the customer/vendor tolerance (T043G), which is posted to the
              payment-difference account (T030 key ZDI)
  residual    the selected items are settled in full and the difference is
              carried forward as a new open item referencing the invoice (REBZG)
  partial     one item stays open; the payment is posted as an open item that
              references it (REBZG) — nothing is cleared
  on_account  the payment is posted as an unassigned open item

With amount 0 and no bank account the transaction is a pure clearing: F-32
(customers), F-44 (vendors) or F-03 (G/L accounts with open item management,
SKB1-XOPVW). A clearing whose items net to zero posts a document header
without line items, as SAP does.

Cash discount is taken gross from the item's terms of payment when the payment
date falls in a discount period. Its tax portion (in proportion to the
invoice's tax lines) corrects the tax account; the net portion goes to the
T030 account of key SKT (granted to customers) or SKE (received from vendors).

Items in foreign currency are cleared in that currency. The clearing document
is translated at the rate of the clearing date, except that each cleared item
is offset at its own historical local amount; the local difference is the
realized exchange rate gain or loss (T030H LHREA / LSREA of the item's
reconciliation or open-item account).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import AccountingDocumentItem, PostingKey
from app.models.gl_master import GLAccountCompanyCode
from app.models.partners import CustomerCompanyCode, VendorCompanyCode
from app.models.payments import AutomaticAccountDetermination, CustomerVendorTolerance
from app.services import fx, payment_terms
from app.services.fiscal import PostingError, company_code
from app.services.posting import DocumentRequest, LineRequest, post_document, to_local

MODES = ("clear", "residual", "partial", "on_account")
_CENT = Decimal("0.01")

# Standard SAP posting keys per account type. Pairs are
# (key for an item on the invoice side, key for an item on the opposite side).
_KEYS = {
    "D": {
        "inv_side": "S",          # customer invoices are debits
        "pay": ("15", "05"),      # incoming payment / outgoing payment
        "clear": ("17", "07"),    # other clearing (credit / debit)
        "residual": ("06", "16"), # payment difference (debit / credit)
        "bank": ("40", "50"),     # bank (G/L) when money comes in / goes out
        "discount": ("40", "SKT"),
        "blart": "DZ",
    },
    "K": {
        "inv_side": "H",          # vendor invoices are credits
        "pay": ("25", "35"),      # outgoing payment / incoming payment
        "clear": ("27", "37"),    # clearing (debit) / other clearing (credit)
        "residual": ("36", "26"), # payment difference (credit / debit)
        "bank": ("50", "40"),     # bank (G/L) when money goes out / comes in
        "discount": ("50", "SKE"),
        "blart": "KZ",
    },
    "S": {
        "inv_side": "S",          # G/L open items: debits counted positive
        "clear": ("50", "40"),
        "residual": ("40", "50"),
        "blart": "AB",
    },
}
# (account type, with payment) -> SAP transaction
_TCODES = {("D", True): "F-28", ("K", True): "F-53", ("D", False): "F-32", ("K", False): "F-44",
           ("S", False): "F-03"}


@dataclass
class PaymentRequest:
    """A payment and/or clearing transaction for one customer, vendor or G/L account."""

    bukrs: str  # Company code
    koart: str  # Account type: D customer / K vendor / S G/L account (clearing only)
    account: str  # Customer (KUNNR), vendor (LIFNR) or G/L account (HKONT)
    budat: date  # Posting date (also the clearing date and discount reference date)
    amount: Decimal = Decimal("0")  # Amount paid; 0 = pure clearing
    items: list[tuple[str, int, int]] = field(default_factory=list)  # (BELNR, GJAHR, BUZEI)
    mode: str = "clear"
    hkont: str | None = None  # Bank G/L account (required when amount > 0)
    bldat: date | None = None  # Document date (defaults to posting date)
    apply_discount: bool = True  # Take cash discount per the items' terms
    blart: str | None = None  # Document type (default DZ / KZ, or AB for pure clearing)
    waers: str | None = None  # Payment currency for a payment on account (else the items' currency)
    xblnr: str | None = None  # Reference
    bktxt: str | None = None  # Header text
    sgtxt: str | None = None  # Item text on the payment lines
    usnam: str = "SYSTEM"
    tcode: str | None = None
    mandt: str | None = None


def post_payment(session: Session, req: PaymentRequest, *, commit: bool = True) -> dict:
    """Post a payment / clearing document and clear the settled items."""
    from app.config import settings

    mandt = req.mandt or settings.default_client
    try:
        return _post_payment(session, mandt, req, commit)
    except Exception:
        session.rollback()
        raise


def _post_payment(session: Session, mandt: str, req: PaymentRequest, commit: bool) -> dict:
    if req.koart not in _KEYS:
        raise PostingError("Account type must be D (customer), K (vendor) or S (G/L account)")
    if req.mode not in MODES:
        raise PostingError(f"Unknown clearing mode {req.mode!r}; use one of {', '.join(MODES)}")
    if req.amount < 0:
        raise PostingError("Payment amount must not be negative")
    if req.koart == "S" and (req.amount or req.mode not in ("clear", "residual")):
        raise PostingError("G/L open items are cleared without a payment (F-03): amount 0, mode clear or residual")
    if req.amount > 0 and not req.hkont:
        raise PostingError("A bank G/L account is required to post a payment")
    if req.mode in ("partial", "on_account") and req.amount <= 0:
        raise PostingError(f"Mode '{req.mode}' needs a payment amount")
    if len(set(req.items)) != len(req.items):
        raise PostingError("The same open item is selected more than once")

    keys = _KEYS[req.koart]
    inv_side = keys["inv_side"]
    cc = company_code(session, mandt, req.bukrs)
    if req.koart == "S":
        _check_open_item_account(session, mandt, req.bukrs, req.account)
    items = [_open_item(session, mandt, req, *key) for key in req.items]
    currencies = {it.header.waers for it in items}
    if len(currencies) > 1:
        raise PostingError(f"The selected items are in different currencies ({', '.join(sorted(currencies))})")
    waers = currencies.pop() if currencies else (req.waers or cc.waers)
    foreign = waers != cc.waers
    kursf = fx.rate(session, mandt, waers, cc.waers, req.budat) if foreign else Decimal("1")

    if req.mode in ("clear", "residual") and not items:
        raise PostingError("Select at least one open item to clear")
    if req.mode == "partial" and len(items) != 1:
        raise PostingError("A partial payment refers to exactly one open item")
    if req.mode == "on_account" and items:
        raise PostingError("A payment on account must not select open items")

    lines: list[LineRequest] = []
    clearing_pos: list[int | None] = []  # BUZEI of the generated line that offsets items[i]
    discounts: list[Decimal] = []
    text = req.sgtxt

    def bank_line(money_in_normal_direction: bool) -> LineRequest:
        bschl = keys["bank"][0 if money_in_normal_direction else 1]
        return LineRequest(bschl=bschl, account=req.hkont, wrbtr=req.amount, sgtxt=text or "Bank")

    open_total = discount = residual = difference = tax_adjustment = Decimal("0")

    if req.mode == "on_account":
        lines.append(bank_line(True))
        lines.append(LineRequest(bschl=keys["pay"][0], account=req.account, wrbtr=req.amount,
                                 sgtxt=text or "Payment on account"))

    elif req.mode == "partial":
        it = items[0]
        on_inv = it.shkzg == inv_side
        if req.amount >= it.wrbtr:
            raise PostingError(
                f"Partial payment {req.amount} must be less than the open amount {it.wrbtr}; clear it instead"
            )
        lines.append(bank_line(on_inv))
        lines.append(LineRequest(
            bschl=keys["pay"][0 if on_inv else 1], account=req.account, wrbtr=req.amount,
            zuonr=it.zuonr, sgtxt=text or f"Partial payment {it.belnr}",
            rebzg=it.belnr, rebzj=it.gjahr, rebzz=it.buzei,
        ))

    else:  # clear / residual
        open_total = sum((_signed(it, inv_side) for it in items), Decimal("0"))
        normal = open_total >= 0  # partner owes us (D) / we owe the partner (K)
        for it in items:
            d = Decimal("0")
            if req.apply_discount and req.koart != "S" and it.shkzg == inv_side:
                d = payment_terms.cash_discount(it, req.budat)[1]
            discounts.append(d)
        discount = sum(discounts, Decimal("0"))
        residual = open_total - discount - (req.amount if normal else -req.amount)

        if req.mode == "clear" and residual:
            tol = _tolerance(session, mandt, req.bukrs, req.koart, req.account)
            if tol is None or not _within(tol, req.koart, residual, open_total):
                raise PostingError(
                    f"Difference of {residual} {waers} remains (open {open_total}, cash discount "
                    f"{discount}, paid {req.amount}) and exceeds the payment-difference tolerance; "
                    f"post it as a residual item or a partial payment"
                )
            difference, residual = residual, Decimal("0")

        if req.amount:
            lines.append(bank_line(normal))
        if discount:
            bschl, ktosl = keys["discount"]
            taxes = _discount_tax(items, discounts, inv_side)
            tax_adjustment = sum(taxes.values(), Decimal("0"))
            lines.append(LineRequest(bschl=bschl, account=_auto_account(session, mandt, cc.ktopl, ktosl),
                                     wrbtr=discount - tax_adjustment, sgtxt="Cash discount"))
            for (mwskz, tax_account), amt in taxes.items():
                lines.append(LineRequest(bschl=bschl, account=tax_account, wrbtr=amt, mwskz=mwskz,
                                         sgtxt="Tax adjustment on cash discount"))
        if difference:
            side = inv_side if difference > 0 else ("H" if inv_side == "S" else "S")
            lines.append(LineRequest(
                bschl="40" if side == "S" else "50",
                account=_auto_account(session, mandt, cc.ktopl, "ZDI", credit=side == "H"),
                wrbtr=abs(difference), sgtxt="Payment difference within tolerance",
            ))

        header_only = not (req.amount or discount or residual or difference or foreign)
        clear_keys = keys["pay"] if req.amount else keys["clear"]
        for it, d in zip(items, discounts):
            if header_only:
                clearing_pos.append(None)
                continue
            lines.append(LineRequest(
                bschl=clear_keys[0 if it.shkzg == inv_side else 1], account=req.account,
                wrbtr=it.wrbtr, zuonr=it.zuonr, sgtxt=text or f"Clearing {it.belnr}",
                wskto=d or None, dmbtr=it.dmbtr if foreign else None,  # offset at the historical rate
            ))
            clearing_pos.append(len(lines))
        if residual:
            ref = next((i for i in items if i.shkzg == inv_side), items[0])
            lines.append(LineRequest(
                bschl=keys["residual"][0 if residual > 0 else 1], account=req.account,
                wrbtr=abs(residual), zuonr=ref.zuonr, zfbdt=ref.zfbdt, zterm=ref.zterm,
                sgtxt=f"Residual item {ref.belnr}", rebzg=ref.belnr, rebzj=ref.gjahr, rebzz=ref.buzei,
            ))

    realized = Decimal("0")
    if foreign and items:
        local = sum(((l.dmbtr if l.dmbtr is not None else to_local(l.wrbtr, kursf))
                     * (1 if _posting_side(session, mandt, l.bschl) == "S" else -1) for l in lines), Decimal("0"))
        if local:
            acc = fx.difference_accounts(session, mandt, cc.ktopl, items[0].hkont)
            realized = local  # debits exceed credits -> balanced by a gain (positive)
            lines.append(LineRequest(
                bschl="50" if local > 0 else "40", account=acc.lhrea if local > 0 else acc.lsrea,
                wrbtr=Decimal("0"), dmbtr=abs(local), sgtxt="Realized exchange rate difference",
            ))

    blart = req.blart or (keys["blart"] if req.amount else "AB")
    header = post_document(session, DocumentRequest(
        mandt=mandt, bukrs=req.bukrs, blart=blart, bldat=req.bldat or req.budat, budat=req.budat,
        waers=waers, kursf=kursf, xblnr=req.xblnr, bktxt=req.bktxt, usnam=req.usnam,
        tcode=req.tcode or _TCODES[(req.koart, bool(req.amount))],
        lines=lines, xclear=True,
    ), commit=False)

    by_buzei = {i.buzei: i for i in header.items}
    cleared = []
    for it, pos, d in zip(items, clearing_pos, discounts):
        rows = [it] if pos is None else [it, by_buzei[pos]]
        for row in rows:
            row.augbl, row.auggj, row.augdt, row.augcp = header.belnr, header.gjahr, req.budat, date.today()
        cleared.append({"belnr": it.belnr, "gjahr": it.gjahr, "buzei": it.buzei,
                        "amount": _signed(it, inv_side), "discount": d})

    if commit:
        session.commit()
    else:
        session.flush()
    return {
        "belnr": header.belnr, "gjahr": header.gjahr, "blart": header.blart, "mode": req.mode,
        "amount": req.amount, "open_total": open_total, "discount": discount,
        "tax_adjustment": tax_adjustment, "difference": difference, "residual": residual,
        "waers": waers, "kursf": kursf, "realized_fx": realized, "cleared": cleared,
    }


def _check_open_item_account(session: Session, mandt: str, bukrs: str, saknr: str) -> None:
    gl = session.get(GLAccountCompanyCode, (mandt, bukrs, saknr))
    if gl is None:
        raise PostingError(f"G/L account {saknr} not created in company code {bukrs}")
    if not gl.xopvw or gl.mitkz:
        raise PostingError(f"G/L account {saknr} is not managed on an open item basis")


def _posting_side(session: Session, mandt: str, bschl: str) -> str:
    pk = session.get(PostingKey, (mandt, bschl))
    if pk is None:
        raise PostingError(f"Posting key {bschl} is not defined")
    return pk.shkzg


def _open_item(
    session: Session, mandt: str, req: PaymentRequest, belnr: str, gjahr: int, buzei: int
) -> AccountingDocumentItem:
    it = session.get(AccountingDocumentItem, (mandt, req.bukrs, belnr.zfill(10), gjahr, buzei))
    ref = f"{belnr}/{gjahr}/{buzei}"
    if it is None:
        raise PostingError(f"Line item {ref} does not exist in company code {req.bukrs}")
    account = {"D": it.kunnr, "K": it.lifnr, "S": it.hkont}[req.koart]
    if it.koart != req.koart or account != req.account:
        raise PostingError(f"Line item {ref} is not an item of account {req.account}")
    if not it.xopvw:
        raise PostingError(f"Line item {ref} is not an open item")
    if it.augbl:
        raise PostingError(f"Line item {ref} is already cleared by document {it.augbl}")
    return it


def _signed(it: AccountingDocumentItem, inv_side: str) -> Decimal:
    """Open amount seen from the invoice side: invoices positive, payments/credit memos negative."""
    return it.wrbtr if it.shkzg == inv_side else -it.wrbtr


def _auto_account(session: Session, mandt: str, ktopl: str, ktosl: str, *, credit: bool = False) -> str:
    row = session.get(AutomaticAccountDetermination, (mandt, ktopl, ktosl, "", "", ""))
    if row is None:
        raise PostingError(f"No G/L account for transaction key {ktosl} in chart of accounts {ktopl} (T030)")
    return (row.konth or row.konts) if credit else row.konts


def _discount_tax(
    items: list[AccountingDocumentItem], discounts: list[Decimal], inv_side: str
) -> dict[tuple[str, str], Decimal]:
    """Tax portion of each gross discount, by (tax code, tax account).

    The portion is the discount times the share of each tax line of the
    invoice in the invoice's gross sub-ledger amount.
    """
    out: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for it, d in zip(items, discounts):
        if not d:
            continue
        doc_lines = it.header.items
        gross = sum((l.wrbtr for l in doc_lines if l.koart == it.koart and l.shkzg == inv_side), Decimal("0"))
        for t in doc_lines:
            if t.buzid == "T" and t.mwskz and gross:
                amt = (d * t.wrbtr / gross).quantize(_CENT, ROUND_HALF_UP)
                if amt:
                    out[(t.mwskz, t.hkont)] += amt
    return dict(out)


def _tolerance(
    session: Session, mandt: str, bukrs: str, koart: str, account: str
) -> CustomerVendorTolerance | None:
    """T043G entry for the partner's tolerance group (KNB1/LFB1-TOGRU), else the default group."""
    if koart not in ("D", "K"):
        return None
    master = (session.get(CustomerCompanyCode, (mandt, account, bukrs)) if koart == "D"
              else session.get(VendorCompanyCode, (mandt, account, bukrs)))
    togru = master.togru if master and master.togru else ""
    return (session.get(CustomerVendorTolerance, (mandt, bukrs, togru))
            or session.get(CustomerVendorTolerance, (mandt, bukrs, "")))


def _within(tol: CustomerVendorTolerance, koart: str, residual: Decimal, open_total: Decimal) -> bool:
    """Is the remaining difference inside the amount and percentage limit of its direction?"""
    gain = (residual > 0) == (koart == "K")  # vendor underpaid / customer overpaid
    amount, pct = (tol.betrh, tol.prozh) if gain else (tol.betrs, tol.prozs)
    limit = min(amount or Decimal("0"), (abs(open_total) * (pct or 0) / 100).quantize(_CENT, ROUND_HALF_UP))
    return abs(residual) <= limit


def tolerance_limits(session: Session, mandt: str, bukrs: str, koart: str, account: str) -> dict:
    """Permitted payment differences for a partner (for the UI)."""
    tol = _tolerance(session, mandt, bukrs, koart, account)
    if tol is None:
        return {"togru": None, "gain_amount": 0, "gain_pct": 0, "loss_amount": 0, "loss_pct": 0}
    return {"togru": tol.togru, "gain_amount": tol.betrh, "gain_pct": tol.prozh,
            "loss_amount": tol.betrs, "loss_pct": tol.prozs}


def proposal(
    session: Session, mandt: str, bukrs: str, koart: str, account: str, budat: date
) -> list[dict]:
    """Open items of an account with due date and the cash discount available on ``budat``."""
    if koart not in _KEYS:
        raise PostingError("Account type must be D (customer), K (vendor) or S (G/L account)")
    inv_side = _KEYS[koart]["inv_side"]
    account_col = {"D": AccountingDocumentItem.kunnr, "K": AccountingDocumentItem.lifnr,
                   "S": AccountingDocumentItem.hkont}[koart]
    items = session.scalars(
        select(AccountingDocumentItem).where(
            AccountingDocumentItem.mandt == mandt,
            AccountingDocumentItem.bukrs == bukrs,
            AccountingDocumentItem.koart == koart,
            account_col == account,
            AccountingDocumentItem.xopvw.is_(True),
            AccountingDocumentItem.augbl.is_(None),
        ).order_by(AccountingDocumentItem.gjahr, AccountingDocumentItem.belnr, AccountingDocumentItem.buzei)
    ).all()

    out = []
    for it in items:
        pct, disc = payment_terms.cash_discount(it, budat) if it.shkzg == inv_side else (Decimal("0"), Decimal("0"))
        faedt = payment_terms.net_due_date(it)
        signed = _signed(it, inv_side)
        out.append({
            "belnr": it.belnr, "gjahr": it.gjahr, "buzei": it.buzei, "bschl": it.bschl,
            "shkzg": it.shkzg, "budat": it.header.budat, "zfbdt": it.zfbdt, "zterm": it.zterm,
            "faedt": faedt, "overdue_days": max((budat - faedt).days, 0),
            "open": signed, "discount_pct": pct, "discount": disc, "net": signed - disc,
            "waers": it.header.waers, "zuonr": it.zuonr, "sgtxt": it.sgtxt, "rebzg": it.rebzg,
        })
    return out


def match_open_item(
    session: Session, mandt: str, bukrs: str, koart: str, account: str, amount: Decimal, budat: date
) -> tuple[tuple[str, int, int], bool] | None:
    """Find one invoice a payment amount settles exactly (net of discount first, then gross).

    Returns ((BELNR, GJAHR, BUZEI), apply_discount) or None.
    """
    candidates = [p for p in proposal(session, mandt, bukrs, koart, account, budat) if p["open"] > 0]
    for p in candidates:
        if p["discount"] and p["net"] == amount:
            return (p["belnr"], p["gjahr"], p["buzei"]), True
    for p in candidates:
        if p["open"] == amount:
            return (p["belnr"], p["gjahr"], p["buzei"]), False
    return None
