"""Bank Accounting services — import an electronic bank statement and post it.

Importing stores FEBKO/FEBEP. Posting walks the statement items: a credit
matched to a customer becomes an incoming payment (debit bank G/L, credit
customer); a debit matched to a vendor becomes an outgoing payment (credit bank
G/L, debit vendor). If the amount settles one open invoice exactly (net of cash
discount, or gross) that invoice is cleared; otherwise the payment is posted on
account for manual clearing. Both go through the clearing service.
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
from app.services import clearing
from app.services.fiscal import PostingError


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
            koart, partner = "D", it.kunnr
        elif it.lifnr:  # outgoing vendor payment
            koart, partner = "K", it.lifnr
        else:
            continue  # unmatched item, left for manual processing

        match = clearing.match_open_item(session, mandt, bukrs, koart, partner, it.kwbtr, it.budat)
        res = clearing.post_payment(session, clearing.PaymentRequest(
            mandt=mandt, bukrs=bukrs, koart=koart, account=partner, budat=it.budat,
            amount=it.kwbtr, hkont=bank_gl,
            items=[match[0]] if match else [],
            apply_discount=match[1] if match else False,
            mode="clear" if match else "on_account",
            bktxt=f"Bank stmt {kukey}/{it.esnum}"[:25], sgtxt=it.vwzw1, tcode="FF_5",
        ), commit=False)
        it.belnr, it.gjahr, it.xbenr = res["belnr"], res["gjahr"], True
        it.nbbln = res["belnr"] if match else None
        session.commit()
        posted.append({"esnum": it.esnum, "belnr": res["belnr"], "partner": partner,
                       "cleared": bool(match), "discount": res["discount"]})

    if items and all(i.xbenr for i in session.scalars(
        select(BankStatementItem).where(BankStatementItem.mandt == mandt, BankStatementItem.kukey == kukey)
    ).all()):
        header.xbobl = True
        session.commit()

    return {"kukey": kukey, "posted": posted}
