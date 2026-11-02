"""Exchange rate differences: revaluation of open foreign-currency items on a date.

Business partner open items (JDT1 partner lines with an open FC amount): the open FC amount at
the rate of the date against the open LC amount gives the unrealized difference. It is posted
on the control account against the unrealized exchange gain / loss accounts and reversed
automatically on the reversal date (normally the next day), so the partners' open items stay
at their historical LC value and the payment later realizes the whole difference.

G/L accounts kept in a foreign currency (OACT ActCurr): FC balance at the rate of the date
against the LC balance; the difference is posted permanently on the account against the
realized exchange gain / loss accounts.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import Account, AccountDetermination, ExchangeRateRun, ExchangeRateRunLine, JournalLine
from app.services import journal
from app.services.admin import B1Error, company, exchange_rate
from app.services.journal import JournalLineRequest, JournalRequest, money

ZERO = Decimal("0")


def _determination(session: Session, on: date) -> AccountDetermination:
    det = session.get(AccountDetermination, str(on.year))
    if det is None:
        raise B1Error(f"No G/L account determination for {on.year}")
    return det


def preview(session: Session, on: date, category: str, currencies: list[str] | None = None) -> list[dict]:
    """Lines of a run: business partner open items (B) or FC G/L accounts (G), with their difference."""
    main = company(session).main_curncy
    rates: dict[str, Decimal] = {}

    def rate(cur: str) -> Decimal:
        if cur not in rates:
            rates[cur] = exchange_rate(session, cur, on)
        return rates[cur]

    out = []
    if category == "B":
        lines = session.scalars(select(JournalLine).where(
            JournalLine.short_name != JournalLine.account, JournalLine.fc_currency.is_not(None),
            JournalLine.ref_date <= on, (JournalLine.bal_fc_deb != 0) | (JournalLine.bal_fc_cred != 0))
            .order_by(JournalLine.short_name, JournalLine.trans_id)).all()
        for l in lines:
            if l.fc_currency == main or (currencies and l.fc_currency not in currencies):
                continue
            open_fc = l.bal_fc_deb - l.bal_fc_cred
            open_lc = l.bal_due_deb - l.bal_due_cred
            new_lc = money(open_fc * rate(l.fc_currency))
            out.append({"short_name": l.short_name, "account": l.account, "trans_id": l.trans_id, "line_id": l.line_id,
                        "trans_type": l.trans_type, "base_ref": l.base_ref, "currency": l.fc_currency,
                        "open_fc": open_fc, "open_lc": open_lc, "rate": rate(l.fc_currency), "new_lc": new_lc,
                        "difference": new_lc - open_lc})
    elif category == "G":
        for acct in session.scalars(select(Account).where(Account.postable == "Y", Account.act_curr.not_in(["##", main]))
                                    .order_by(Account.acct_code)):
            if currencies and acct.act_curr not in currencies:
                continue
            fc, lc = session.execute(select(
                func.coalesce(func.sum(JournalLine.fc_debit - JournalLine.fc_credit), 0),
                func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
                JournalLine.account == acct.acct_code, JournalLine.ref_date <= on)).one()
            fc, lc = Decimal(fc), Decimal(lc)
            if not fc and not lc:
                continue
            new_lc = money(fc * rate(acct.act_curr))
            out.append({"short_name": acct.acct_code, "account": acct.acct_code, "trans_id": None, "line_id": None,
                        "trans_type": None, "base_ref": None, "currency": acct.act_curr, "open_fc": fc, "open_lc": lc,
                        "rate": rate(acct.act_curr), "new_lc": new_lc, "difference": new_lc - lc})
    else:
        raise B1Error("Category must be B (business partners) or G (G/L accounts in foreign currency)")
    return out


def run(session: Session, on: date, category: str, storno_date: date | None = None,
        currencies: list[str] | None = None) -> ExchangeRateRun:
    """Post the differences of a run; business partner runs are reversed on storno_date (default: next day)."""
    try:
        if category == "B":
            storno_date = storno_date or on + timedelta(days=1)
            if storno_date <= on:
                raise B1Error("The reversal date must be after the run date")
            if session.scalar(select(ExchangeRateRun).where(ExchangeRateRun.run_date == on,
                                                            ExchangeRateRun.category == "B")) is not None:
                raise B1Error(f"Business partner items were already revalued on {on.isoformat()}")
        else:
            storno_date = None
        det = _determination(session, on)
        lines = [x for x in preview(session, on, category, currencies) if x["difference"]]
        gain_acct, loss_acct = (det.unreal_gain, det.unreal_loss) if category == "B" else (det.exch_gain, det.exch_loss)
        per_account: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for x in lines:
            per_account[x["account"]] += x["difference"]
        gain = sum((d for d in per_account.values() if d > 0), ZERO)
        loss = -sum((d for d in per_account.values() if d < 0), ZERO)
        r = ExchangeRateRun(abs_entry=(session.scalar(select(func.max(ExchangeRateRun.abs_entry))) or 0) + 1,
                            run_date=on, category=category, storno_date=storno_date, total_gain=gain, total_loss=loss)
        for n, x in enumerate(lines):
            r.lines.append(ExchangeRateRunLine(line_num=n, **{k: x[k] for k in (
                "short_name", "account", "trans_id", "line_id", "currency", "open_fc", "open_lc", "rate", "new_lc",
                "difference")}))
        if per_account:
            je_lines = [JournalLineRequest(account=acct, debit=d if d > 0 else ZERO, credit=-d if d < 0 else ZERO,
                                           line_memo="Exchange rate difference")
                        for acct, d in sorted(per_account.items()) if d]
            if gain:
                je_lines.append(JournalLineRequest(account=gain_acct, credit=gain, line_memo="Exchange rate gain"))
            if loss:
                je_lines.append(JournalLineRequest(account=loss_acct, debit=loss, line_memo="Exchange rate loss"))
            je = journal.post_entry(session, JournalRequest(
                ref_date=on, memo=f"Exchange rate differences {'BP' if category == 'B' else 'G/L'} {on.isoformat()}"[:50],
                ref1=f"ERD {on.isoformat()}", trans_type="30", manual=False, lines=je_lines,
                auto_storno=storno_date is not None, storno_date=storno_date), commit=False)
            r.trans_id = je.trans_id
        session.add(r)
        session.commit()
        return r
    except Exception:
        session.rollback()
        raise
