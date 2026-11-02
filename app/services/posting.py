"""The FI posting engine — turns a document request into BKPF/BSEG + GLT0 + COEP.

This is the heart of Financial Accounting. It enforces the SAP posting rules:

  * every line's debit/credit indicator (SHKZG) and account type (KOART) come
    from its posting key (TBSL);
  * the document must balance (sum of debits == sum of credits) in the
    document currency and in local currency;
  * the posting period must be open for each account type (T001B);
  * sub-ledger lines (customer D / vendor K) post to their reconciliation
    account in the G/L;
  * the document number is drawn from the number range of the document type;
  * G/L transaction figures (GLT0) are updated, and CO-relevant lines are
    mirrored into COEP in real time.

Call ``post_document`` with a ``DocumentRequest``. With ``bstat='V'`` the
document is parked: it is validated, numbered and stored, but nothing is
updated (no GLT0, CO or asset values) and its items are not open items until
``post_parked`` posts it (FBV0); ``delete_parked`` discards it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.controlling import COLineItem, CostElement, CostElementCO
from app.models.documents import (
    AccountingDocumentHeader,
    AccountingDocumentItem,
    DocumentType,
    GLAccountTotals,
    NumberRange,
    PostingKey,
)
from app.models.gl_master import GLAccountCompanyCode
from app.models.partners import CustomerCompanyCode, VendorCompanyCode
from app.services import payment_terms
from app.services import tax as tax_svc
from app.services.fiscal import (
    PostingError,
    check_period_open,
    company_code,
    controlling_area,
    determine_period,
)

_CENT = Decimal("0.01")
_PRIMARY_CO_CATEGORIES = {"1", "01", "3", "03", "11", "12"}  # primary cost/revenue


@dataclass
class LineRequest:
    """One line item as supplied by the caller (pre-posting)."""

    bschl: str  # Posting key (decides debit/credit + account type)
    account: str  # G/L account, or customer / vendor number depending on posting key
    wrbtr: Decimal  # Amount in document currency
    mwskz: str | None = None  # Tax code
    calculate_tax: bool = False  # Auto-generate the tax line from this base line
    sgtxt: str | None = None  # Line item text
    zuonr: str | None = None  # Assignment number
    gsber: str | None = None  # Business area
    kostl: str | None = None  # Cost center
    aufnr: str | None = None  # Internal order
    prctr: str | None = None  # Profit center
    zfbdt: date | None = None  # Baseline date (due date calc)
    zterm: str | None = None  # Payment terms
    umskz: str | None = None  # Special G/L indicator
    rebzg: str | None = None  # Invoice reference: document number (partial/residual items)
    rebzj: int | None = None  # Invoice reference: fiscal year
    rebzz: int | None = None  # Invoice reference: line item
    wskto: Decimal | None = None  # Cash discount amount taken (document currency)
    zlsch: str | None = None  # Payment method (overrides the partner's list)
    zlspr: str | None = None  # Payment block key
    anln2: str = "0000"  # Asset sub-number (account type A)
    anbwa: str | None = None  # Asset transaction type (account type A)
    afabe: str = "01"  # Depreciation area (account type A)
    bzdat: date | None = None  # Asset value date
    buzid: str | None = None  # Line item ID (T = tax line, e.g. copied by a reversal)
    dmbtr: Decimal | None = None  # Fixed local amount (clearing at the item's historical rate)


@dataclass
class DocumentRequest:
    """A document to post (header fields + lines)."""

    bukrs: str  # Company code
    blart: str  # Document type
    bldat: date  # Document date
    budat: date  # Posting date
    waers: str  # Document currency
    lines: list[LineRequest]
    kursf: Decimal | None = None  # Exchange rate to local currency (None: TCURR rate on the posting date)
    xblnr: str | None = None  # Reference document number
    bktxt: str | None = None  # Document header text
    usnam: str = "SYSTEM"  # User
    tcode: str | None = None  # Transaction code
    kokrs: str | None = None  # Controlling area (for CO integration)
    mandt: str | None = None  # Client (defaults to settings)
    xclear: bool = False  # Clearing document: may have no line items (zero-balance clearing)
    bstat: str = " "  # Document status: ' ' posted, 'V' parked, 'D' recurring entry original
    dbblg: str | None = None  # Recurring entry original this document was posted from


def to_local(amount: Decimal, rate: Decimal) -> Decimal:
    return (amount * rate).quantize(_CENT, ROUND_HALF_UP)


def _posting_key(session: Session, mandt: str, bschl: str) -> PostingKey:
    pk = session.get(PostingKey, (mandt, bschl))
    if pk is None:
        raise PostingError(f"Posting key {bschl} is not defined")
    return pk


def _account_type_allowed(doc: DocumentType, koart: str) -> bool:
    return {
        "S": doc.xsach,
        "D": doc.xkund,
        "K": doc.xlief,
        "A": doc.xanlg,
        "M": doc.xmate,
    }.get(koart, False)


def _next_document_number(session: Session, mandt: str, bukrs: str, numkr: str, gjahr: int) -> str:
    rng = session.get(NumberRange, (mandt, "RF_BELEG", bukrs, numkr, gjahr))
    if rng is None:
        rng = session.get(NumberRange, (mandt, "RF_BELEG", bukrs, numkr, 0))
    if rng is None:
        raise PostingError(f"Number range {numkr} not defined for company code {bukrs}")
    nxt = int(rng.nrlevel or "0") + 1
    if nxt > int(rng.tonumber):
        raise PostingError(f"Number range {numkr} is exhausted for company code {bukrs}")
    rng.nrlevel = str(nxt)
    return str(nxt).zfill(10)


def _reconciliation_account(session: Session, mandt: str, bukrs: str, koart: str, account: str) -> str:
    """Resolve the G/L reconciliation account for a sub-ledger line."""
    if koart == "D":
        rec = session.get(CustomerCompanyCode, (mandt, account, bukrs))
        if rec is None:
            raise PostingError(f"Customer {account} not extended to company code {bukrs}")
        if rec.sperr:
            raise PostingError(f"Customer {account} is blocked for posting in {bukrs}")
        return rec.akont
    if koart == "K":
        rec = session.get(VendorCompanyCode, (mandt, account, bukrs))
        if rec is None:
            raise PostingError(f"Vendor {account} not extended to company code {bukrs}")
        if rec.sperr:
            raise PostingError(f"Vendor {account} is blocked for posting in {bukrs}")
        return rec.akont
    raise PostingError(f"Unsupported sub-ledger account type {koart}")


def _validate_gl_account(session: Session, mandt: str, bukrs: str, saknr: str) -> GLAccountCompanyCode:
    gl = session.get(GLAccountCompanyCode, (mandt, bukrs, saknr))
    if gl is None:
        raise PostingError(f"G/L account {saknr} not created in company code {bukrs}")
    if gl.xspeb:
        raise PostingError(f"G/L account {saknr} is blocked for posting in {bukrs}")
    return gl


@dataclass
class _ResolvedLine:
    bschl: str
    koart: str
    shkzg: str
    hkont: str
    saknr: str | None
    kunnr: str | None
    lifnr: str | None
    wrbtr: Decimal
    dmbtr: Decimal
    src: LineRequest | None = None
    buzid: str | None = None
    mwskz: str | None = None
    wmwst: Decimal | None = None
    mwsts: Decimal | None = None
    ktosl: str | None = None
    terms: object | None = None  # T052 terms of payment (sub-ledger invoice lines)
    xopvw: bool = False  # Open item management (D/K always; G/L per SKB1-XOPVW)


def post_document(
    session: Session, req: DocumentRequest, *, commit: bool = True
) -> AccountingDocumentHeader:
    """Validate and post a document. Rolls back on error.

    With ``commit=False`` the document is only flushed, so a caller (e.g. the
    clearing service) can make further changes in the same transaction.
    """
    from app.config import settings

    mandt = req.mandt or settings.default_client
    try:
        return _post(session, mandt, req, commit)
    except Exception:
        session.rollback()
        raise


def _post(
    session: Session, mandt: str, req: DocumentRequest, commit: bool
) -> AccountingDocumentHeader:
    cc = company_code(session, mandt, req.bukrs)
    ktopl = cc.ktopl
    local_currency = cc.waers

    doc_type = session.get(DocumentType, (mandt, req.blart))
    if doc_type is None:
        raise PostingError(f"Document type {req.blart} is not defined")
    _check_text_lengths(req)
    kokrs = req.kokrs or controlling_area(session, mandt, req.bukrs)

    gjahr, monat = determine_period(session, mandt, cc.periv, req.budat)
    if req.kursf is not None:
        kursf = req.kursf
    elif req.waers == local_currency:
        kursf = Decimal("1")
    else:
        from app.services import fx

        kursf = fx.rate(session, mandt, req.waers, local_currency, req.budat)

    # Tax calculation procedure is assigned to the company code's country (T005).
    kalsm = None
    if any(ln.calculate_tax and ln.mwskz for ln in req.lines):
        kalsm = _tax_procedure(session, mandt, cc.land1)

    resolved: list[_ResolvedLine] = []
    tax_lines: list[_ResolvedLine] = []

    for ln in req.lines:
        pk = _posting_key(session, mandt, ln.bschl)
        if not _account_type_allowed(doc_type, pk.koart):
            raise PostingError(
                f"Document type {req.blart} does not allow account type '{pk.koart}'"
            )

        xopvw = pk.koart in ("D", "K")
        if pk.koart == "S":
            xopvw = _validate_gl_account(session, mandt, req.bukrs, ln.account).xopvw
            hkont, saknr, kunnr, lifnr = ln.account, ln.account, None, None
        elif pk.koart == "D":
            hkont = _reconciliation_account(session, mandt, req.bukrs, "D", ln.account)
            saknr, kunnr, lifnr = None, ln.account, None
            _validate_gl_account(session, mandt, req.bukrs, hkont)
        elif pk.koart == "K":
            hkont = _reconciliation_account(session, mandt, req.bukrs, "K", ln.account)
            saknr, kunnr, lifnr = None, None, ln.account
            _validate_gl_account(session, mandt, req.bukrs, hkont)
        elif pk.koart == "A":
            hkont = _asset_apc_account(session, mandt, req.bukrs, ktopl, ln.account, ln.anln2, ln.afabe)
            saknr, kunnr, lifnr = None, None, None
            _validate_gl_account(session, mandt, req.bukrs, hkont)
        else:
            raise PostingError(f"Account type '{pk.koart}' not yet supported by the engine")

        dmbtr = ln.dmbtr if ln.dmbtr is not None else to_local(ln.wrbtr, kursf)
        rl = _ResolvedLine(
            bschl=ln.bschl, koart=pk.koart, shkzg=pk.shkzg, hkont=hkont, saknr=saknr,
            kunnr=kunnr, lifnr=lifnr, wrbtr=ln.wrbtr, dmbtr=dmbtr, src=ln, mwskz=ln.mwskz,
            xopvw=xopvw, buzid=ln.buzid,
        )
        # Invoices / credit memos (sales-related keys) carry terms of payment;
        # other sub-ledger lines only when terms are entered explicitly.
        if pk.koart in ("D", "K") and (ln.zterm or pk.xumsw):
            rl.terms = payment_terms.for_line(session, mandt, req.bukrs, pk.koart, ln.account, ln.zterm)
        resolved.append(rl)

        # Auto tax line generation from a base line flagged for tax calculation.
        if ln.calculate_tax and ln.mwskz:
            detail = tax_svc.calculate_tax(session, mandt, kalsm, ln.mwskz, ln.wrbtr)
            tax_amt = detail["tax_amount"]
            rl.mwskz = ln.mwskz
            rl.wmwst = tax_amt
            rl.mwsts = to_local(tax_amt, kursf)
            rl.ktosl = detail["ktosl"]
            # The tax line takes the side of its base line: revenue (credit) carries
            # output tax as a credit, a sales credit memo (debit) reduces it with a
            # debit; expenses / vendor credit memos do the same for input tax.
            tax_shkzg = pk.shkzg
            tax_acct = tax_svc.tax_account(
                session, mandt, ktopl, detail["ktosl"], ln.mwskz, req.bukrs,
            )
            _validate_gl_account(session, mandt, req.bukrs, tax_acct)
            tax_lines.append(
                _ResolvedLine(
                    bschl="40" if tax_shkzg == "S" else "50",
                    koart="S", shkzg=tax_shkzg, hkont=tax_acct, saknr=tax_acct,
                    kunnr=None, lifnr=None, wrbtr=tax_amt, dmbtr=to_local(tax_amt, kursf),
                    buzid="T", mwskz=ln.mwskz, ktosl=detail["ktosl"],
                )
            )

    all_lines = resolved + tax_lines
    # SAP posts a zero-balance clearing as a header without line items.
    if len(all_lines) < 2 and not (req.xclear and not all_lines):
        raise PostingError("A document must have at least two line items")

    if req.waers != local_currency:
        _absorb_rounding(all_lines, req.lines)
    _check_balanced(all_lines, req.waers, local_currency)

    posted = req.bstat == " "
    if req.bstat not in (" ", "V", "D"):
        raise PostingError(f"Document status {req.bstat!r} cannot be posted directly")
    if posted:  # a parked document is checked when it is posted
        for koart in {"+"} | {rl.koart for rl in all_lines}:
            check_period_open(session, mandt, req.bukrs, koart, gjahr, monat)

    # Recurring entry originals are numbered from the dedicated interval X1, as in SAP.
    numkr = "X1" if req.bstat == "D" else doc_type.numkr
    belnr = _next_document_number(session, mandt, req.bukrs, numkr, gjahr)

    header = AccountingDocumentHeader(
        mandt=mandt, bukrs=req.bukrs, belnr=belnr, gjahr=gjahr, blart=req.blart,
        bldat=req.bldat, budat=req.budat, monat=monat, usnam=req.usnam, tcode=req.tcode,
        xblnr=req.xblnr, bktxt=req.bktxt, waers=req.waers, kursf=kursf,
        wwert=req.budat if req.waers != local_currency else None,
        hwaer=local_currency, bstat=req.bstat, awtyp="BKPF", kokrs=kokrs,
        ppnam=req.usnam if req.bstat == "V" else None, dbblg=req.dbblg,
    )
    session.add(header)

    buzei = 0
    for rl in all_lines:
        buzei += 1
        src = rl.src
        item = AccountingDocumentItem(
            mandt=mandt, bukrs=req.bukrs, belnr=belnr, gjahr=gjahr, buzei=buzei,
            buzid=rl.buzid, bschl=rl.bschl, koart=rl.koart, shkzg=rl.shkzg,
            bstat=None if posted else req.bstat,
            umskz=(src.umskz if src else None), hkont=rl.hkont, saknr=rl.saknr,
            kunnr=rl.kunnr, lifnr=rl.lifnr, wrbtr=rl.wrbtr, dmbtr=rl.dmbtr,
            mwskz=rl.mwskz, ktosl=rl.ktosl, wmwst=rl.wmwst, mwsts=rl.mwsts,
            gsber=(src.gsber if src else None),
            sgtxt=(src.sgtxt if src else None),
            zuonr=(src.zuonr if src else None),
            zfbdt=(src.zfbdt if src else None) or (
                payment_terms.baseline_date(rl.terms, req.bldat, req.budat)
                if rl.koart in ("D", "K") else None
            ),
            zterm=(src.zterm if src else None),
            rebzg=(src.rebzg if src else None),
            rebzj=(src.rebzj if src else None),
            rebzz=(src.rebzz if src else None),
            wskto=(src.wskto if src else None),
            zlsch=(src.zlsch if src else None),
            zlspr=(src.zlspr if src else None),
            sknto=(to_local(src.wskto, kursf) if src and src.wskto else None),
            kostl=(src.kostl if src else None),
            aufnr=(src.aufnr if src else None),
            prctr=(src.prctr if src else None),
            kokrs=kokrs,
            xopvw=rl.xopvw and posted,
            anln1=(src.account if src and rl.koart == "A" else None),
            anln2=(src.anln2 if src and rl.koart == "A" else None),
            anbwa=(src.anbwa if src and rl.koart == "A" else None),
            bzdat=(src.bzdat or req.budat if src and rl.koart == "A" else None),
        )
        for name, value in payment_terms.line_fields(rl.terms, rl.wrbtr).items():
            setattr(item, name, value)
        session.add(item)
        if posted:
            _update_totals(session, mandt, req.bukrs, gjahr, monat, rl, local_currency)
            _mirror_co(session, mandt, req, gjahr, monat, belnr, buzei, rl, kokrs)
            if rl.koart == "A" and src:
                _update_asset_values(session, mandt, req, gjahr, belnr, buzei, rl, monat)

    if commit:
        session.commit()
    else:
        session.flush()
    session.refresh(header)
    return header


def post_parked(
    session: Session, mandt: str, bukrs: str, belnr: str, gjahr: int, *, usnam: str = "SYSTEM",
    commit: bool = True,
) -> AccountingDocumentHeader:
    """Post a parked document (FBV0): update totals, CO and assets; activate its open items."""
    try:
        header = session.get(AccountingDocumentHeader, (mandt, bukrs, belnr.zfill(10), gjahr))
        if header is None:
            raise PostingError(f"Document {belnr}/{gjahr} does not exist in company code {bukrs}")
        if header.bstat != "V":
            raise PostingError(f"Document {header.belnr}/{gjahr} is not a parked document")
        cc = company_code(session, mandt, bukrs)
        for koart in {"+"} | {i.koart for i in header.items}:
            check_period_open(session, mandt, bukrs, koart, header.gjahr, header.monat)
        req = DocumentRequest(
            mandt=mandt, bukrs=bukrs, blart=header.blart, bldat=header.bldat, budat=header.budat,
            waers=header.waers, kursf=header.kursf, kokrs=header.kokrs, lines=[],
        )
        for item in header.items:
            rl = _ResolvedLine(
                bschl=item.bschl, koart=item.koart, shkzg=item.shkzg, hkont=item.hkont,
                saknr=item.saknr, kunnr=item.kunnr, lifnr=item.lifnr, wrbtr=item.wrbtr,
                dmbtr=item.dmbtr, src=line_from_item(item), buzid=item.buzid, mwskz=item.mwskz,
            )
            _update_totals(session, mandt, bukrs, header.gjahr, header.monat, rl, cc.waers)
            _mirror_co(session, mandt, req, header.gjahr, header.monat, header.belnr, item.buzei, rl,
                       header.kokrs or controlling_area(session, mandt, bukrs))
            if item.koart == "A":
                _update_asset_values(session, mandt, req, header.gjahr, header.belnr, item.buzei, rl, header.monat)
            item.bstat = None
            item.xopvw = item.koart in ("D", "K") or (
                item.koart == "S" and _validate_gl_account(session, mandt, bukrs, item.hkont).xopvw)
        header.bstat, header.aedat, header.usnam = " ", date.today(), usnam
        if commit:
            session.commit()
        else:
            session.flush()
        session.refresh(header)
        return header
    except Exception:
        session.rollback()
        raise


def delete_parked(session: Session, mandt: str, bukrs: str, belnr: str, gjahr: int) -> None:
    """Delete a parked document: status Z, the number stays used (as in SAP)."""
    header = session.get(AccountingDocumentHeader, (mandt, bukrs, belnr.zfill(10), gjahr))
    if header is None or header.bstat != "V":
        raise PostingError(f"Document {belnr}/{gjahr} is not a parked document")
    header.bstat, header.aedat = "Z", date.today()
    for item in header.items:
        item.bstat = "Z"
    session.commit()


def line_from_item(item: AccountingDocumentItem) -> LineRequest:
    """Rebuild the line request a posted/parked BSEG row came from."""
    return LineRequest(
        bschl=item.bschl,
        account=item.kunnr or item.lifnr or item.anln1 or item.saknr or item.hkont,
        wrbtr=item.wrbtr, mwskz=item.mwskz, sgtxt=item.sgtxt, zuonr=item.zuonr, gsber=item.gsber,
        kostl=item.kostl, aufnr=item.aufnr, prctr=item.prctr, zfbdt=item.zfbdt, zterm=item.zterm,
        umskz=item.umskz, rebzg=item.rebzg, rebzj=item.rebzj, rebzz=item.rebzz, zlsch=item.zlsch,
        zlspr=item.zlspr, anln2=item.anln2 or "0000", anbwa=item.anbwa, bzdat=item.bzdat, buzid=item.buzid,
    )


def _absorb_rounding(lines: list[_ResolvedLine], requested: list[LineRequest]) -> None:
    """Put the cent differences of translating each line into the largest translated line.

    Lines with a fixed local amount (``LineRequest.dmbtr``) are never adjusted.
    """
    diff = sum((l.dmbtr if l.shkzg == "S" else -l.dmbtr for l in lines), Decimal("0"))
    if not diff or abs(diff) > _CENT * len(lines):
        return  # balanced, or a real error that _check_balanced reports
    fixed = {id(r) for r in requested if r.dmbtr is not None}
    side = "H" if diff > 0 else "S"  # raise the lighter side
    candidates = [l for l in lines if l.shkzg == side and id(l.src) not in fixed]
    if candidates:
        max(candidates, key=lambda l: l.dmbtr).dmbtr += abs(diff)


# BKPF / BSEG text fields and their lengths (PostgreSQL rejects longer values).
_HEADER_TEXTS = {"bktxt": 25, "xblnr": 16}
_LINE_TEXTS = {"sgtxt": 50, "zuonr": 18}


def _check_text_lengths(req: DocumentRequest) -> None:
    for field_name, size in _HEADER_TEXTS.items():
        value = getattr(req, field_name)
        if value and len(value) > size:
            raise PostingError(f"Header field {field_name.upper()} allows {size} characters: {value!r}")
    for n, ln in enumerate(req.lines, start=1):
        for field_name, size in _LINE_TEXTS.items():
            value = getattr(ln, field_name)
            if value and len(value) > size:
                raise PostingError(f"Line {n}: {field_name.upper()} allows {size} characters: {value!r}")


def _check_balanced(lines: list[_ResolvedLine], waers: str, local: str) -> None:
    doc_debit = sum((l.wrbtr for l in lines if l.shkzg == "S"), Decimal("0"))
    doc_credit = sum((l.wrbtr for l in lines if l.shkzg == "H"), Decimal("0"))
    if doc_debit != doc_credit:
        raise PostingError(
            f"Document not balanced in {waers}: debits {doc_debit} vs credits {doc_credit}"
        )
    loc_debit = sum((l.dmbtr for l in lines if l.shkzg == "S"), Decimal("0"))
    loc_credit = sum((l.dmbtr for l in lines if l.shkzg == "H"), Decimal("0"))
    if loc_debit != loc_credit:
        raise PostingError(
            f"Document not balanced in {local}: debits {loc_debit} vs credits {loc_credit}"
        )


def _update_totals(
    session: Session, mandt: str, bukrs: str, gjahr: int, monat: int,
    rl: _ResolvedLine, currency: str,
) -> None:
    rbusa = (rl.src.gsber if rl.src and rl.src.gsber else "")
    key = (mandt, "0", "00", bukrs, gjahr, rl.hkont, rbusa, rl.shkzg)
    row = session.get(GLAccountTotals, key)
    if row is None:
        row = GLAccountTotals(
            mandt=mandt, rrcty="0", rldnr="00", bukrs=bukrs, gjahr=gjahr,
            racct=rl.hkont, rbusa=rbusa, drcrk=rl.shkzg, rtcur=currency,
        )
        session.add(row)
        session.flush([row])  # so the next line of the same account finds it via session.get
    col = f"tsl{monat:02d}"
    setattr(row, col, (getattr(row, col) or Decimal("0")) + rl.dmbtr)


def _mirror_co(
    session: Session, mandt: str, req: DocumentRequest, gjahr: int, monat: int,
    belnr: str, buzei: int, rl: _ResolvedLine, default_kokrs: str | None,
) -> None:
    """Real-time FI->CO: mirror cost-element postings onto their CO object."""
    src = rl.src
    if src is None:
        return
    if not (src.kostl or src.aufnr):
        return
    kokrs = req.kokrs or default_kokrs
    if not kokrs:
        return
    cc = company_code(session, mandt, req.bukrs)
    # Only primary cost elements flow to CO.
    cska = session.get(CostElement, (mandt, cc.ktopl, rl.hkont))
    if cska is None:
        return
    cskb = (
        session.query(CostElementCO)
        .filter_by(mandt=mandt, kokrs=kokrs, kstar=rl.hkont)
        .first()
    )
    if cskb is None or cskb.katyp not in _PRIMARY_CO_CATEGORIES:
        return

    if src.kostl:
        objnr = f"KS{kokrs}{src.kostl}"
    else:
        objnr = f"OR{src.aufnr}"
    signed = rl.dmbtr if rl.shkzg == "S" else -rl.dmbtr
    co_buzei = (
        session.query(COLineItem).filter_by(mandt=mandt, kokrs=kokrs, belnr=belnr).count()
    ) + 1
    session.add(
        COLineItem(
            mandt=mandt, kokrs=kokrs, belnr=belnr, buzei=co_buzei, perio=monat,
            gjahr=gjahr, wrttp="04", versn="000", kstar=rl.hkont, objnr=objnr,
            bukrs=req.bukrs, kostl=src.kostl, aufnr=src.aufnr, prctr=src.prctr,
            wkgbtr=signed, owaer=cc.waers, twaer=req.waers, vrgng="COIN",
            refbn=belnr, refbz=buzei, refgj=gjahr,
        )
    )


# --- tax procedure helpers -------------------------------------------------

def _tax_procedure(session: Session, mandt: str, land1: str) -> str:
    from app.models.tax import Country

    country = session.get(Country, (mandt, land1))
    if country is None or not country.kalsm:
        raise PostingError(f"No tax procedure assigned to country {land1}")
    return country.kalsm


# --- asset accounting helpers ----------------------------------------------

def _asset_apc_account(
    session: Session, mandt: str, bukrs: str, ktopl: str, anln1: str, anln2: str, afabe: str
) -> str:
    """Resolve an asset's APC balance-sheet account from its class (T095)."""
    from app.models.assets import Asset, AssetAccountDetermination, AssetClass

    asset = session.get(Asset, (mandt, bukrs, anln1, anln2))
    if asset is None:
        raise PostingError(f"Asset {anln1}-{anln2} does not exist in company code {bukrs}")
    if asset.lvorm:
        raise PostingError(f"Asset {anln1}-{anln2} is flagged for deletion")
    anka = session.get(AssetClass, (mandt, asset.anlkl))
    if anka is None:
        raise PostingError(f"Asset class {asset.anlkl} is not defined")
    det = session.get(AssetAccountDetermination, (mandt, ktopl, anka.ktogr, afabe))
    if det is None:
        raise PostingError(
            f"No account determination (T095) for {anka.ktogr}/area {afabe} in {ktopl}"
        )
    return det.ktansw


def _update_asset_values(
    session: Session, mandt: str, req: DocumentRequest, gjahr: int,
    belnr: str, buzei: int, rl: _ResolvedLine, monat: int,
) -> None:
    """Write the ANEP transaction and roll the amount into ANLC asset values."""
    from app.models.assets import AssetLineItem, AssetValues

    src = rl.src
    anln1, anln2 = src.account, src.anln2
    signed = rl.dmbtr if rl.shkzg == "S" else -rl.dmbtr

    lnran = (
        session.query(AssetLineItem)
        .filter_by(mandt=mandt, bukrs=req.bukrs, anln1=anln1, anln2=anln2, gjahr=gjahr)
        .count()
    ) + 1
    session.add(
        AssetLineItem(
            mandt=mandt, bukrs=req.bukrs, anln1=anln1, anln2=anln2, gjahr=gjahr,
            lnran=lnran, afabe=src.afabe, bwasl=src.anbwa or "100", anbtr=signed,
            belnr=belnr, buzei=buzei, budat=req.budat, bzdat=src.bzdat or req.budat,
        )
    )
    val = session.get(AssetValues, (mandt, req.bukrs, anln1, anln2, gjahr, src.afabe))
    if val is None:
        val = AssetValues(
            mandt=mandt, bukrs=req.bukrs, anln1=anln1, anln2=anln2, gjahr=gjahr, afabe=src.afabe
        )
        session.add(val)
        session.flush([val])
    # Acquisition (debit asset) increases ANSWL; retirement (credit) increases ABGAN.
    if rl.shkzg == "S":
        val.answl = (val.answl or Decimal("0")) + rl.dmbtr
    else:
        val.abgan = (val.abgan or Decimal("0")) + rl.dmbtr
