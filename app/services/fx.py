"""Exchange rates (TCURR) and foreign currency valuation of open items (FAGL_FCV).

``rate`` returns the local-currency value of one unit of a currency on a date:
the newest TCURR entry of the rate type valid on that date, or the inverse of
the reverse entry. TCURR keeps GDATU as a plain date here (SAP stores it
inverted, 99999999 - date).

``valuate`` revalues every open item in foreign currency (customers, vendors
and open-item G/L accounts) at the key-date rate. The difference to the
item's local amount is posted per open item / reconciliation account against
the T030H balance sheet adjustment account (LKORR) with valuation gain
(LHBEW) or loss (LSBEW), and reversed on the next day, so each valuation
starts again from the historical local amounts.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.documents import AccountingDocumentHeader, AccountingDocumentItem
from app.models.organizational import ExchangeRate
from app.models.payments import ExchangeDifferenceAccounts
from app.services.fiscal import PostingError, company_code

_CENT = Decimal("0.01")
_RATE = Decimal("0.00001")


def rate(session: Session, mandt: str, fcurr: str, tcurr: str, on: date, kurst: str = "M") -> Decimal:
    """Value of 1 ``fcurr`` in ``tcurr`` on a date (TCURR, rate type M by default)."""
    if fcurr == tcurr:
        return Decimal("1")
    direct = _latest(session, mandt, kurst, fcurr, tcurr, on)
    if direct is not None:
        return (direct.ukurs * direct.tfact / direct.ffact).quantize(_RATE, ROUND_HALF_UP)
    inverse = _latest(session, mandt, kurst, tcurr, fcurr, on)
    if inverse is not None and inverse.ukurs:
        return (inverse.ffact / (inverse.ukurs * inverse.tfact)).quantize(_RATE, ROUND_HALF_UP)
    raise PostingError(f"No exchange rate {kurst} {fcurr}/{tcurr} valid on {on.isoformat()} (TCURR)")


def _latest(session, mandt, kurst, fcurr, tcurr, on) -> ExchangeRate | None:
    return session.scalars(select(ExchangeRate).where(
        ExchangeRate.mandt == mandt, ExchangeRate.kurst == kurst, ExchangeRate.fcurr == fcurr,
        ExchangeRate.tcurr == tcurr, ExchangeRate.gdatu <= on,
    ).order_by(ExchangeRate.gdatu.desc())).first()


def difference_accounts(session: Session, mandt: str, ktopl: str, hkont: str) -> ExchangeDifferenceAccounts:
    row = session.get(ExchangeDifferenceAccounts, (mandt, ktopl, hkont))
    if row is None:
        raise PostingError(f"No exchange rate difference accounts (T030H) for account {hkont} in {ktopl}")
    return row


def valuate(session: Session, mandt: str, bukrs: str, key_date: date, *, post: bool = False,
            usnam: str = "SYSTEM") -> dict:
    """Value foreign-currency open items at ``key_date``; optionally post and reverse the result."""
    from app.services.posting import DocumentRequest, LineRequest, post_document
    from app.services.reversal import reverse_document

    cc = company_code(session, mandt, bukrs)
    marker = f"FCV{key_date:%Y%m%d}"
    if post and session.scalars(select(AccountingDocumentHeader).where(
            AccountingDocumentHeader.mandt == mandt, AccountingDocumentHeader.bukrs == bukrs,
            AccountingDocumentHeader.xblnr == marker, AccountingDocumentHeader.tcode == "FAGL_FCV")).first():
        raise PostingError(f"Open items were already valuated on {key_date.isoformat()} (document reference {marker})")

    items = session.scalars(
        select(AccountingDocumentItem).join(AccountingDocumentItem.header).where(
            AccountingDocumentItem.mandt == mandt, AccountingDocumentItem.bukrs == bukrs,
            AccountingDocumentItem.xopvw.is_(True),
            AccountingDocumentHeader.waers != cc.waers,
            AccountingDocumentHeader.budat <= key_date,
            or_(AccountingDocumentItem.augbl.is_(None), AccountingDocumentItem.augdt > key_date),
        ).order_by(AccountingDocumentItem.hkont, AccountingDocumentItem.gjahr, AccountingDocumentItem.belnr)
    ).all()

    lines, per_account = [], defaultdict(lambda: Decimal("0"))
    rates: dict[str, Decimal] = {}
    for it in items:
        waers = it.header.waers
        if waers not in rates:
            rates[waers] = rate(session, mandt, waers, cc.waers, key_date)
        sign = 1 if it.shkzg == "S" else -1
        before = sign * it.dmbtr
        after = sign * (it.wrbtr * rates[waers]).quantize(_CENT, ROUND_HALF_UP)
        diff = after - before
        per_account[it.hkont] += diff
        lines.append({
            "belnr": it.belnr, "gjahr": it.gjahr, "buzei": it.buzei, "koart": it.koart,
            "account": it.kunnr or it.lifnr or it.hkont, "hkont": it.hkont, "waers": waers,
            "wrbtr": sign * it.wrbtr, "rate_hist": (it.dmbtr / it.wrbtr).quantize(_RATE, ROUND_HALF_UP) if it.wrbtr else None,
            "rate_key": rates[waers], "local_before": before, "local_after": after, "difference": diff,
        })

    postings = []
    for hkont, diff in sorted(per_account.items()):
        if not diff:
            continue
        acc = difference_accounts(session, mandt, cc.ktopl, hkont)
        if diff > 0:  # receivable worth more / payable worth less: debit adjustment, credit gain
            debit, credit = acc.lkorr, acc.lhbew
        else:
            debit, credit = acc.lsbew, acc.lkorr
        postings.append({"hkont": hkont, "difference": diff, "debit": debit, "credit": credit})

    result = {"bukrs": bukrs, "key_date": key_date, "waers": cc.waers, "rates": rates,
              "items": lines, "postings": postings, "total": sum(per_account.values(), Decimal("0")),
              "document": None, "reversal": None}
    if post and postings:
        doc = post_document(session, DocumentRequest(
            mandt=mandt, bukrs=bukrs, blart="SA", bldat=key_date, budat=key_date, waers=cc.waers,
            xblnr=marker, bktxt=f"FX valuation {key_date.isoformat()}", usnam=usnam, tcode="FAGL_FCV",
            lines=[ln for p in postings for ln in (
                LineRequest(bschl="40", account=p["debit"], wrbtr=abs(p["difference"]), sgtxt=f"FX valuation {p['hkont']}"),
                LineRequest(bschl="50", account=p["credit"], wrbtr=abs(p["difference"]), sgtxt=f"FX valuation {p['hkont']}"),
            )],
        ), commit=False)
        rev = reverse_document(session, mandt, bukrs, doc.belnr, doc.gjahr,
                               budat=key_date + timedelta(days=1), usnam=usnam, commit=False)
        session.commit()
        result["document"] = {"belnr": doc.belnr, "gjahr": doc.gjahr}
        result["reversal"] = {"belnr": rev.belnr, "gjahr": rev.gjahr, "budat": rev.budat}
    return result
