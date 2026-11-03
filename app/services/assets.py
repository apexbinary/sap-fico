"""Fixed assets: classes, capitalization, monthly depreciation runs, retirement, asset register.

Capitalization: asset account debited against an offset account (vendor clearing, bank, ...).
Depreciation per month from the capitalization month: straight line (cost - salvage) / useful life,
the last month takes the rest; written-down value book value x rate / 12 (Companies Act WDV). A run
posts one journal entry per month for all assets (expense against accumulated depreciation) and
can be reversed (the latest month first). Retirement on a date: depreciation up to the previous
month must be run; cost and accumulated depreciation leave, proceeds go to the offset account,
the difference is the gain / loss on the class's retirement account.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import AssetClass, AssetTransaction, FixedAsset
from app.models.finance import Account
from app.services import journal
from app.services.admin import B1Error

ZERO = Decimal("0")
CENT = Decimal("0.01")


def _month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _next_month_end(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, calendar.monthrange(y, m)[1])


def _account(session: Session, code: str | None, what: str) -> str:
    a = session.get(Account, code) if code else None
    if a is None or a.postable != "Y":
        raise B1Error(f"{what}: account {code} does not exist or is a title account")
    return code


def save_class(session: Session, data: dict, code: str | None = None) -> AssetClass:
    if code is None:
        code = (data.get("code") or "").strip().upper()
        if not re.match(r"^[A-Z0-9_-]{1,8}$", code):
            raise B1Error("An asset class code has 1-8 letters, digits, '_' or '-'")
        if session.get(AssetClass, code) is not None:
            raise B1Error(f"Asset class {code} already exists")
        c = AssetClass(code=code)
        session.add(c)
    else:
        c = session.get(AssetClass, code)
        if c is None:
            raise B1Error(f"Asset class {code} does not exist")
    for key, what in (("asset_acct", "Asset account"), ("acc_dep_acct", "Accumulated depreciation"), ("dep_acct", "Depreciation expense"),
                      ("retire_acct", "Retirement gain / loss")):
        if key in data:
            setattr(c, key, _account(session, data[key], what))
    if data.get("name"):
        c.name = data["name"].strip()[:50]
    if data.get("method"):
        if data["method"] not in {"SL", "WD"}:
            raise B1Error("Method: SL straight line or WD written-down value")
        c.method = data["method"]
    if "useful_life" in data:
        c.useful_life = int(data["useful_life"]) if data["useful_life"] else None
    if "wdv_rate" in data:
        c.wdv_rate = Decimal(str(data["wdv_rate"])) if data["wdv_rate"] else None
    if not all([c.name, c.asset_acct, c.acc_dep_acct, c.dep_acct, c.retire_acct]):
        raise B1Error("Enter the name and all accounts of the class")
    if (c.method or "SL") == "SL" and not (c.useful_life and c.useful_life > 0):
        raise B1Error("Straight line needs the useful life in months")
    if c.method == "WD" and not (c.wdv_rate and 0 < c.wdv_rate < 100):
        raise B1Error("Written-down value needs a rate between 0 and 100 %")
    c.method = c.method or "SL"
    session.commit()
    return c


def save_asset(session: Session, data: dict, code: str | None = None) -> FixedAsset:
    if code is None:
        code = (data.get("asset_code") or "").strip().upper()
        if not re.match(r"^[A-Z0-9_./-]{1,20}$", code):
            raise B1Error("An asset code has 1-20 letters, digits or . _ / -")
        if session.get(FixedAsset, code) is not None:
            raise B1Error(f"Asset {code} already exists")
        a = FixedAsset(asset_code=code, status="N", cost=ZERO, acc_dep=ZERO, salvage=ZERO)
        session.add(a)
    else:
        a = session.get(FixedAsset, code)
        if a is None:
            raise B1Error(f"Asset {code} does not exist")
    if data.get("class_code"):
        if a.status != "N" and data["class_code"] != a.class_code:
            raise B1Error("The class of a capitalized asset cannot change")
        if session.get(AssetClass, data["class_code"]) is None:
            raise B1Error(f"Asset class {data['class_code']} does not exist")
        a.class_code = data["class_code"]
    for key in ("name", "serial", "location"):
        if key in data and data[key] is not None:
            setattr(a, key, data[key].strip() or None)
    if "salvage" in data and data["salvage"] is not None:
        if a.status != "N":
            raise B1Error("The salvage value is set before capitalization")
        a.salvage = Decimal(str(data["salvage"]))
        if a.salvage < 0:
            raise B1Error("The salvage value cannot be negative")
    if not a.name or not a.class_code:
        raise B1Error("Enter the asset name and class")
    session.commit()
    return a


def _post(session: Session, on: date, memo: str, lines: list[tuple[str, Decimal]], ref3: str) -> int:
    reqs = [journal.JournalLineRequest(account=acct, debit=amt if amt > 0 else ZERO, credit=-amt if amt < 0 else ZERO)
            for acct, amt in lines if amt]
    je = journal.post_entry(session, journal.JournalRequest(ref_date=on, memo=memo[:50], ref3=ref3, manual=False, trans_type="30", lines=reqs),
                            commit=False)
    return je.trans_id


def capitalize(session: Session, code: str, on: date, amount: Decimal, offset_acct: str) -> FixedAsset:
    a = session.get(FixedAsset, code)
    if a is None:
        raise B1Error(f"Asset {code} does not exist")
    if a.status == "R":
        raise B1Error(f"Asset {code} is retired")
    amount = Decimal(str(amount)).quantize(CENT)
    if amount <= 0:
        raise B1Error("The capitalization amount must be positive")
    if a.dep_until is not None:
        raise B1Error("Depreciation was already posted: capitalize further values on a new asset")
    c = session.get(AssetClass, a.class_code)
    _account(session, offset_acct, "Offset account")
    try:
        tid = _post(session, on, f"Capitalization {a.asset_code}", [(c.asset_acct, amount), (offset_acct, -amount)], f"FA:{a.asset_code}")
        a.cost += amount
        a.cap_date = a.cap_date or on
        a.status = "A"
        if a.salvage > a.cost:
            raise B1Error("The salvage value exceeds the cost")
        a.transactions.append(AssetTransaction(line_id=len(a.transactions), tran_type="C", doc_date=on, amount=amount, trans_id=tid,
                                               reversed="N", memo=f"Offset {offset_acct}"))
        session.commit()
        return a
    except Exception:
        session.rollback()
        raise


def _monthly(a: FixedAsset, c: AssetClass, month_end: date) -> Decimal:
    book = a.cost - a.acc_dep
    if book <= a.salvage:
        return ZERO
    if c.method == "WD":
        return min((book * c.wdv_rate / 100 / 12).quantize(CENT), book - a.salvage)
    start = a.cap_date
    months_done = (month_end.year - start.year) * 12 + month_end.month - start.month  # months before this one
    if months_done >= c.useful_life - 1:
        return book - a.salvage  # the last month takes the rest
    return min(((a.cost - a.salvage) / c.useful_life).quantize(CENT), book - a.salvage)


def depreciation_preview(session: Session, month: date) -> list[dict]:
    """Depreciation of a month (all active assets depreciated up to the month before)."""
    me = _month_end(month)
    out = []
    for a in session.scalars(select(FixedAsset).where(FixedAsset.status == "A").order_by(FixedAsset.asset_code)):
        if a.cap_date > me:
            continue
        due_from = _month_end(a.cap_date) if a.dep_until is None else _next_month_end(a.dep_until)
        if due_from > me:
            continue
        if due_from < me:
            raise B1Error(f"Asset {a.asset_code}: depreciation of {due_from:%Y-%m} is not posted yet; run the months in order")
        c = session.get(AssetClass, a.class_code)
        amt = _monthly(a, c, me)
        if amt:
            out.append({"asset_code": a.asset_code, "name": a.name, "class_code": a.class_code, "method": c.method, "amount": amt,
                        "book_before": a.cost - a.acc_dep, "book_after": a.cost - a.acc_dep - amt})
    return out


def run_depreciation(session: Session, month: date) -> int | None:
    """Post the depreciation of a month for all assets (one journal entry); returns its TransId."""
    me = _month_end(month)
    rows = depreciation_preview(session, month)
    if not rows:
        return None
    try:
        by_acct: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for r in rows:
            c = session.get(AssetClass, r["class_code"])
            by_acct[c.dep_acct] += r["amount"]
            by_acct[c.acc_dep_acct] -= r["amount"]
        tid = _post(session, me, f"Depreciation {me:%Y-%m}", list(by_acct.items()), f"FAD:{me:%Y-%m}")
        for r in rows:
            a = session.get(FixedAsset, r["asset_code"])
            a.acc_dep += r["amount"]
            a.dep_until = me
            a.transactions.append(AssetTransaction(line_id=len(a.transactions), tran_type="D", doc_date=me, amount=r["amount"],
                                                   period=f"{me:%Y-%m}", trans_id=tid, reversed="N"))
        session.commit()
        return tid
    except Exception:
        session.rollback()
        raise


def reverse_depreciation(session: Session, month: date) -> None:
    """Reverse the depreciation run of a month (only the latest month of each asset)."""
    me = _month_end(month)
    rows = session.scalars(select(AssetTransaction).where(AssetTransaction.tran_type == "D", AssetTransaction.period == f"{me:%Y-%m}",
                                                          AssetTransaction.reversed == "N")).all()
    if not rows:
        raise B1Error(f"No depreciation posted for {me:%Y-%m}")
    try:
        for t in rows:
            a = session.get(FixedAsset, t.asset_code)
            if a.dep_until != me or a.status == "R":
                raise B1Error(f"Asset {a.asset_code}: later depreciation or a retirement exists; reverse those first")
        journal.reverse_entry(session, rows[0].trans_id, ref_date=me, commit=False)
        for t in rows:
            a = session.get(FixedAsset, t.asset_code)
            a.acc_dep -= t.amount
            prev = [x for x in a.transactions if x.tran_type == "D" and x.reversed == "N" and x is not t]
            a.dep_until = max((x.doc_date for x in prev), default=None)
            t.reversed = "Y"
        session.commit()
    except Exception:
        session.rollback()
        raise


def retire(session: Session, code: str, on: date, proceeds: Decimal, offset_acct: str) -> FixedAsset:
    a = session.get(FixedAsset, code)
    if a is None or a.status != "A":
        raise B1Error(f"Asset {code} is not an active asset")
    needed = _month_end(date(on.year - 1, 12, 1) if on.month == 1 else date(on.year, on.month - 1, 1))  # previous month end
    if a.cap_date <= needed and (a.dep_until is None or a.dep_until < needed):
        raise B1Error(f"Asset {code}: run the depreciation up to {needed:%Y-%m} before retiring it")
    proceeds = Decimal(str(proceeds or 0)).quantize(CENT)
    if proceeds < 0:
        raise B1Error("Proceeds cannot be negative")
    c = session.get(AssetClass, a.class_code)
    if proceeds:
        _account(session, offset_acct, "Proceeds account")
    book = a.cost - a.acc_dep
    gain = proceeds - book  # positive gain, negative loss
    try:
        lines = [(c.asset_acct, -a.cost), (c.acc_dep_acct, a.acc_dep), (c.retire_acct, -gain)]
        if proceeds:
            lines.append((offset_acct, proceeds))
        tid = _post(session, on, f"Retirement {a.asset_code}", lines, f"FA:{a.asset_code}")
        a.transactions.append(AssetTransaction(line_id=len(a.transactions), tran_type="R", doc_date=on, amount=proceeds, trans_id=tid,
                                               reversed="N", memo=f"Book value {book}, {'gain' if gain >= 0 else 'loss'} {abs(gain)}"))
        a.status, a.retire_date = "R", on
        session.commit()
        return a
    except Exception:
        session.rollback()
        raise


def out(a: FixedAsset) -> dict:
    return {"asset_code": a.asset_code, "name": a.name, "class_code": a.class_code, "serial": a.serial, "location": a.location,
            "cap_date": a.cap_date, "cost": a.cost, "salvage": a.salvage, "acc_dep": a.acc_dep, "book_value": a.cost - a.acc_dep,
            "dep_until": a.dep_until, "status": a.status, "retire_date": a.retire_date,
            "transactions": [{"tran_type": t.tran_type, "doc_date": t.doc_date, "amount": t.amount, "period": t.period, "trans_id": t.trans_id,
                              "reversed": t.reversed == "Y", "memo": t.memo} for t in a.transactions]}


def class_out(c: AssetClass) -> dict:
    return {"code": c.code, "name": c.name, "asset_acct": c.asset_acct, "acc_dep_acct": c.acc_dep_acct, "dep_acct": c.dep_acct,
            "retire_acct": c.retire_acct, "method": c.method, "useful_life": c.useful_life, "wdv_rate": c.wdv_rate}
