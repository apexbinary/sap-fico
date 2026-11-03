"""End-to-end check for fixed assets.

A computer (straight line, 36 months) capitalized for 36,000 depreciates 1,000 a month from its
capitalization month; a furniture asset (WDV 25.89 %) 100,000 x 25.89 % / 12 = 2,157.50 in its first
month; months must be posted in order, a month can be reversed (latest first); retiring needs the
depreciation up to the previous month: sold for 30,000 at book value 33,000 the loss of 3,000 goes
to 724000, cost and accumulated depreciation leave the accounts; trial balance 0.

A depreciation run covers all assets, so the check starts after the latest month already posted
(rerunnable while the posting periods last).

Run after app.seed:  python -m app.verify_assets
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.assets import FixedAsset
from app.models.finance import Account, JournalLine
from app.services import assets
from app.services.admin import B1Error

D = Decimal


def _refused(fn, text: str, s) -> None:
    try:
        fn()
    except B1Error as exc:
        assert text in str(exc), exc
        s.rollback()
        return
    raise AssertionError(f"expected refusal: {text}")


def main() -> None:
    s = SessionLocal()
    try:
        n = s.scalar(select(func.count()).select_from(FixedAsset)) + 1
        pc, fu = f"PC-{n:04d}", f"FU-{n:04d}"
        assets.save_asset(s, {"asset_code": pc, "name": "Laptop", "class_code": "COMP", "serial": "SN-LT-1"})
        assets.save_asset(s, {"asset_code": fu, "name": "Office desks", "class_code": "FURN"})
        last = s.scalar(select(func.max(FixedAsset.dep_until)))
        m0 = date(2026, 1, 1) if last is None else (date(last.year + 1, 1, 1) if last.month == 12 else date(last.year, last.month + 1, 1))

        def mon(k: int) -> date:
            return date(m0.year + (m0.month - 1 + k) // 12, (m0.month - 1 + k) % 12 + 1, 1)

        assets.capitalize(s, pc, mon(0).replace(day=15), D(36000), "112000")
        assets.capitalize(s, fu, mon(0).replace(day=20), D(100000), "112000")
        first = {r["asset_code"]: r["amount"] for r in assets.depreciation_preview(s, mon(0))}
        assert first[pc] == 1000 and first[fu] == D("2157.50"), first
        assets.run_depreciation(s, mon(0))
        _refused(lambda: assets.depreciation_preview(s, mon(2)), "run the months in order", s)
        assets.run_depreciation(s, mon(1))
        a = s.get(FixedAsset, fu)
        assert a.acc_dep == D("2157.50") + ((D(100000) - D("2157.50")) * D("25.89") / 100 / 12).quantize(D("0.01"))
        assets.run_depreciation(s, mon(2))
        assets.reverse_depreciation(s, mon(2))
        assert s.get(FixedAsset, pc).acc_dep == 2000
        print(f"1 {pc} straight line 1,000 / month from {mon(0):%Y-%m}, {fu} WDV 2,157.50 in the first month; months in order; "
              f"{mon(2):%Y-%m} reversed")

        sold = mon(3).replace(day=10)
        _refused(lambda: assets.retire(s, pc, sold, D(30000), "112000"), f"run the depreciation up to {mon(2):%Y-%m}", s)
        assets.run_depreciation(s, mon(2))
        loss_before = s.scalar(select(Account.curr_total).where(Account.acct_code == "724000"))
        r = assets.retire(s, pc, sold, D(30000), "112000")
        assert r.status == "R" and r.acc_dep == 3000
        lines = {l.account: l.debit - l.credit for l in s.scalars(select(JournalLine).where(JournalLine.trans_id == r.transactions[-1].trans_id))}
        assert lines["122000"] == -36000 and lines["129000"] == 3000 and lines["724000"] == 3000 and lines["112000"] == 30000
        assert s.scalar(select(Account.curr_total).where(Account.acct_code == "724000")) - loss_before == 3000
        assert not [x for x in assets.depreciation_preview(s, mon(3)) if x["asset_code"] == pc]
        assert s.scalar(select(func.sum(Account.curr_total)).where(Account.postable == "Y")) == 0
        print(f"2 {pc} sold on {sold:%d-%m-%Y} for 30,000 at book value 33,000: loss 3,000 on 724000, cost and accumulated depreciation "
              "out; no further depreciation; trial balance 0")
        print("\nOK - fixed assets are capitalized, depreciated and retired.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
