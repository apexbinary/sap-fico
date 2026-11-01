"""Tax calculation and account determination.

Given a tax base amount and a tax code, computes the tax amount from TAXRATE and
resolves the posting account from T030K. Supports input (VST) and output (MWS)
tax; the transaction key is derived from the tax type (A=output -> MWS,
V=input -> VST).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tax import TaxAccount, TaxCode, TaxRate
from app.services.fiscal import PostingError

_CENT = Decimal("0.01")


def _transaction_key(mwart: str) -> str:
    """Map tax type to the standard account-determination transaction key."""
    return "MWS" if mwart == "A" else "VST"


def resolve_tax_code(session: Session, mandt: str, kalsm: str, mwskz: str) -> TaxCode:
    code = session.get(TaxCode, (mandt, kalsm, mwskz))
    if code is None:
        raise PostingError(f"Tax code {mwskz} not defined in procedure {kalsm}")
    if code.xinact:
        raise PostingError(f"Tax code {mwskz} is inactive")
    return code


def tax_rate(session: Session, mandt: str, kalsm: str, mwskz: str, ktosl: str) -> TaxRate | None:
    return session.scalars(
        select(TaxRate).where(
            TaxRate.mandt == mandt,
            TaxRate.kalsm == kalsm,
            TaxRate.mwskz == mwskz,
            TaxRate.ktosl == ktosl,
        )
    ).first()


def calculate_tax(
    session: Session,
    mandt: str,
    kalsm: str,
    mwskz: str,
    base_amount: Decimal,
) -> dict:
    """Return tax detail for a base amount.

    Result keys: ktosl (transaction key), rate, tax_amount, deductible.
    """
    code = resolve_tax_code(session, mandt, kalsm, mwskz)
    ktosl = _transaction_key(code.mwart)
    rate = tax_rate(session, mandt, kalsm, mwskz, ktosl)
    if rate is None:
        raise PostingError(f"No tax rate for code {mwskz} / key {ktosl}")
    tax_amount = (base_amount * rate.kbetr / Decimal("100")).quantize(_CENT, ROUND_HALF_UP)
    return {
        "ktosl": ktosl,
        "mwart": code.mwart,
        "rate": rate.kbetr,
        "tax_amount": tax_amount,
        "deductible": rate.deductible,
    }


def tax_account(
    session: Session, mandt: str, ktopl: str, ktosl: str, mwskz: str, bukrs: str
) -> str:
    """Resolve the tax G/L account from T030K (company-code specific then generic)."""
    acct = session.get(TaxAccount, (mandt, ktopl, ktosl, mwskz, bukrs))
    if acct is None:
        acct = session.get(TaxAccount, (mandt, ktopl, ktosl, mwskz, ""))
    if acct is None:
        raise PostingError(
            f"No tax account (T030K) for key {ktosl} / code {mwskz} in {ktopl}"
        )
    return acct.konts
