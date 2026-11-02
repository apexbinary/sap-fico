"""Document reversal (FB08) and resetting cleared items (FBRA).

A reversal posts a mirror document through the posting engine: every line
keeps its account, amount, tax code and CO assignment, and its posting key is
replaced by the key's reversal key (TBSL-STBSL), which flips debit and credit.
The reversal and the original reference each other (BKPF-STBLG/STJAH, reason
STGRD), and their open items clear each other.

A document whose open items are already cleared cannot be reversed: reset the
clearing first (``reset_clearing``), optionally reversing the clearing
document in the same step, as FBRA does.

Asset documents are reversed like AB08: the asset line items (ANEP) get the
opposite amounts and the reversed movement is reduced in the asset values
(ANLC). Reversing a depreciation document (AF) takes its ANLP depreciation
back out of the asset values. ``mass_reverse`` reverses a list (F.80).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.documents import (
    AccountingDocumentHeader,
    AccountingDocumentItem,
    DocumentType,
    PostingKey,
)
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, line_from_item, post_document

REASONS = {"01": "Reversal in current period", "02": "Reversal in closed period"}


def _document(session: Session, mandt: str, bukrs: str, belnr: str, gjahr: int) -> AccountingDocumentHeader:
    header = session.get(AccountingDocumentHeader, (mandt, bukrs, belnr.zfill(10), gjahr))
    if header is None:
        raise PostingError(f"Document {belnr}/{gjahr} does not exist in company code {bukrs}")
    return header


def reverse_document(
    session: Session, mandt: str, bukrs: str, belnr: str, gjahr: int, *,
    budat: date | None = None, stgrd: str = "01", usnam: str = "SYSTEM", commit: bool = True,
) -> AccountingDocumentHeader:
    """Reverse a posted document; returns the reversal document."""
    try:
        return _reverse(session, mandt, bukrs, belnr, gjahr, budat, stgrd, usnam, commit)
    except Exception:
        session.rollback()
        raise


def _reverse(session, mandt, bukrs, belnr, gjahr, budat, stgrd, usnam, commit):
    if stgrd not in REASONS:
        raise PostingError(f"Unknown reversal reason {stgrd}; use one of {', '.join(REASONS)}")
    header = _document(session, mandt, bukrs, belnr, gjahr)
    ref = f"{header.belnr}/{gjahr}"
    if header.bstat != " ":
        raise PostingError(f"Document {ref} is not a posted document (status {header.bstat!r})")
    if header.stblg:
        raise PostingError(f"Document {ref} is already reversed by / a reversal of {header.stblg}")
    if not header.items:
        raise PostingError(f"Document {ref} has no line items; reset its clearing instead (FBRA)")
    for i in header.items:
        if i.augbl:
            raise PostingError(
                f"Line {i.buzei} of document {ref} is cleared by {i.augbl}; reset the clearing first (FBRA)"
            )

    lines = []
    for item in header.items:
        pk = session.get(PostingKey, (mandt, item.bschl))
        if pk is None or not pk.stbsl:
            raise PostingError(f"Posting key {item.bschl} has no reversal posting key (TBSL-STBSL)")
        line = line_from_item(item)
        line.bschl = pk.stbsl
        line.zterm = line.zfbdt = None  # the reversal item is cleared at once
        lines.append(line)

    doc_type = session.get(DocumentType, (mandt, header.blart))
    rev = post_document(session, DocumentRequest(
        mandt=mandt, bukrs=bukrs, blart=(doc_type.stbla if doc_type and doc_type.stbla else header.blart),
        bldat=header.bldat, budat=budat or header.budat, waers=header.waers, kursf=header.kursf,
        xblnr=header.xblnr, bktxt=f"Reversal of {header.belnr}"[:25], usnam=usnam, tcode="FB08",
        kokrs=header.kokrs, lines=lines, xstor=True,
    ), commit=False)
    _reverse_depreciation(session, mandt, bukrs, header)

    rev.stblg, rev.stjah, rev.stgrd = header.belnr, header.gjahr, stgrd
    header.stblg, header.stjah, header.stgrd = rev.belnr, rev.gjahr, stgrd
    for orig, new in zip(header.items, rev.items):
        if orig.xopvw:
            for row in (orig, new):
                row.augbl, row.auggj, row.augdt, row.augcp = rev.belnr, rev.gjahr, rev.budat, date.today()
    if commit:
        session.commit()
    else:
        session.flush()
    session.refresh(rev)
    return rev


def _reverse_depreciation(session: Session, mandt: str, bukrs: str, header: AccountingDocumentHeader) -> None:
    """Take the depreciation of a reversed depreciation document out of ANLC (ANLP no longer posted)."""
    from app.models.assets import AssetValues, DepreciationPosting

    for anlp in session.scalars(select(DepreciationPosting).where(
            DepreciationPosting.mandt == mandt, DepreciationPosting.bukrs == bukrs,
            DepreciationPosting.belnr == header.belnr, DepreciationPosting.gjahr == header.gjahr,
            DepreciationPosting.xbuchen.is_(True))):
        val = session.get(AssetValues, (mandt, bukrs, anlp.anln1, anlp.anln2, anlp.gjahr, anlp.afabe))
        if val is not None:
            val.nafag = (val.nafag or 0) - anlp.nafaz
        anlp.xbuchen = False


def mass_reverse(
    session: Session, mandt: str, bukrs: str, documents: list[tuple[str, int]], *,
    budat: date | None = None, stgrd: str = "01", usnam: str = "SYSTEM",
) -> list[dict]:
    """Reverse several documents (F.80); each one on its own, failures are reported, not raised."""
    results = []
    for belnr, gjahr in documents:
        try:
            rev = reverse_document(session, mandt, bukrs, belnr, gjahr, budat=budat, stgrd=stgrd, usnam=usnam)
            results.append({"belnr": belnr.zfill(10), "gjahr": gjahr, "reversal": rev.belnr, "error": None})
        except PostingError as exc:
            results.append({"belnr": belnr.zfill(10), "gjahr": gjahr, "reversal": None, "error": str(exc)})
    return results


def reset_clearing(
    session: Session, mandt: str, bukrs: str, belnr: str, gjahr: int, *,
    reverse: bool = False, budat: date | None = None, stgrd: str = "01", usnam: str = "SYSTEM",
) -> dict:
    """Reopen every item cleared by a clearing document; optionally reverse that document."""
    try:
        header = _document(session, mandt, bukrs, belnr, gjahr)
        rows = session.scalars(select(AccountingDocumentItem).where(
            AccountingDocumentItem.mandt == mandt, AccountingDocumentItem.bukrs == bukrs,
            AccountingDocumentItem.augbl == header.belnr,
            or_(AccountingDocumentItem.auggj == gjahr, AccountingDocumentItem.auggj.is_(None)),
        )).all()
        if not rows:
            raise PostingError(f"Document {header.belnr}/{gjahr} has not cleared any items")
        for r in rows:
            r.augbl = r.auggj = r.augdt = r.augcp = None
        result = {"belnr": header.belnr, "gjahr": gjahr, "reset_items": len(rows), "reversal": None}
        if reverse:
            if not header.items:
                raise PostingError(f"Document {header.belnr}/{gjahr} has no line items to reverse")
            session.flush()
            rev = _reverse(session, mandt, bukrs, header.belnr, gjahr, budat, stgrd, usnam, commit=False)
            result["reversal"] = {"belnr": rev.belnr, "gjahr": rev.gjahr}
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
