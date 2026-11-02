"""Automatic payment program (F110): parameters -> proposal -> payment run -> payment medium.

Proposal rules (vendors, outgoing payments):
  * open vendor items of the paying company code, entered up to REGUV-CPUDT,
    for the vendors in the selection;
  * an invoice is paid now if it would be overdue by the next run (net due
    date < NEDAT), or if paying now earns a better cash discount than paying at
    the next run; otherwise it waits for a later run;
  * credit memos and other debit items are offset in full;
  * payment method: the item's ZLSCH, else the first method of the vendor's
    list (LFB1-ZWELS) that the run allows and the company code supports (T042E);
  * house bank: the first T042I ranking entry for method and currency.

Items that cannot be paid (payment block, vendor blocked, no valid payment
method, foreign currency) are listed in an exception group with ZLSCH ''.
Payable groups that still fail a check (net credit balance, missing bank
details, amount limits, no house bank) keep their exception and are skipped by
the payment run. The payment run posts each remaining group through the
clearing service, and the medium is a SEPA credit transfer (pain.001.001.03).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bank import Bank, HouseBank, HouseBankAccount
from app.models.documents import AccountingDocumentHeader, AccountingDocumentItem
from app.models.partners import Vendor, VendorBankDetails, VendorCompanyCode
from app.models.payment_run import PaymentRunControl, PaymentRunItem, PaymentRunPayee
from app.models.payments import BankDetermination, CompanyCodePaymentMethod, PaymentMethod
from app.services import clearing, payment_terms
from app.services.fiscal import PostingError, company_code

_PAIN = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"


def get_run(session: Session, mandt: str, laufd: date, laufi: str) -> PaymentRunControl:
    run = session.get(PaymentRunControl, (mandt, laufd, laufi))
    if run is None:
        raise PostingError(f"Payment run {laufd.isoformat()}/{laufi} does not exist")
    return run


def create_proposal(
    session: Session, mandt: str, *, laufd: date, laufi: str, zbukr: str, zwels: str,
    zaldt: date, nedat: date, cpudt: date | None = None,
    lifnr_low: str | None = None, lifnr_high: str | None = None, usnam: str = "SYSTEM",
) -> PaymentRunControl:
    """Save the run parameters and build (or rebuild) the payment proposal."""
    if nedat <= zaldt:
        raise PostingError("The next payment date must be after the posting date")
    if not zwels:
        raise PostingError("Enter at least one payment method")
    existing = session.get(PaymentRunControl, (mandt, laufd, laufi))
    if existing is not None:
        if existing.xecht:
            raise PostingError(f"Payment run {laufd.isoformat()}/{laufi} was already executed")
        session.delete(existing)
        session.flush()

    cc = company_code(session, mandt, zbukr)
    run = PaymentRunControl(
        mandt=mandt, laufd=laufd, laufi=laufi, zbukr=zbukr, zwels=zwels, zaldt=zaldt,
        nedat=nedat, cpudt=cpudt or date.today(), lifnr_low=lifnr_low, lifnr_high=lifnr_high,
        usnam=usnam, xvore=True, vorer=datetime.utcnow(),
    )
    session.add(run)

    supported = {
        e.zlsch: e for e in session.scalars(select(CompanyCodePaymentMethod).where(
            CompanyCodePaymentMethod.mandt == mandt, CompanyCodePaymentMethod.zbukr == zbukr))
        if e.zlsch in zwels
    }
    methods = {
        m.zlsch: m for m in session.scalars(select(PaymentMethod).where(
            PaymentMethod.mandt == mandt, PaymentMethod.land1 == cc.land1))
    }

    stmt = (
        select(AccountingDocumentItem)
        .join(AccountingDocumentItem.header)
        .where(
            AccountingDocumentItem.mandt == mandt,
            AccountingDocumentItem.bukrs == zbukr,
            AccountingDocumentItem.koart == "K",
            AccountingDocumentItem.augbl.is_(None),
            AccountingDocumentHeader.cpudt <= run.cpudt,
        )
        .order_by(AccountingDocumentItem.lifnr, AccountingDocumentItem.gjahr,
                  AccountingDocumentItem.belnr, AccountingDocumentItem.buzei)
    )
    if lifnr_low:
        stmt = stmt.where(AccountingDocumentItem.lifnr >= lifnr_low)
    if lifnr_high:
        stmt = stmt.where(AccountingDocumentItem.lifnr <= lifnr_high)

    by_vendor: dict[str, list[AccountingDocumentItem]] = defaultdict(list)
    for it in session.scalars(stmt):
        by_vendor[it.lifnr].append(it)

    for lifnr, items in by_vendor.items():
        due = [it for it in items if it.shkzg == "S" or _due(it, zaldt, nedat)]
        if not any(it.shkzg == "H" for it in due):
            continue  # nothing due for this vendor in this run
        _propose_vendor(session, run, cc, lifnr, due, supported, methods)

    session.commit()
    session.refresh(run)
    return run


def _due(it: AccountingDocumentItem, zaldt: date, nedat: date) -> bool:
    """Pay now if overdue by the next run, or if waiting would lose cash discount."""
    if payment_terms.net_due_date(it) < nedat:
        return True
    return payment_terms.cash_discount(it, zaldt)[0] > payment_terms.cash_discount(it, nedat)[0]


def _propose_vendor(session, run, cc, lifnr, items, supported, methods) -> None:
    mandt = run.mandt
    lfa1 = session.get(Vendor, (mandt, lifnr))
    lfb1 = session.get(VendorCompanyCode, (mandt, lifnr, run.zbukr))
    vendor_methods = [m for m in (lfb1.zwels if lfb1 and lfb1.zwels else "") if m in supported]

    groups: dict[str, list[AccountingDocumentItem]] = defaultdict(list)
    excluded: list[tuple[AccountingDocumentItem, str]] = []
    for it in items:
        if lfb1 and lfb1.zahls:
            excluded.append((it, f"vendor blocked for payment ({lfb1.zahls})"))
        elif it.zlspr:
            excluded.append((it, f"payment block {it.zlspr}"))
        elif it.header.waers != cc.waers:
            excluded.append((it, f"currency {it.header.waers} not supported"))
        elif it.zlsch:
            if it.zlsch in supported:
                groups[it.zlsch].append(it)
            else:
                excluded.append((it, f"payment method {it.zlsch} not allowed in this run"))
        elif vendor_methods:
            groups[vendor_methods[0]].append(it)
        else:
            excluded.append((it, "no valid payment method"))

    for zlsch, its in groups.items():
        payee = _payee(run, cc, lifnr, zlsch, lfa1)
        total = Decimal("0")
        for it in its:
            disc = payment_terms.cash_discount(it, run.zaldt)[1] if it.shkzg == "H" else Decimal("0")
            signed = it.wrbtr if it.shkzg == "H" else -it.wrbtr
            payee.items.append(_regup(payee, it, signed, disc))
            total += signed
            payee.rskon += disc
        payee.rwbtr = total - payee.rskon
        payee.exception = _check_group(session, payee, cc, supported[zlsch], methods.get(zlsch))
        run.payees.append(payee)

    if excluded:
        payee = _payee(run, cc, lifnr, "", lfa1)
        for it, _ in excluded:
            signed = it.wrbtr if it.shkzg == "H" else -it.wrbtr
            payee.items.append(_regup(payee, it, signed, Decimal("0")))
            payee.rwbtr += signed
        payee.exception = ("Not paid: " + "; ".join(sorted({why for _, why in excluded})))[:120]
        run.payees.append(payee)


def _payee(run, cc, lifnr, zlsch, lfa1) -> PaymentRunPayee:
    return PaymentRunPayee(
        mandt=run.mandt, laufd=run.laufd, laufi=run.laufi, zbukr=run.zbukr, lifnr=lifnr,
        zlsch=zlsch, name1=lfa1.name1 if lfa1 else None, waers=cc.waers, zaldt=run.zaldt,
        rwbtr=Decimal("0"), rskon=Decimal("0"),
    )


def _regup(payee, it, signed, disc) -> PaymentRunItem:
    return PaymentRunItem(
        mandt=payee.mandt, laufd=payee.laufd, laufi=payee.laufi, zbukr=payee.zbukr,
        lifnr=payee.lifnr, zlsch=payee.zlsch, bukrs=it.bukrs, belnr=it.belnr, gjahr=it.gjahr,
        buzei=it.buzei, shkzg=it.shkzg, wrbtr=signed, wskto=disc,
        faedt=payment_terms.net_due_date(it), zlspr=it.zlspr, xblnr=it.header.xblnr, sgtxt=it.sgtxt,
    )


def _check_group(session, payee, cc, t042e, t042z) -> str | None:
    """Fill payee bank and house bank data; return an exception reason or None."""
    mandt = payee.mandt
    if payee.rwbtr <= 0:
        return f"Net credit balance {payee.rwbtr} {payee.waers}: no payment"

    bank = session.scalars(select(VendorBankDetails).where(
        VendorBankDetails.mandt == mandt, VendorBankDetails.lifnr == payee.lifnr)).first()
    if bank is not None:
        bnka = session.get(Bank, (mandt, bank.banks, bank.bankl))
        payee.zbnks, payee.zbnkl, payee.zbnkn, payee.ziban = bank.banks, bank.bankl, bank.bankn, bank.iban
        payee.zswif = bnka.swift if bnka else None
    if t042z is not None and t042z.xbkkt and (bank is None or not bank.iban):
        return f"No bank details with IBAN (LFBK) for payment method {payee.zlsch}"

    if payee.rwbtr < (t042e.minbt or 0):
        return f"Amount {payee.rwbtr} below minimum {t042e.minbt} for payment method {payee.zlsch}"
    if t042e.maxbt and payee.rwbtr > t042e.maxbt:
        return f"Amount {payee.rwbtr} above maximum {t042e.maxbt} for payment method {payee.zlsch}"

    rank = session.scalars(select(BankDetermination).where(
        BankDetermination.mandt == mandt, BankDetermination.zbukr == payee.zbukr,
        BankDetermination.zlsch == payee.zlsch, BankDetermination.waers == payee.waers,
    ).order_by(BankDetermination.rangf)).first()
    if rank is None:
        return f"No house bank (T042I) for payment method {payee.zlsch} in {payee.waers}"
    acct = session.get(HouseBankAccount, (mandt, payee.zbukr, rank.hbkid, rank.hktid))
    payee.hbkid, payee.hktid, payee.ukont = rank.hbkid, rank.hktid, rank.ukont
    payee.ubknt, payee.ubiban = (acct.bankn, acct.iban) if acct else (None, None)
    return None


def delete_proposal(session: Session, mandt: str, laufd: date, laufi: str) -> None:
    run = get_run(session, mandt, laufd, laufi)
    if run.xecht:
        raise PostingError(f"Payment run {laufd.isoformat()}/{laufi} was already executed")
    session.delete(run)
    session.commit()


def execute(session: Session, mandt: str, laufd: date, laufi: str) -> PaymentRunControl:
    """Post one payment document per payable group and clear its items."""
    run = get_run(session, mandt, laufd, laufi)
    if not run.xvore:
        raise PostingError("Create a payment proposal first")
    if run.xecht:
        raise PostingError(f"Payment run {laufd.isoformat()}/{laufi} was already executed")

    cc = company_code(session, mandt, run.zbukr)
    for payee in list(run.payees):
        if payee.exception or not payee.items:
            continue
        method = session.get(PaymentMethod, (mandt, cc.land1, payee.zlsch))
        req = clearing.PaymentRequest(
            mandt=mandt, bukrs=run.zbukr, koart="K", account=payee.lifnr, budat=run.zaldt,
            amount=payee.rwbtr, hkont=payee.ukont,
            items=[(i.belnr, i.gjahr, i.buzei) for i in payee.items],
            blart=(method.blart if method and method.blart else None) or "ZP", tcode="F110",
            bktxt=f"F110 {run.laufd:%Y%m%d}/{run.laufi}", sgtxt=f"Payment run {run.laufi}",
            usnam=run.usnam,
        )
        try:
            res = clearing.post_payment(session, req, commit=False)
        except PostingError as exc:  # post_payment rolled the attempt back
            payee.exception = f"Payment failed: {exc}"[:120]
            session.commit()
            continue
        payee.vblnr, payee.gjahr, payee.rskon = res["belnr"], res["gjahr"], res["discount"]
        session.commit()

    run.xecht, run.echer = True, datetime.utcnow()
    session.commit()
    session.refresh(run)
    return run


def sepa_credit_transfer(session: Session, mandt: str, laufd: date, laufi: str) -> bytes:
    """Payment medium: SEPA credit transfer initiation (pain.001.001.03)."""
    run = get_run(session, mandt, laufd, laufi)
    paid = [p for p in run.payees if p.vblnr]
    if not paid:
        raise PostingError("The payment run has no executed payments")
    cc = company_code(session, mandt, run.zbukr)
    msg_id = f"F110-{run.laufd:%Y%m%d}-{run.laufi}"

    def sub(parent, tag, text=None, **attrs):
        node = ET.SubElement(parent, tag, attrs)
        if text is not None:
            node.text = str(text)
        return node

    root = ET.Element("Document", xmlns=_PAIN)
    init = sub(root, "CstmrCdtTrfInitn")
    hdr = sub(init, "GrpHdr")
    sub(hdr, "MsgId", msg_id)
    sub(hdr, "CreDtTm", datetime.utcnow().replace(microsecond=0).isoformat())
    sub(hdr, "NbOfTxs", len(paid))
    sub(hdr, "CtrlSum", f"{sum(p.rwbtr for p in paid):.2f}")
    sub(sub(hdr, "InitgPty"), "Nm", cc.butxt)

    by_account: dict[tuple[str, str], list[PaymentRunPayee]] = defaultdict(list)
    for p in paid:
        by_account[(p.hbkid, p.hktid)].append(p)
    for (hbkid, hktid), payees in by_account.items():
        house_bank = session.get(HouseBank, (mandt, run.zbukr, hbkid))
        inf = sub(init, "PmtInf")
        sub(inf, "PmtInfId", f"{msg_id}-{hbkid}{hktid}")
        sub(inf, "PmtMtd", "TRF")
        sub(inf, "NbOfTxs", len(payees))
        sub(inf, "CtrlSum", f"{sum(p.rwbtr for p in payees):.2f}")
        sub(sub(sub(inf, "PmtTpInf"), "SvcLvl"), "Cd", "SEPA")
        sub(inf, "ReqdExctnDt", run.zaldt.isoformat())
        sub(sub(inf, "Dbtr"), "Nm", cc.butxt)
        sub(sub(sub(inf, "DbtrAcct"), "Id"), "IBAN", payees[0].ubiban or "")
        agent = sub(sub(inf, "DbtrAgt"), "FinInstnId")
        if house_bank and house_bank.swift:
            sub(agent, "BIC", house_bank.swift)
        sub(inf, "ChrgBr", "SLEV")
        for p in payees:
            tx = sub(inf, "CdtTrfTxInf")
            sub(sub(tx, "PmtId"), "EndToEndId", f"{p.vblnr}{p.gjahr}")
            sub(sub(tx, "Amt"), "InstdAmt", f"{p.rwbtr:.2f}", Ccy=p.waers)
            if p.zswif:
                sub(sub(sub(tx, "CdtrAgt"), "FinInstnId"), "BIC", p.zswif)
            sub(sub(tx, "Cdtr"), "Nm", p.name1 or p.lifnr)
            sub(sub(sub(tx, "CdtrAcct"), "Id"), "IBAN", p.ziban or "")
            refs = ", ".join(i.xblnr or i.belnr for i in p.items if i.wrbtr > 0)
            sub(sub(tx, "RmtInf"), "Ustrd", f"Invoices {refs}"[:140])

    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def run_summary(run: PaymentRunControl, *, with_items: bool = True) -> dict:
    payable = [p for p in run.payees if not p.exception]
    out = {
        "laufd": run.laufd, "laufi": run.laufi, "zbukr": run.zbukr, "zwels": run.zwels,
        "zaldt": run.zaldt, "nedat": run.nedat, "cpudt": run.cpudt,
        "lifnr_low": run.lifnr_low, "lifnr_high": run.lifnr_high,
        "xvore": run.xvore, "xecht": run.xecht,
        "status": "Payment run executed" if run.xecht else ("Proposal created" if run.xvore else "Parameters entered"),
        "payments": len(payable), "exceptions": len(run.payees) - len(payable),
        "total": sum((p.rwbtr for p in payable), Decimal("0")),
        "discount": sum((p.rskon for p in payable), Decimal("0")),
    }
    if with_items:
        out["payees"] = [{
            "lifnr": p.lifnr, "name1": p.name1, "zlsch": p.zlsch, "waers": p.waers,
            "rwbtr": p.rwbtr, "rskon": p.rskon, "hbkid": p.hbkid, "hktid": p.hktid,
            "ziban": p.ziban, "vblnr": p.vblnr, "gjahr": p.gjahr, "exception": p.exception,
            "items": [{
                "belnr": i.belnr, "gjahr": i.gjahr, "buzei": i.buzei, "shkzg": i.shkzg,
                "wrbtr": i.wrbtr, "wskto": i.wskto, "faedt": i.faedt, "zlspr": i.zlspr,
                "xblnr": i.xblnr, "sgtxt": i.sgtxt,
            } for i in p.items],
        } for p in run.payees]
    return out
