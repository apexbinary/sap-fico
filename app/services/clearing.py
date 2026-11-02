"""Payments and open-item clearing (F-28 / F-53 / F-32 / F-44).

A payment or clearing transaction posts ONE document through the posting engine
and, in the same database transaction, stamps the clearing document
(AUGBL / AUGGJ / AUGDT) on every open item it settles and on the offsetting
lines it generated. Modes:

  clear       the selected items are settled in full; payment + cash discount
              must equal their open balance exactly
  residual    the selected items are settled in full and the difference is
              carried forward as a new open item referencing the invoice (REBZG)
  partial     one item stays open; the payment is posted as an open item that
              references it (REBZG) — nothing is cleared
  on_account  the payment is posted as an unassigned open item

With amount 0 and no bank account the transaction is a pure clearing
(F-32 customers / F-44 vendors), e.g. an invoice against a credit memo.

Cash discount is taken gross from the item's terms of payment when the payment
date falls in a discount period, and posted to the T030 account of transaction
key SKT (granted to customers) or SKE (received from vendors).
Not yet supported: tax adjustment on cash discount, payment-difference
tolerances (T043G), and clearing in foreign currency (needs FX valuation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import AccountingDocumentItem
from app.models.payments import AutomaticAccountDetermination
from app.services import payment_terms
from app.services.fiscal import PostingError, company_code
from app.services.posting import DocumentRequest, LineRequest, post_document

MODES = ("clear", "residual", "partial", "on_account")

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
}
# (account type, with payment) -> SAP transaction
_TCODES = {("D", True): "F-28", ("K", True): "F-53", ("D", False): "F-32", ("K", False): "F-44"}


@dataclass
class PaymentRequest:
    """A payment and/or clearing transaction for one customer or vendor."""

    bukrs: str  # Company code
    koart: str  # Account type: D customer / K vendor
    account: str  # Customer (KUNNR) or vendor (LIFNR) number
    budat: date  # Posting date (also the clearing date and discount reference date)
    amount: Decimal = Decimal("0")  # Amount paid; 0 = pure clearing
    items: list[tuple[str, int, int]] = field(default_factory=list)  # (BELNR, GJAHR, BUZEI)
    mode: str = "clear"
    hkont: str | None = None  # Bank G/L account (required when amount > 0)
    bldat: date | None = None  # Document date (defaults to posting date)
    apply_discount: bool = True  # Take cash discount per the items' terms
    blart: str | None = None  # Document type (default DZ / KZ, or AB for pure clearing)
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
        raise PostingError("Account type must be D (customer) or K (vendor)")
    if req.mode not in MODES:
        raise PostingError(f"Unknown clearing mode {req.mode!r}; use one of {', '.join(MODES)}")
    if req.amount < 0:
        raise PostingError("Payment amount must not be negative")
    if req.amount > 0 and not req.hkont:
        raise PostingError("A bank G/L account is required to post a payment")
    if req.mode in ("partial", "on_account") and req.amount <= 0:
        raise PostingError(f"Mode '{req.mode}' needs a payment amount")
    if len(set(req.items)) != len(req.items):
        raise PostingError("The same open item is selected more than once")

    keys = _KEYS[req.koart]
    inv_side = keys["inv_side"]
    cc = company_code(session, mandt, req.bukrs)
    items = [_open_item(session, mandt, req, cc.waers, *key) for key in req.items]

    if req.mode in ("clear", "residual") and not items:
        raise PostingError("Select at least one open item to clear")
    if req.mode == "partial" and len(items) != 1:
        raise PostingError("A partial payment refers to exactly one open item")
    if req.mode == "on_account" and items:
        raise PostingError("A payment on account must not select open items")

    lines: list[LineRequest] = []
    clearing_pos: list[int] = []  # BUZEI of the generated line that offsets items[i]
    discounts: list[Decimal] = []
    text = req.sgtxt

    def bank_line(money_in_normal_direction: bool) -> LineRequest:
        bschl = keys["bank"][0 if money_in_normal_direction else 1]
        return LineRequest(bschl=bschl, account=req.hkont, wrbtr=req.amount, sgtxt=text or "Bank")

    open_total = discount = residual = Decimal("0")

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
            if req.apply_discount and it.shkzg == inv_side:
                d = payment_terms.cash_discount(it, req.budat)[1]
            discounts.append(d)
        discount = sum(discounts, Decimal("0"))
        residual = open_total - discount - (req.amount if normal else -req.amount)
        if req.mode == "clear" and residual != 0:
            raise PostingError(
                f"Difference of {residual} {cc.waers} remains (open {open_total}, cash discount "
                f"{discount}, paid {req.amount}); post it as a residual item or a partial payment"
            )

        if req.amount:
            lines.append(bank_line(normal))
        if discount:
            bschl, ktosl = keys["discount"]
            lines.append(LineRequest(bschl=bschl, account=_auto_account(session, mandt, cc.ktopl, ktosl),
                                     wrbtr=discount, sgtxt="Cash discount"))
        clear_keys = keys["pay"] if req.amount else keys["clear"]
        for it, d in zip(items, discounts):
            lines.append(LineRequest(
                bschl=clear_keys[0 if it.shkzg == inv_side else 1], account=req.account,
                wrbtr=it.wrbtr, zuonr=it.zuonr, sgtxt=text or f"Clearing {it.belnr}",
                wskto=d or None,
            ))
            clearing_pos.append(len(lines))
        if residual:
            ref = next((i for i in items if i.shkzg == inv_side), items[0])
            lines.append(LineRequest(
                bschl=keys["residual"][0 if residual > 0 else 1], account=req.account,
                wrbtr=abs(residual), zuonr=ref.zuonr, zfbdt=ref.zfbdt, zterm=ref.zterm,
                sgtxt=f"Residual item {ref.belnr}", rebzg=ref.belnr, rebzj=ref.gjahr, rebzz=ref.buzei,
            ))

    blart = req.blart or (keys["blart"] if req.amount else "AB")
    header = post_document(session, DocumentRequest(
        mandt=mandt, bukrs=req.bukrs, blart=blart, bldat=req.bldat or req.budat, budat=req.budat,
        waers=cc.waers, xblnr=req.xblnr, bktxt=req.bktxt, usnam=req.usnam,
        tcode=req.tcode or _TCODES[(req.koart, bool(req.amount))],
        lines=lines,
    ), commit=False)

    by_buzei = {i.buzei: i for i in header.items}
    cleared = []
    for it, pos, d in zip(items, clearing_pos, discounts):
        for row in (it, by_buzei[pos]):
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
        "residual": residual, "cleared": cleared,
    }


def _open_item(
    session: Session, mandt: str, req: PaymentRequest, local: str, belnr: str, gjahr: int, buzei: int
) -> AccountingDocumentItem:
    it = session.get(AccountingDocumentItem, (mandt, req.bukrs, belnr.zfill(10), gjahr, buzei))
    ref = f"{belnr}/{gjahr}/{buzei}"
    if it is None:
        raise PostingError(f"Line item {ref} does not exist in company code {req.bukrs}")
    partner = it.kunnr if req.koart == "D" else it.lifnr
    if it.koart != req.koart or partner != req.account:
        raise PostingError(f"Line item {ref} is not an item of account {req.account}")
    if it.augbl:
        raise PostingError(f"Line item {ref} is already cleared by document {it.augbl}")
    if it.header.waers != local:
        raise PostingError(
            f"Line item {ref} is in {it.header.waers}; clearing is only supported in local currency {local}"
        )
    return it


def _signed(it: AccountingDocumentItem, inv_side: str) -> Decimal:
    """Open amount seen from the invoice side: invoices positive, payments/credit memos negative."""
    return it.wrbtr if it.shkzg == inv_side else -it.wrbtr


def _auto_account(session: Session, mandt: str, ktopl: str, ktosl: str) -> str:
    row = session.get(AutomaticAccountDetermination, (mandt, ktopl, ktosl, "", "", ""))
    if row is None:
        raise PostingError(f"No G/L account for transaction key {ktosl} in chart of accounts {ktopl} (T030)")
    return row.konts


def proposal(
    session: Session, mandt: str, bukrs: str, koart: str, account: str, budat: date
) -> list[dict]:
    """Open items of a partner with due date and the cash discount available on ``budat``."""
    if koart not in _KEYS:
        raise PostingError("Account type must be D (customer) or K (vendor)")
    inv_side = _KEYS[koart]["inv_side"]
    partner = AccountingDocumentItem.kunnr if koart == "D" else AccountingDocumentItem.lifnr
    items = session.scalars(
        select(AccountingDocumentItem).where(
            AccountingDocumentItem.mandt == mandt,
            AccountingDocumentItem.bukrs == bukrs,
            AccountingDocumentItem.koart == koart,
            partner == account,
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
