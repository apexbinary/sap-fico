"""Terms of payment (T052) — baseline date, cash discount and net due date.

The posting engine copies the terms onto each customer/vendor invoice line
(BSEG-ZTERM, ZBD1T/ZBD1P, ZBD2T/ZBD2P, ZBD3T, SKFBT); everything downstream
(open-item reports, payments, clearing) reads those line fields, never T052,
so later changes to the terms do not alter already posted items.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import AccountingDocumentItem
from app.models.partners import CustomerCompanyCode, VendorCompanyCode
from app.models.payments import PaymentTerms
from app.services.fiscal import PostingError

_CENT = Decimal("0.01")


def for_line(
    session: Session, mandt: str, bukrs: str, koart: str, account: str, zterm: str | None
) -> PaymentTerms | None:
    """Terms for a sub-ledger line: the entered key, else the partner master's.

    An explicitly entered key must exist; a master-data default that is not
    customized is ignored (the line is then due on its baseline date).
    """
    if zterm:
        terms = _get(session, mandt, zterm)
        if terms is None:
            raise PostingError(f"Terms of payment {zterm} are not defined")
        return terms
    master = (
        session.get(CustomerCompanyCode, (mandt, account, bukrs))
        if koart == "D"
        else session.get(VendorCompanyCode, (mandt, account, bukrs))
    )
    if master is None or not master.zterm:
        return None
    return _get(session, mandt, master.zterm)


def _get(session: Session, mandt: str, zterm: str) -> PaymentTerms | None:
    return session.scalars(
        select(PaymentTerms)
        .where(PaymentTerms.mandt == mandt, PaymentTerms.zterm == zterm)
        .order_by(PaymentTerms.ztagg)
    ).first()


def baseline_date(terms: PaymentTerms | None, bldat: date, budat: date) -> date:
    """Baseline date for due-date calculation (T052-ZDART), default posting date."""
    zdart = terms.zdart if terms else None
    if zdart == "D":
        return bldat
    if zdart == "C":
        return date.today()
    return budat


def line_fields(terms: PaymentTerms | None, wrbtr: Decimal) -> dict:
    """BSEG payment-terms fields to stamp on an invoice line."""
    if terms is None:
        return {}
    return {
        "zterm": terms.zterm,
        "zbd1t": terms.ztag1, "zbd1p": terms.zprz1,
        "zbd2t": terms.ztag2, "zbd2p": terms.zprz2,
        "zbd3t": terms.ztag3,
        "skfbt": wrbtr if (terms.zprz1 or terms.zprz2) else None,
    }


def _baseline(item: AccountingDocumentItem) -> date:
    return item.zfbdt or item.header.budat


def net_due_date(item: AccountingDocumentItem) -> date:
    """Net due date (SAP FAEDT): baseline + the longest payment period."""
    days = item.zbd3t or item.zbd2t or item.zbd1t or 0
    return _baseline(item) + timedelta(days=days)


def cash_discount(item: AccountingDocumentItem, on_date: date) -> tuple[Decimal, Decimal]:
    """(percentage, amount in document currency) available when paying on a date."""
    base = _baseline(item)
    pct = Decimal("0")
    if item.zbd1p and on_date <= base + timedelta(days=item.zbd1t or 0):
        pct = item.zbd1p
    elif item.zbd2p and on_date <= base + timedelta(days=item.zbd2t or 0):
        pct = item.zbd2p
    if not pct:
        return Decimal("0"), Decimal("0")
    eligible = item.skfbt if item.skfbt is not None else item.wrbtr
    return pct, (eligible * pct / Decimal("100")).quantize(_CENT, ROUND_HALF_UP)
