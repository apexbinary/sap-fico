"""Bank Accounting services — import an electronic bank statement and post it.

Importing stores FEBKO/FEBEP. Posting walks the statement items: a credit
matched to a customer becomes an incoming payment (debit bank G/L, credit
customer); a debit matched to a vendor becomes an outgoing payment (credit bank
G/L, debit vendor). Matched open items are cleared (AUGBL set on both sides).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bank import (
    BankStatementHeader,
    BankStatementItem,
    HouseBankAccount,
)
from app.models.documents import AccountingDocumentItem
from app.models.organizational import CompanyCode
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, LineRequest, post_document


def import_statement(
    session: Session, mandt: str, bukrs: str, hbkid: str, hktid: str, kukey: str,
    statement_date: date, items: list[dict], *, opening: Decimal = Decimal("0"),
    closing: Decimal | None = None, aznum: str | None = None,
) -> dict:
    """Store a bank statement (FEBKO header + FEBEP items).

    Each item dict: {amount, shkzg ('S'/'H'), valut?, note?, kunnr?, lifnr?}.
    """
    acct = session.get(HouseBankAccount, (mandt, bukrs, hbkid, hktid))
    if acct is None:
        raise PostingError(f"House bank account {hbkid}/{hktid} not defined in {bukrs}")

    net = Decimal("0")
    for it in items:
        amt = Decimal(str(it["amount"]))
        net += amt if it["shkzg"] == "H" else -amt
    close = closing if closing is not None else opening + net

    session.merge(
        BankStatementHeader(
            mandt=mandt, kukey=kukey, bukrs=bukrs, hbkid=hbkid, hktid=hktid,
            waers=acct.waers, bankn=acct.bankn, aznum=aznum, adatu=statement_date,
            anfsl=opening, ensal=close, xbobl=False,
        )
    )
    for i, it in enumerate(items, start=1):
        session.merge(
            BankStatementItem(
                mandt=mandt, kukey=kukey, esnum=i, kwbtr=Decimal(str(it["amount"])),
                kwaer=acct.waers, shkzg=it["shkzg"], valut=it.get("valut", statement_date),
                budat=statement_date, vwzw1=it.get("note"), partn=it.get("partner"),
                kunnr=it.get("kunnr"), lifnr=it.get("lifnr"), xbenr=False,
            )
        )
    session.commit()
    return {"kukey": kukey, "items": len(items), "opening": str(opening), "closing": str(close)}


def post_statement(session: Session, mandt: str, bukrs: str, kukey: str) -> dict:
    """Post and reconcile all unposted items of a bank statement."""
    cc = session.get(CompanyCode, (mandt, bukrs))
    header = session.get(BankStatementHeader, (mandt, kukey))
    if header is None:
        raise PostingError(f"Bank statement {kukey} not found")
    acct = session.get(HouseBankAccount, (mandt, bukrs, header.hbkid, header.hktid))
    bank_gl = acct.hkont

    items = session.scalars(
        select(BankStatementItem).where(
            BankStatementItem.mandt == mandt, BankStatementItem.kukey == kukey,
            BankStatementItem.xbenr.is_(False),
        ).order_by(BankStatementItem.esnum)
    ).all()

    posted = []
    for it in items:
        if it.kunnr:  # incoming customer payment
            lines = [
                LineRequest(bschl="40", account=bank_gl, wrbtr=it.kwbtr, sgtxt="Bank incoming"),
                LineRequest(bschl="15", account=it.kunnr, wrbtr=it.kwbtr, sgtxt="Incoming payment"),
            ]
            koart, partner = "D", it.kunnr
        elif it.lifnr:  # outgoing vendor payment
            lines = [
                LineRequest(bschl="50", account=bank_gl, wrbtr=it.kwbtr, sgtxt="Bank outgoing"),
                LineRequest(bschl="25", account=it.lifnr, wrbtr=it.kwbtr, sgtxt="Outgoing payment"),
            ]
            koart, partner = "K", it.lifnr
        else:
            continue  # unmatched item, left for manual processing

        header_doc = post_document(session, DocumentRequest(
            mandt=mandt, bukrs=bukrs, blart="DZ" if koart == "D" else "KZ",
            bldat=it.budat, budat=it.budat, waers=header.waers,
            bktxt=f"Bank statement {kukey}/{it.esnum}", lines=lines,
        ))
        it.belnr, it.gjahr, it.xbenr = header_doc.belnr, header_doc.gjahr, True

        cleared = _clear_open_items(session, mandt, bukrs, koart, partner, it.kwbtr, header_doc.belnr, it.budat)
        it.nbbln = header_doc.belnr if cleared else None
        session.commit()
        posted.append({"esnum": it.esnum, "belnr": header_doc.belnr, "partner": partner, "cleared": cleared})

    if items and all(i.xbenr for i in session.scalars(
        select(BankStatementItem).where(BankStatementItem.mandt == mandt, BankStatementItem.kukey == kukey)
    ).all()):
        header.xbobl = True
        session.commit()

    return {"kukey": kukey, "posted": posted}


def _clear_open_items(
    session: Session, mandt: str, bukrs: str, koart: str, partner: str,
    amount: Decimal, augbl: str, augdt: date,
) -> bool:
    """Clear the open item(s) of a partner matching the payment amount (FIFO)."""
    field = AccountingDocumentItem.kunnr if koart == "D" else AccountingDocumentItem.lifnr
    # The payment line posts the opposite side of the invoice; find the open invoice.
    inv_side = "S" if koart == "D" else "H"
    items = session.scalars(
        select(AccountingDocumentItem).where(
            AccountingDocumentItem.mandt == mandt,
            AccountingDocumentItem.bukrs == bukrs,
            AccountingDocumentItem.koart == koart,
            field == partner,
            AccountingDocumentItem.shkzg == inv_side,
            AccountingDocumentItem.augbl.is_(None),
        ).order_by(AccountingDocumentItem.gjahr, AccountingDocumentItem.belnr)
    ).all()

    for inv in items:
        if inv.dmbtr == amount:
            inv.augbl, inv.augdt = augbl, augdt
            # also clear the payment line itself
            pay_items = session.scalars(
                select(AccountingDocumentItem).where(
                    AccountingDocumentItem.mandt == mandt,
                    AccountingDocumentItem.bukrs == bukrs,
                    AccountingDocumentItem.belnr == augbl,
                    AccountingDocumentItem.koart == koart,
                )
            ).all()
            for p in pay_items:
                p.augbl, p.augdt = augbl, augdt
            return True
    return False
