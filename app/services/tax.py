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


def reverse_charge(session: Session, tg: TaxGroup | None, net: Decimal, imp_acct: str | None = None) -> list[tuple[str, str, Decimal, str]]:
    """Tax the recipient pays itself (reverse charge / import of goods): [(input account, liability account,
    amount, component)], each component rounded on its own. The vendor is not charged this tax."""
    from app.services.admin import B1Error

    if tg is None or tg.rev_charge not in {"Y", "I"}:
        return []
    out = []
    for authority, rate in components(session, tg):
        offset = imp_acct if tg.rev_charge == "I" else authority.rvs_chrg_act
        if not offset:
            raise B1Error(f"Tax authority {authority.code} has no reverse charge liability account")
        out.append((authority.purch_tax, offset, _money(net * rate / 100), authority.code))
    return out


def apportion(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split an amount in proportion to the weights (bill of entry value over the import lines); the last takes the rest."""
    base = sum(weights, ZERO)
    if not weights:
        return []
    if not base:
        return [ZERO] * (len(weights) - 1) + [_money(total)]
    out = [_money(total * w / base) for w in weights[:-1]]
    return out + [_money(total) - sum(out, ZERO)]


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
                                                        TaxGroup.rev_charge == tg.rev_charge, TaxGroup.inactive.is_(False))):
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


def supply(session: Session, side: str, bp, header: dict) -> tuple[str | None, str | None]:
    """Place of supply: (intra / inter / None, state) from the company state against the ship-to
    (sales) or bill-to (purchasing) state."""
    from app.services.admin import company

    comp = company(session)
    if bp is None:
        return None, None
    state = (partner_state(session, bp, "S", header.get("ship_to_code")) if side == "S" else None) \
        or partner_state(session, bp, "B", header.get("pay_to_code"))
    if state is None or not comp.state:
        return None, state
    return ("intra" if state == comp.state else "inter"), state


# ------------------------------------------------------------- tax setup (maintenance)
def _check_account(session: Session, code: str | None, what: str) -> None:
    from app.models.finance import Account
    from app.services.admin import B1Error

    acct = session.get(Account, code) if code else None
    if acct is None or acct.postable != "Y" or acct.loc_man_tran == "Y":
        raise B1Error(f"Enter an active {what} G/L account (not a control account)")


def tax_code_used(session: Session, code: str) -> bool:
    """A tax code with postings or document lines keeps its category, rate and components (as in B1)."""
    from app.models.documents import DOCUMENT_CLASSES
    from app.models.finance import JournalLine

    if session.scalar(select(JournalLine.trans_id).where(JournalLine.vat_group == code).limit(1)) is not None:
        return True
    return any(session.scalar(select(line_cls.doc_entry).where(line_cls.vat_group == code).limit(1)) is not None
               for _, line_cls in DOCUMENT_CLASSES.values())


def save_tax_type(session: Session, code: str, name: str) -> None:
    from app.models.admin import TaxType
    from app.services.admin import B1Error

    if not code.strip():
        raise B1Error("Enter a tax type code")
    session.merge(TaxType(code=code.strip().upper(), name=name))
    session.commit()


def save_tax_authority(session: Session, code: str, name: str, type_code: str | None, sales_tax: str,
                       purch_tax: str, rvs_chrg_act: str | None = None) -> None:
    from app.models.admin import TaxType
    from app.services.admin import B1Error

    if not code.strip():
        raise B1Error("Enter a tax authority code")
    if type_code and session.get(TaxType, type_code) is None:
        raise B1Error(f"Tax type {type_code} does not exist")
    _check_account(session, sales_tax, "output tax")
    _check_account(session, purch_tax, "input tax")
    if rvs_chrg_act:
        _check_account(session, rvs_chrg_act, "reverse charge liability")
    session.merge(TaxAuthority(code=code.strip().upper(), name=name, type=type_code, sales_tax=sales_tax,
                               purch_tax=purch_tax, rvs_chrg_act=rvs_chrg_act or None))
    session.commit()


def save_tax_code(session: Session, code: str, name: str, category: str, components_in: list[tuple[str, Decimal]],
                  rate: Decimal | None = None, account: str | None = None, inactive: bool = False,
                  rev_charge: str = "N") -> TaxGroup:
    """Add or change a tax code: either components (rate = their sum) or one rate with its own account."""
    from app.services.admin import B1Error

    code = code.strip().upper()
    if not code or len(code) > 8:
        raise B1Error("Enter a tax code of up to 8 characters")
    if category not in {"O", "I"}:
        raise B1Error("Category must be O (output, sales) or I (input, purchasing)")
    components_in = [(sta, Decimal(r)) for sta, r in components_in]
    for sta, r in components_in:
        if session.get(TaxAuthority, sta) is None:
            raise B1Error(f"Tax authority {sta} does not exist")
        if r < 0:
            raise B1Error("A component rate cannot be negative")
    if len({sta for sta, _ in components_in}) != len(components_in):
        raise B1Error("A tax authority can appear only once in a tax code")
    rev_charge = rev_charge or "N"
    if rev_charge not in {"N", "Y", "I"}:
        raise B1Error("Reverse charge: N no, Y reverse charge, I import of goods")
    if rev_charge != "N":
        if category != "I":
            raise B1Error("Reverse charge and import codes are input (purchasing) tax codes")
        if not components_in:
            raise B1Error("A reverse charge / import code needs tax components")
        if rev_charge == "Y" and any(not session.get(TaxAuthority, sta).rvs_chrg_act for sta, _ in components_in):
            raise B1Error("Every component of a reverse charge code needs a tax authority with a reverse charge liability account")
    new_rate = sum((r for _, r in components_in), ZERO) if components_in else Decimal(rate or 0)
    if new_rate < 0 or new_rate >= 100:
        raise B1Error("The rate must be between 0 and 100 %")
    first = session.get(TaxAuthority, components_in[0][0]) if components_in else None
    acct = account or ((first.sales_tax if category == "O" else first.purch_tax) if first else None)
    _check_account(session, acct, "tax")
    tg = session.get(TaxGroup, code)
    if tg is not None:
        old = [(a.code, r) for a, r in components(session, tg)]
        changed = tg.category != category or tg.rate != new_rate or old != components_in or tg.rev_charge != rev_charge
        if changed and tax_code_used(session, code):
            raise B1Error(f"Tax code {code} is used in postings; its category, rate and components cannot change "
                          f"(create a new code and set this one inactive)")
    else:
        tg = TaxGroup(code=code)
        session.add(tg)
    tg.name, tg.category, tg.rate, tg.account, tg.inactive, tg.rev_charge = name, category, new_rate, acct, inactive, rev_charge
    session.flush()
    for row in session.scalars(select(TaxComponent).where(TaxComponent.stc_code == code)):
        session.delete(row)
    session.flush()
    for line, (sta, r) in enumerate(components_in):
        session.add(TaxComponent(stc_code=code, line=line, sta_code=sta, efctiv_rate=r))
    session.commit()
    return tg


def save_hsn(session: Session, chapter_id: str, dscription: str, item_type: str = "I", abs_entry: int | None = None):
    from sqlalchemy import func

    from app.models.admin import HsnCode
    from app.services.admin import B1Error

    chapter_id = (chapter_id or "").strip()
    if not chapter_id.isdigit() or not 4 <= len(chapter_id) <= 8:
        raise B1Error("An HSN / SAC code has 4 to 8 digits")
    if item_type not in {"I", "S"}:
        raise B1Error("Type must be I (goods, HSN) or S (services, SAC)")
    other = session.scalar(select(HsnCode).where(HsnCode.chapter_id == chapter_id))
    if other is not None and other.abs_entry != abs_entry:
        raise B1Error(f"HSN / SAC code {chapter_id} already exists")
    row = session.get(HsnCode, abs_entry) if abs_entry else None
    if row is None:
        row = HsnCode(abs_entry=(session.scalar(select(func.max(HsnCode.abs_entry))) or 0) + 1)
        session.add(row)
    row.chapter_id, row.dscription, row.item_type = chapter_id, dscription, item_type
    session.commit()
    return row


DETERMINATION_FIELDS = ["priority", "doc_area", "card_code", "group_code", "item_code", "itms_grp_cod", "chapter_id",
                        "state", "supply", "tax_code", "descr", "active"]


def save_determination(session: Session, data: dict, abs_id: int | None = None):
    from sqlalchemy import func

    from app.models.admin import TaxDetermination
    from app.services.admin import B1Error

    if data.get("doc_area") not in {"S", "P"}:
        raise B1Error("Document area must be S (sales) or P (purchasing)")
    if data.get("supply") not in (None, "I", "O"):
        raise B1Error("Supply must be I (intra-state), O (inter-state) or empty")
    tg = session.get(TaxGroup, data.get("tax_code") or "")
    if tg is None or tg.category != ("O" if data["doc_area"] == "S" else "I"):
        raise B1Error(f"Tax code {data.get('tax_code')} is not "
                      f"{'an output' if data['doc_area'] == 'S' else 'an input'} tax code")
    row = session.get(TaxDetermination, abs_id) if abs_id else None
    if row is None:
        row = TaxDetermination(abs_id=(session.scalar(select(func.max(TaxDetermination.abs_id))) or 0) + 1)
        session.add(row)
    for key in DETERMINATION_FIELDS:
        if key in data:
            setattr(row, key, data[key])
    session.commit()
    return row


# ------------------------------------------------------------- tax code determination
def determine(session: Session, side: str, bp, item, place: tuple[str | None, str | None]):
    """The first matching active rule (OTCD, lowest priority number first), or None."""
    from app.models.admin import TaxDetermination

    kind, state = place
    rules = session.scalars(select(TaxDetermination).where(
        TaxDetermination.active == "Y", TaxDetermination.doc_area == side).order_by(
        TaxDetermination.priority, TaxDetermination.abs_id)).all()
    for r in rules:
        if r.card_code and (bp is None or r.card_code != bp.card_code):
            continue
        if r.group_code is not None and (bp is None or r.group_code != bp.group_code):
            continue
        if r.item_code and (item is None or r.item_code != item.item_code):
            continue
        if r.itms_grp_cod is not None and (item is None or r.itms_grp_cod != item.itms_grp_cod):
            continue
        if r.chapter_id and (item is None or r.chapter_id != item.chapter_id):
            continue
        if r.state and r.state != state:
            continue
        if r.supply and r.supply != {"intra": "I", "inter": "O"}.get(kind):
            continue
        return r
    return None
