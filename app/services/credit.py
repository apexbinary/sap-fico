"""Credit limit and commitment limit check of customers (B1: General Settings -> BP).

Exposure = balance + open deliveries + open orders (OCRD Balance + DNotesBal + OrdersBal). When a
sales document of a checked type raises the exposure above the credit limit (OCRD CreditLine),
or an invoice raises the balance above the commitment limit (OCRD DebtLine), the document is
refused (B block) or needs a confirmation (W warn). Copied lines move value between orders,
deliveries and balance without raising the exposure, so only new value is checked. A limit of 0
means no limit.
"""

from __future__ import annotations

from decimal import Decimal

from app.models.partners import BusinessPartner
from app.services.admin import B1Error, company

CONFIRM = "confirm to add anyway"
CHECKED_TYPES = {"17": "Sales orders", "15": "Deliveries", "13": "A/R invoices"}


class CreditLimitWarning(B1Error):
    """Limit exceeded in warn mode: the document is added when the request confirms it."""


def amount_text(x: Decimal, inr: bool) -> str:
    """Amount with thousands separators; Indian grouping (12,34,567.00) for INR companies."""
    s = f"{Decimal(x):,.2f}"
    if not inr:
        return s
    whole, frac = f"{abs(Decimal(x)):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ("-" if x < 0 else "") + ",".join(groups + [tail]) + "." + frac


def exposure(bp: BusinessPartner) -> Decimal:
    return (bp.balance or 0) + (bp.dnotes_bal or 0) + (bp.orders_bal or 0)


def snapshot(bp: BusinessPartner | None) -> tuple[Decimal, Decimal] | None:
    return (exposure(bp), bp.balance or Decimal(0)) if bp is not None and bp.card_type == "C" else None


def settings(session) -> dict:
    c = company(session)
    return {"credit_check": c.crd_lmt_chk, "commitment_check": c.cmt_lmt_chk,
            "documents": [x for x in (c.crd_lmt_docs or "").split(",") if x], "types": CHECKED_TYPES}


def save_settings(session, data: dict) -> dict:
    c = company(session)
    for key, col in (("credit_check", "crd_lmt_chk"), ("commitment_check", "cmt_lmt_chk")):
        if data.get(key) is not None:
            if data[key] not in {"N", "W", "B"}:
                raise B1Error("Check: N none, W warn, B block")
            setattr(c, col, data[key])
    if data.get("documents") is not None:
        bad = [x for x in data["documents"] if x not in CHECKED_TYPES]
        if bad:
            raise B1Error(f"Unknown document type {bad[0]}")
        c.crd_lmt_docs = ",".join(x for x in CHECKED_TYPES if x in data["documents"])
    session.commit()
    return settings(session)


def check(session, obj: str, bp: BusinessPartner | None, before: tuple[Decimal, Decimal] | None, confirmed: bool) -> None:
    """Called after the document is posted (not committed): raise to refuse or to ask for a confirmation."""
    if before is None or bp is None:
        return
    c = company(session)
    problems, block = [], False
    f = lambda x: amount_text(x, c.main_curncy == "INR")  # noqa: E731
    after_exposure, after_balance = exposure(bp), bp.balance or Decimal(0)
    if c.crd_lmt_chk != "N" and obj in (c.crd_lmt_docs or "").split(",") and bp.credit_line \
            and after_exposure > bp.credit_line and after_exposure > before[0]:
        problems.append(f"Credit limit of {bp.card_code} exceeded: exposure {f(after_exposure)} "
                        f"(balance + open deliveries + open orders) > credit limit {f(bp.credit_line)}")
        block = block or c.crd_lmt_chk == "B"
    if c.cmt_lmt_chk != "N" and obj == "13" and bp.debt_line and after_balance > bp.debt_line and after_balance > before[1]:
        problems.append(f"Commitment limit of {bp.card_code} exceeded: balance {f(after_balance)} > commitment limit {f(bp.debt_line)}")
        block = block or c.cmt_lmt_chk == "B"
    if not problems:
        return
    if block:
        raise B1Error("; ".join(problems))
    if not confirmed:
        raise CreditLimitWarning("; ".join(problems) + f" ({CONFIRM})")
