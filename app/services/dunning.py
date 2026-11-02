"""Dunning program (F150): proposal -> dunning run -> dunning notices.

For each customer with dunning data (KNB5) in the selection:

  * an open debit item is overdue when its days in arrears on the dunning
    date (dunning date - net due date) exceed the procedure's grace period;
  * its new dunning level is the highest level whose days in arrears it has
    reached (T047B), but at most one level above its previous level
    (BSEG-MANST), and never lower;
  * open credit items (payments on account, credit memos) are listed and
    offset against the overdue total;
  * a notice is issued when an item's level rises (or the level is flagged
    "always dun"), the dunning interval since the last notice (KNB5-MADAT +
    T047A-RHYTM) has passed, the account has no dunning block and the
    overdue total reaches the procedure minimum; otherwise the account is
    listed with the reason;
  * the charge of the notice's level comes from T047C.

The dunning run writes the new levels: BSEG-MANST/MADAT per item and
KNB5-MAHNS/MADAT per account. Notices are rendered as printable HTML.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bank import HouseBankAccount
from app.models.documents import AccountingDocumentItem
from app.models.dunning import (
    DunningAccount,
    DunningCharge,
    DunningItem,
    DunningLevel,
    DunningProcedure,
    DunningRunControl,
)
from app.models.partners import Customer, CustomerDunningData
from app.services import payment_terms
from app.services.fiscal import PostingError, company_code

ZERO = Decimal("0")


def get_run(session: Session, mandt: str, laufd: date, laufi: str) -> DunningRunControl:
    run = session.get(DunningRunControl, (mandt, laufd, laufi))
    if run is None:
        raise PostingError(f"Dunning run {laufd.isoformat()}/{laufi} does not exist")
    return run


def create_proposal(
    session: Session, mandt: str, *, laufd: date, laufi: str, ausdt: date, bukrs: str,
    kunnr_low: str | None = None, kunnr_high: str | None = None, usnam: str = "SYSTEM",
) -> DunningRunControl:
    existing = session.get(DunningRunControl, (mandt, laufd, laufi))
    if existing is not None:
        if existing.xecht:
            raise PostingError(f"Dunning run {laufd.isoformat()}/{laufi} was already executed")
        session.delete(existing)
        session.flush()

    cc = company_code(session, mandt, bukrs)
    run = DunningRunControl(mandt=mandt, laufd=laufd, laufi=laufi, ausdt=ausdt, bukrs=bukrs,
                            kunnr_low=kunnr_low, kunnr_high=kunnr_high, usnam=usnam,
                            xvore=True, vorer=datetime.utcnow())
    session.add(run)

    stmt = select(CustomerDunningData).where(
        CustomerDunningData.mandt == mandt, CustomerDunningData.bukrs == bukrs).order_by(CustomerDunningData.kunnr)
    if kunnr_low:
        stmt = stmt.where(CustomerDunningData.kunnr >= kunnr_low)
    if kunnr_high:
        stmt = stmt.where(CustomerDunningData.kunnr <= kunnr_high)
    for knb5 in session.scalars(stmt):
        account = _propose_account(session, run, cc, knb5)
        if account is not None:
            run.accounts.append(account)

    session.commit()
    session.refresh(run)
    return run


def _propose_account(session, run, cc, knb5: CustomerDunningData) -> DunningAccount | None:
    mandt = run.mandt
    proc = session.get(DunningProcedure, (mandt, knb5.mahna))
    if proc is None:
        raise PostingError(f"Dunning procedure {knb5.mahna} of customer {knb5.kunnr} is not defined")
    levels = session.scalars(select(DunningLevel).where(
        DunningLevel.mandt == mandt, DunningLevel.mahna == proc.mahna).order_by(DunningLevel.mahns)).all()
    items = session.scalars(select(AccountingDocumentItem).where(
        AccountingDocumentItem.mandt == mandt, AccountingDocumentItem.bukrs == run.bukrs,
        AccountingDocumentItem.koart == "D", AccountingDocumentItem.kunnr == knb5.kunnr,
        AccountingDocumentItem.xopvw.is_(True), AccountingDocumentItem.augbl.is_(None),
    ).order_by(AccountingDocumentItem.gjahr, AccountingDocumentItem.belnr, AccountingDocumentItem.buzei)).all()

    account = DunningAccount(
        mandt=mandt, laufd=run.laufd, laufi=run.laufi, koart="D", bukrs=run.bukrs, kunnr=knb5.kunnr,
        mahna=proc.mahna, mahnv=knb5.mahns or 0, waers=cc.waers, salhw=ZERO, mahng=ZERO, xmflg=True,
    )
    overdue = False
    for it in items:
        faedt = payment_terms.net_due_date(it)
        verzn = (run.ausdt - faedt).days
        old = it.manst or 0
        if it.shkzg == "S":
            if verzn <= proc.gracp:
                continue  # not overdue (yet)
            reached = max((lv.mahns for lv in levels if verzn >= lv.verzn), default=0)
            new = old if it.mansp else max(old, min(reached, old + 1, proc.mstuf))
            if new == 0:
                continue
            overdue = True
            amount = it.wrbtr
        else:
            new, amount = 0, -it.wrbtr  # open credit: offset
        account.items.append(DunningItem(
            mandt=mandt, laufd=run.laufd, laufi=run.laufi, koart="D", bukrs=run.bukrs, kunnr=knb5.kunnr,
            belnr=it.belnr, gjahr=it.gjahr, buzei=it.buzei, shkzg=it.shkzg, dmshb=amount, faedt=faedt,
            verzn=max(verzn, 0), mahnn=new, manst=old, mansp=it.mansp, xblnr=it.header.xblnr, sgtxt=it.sgtxt,
        ))
    if not overdue:
        return None

    dunned = [i for i in account.items if i.shkzg == "S" and not i.mansp]
    account.salhw = sum((i.dmshb for i in account.items if not i.mansp), ZERO)
    account.mahns = max((i.mahnn for i in dunned), default=0)
    level = next((lv for lv in levels if lv.mahns == account.mahns), None)
    charge = session.get(DunningCharge, (mandt, proc.mahna, account.mahns, cc.waers))
    account.mahng = charge.mahng if charge else ZERO

    next_allowed = knb5.madat + timedelta(days=proc.rhytm) if knb5.madat else None
    if knb5.mansp:
        account.reason = f"Dunning block {knb5.mansp} on the account"
    elif next_allowed and run.ausdt < next_allowed:
        account.reason = f"Dunned on {knb5.madat.isoformat()}; next notice from {next_allowed.isoformat()}"
    elif account.salhw < max(proc.minbt, Decimal("0.01")):
        account.reason = f"Overdue balance {account.salhw} below minimum {proc.minbt}"
    elif not any(i.mahnn > i.manst for i in dunned) and not (level and level.xalwy):
        account.reason = "No dunning level change"
    account.xmflg = account.reason is None
    return account


def delete_proposal(session: Session, mandt: str, laufd: date, laufi: str) -> None:
    run = get_run(session, mandt, laufd, laufi)
    if run.xecht:
        raise PostingError(f"Dunning run {laufd.isoformat()}/{laufi} was already executed")
    session.delete(run)
    session.commit()


def execute(session: Session, mandt: str, laufd: date, laufi: str) -> DunningRunControl:
    """Write the new dunning levels to the items (BSEG) and accounts (KNB5)."""
    run = get_run(session, mandt, laufd, laufi)
    if run.xecht:
        raise PostingError(f"Dunning run {laufd.isoformat()}/{laufi} was already executed")
    for account in run.accounts:
        if not account.xmflg:
            continue
        for di in account.items:
            if di.shkzg != "S" or di.mansp:
                continue
            it = session.get(AccountingDocumentItem, (mandt, di.bukrs, di.belnr, di.gjahr, di.buzei))
            if it is None or it.augbl:
                continue  # cleared since the proposal
            it.manst, it.madat = di.mahnn, run.ausdt
        knb5 = session.get(CustomerDunningData, (mandt, account.kunnr, account.bukrs, ""))
        knb5.mahns, knb5.madat = account.mahns, run.ausdt
    run.xecht, run.echer = True, datetime.utcnow()
    session.commit()
    session.refresh(run)
    return run


def run_summary(run: DunningRunControl, *, with_items: bool = True) -> dict:
    issued = [a for a in run.accounts if a.xmflg]
    out = {
        "laufd": run.laufd, "laufi": run.laufi, "ausdt": run.ausdt, "bukrs": run.bukrs,
        "kunnr_low": run.kunnr_low, "kunnr_high": run.kunnr_high, "xvore": run.xvore, "xecht": run.xecht,
        "status": "Dunning run executed" if run.xecht else "Proposal created",
        "notices": len(issued), "listed": len(run.accounts) - len(issued),
        "total": sum((a.salhw for a in issued), ZERO), "charges": sum((a.mahng for a in issued), ZERO),
    }
    if with_items:
        out["accounts"] = [{
            "kunnr": a.kunnr, "mahna": a.mahna, "mahns": a.mahns, "mahnv": a.mahnv, "waers": a.waers,
            "salhw": a.salhw, "mahng": a.mahng, "xmflg": a.xmflg, "reason": a.reason,
            "items": [{
                "belnr": i.belnr, "gjahr": i.gjahr, "buzei": i.buzei, "shkzg": i.shkzg, "dmshb": i.dmshb,
                "faedt": i.faedt, "verzn": i.verzn, "mahnn": i.mahnn, "manst": i.manst, "mansp": i.mansp,
                "xblnr": i.xblnr, "sgtxt": i.sgtxt,
            } for i in a.items],
        } for a in run.accounts]
    return out


_INTRO = {
    1: "Our records show that the following items are overdue. Perhaps this has escaped your notice.",
    2: "Despite our reminder, the following items are still unpaid.",
    3: "The following items remain unpaid despite repeated reminders. Please settle them immediately.",
    4: "Unless the following items are paid within seven days, we will hand the matter to our legal department.",
}


def notice_html(session: Session, mandt: str, laufd: date, laufi: str, kunnr: str) -> str:
    """Printable dunning notice for one customer of a run."""
    run = get_run(session, mandt, laufd, laufi)
    account = next((a for a in run.accounts if a.kunnr == kunnr.zfill(10)), None)
    if account is None or not account.xmflg:
        raise PostingError(f"Dunning run {laufd.isoformat()}/{laufi} issues no notice for customer {kunnr}")
    cc = company_code(session, mandt, run.bukrs)
    cust = session.get(Customer, (mandt, account.kunnr))
    level = session.get(DunningLevel, (mandt, account.mahna, account.mahns))
    bank = session.scalars(select(HouseBankAccount).where(
        HouseBankAccount.mandt == mandt, HouseBankAccount.bukrs == run.bukrs)).first()
    e = lambda v: escape(str(v)) if v is not None else ""  # noqa: E731
    money = lambda v: f"{v:,.2f}"  # noqa: E731
    rows = "".join(
        f"<tr><td>{e(i.xblnr or i.belnr)}</td><td>{e(i.belnr)}/{i.gjahr}</td><td>{e(i.faedt)}</td>"
        f"<td class='n'>{i.verzn if i.shkzg == 'S' else ''}</td><td class='n'>{i.mahnn or ''}</td>"
        f"<td class='n'>{money(i.dmshb)}</td></tr>"
        for i in account.items if not i.mansp)
    total = account.salhw + account.mahng
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(level.text1 if level else 'Dunning notice')} {e(account.kunnr)}</title>
<style>body{{font:14px/1.5 Georgia,serif;max-width:760px;margin:40px auto;color:#222;padding:0 16px}}
h1{{font-size:22px;margin:32px 0 8px}}table{{width:100%;border-collapse:collapse;margin:16px 0}}
th,td{{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left}}.n{{text-align:right}}
.meta{{display:flex;justify-content:space-between}}.foot{{margin-top:28px;color:#555;font-size:13px}}
@media print{{button{{display:none}}}}</style></head><body>
<button onclick="window.print()">Print</button>
<div class="meta"><div><strong>{e(cc.butxt)}</strong><br>{e(cc.ort01)}</div>
<div style="text-align:right">Date: {e(run.ausdt)}<br>Customer: {e(account.kunnr)}<br>Dunning level: {account.mahns}</div></div>
<p style="margin-top:28px">{e(cust.name1 if cust else account.kunnr)}<br>{e(cust.stras if cust else '')}<br>
{e(cust.pstlz if cust else '')} {e(cust.ort01 if cust else '')}</p>
<h1>{e(level.text1 if level else 'Dunning notice')}</h1>
<p>{e(_INTRO.get(account.mahns, _INTRO[4]))}</p>
<table><thead><tr><th>Reference</th><th>Document</th><th>Due date</th><th class="n">Days overdue</th>
<th class="n">Level</th><th class="n">Amount ({e(account.waers)})</th></tr></thead><tbody>{rows}</tbody>
<tfoot><tr><td colspan="5">Overdue balance</td><td class="n">{money(account.salhw)}</td></tr>
{f'<tr><td colspan="5">Dunning charge</td><td class="n">{money(account.mahng)}</td></tr>' if account.mahng else ''}
<tr><td colspan="5"><strong>Amount due</strong></td><td class="n"><strong>{money(total)}</strong></td></tr></tfoot></table>
<p>Please transfer the amount due{f' to IBAN {e(bank.iban)}' if bank and bank.iban else ''}, quoting customer number {e(account.kunnr)}.
If you have paid in the meantime, please disregard this notice.</p>
<p class="foot">{e(cc.butxt)} · Dunning procedure {e(account.mahna)} · Run {e(run.laufd)}/{e(run.laufi)}</p>
</body></html>"""
