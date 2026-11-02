"""Employee tolerances (T043 / T043T): what a user may post and clear.

A user's tolerance group comes from T043 (user + company code); without an
entry the default group '' applies. T043T limits the amount per document and
per customer/vendor item, the cash discount percentage a user may grant, and
the payment difference a user may write off. A company code without T043T
entries has no limits.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.payments import EmployeeTolerance, UserToleranceGroup
from app.services.fiscal import PostingError

_CENT = Decimal("0.01")


def employee_tolerance(session: Session, mandt: str, bukrs: str, usnam: str) -> EmployeeTolerance | None:
    assignment = session.get(UserToleranceGroup, (mandt, usnam, bukrs))
    togru = assignment.togru if assignment else ""
    return session.get(EmployeeTolerance, (mandt, bukrs, togru)) or session.get(EmployeeTolerance, (mandt, bukrs, ""))


def check_document(session: Session, mandt: str, bukrs: str, usnam: str, lines) -> None:
    """Posting limits: amount per document and per customer/vendor item (local currency)."""
    tol = employee_tolerance(session, mandt, bukrs, usnam)
    if tol is None:
        return
    total = sum((l.dmbtr for l in lines if l.shkzg == "S"), Decimal("0"))
    if total > tol.betrh:
        raise PostingError(
            f"User {usnam} may post documents up to {tol.betrh} {tol.waers} "
            f"(tolerance group '{tol.togru}'); this document is {total}")
    for l in lines:
        if l.koart in ("D", "K") and l.dmbtr > tol.betrp:
            raise PostingError(
                f"User {usnam} may post customer/vendor items up to {tol.betrp} {tol.waers} "
                f"(tolerance group '{tol.togru}'); item amount {l.dmbtr}")


def check_cash_discount(tol: EmployeeTolerance | None, usnam: str, pct: Decimal) -> None:
    if tol is not None and pct > tol.sktpr:
        raise PostingError(f"User {usnam} may grant cash discount up to {tol.sktpr}% (tolerance group '{tol.togru}')")


def difference_allowed(tol: EmployeeTolerance | None, difference: Decimal, open_total: Decimal) -> bool:
    """Is a payment difference within the user's own limit (amount and percentage)?"""
    if tol is None:
        return True
    limit = min(tol.zubet, (abs(open_total) * tol.zuprz / 100).quantize(_CENT, ROUND_HALF_UP))
    return abs(difference) <= limit
