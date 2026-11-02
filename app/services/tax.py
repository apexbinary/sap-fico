"""Tax calculation: tax groups with components, GST place of supply.

A tax group (OVTG) either posts its whole rate to its own account, or is made of
components (STC1) whose tax authorities (OSTA) carry the output / input accounts:
India's GST 18 % is CGST 9 % + SGST 9 % within a state and IGST 18 % between states.
Each component is rounded on its own; the tax of a line is the sum of its components.

Place of supply: when the company and the partner are in the same state the
intra-state code (CGST + SGST) applies, otherwise the inter-state code (IGST) of the
same rate; a line's GST code is switched to the matching one automatically.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import TaxAuthority, TaxComponent, TaxGroup

ZERO = Decimal("0")
INTRA, INTER = {"CGST", "SGST", "UTGST"}, {"IGST"}


def _money(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def components(session: Session, tg: TaxGroup) -> list[tuple[TaxAuthority, Decimal]]:
    rows = session.scalars(select(TaxComponent).where(TaxComponent.stc_code == tg.code).order_by(TaxComponent.line)).all()
    return [(session.get(TaxAuthority, r.sta_code), r.efctiv_rate) for r in rows]


def split(session: Session, tg: TaxGroup | None, net: Decimal) -> list[tuple[str, Decimal, str]]:
    """Tax of a net amount: [(account, amount, component)], each component rounded on its own."""
    if tg is None:
        return []
    comps = components(session, tg)
    if not comps:
        return [(tg.account, _money(net * tg.rate / 100), tg.code)]
    out = []
    for authority, rate in comps:
        account = authority.sales_tax if tg.category == "O" else authority.purch_tax
        out.append((account, _money(net * rate / 100), authority.code))
    return out


def gst_kind(session: Session, tg: TaxGroup | None) -> str | None:
    """'intra' (CGST + SGST), 'inter' (IGST) or None for a tax group without GST components."""
    if tg is None:
        return None
    codes = {a.code for a, _ in components(session, tg)}
    if codes & INTER:
        return "inter"
    if codes & INTRA:
        return "intra"
    return None


def matching_gst_group(session: Session, tg: TaxGroup, kind: str) -> TaxGroup | None:
    """The GST code of the same category and rate for intra- or inter-state supply."""
    for other in session.scalars(select(TaxGroup).where(TaxGroup.category == tg.category, TaxGroup.rate == tg.rate,
                                                        TaxGroup.inactive.is_(False))):
        if gst_kind(session, other) == kind:
            return other
    return None


def partner_state(session: Session, bp, address_type: str, address_id: str | None) -> str | None:
    """State of a partner address (CRD1), else of its general address when in the same country."""
    from app.models.partners import PartnerAddress

    if address_id:
        a = session.get(PartnerAddress, (bp.card_code, address_type, address_id))
        if a is not None and a.state:
            return a.state
    return None


def supply_kind(session: Session, side: str, bp, header: dict) -> str | None:
    """Intra- or inter-state supply: company state against the ship-to (sales) or bill-to (purchasing) state."""
    from app.services.admin import company

    comp = company(session)
    if bp is None or not comp.state:
        return None
    state = (partner_state(session, bp, "S", header.get("ship_to_code")) if side == "S" else None) \
        or partner_state(session, bp, "B", header.get("pay_to_code"))
    if state is None:
        return None
    return "intra" if state == comp.state else "inter"
