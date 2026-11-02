"""Automatic payment program (F110): parameters -> proposal -> payment run -> payment media.

The run pays vendors with outgoing payment methods (T042Z-XEINZ off, e.g. T
bank transfer) and collects from customers with incoming methods (XEINZ on,
e.g. E SEPA direct debit). Proposal rules, per partner:

  * open items of the paying company code, entered up to REGUV-CPUDT, for the
    vendors / customers in the selection;
  * an invoice is settled now if it would be overdue by the next run (net due
    date < NEDAT), or if settling now earns a better cash discount than at the
    next run; otherwise it waits for a later run;
  * credit memos and other opposite-side items are offset in full;
  * payment method: the item's ZLSCH, else the first method of the partner's
    list (LFB1/KNB1-ZWELS) that the run allows and the company code supports
    (T042E) for that direction;
  * house bank: the first T042I ranking entry for method and currency.

Items that cannot be settled (payment block, partner blocked, no valid payment
method, foreign currency) go to an exception group with ZLSCH ''. Payable
groups that fail a check (net credit balance, missing bank details or SEPA
mandate, amount limits, no house bank) keep their exception and are skipped by
the payment run. The payment run posts each remaining group through the
clearing service; the media are SEPA credit transfer (pain.001.001.03) and
SEPA direct debit (pain.008.001.02) files.
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
from app.models.partners import (
    Customer,
    CustomerBankDetails,
    CustomerCompanyCode,
    SepaMandate,
    Vendor,
    VendorBankDetails,
    VendorCompanyCode,
)
from app.models.payment_run import PaymentRunControl, PaymentRunItem, PaymentRunPayee
from app.models.payments import BankDetermination, CompanyCodePaymentMethod, PaymentMethod
from app.services import clearing, payment_terms
from app.services.fiscal import PostingError, company_code

_PAIN001 = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
_PAIN008 = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.02"

# Per account type: partner column, invoice side, and whether settling it is incoming money.
_PARTNER = {
    "K": {"col": AccountingDocumentItem.lifnr, "inv_side": "H", "incoming": False},
    "D": {"col": AccountingDocumentItem.kunnr, "inv_side": "S", "incoming": True},
}


def get_run(session: Session, mandt: str, laufd: date, laufi: str) -> PaymentRunControl:
    run = session.get(PaymentRunControl, (mandt, laufd, laufi))
    if run is None:
        raise PostingError(f"Payment run {laufd.isoformat()}/{laufi} does not exist")
    return run


def create_proposal(
    session: Session, mandt: str, *, laufd: date, laufi: str, zbukr: str, zwels: str,
    zaldt: date, nedat: date, cpudt: date | None = None,
    lifnr_low: str | None = None, lifnr_high: str | None = None,
    kunnr_low: str | None = None, kunnr_high: str | None = None, usnam: str = "SYSTEM",
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
        kunnr_low=kunnr_low, kunnr_high=kunnr_high, usnam=usnam, xvore=True, vorer=datetime.utcnow(),
    )
    session.add(run)

    methods = {
        m.zlsch: m for m in session.scalars(select(PaymentMethod).where(
            PaymentMethod.mandt == mandt, PaymentMethod.land1 == cc.land1))
    }
    supported = {
        e.zlsch: e for e in session.scalars(select(CompanyCodePaymentMethod).where(
            CompanyCodePaymentMethod.mandt == mandt, CompanyCodePaymentMethod.zbukr == zbukr))
        if e.zlsch in zwels and e.zlsch in methods
    }
    ranges = {"K": (lifnr_low, lifnr_high), "D": (kunnr_low, kunnr_high)}

    for koart, cfg in _PARTNER.items():
        allowed = {z: e for z, e in supported.items() if methods[z].xeinz == cfg["incoming"]}
        if not allowed:
            continue  # the run has no method for this direction
        stmt = (
            select(AccountingDocumentItem)
            .join(AccountingDocumentItem.header)
            .where(
                AccountingDocumentItem.mandt == mandt,
                AccountingDocumentItem.bukrs == zbukr,
                AccountingDocumentItem.koart == koart,
                AccountingDocumentItem.augbl.is_(None),
                AccountingDocumentHeader.cpudt <= run.cpudt,
            )
            .order_by(cfg["col"], AccountingDocumentItem.gjahr,
                      AccountingDocumentItem.belnr, AccountingDocumentItem.buzei)
        )
        low, high = ranges[koart]
        if low:
            stmt = stmt.where(cfg["col"] >= low)
        if high:
            stmt = stmt.where(cfg["col"] <= high)

        by_partner: dict[str, list[AccountingDocumentItem]] = defaultdict(list)
        for it in session.scalars(stmt):
            by_partner[it.lifnr if koart == "K" else it.kunnr].append(it)
        for partner, items in by_partner.items():
            due = [it for it in items if it.shkzg != cfg["inv_side"] or _due(it, zaldt, nedat)]
            if any(it.shkzg == cfg["inv_side"] for it in due):
                _propose_partner(session, run, cc, koart, partner, due, allowed, methods)

    session.commit()
    session.refresh(run)
    return run


def _due(it: AccountingDocumentItem, zaldt: date, nedat: date) -> bool:
    """Settle now if overdue by the next run, or if waiting would lose cash discount."""
    if payment_terms.net_due_date(it) < nedat:
        return True
    return payment_terms.cash_discount(it, zaldt)[0] > payment_terms.cash_discount(it, nedat)[0]


def _propose_partner(session, run, cc, koart, partner, items, allowed, methods) -> None:
    mandt, inv_side = run.mandt, _PARTNER[koart]["inv_side"]
    if koart == "K":
        name = session.get(Vendor, (mandt, partner))
        master = session.get(VendorCompanyCode, (mandt, partner, run.zbukr))
    else:
        name = session.get(Customer, (mandt, partner))
        master = session.get(CustomerCompanyCode, (mandt, partner, run.zbukr))
    partner_methods = [m for m in (master.zwels if master and master.zwels else "") if m in allowed]

    groups: dict[str, list[AccountingDocumentItem]] = defaultdict(list)
    excluded: list[tuple[AccountingDocumentItem, str]] = []
    for it in items:
        if master and master.zahls:
            excluded.append((it, f"partner blocked for payment ({master.zahls})"))
        elif it.zlspr:
            excluded.append((it, f"payment block {it.zlspr}"))
        elif it.header.waers != cc.waers:
            excluded.append((it, f"currency {it.header.waers} not supported"))
        elif it.zlsch:
            if it.zlsch in allowed:
                groups[it.zlsch].append(it)
            else:
                excluded.append((it, f"payment method {it.zlsch} not allowed in this run"))
        elif partner_methods:
            groups[partner_methods[0]].append(it)
        else:
            excluded.append((it, "no valid payment method"))

    def signed(it):
        return it.wrbtr if it.shkzg == inv_side else -it.wrbtr

    for zlsch, its in groups.items():
        payee = _payee(run, cc, koart, partner, zlsch, name)
        for it in its:
            disc = payment_terms.cash_discount(it, run.zaldt)[1] if it.shkzg == inv_side else Decimal("0")
            payee.items.append(_regup(payee, it, signed(it), disc))
            payee.rwbtr += signed(it)
            payee.rskon += disc
        payee.rwbtr -= payee.rskon
        payee.exception = _check_group(session, payee, koart, allowed[zlsch], methods.get(zlsch))
        run.payees.append(payee)

    if excluded:
        payee = _payee(run, cc, koart, partner, "", name)
        for it, _ in excluded:
            payee.items.append(_regup(payee, it, signed(it), Decimal("0")))
            payee.rwbtr += signed(it)
        payee.exception = ("Not paid: " + "; ".join(sorted({why for _, why in excluded})))[:120]
        run.payees.append(payee)


def _payee(run, cc, koart, partner, zlsch, name) -> PaymentRunPayee:
    return PaymentRunPayee(
        mandt=run.mandt, laufd=run.laufd, laufi=run.laufi, zbukr=run.zbukr,
        lifnr=partner if koart == "K" else "", kunnr=partner if koart == "D" else "",
        zlsch=zlsch, name1=name.name1 if name else None, waers=cc.waers, zaldt=run.zaldt,
        rwbtr=Decimal("0"), rskon=Decimal("0"),
    )


def _regup(payee, it, signed, disc) -> PaymentRunItem:
    return PaymentRunItem(
        mandt=payee.mandt, laufd=payee.laufd, laufi=payee.laufi, zbukr=payee.zbukr,
        lifnr=payee.lifnr, kunnr=payee.kunnr, zlsch=payee.zlsch, bukrs=it.bukrs, belnr=it.belnr,
        gjahr=it.gjahr, buzei=it.buzei, shkzg=it.shkzg, wrbtr=signed, wskto=disc,
        faedt=payment_terms.net_due_date(it), zlspr=it.zlspr, xblnr=it.header.xblnr, sgtxt=it.sgtxt,
    )


def _check_group(session, payee, koart, t042e, t042z) -> str | None:
    """Fill partner bank / mandate and house bank data; return an exception reason or None."""
    mandt = payee.mandt
    if payee.rwbtr <= 0:
        return f"Net credit balance {payee.rwbtr} {payee.waers}: no payment"

    bank_model = VendorBankDetails if koart == "K" else CustomerBankDetails
    partner_col = VendorBankDetails.lifnr if koart == "K" else CustomerBankDetails.kunnr
    bank = session.scalars(select(bank_model).where(
        bank_model.mandt == mandt, partner_col == (payee.lifnr or payee.kunnr))).first()
    if bank is not None:
        bnka = session.get(Bank, (mandt, bank.banks, bank.bankl))
        payee.zbnks, payee.zbnkl, payee.zbnkn, payee.ziban = bank.banks, bank.bankl, bank.bankn, bank.iban
        payee.zswif = bnka.swift if bnka else None

    if koart == "D" and t042z is not None and t042z.xeinz:
        mandate = _active_mandate(session, mandt, payee.zbukr, payee.kunnr, payee.zaldt)
        if mandate is None:
            return f"No active SEPA mandate for customer {payee.kunnr}"
        payee.mndid, payee.ziban, payee.zswif = mandate.mndid, mandate.snd_iban, mandate.snd_bic or payee.zswif
    elif t042z is not None and t042z.xbkkt and (bank is None or not bank.iban):
        return f"No bank details with IBAN for payment method {payee.zlsch}"

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


def _active_mandate(session, mandt, bukrs, kunnr, on_date) -> SepaMandate | None:
    return session.scalars(select(SepaMandate).where(
        SepaMandate.mandt == mandt, SepaMandate.snd_id == kunnr, SepaMandate.rec_id == bukrs,
        SepaMandate.status == "1", SepaMandate.sign_date <= on_date,
    ).order_by(SepaMandate.sign_date.desc())).first()


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
            mandt=mandt, bukrs=run.zbukr, koart="D" if payee.kunnr else "K",
            account=payee.kunnr or payee.lifnr, budat=run.zaldt, amount=payee.rwbtr, hkont=payee.ukont,
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


# --- payment media ------------------------------------------------------------

def _sub(parent, tag, text=None, **attrs):
    node = ET.SubElement(parent, tag, attrs)
    if text is not None:
        node.text = str(text)
    return node


def _remittance(p: PaymentRunPayee) -> str:
    refs = ", ".join(i.xblnr or i.belnr for i in p.items if i.wrbtr > 0)
    return f"Invoices {refs}"[:140]


def _executed(session, mandt, laufd, laufi, koart):
    run = get_run(session, mandt, laufd, laufi)
    paid = [p for p in run.payees if p.vblnr and bool(p.kunnr) == (koart == "D")]
    if not paid:
        kind = "direct debits" if koart == "D" else "outgoing payments"
        raise PostingError(f"The payment run has no executed {kind}")
    return run, paid, company_code(session, mandt, run.zbukr)


def _group_header(init, msg_id, paid, initiator):
    hdr = _sub(init, "GrpHdr")
    _sub(hdr, "MsgId", msg_id)
    _sub(hdr, "CreDtTm", datetime.utcnow().replace(microsecond=0).isoformat())
    _sub(hdr, "NbOfTxs", len(paid))
    _sub(hdr, "CtrlSum", f"{sum(p.rwbtr for p in paid):.2f}")
    _sub(_sub(hdr, "InitgPty"), "Nm", initiator)


def sepa_credit_transfer(session: Session, mandt: str, laufd: date, laufi: str) -> bytes:
    """Payment medium for vendor payments: SEPA credit transfer (pain.001.001.03)."""
    run, paid, cc = _executed(session, mandt, laufd, laufi, "K")
    msg_id = f"F110-{run.laufd:%Y%m%d}-{run.laufi}"
    root = ET.Element("Document", xmlns=_PAIN001)
    init = _sub(root, "CstmrCdtTrfInitn")
    _group_header(init, msg_id, paid, cc.butxt)

    by_account: dict[tuple[str, str], list[PaymentRunPayee]] = defaultdict(list)
    for p in paid:
        by_account[(p.hbkid, p.hktid)].append(p)
    for (hbkid, hktid), payees in by_account.items():
        house_bank = session.get(HouseBank, (mandt, run.zbukr, hbkid))
        inf = _sub(init, "PmtInf")
        _sub(inf, "PmtInfId", f"{msg_id}-{hbkid}{hktid}")
        _sub(inf, "PmtMtd", "TRF")
        _sub(inf, "NbOfTxs", len(payees))
        _sub(inf, "CtrlSum", f"{sum(p.rwbtr for p in payees):.2f}")
        _sub(_sub(_sub(inf, "PmtTpInf"), "SvcLvl"), "Cd", "SEPA")
        _sub(inf, "ReqdExctnDt", run.zaldt.isoformat())
        _sub(_sub(inf, "Dbtr"), "Nm", cc.butxt)
        _sub(_sub(_sub(inf, "DbtrAcct"), "Id"), "IBAN", payees[0].ubiban or "")
        agent = _sub(_sub(inf, "DbtrAgt"), "FinInstnId")
        if house_bank and house_bank.swift:
            _sub(agent, "BIC", house_bank.swift)
        _sub(inf, "ChrgBr", "SLEV")
        for p in payees:
            tx = _sub(inf, "CdtTrfTxInf")
            _sub(_sub(tx, "PmtId"), "EndToEndId", f"{p.vblnr}{p.gjahr}")
            _sub(_sub(tx, "Amt"), "InstdAmt", f"{p.rwbtr:.2f}", Ccy=p.waers)
            if p.zswif:
                _sub(_sub(_sub(tx, "CdtrAgt"), "FinInstnId"), "BIC", p.zswif)
            _sub(_sub(tx, "Cdtr"), "Nm", p.name1 or p.lifnr)
            _sub(_sub(_sub(tx, "CdtrAcct"), "Id"), "IBAN", p.ziban or "")
            _sub(_sub(tx, "RmtInf"), "Ustrd", _remittance(p))

    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def sepa_direct_debit(session: Session, mandt: str, laufd: date, laufi: str) -> bytes:
    """Payment medium for customer collections: SEPA core direct debit (pain.008.001.02)."""
    run, paid, cc = _executed(session, mandt, laufd, laufi, "D")
    msg_id = f"F110-{run.laufd:%Y%m%d}-{run.laufi}-DD"
    mandates = {p.mndid: session.get(SepaMandate, (mandt, p.mndid)) for p in paid}
    root = ET.Element("Document", xmlns=_PAIN008)
    init = _sub(root, "CstmrDrctDbtInitn")
    _group_header(init, msg_id, paid, cc.butxt)

    by_key: dict[tuple[str, str, str], list[PaymentRunPayee]] = defaultdict(list)
    for p in paid:
        by_key[(p.hbkid, p.hktid, mandates[p.mndid].pay_type)].append(p)
    for (hbkid, hktid, seq), payees in by_key.items():
        house_bank = session.get(HouseBank, (mandt, run.zbukr, hbkid))
        inf = _sub(init, "PmtInf")
        _sub(inf, "PmtInfId", f"{msg_id}-{hbkid}{hktid}-{seq}")
        _sub(inf, "PmtMtd", "DD")
        _sub(inf, "NbOfTxs", len(payees))
        _sub(inf, "CtrlSum", f"{sum(p.rwbtr for p in payees):.2f}")
        tp = _sub(inf, "PmtTpInf")
        _sub(_sub(tp, "SvcLvl"), "Cd", "SEPA")
        _sub(_sub(tp, "LclInstrm"), "Cd", "CORE")
        _sub(tp, "SeqTp", seq)
        _sub(inf, "ReqdColltnDt", run.zaldt.isoformat())
        _sub(_sub(inf, "Cdtr"), "Nm", cc.butxt)
        _sub(_sub(_sub(inf, "CdtrAcct"), "Id"), "IBAN", payees[0].ubiban or "")
        agent = _sub(_sub(inf, "CdtrAgt"), "FinInstnId")
        if house_bank and house_bank.swift:
            _sub(agent, "BIC", house_bank.swift)
        _sub(inf, "ChrgBr", "SLEV")
        scheme = _sub(_sub(_sub(inf, "CdtrSchmeId"), "Id"), "PrvtId")
        other = _sub(scheme, "Othr")
        _sub(other, "Id", mandates[payees[0].mndid].rec_crdid)
        _sub(_sub(other, "SchmeNm"), "Prtry", "SEPA")
        for p in payees:
            m = mandates[p.mndid]
            tx = _sub(inf, "DrctDbtTxInf")
            _sub(_sub(tx, "PmtId"), "EndToEndId", f"{p.vblnr}{p.gjahr}")
            _sub(tx, "InstdAmt", f"{p.rwbtr:.2f}", Ccy=p.waers)
            mri = _sub(_sub(tx, "DrctDbtTx"), "MndtRltdInf")
            _sub(mri, "MndtId", m.mndid)
            _sub(mri, "DtOfSgntr", m.sign_date.isoformat())
            if p.zswif:
                _sub(_sub(_sub(tx, "DbtrAgt"), "FinInstnId"), "BIC", p.zswif)
            _sub(_sub(tx, "Dbtr"), "Nm", p.name1 or p.kunnr)
            _sub(_sub(_sub(tx, "DbtrAcct"), "Id"), "IBAN", p.ziban or "")
            _sub(_sub(tx, "RmtInf"), "Ustrd", _remittance(p))

    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def run_summary(run: PaymentRunControl, *, with_items: bool = True) -> dict:
    payable = [p for p in run.payees if not p.exception]
    executed = [p for p in run.payees if p.vblnr]
    out = {
        "laufd": run.laufd, "laufi": run.laufi, "zbukr": run.zbukr, "zwels": run.zwels,
        "zaldt": run.zaldt, "nedat": run.nedat, "cpudt": run.cpudt,
        "lifnr_low": run.lifnr_low, "lifnr_high": run.lifnr_high,
        "kunnr_low": run.kunnr_low, "kunnr_high": run.kunnr_high,
        "xvore": run.xvore, "xecht": run.xecht,
        "status": "Payment run executed" if run.xecht else ("Proposal created" if run.xvore else "Parameters entered"),
        "payments": len(payable), "exceptions": len(run.payees) - len(payable),
        "total": sum((p.rwbtr for p in payable), Decimal("0")),
        "discount": sum((p.rskon for p in payable), Decimal("0")),
        "has_transfers": any(p.lifnr for p in executed),
        "has_direct_debits": any(p.kunnr for p in executed),
    }
    if with_items:
        out["payees"] = [{
            "koart": "D" if p.kunnr else "K", "partner": p.kunnr or p.lifnr,
            "lifnr": p.lifnr, "kunnr": p.kunnr, "name1": p.name1, "zlsch": p.zlsch, "waers": p.waers,
            "rwbtr": p.rwbtr, "rskon": p.rskon, "hbkid": p.hbkid, "hktid": p.hktid,
            "ziban": p.ziban, "mndid": p.mndid, "vblnr": p.vblnr, "gjahr": p.gjahr,
            "exception": p.exception,
            "items": [{
                "belnr": i.belnr, "gjahr": i.gjahr, "buzei": i.buzei, "shkzg": i.shkzg,
                "wrbtr": i.wrbtr, "wskto": i.wskto, "faedt": i.faedt, "zlspr": i.zlspr,
                "xblnr": i.xblnr, "sgtxt": i.sgtxt,
            } for i in p.items],
        } for p in run.payees]
    return out
