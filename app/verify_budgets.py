"""End-to-end check for budgets.

An annual budget is split equally over 12 months (the last month takes the rounding), monthly
amounts are kept as entered; revenue accounts are budgeted on the credit side; a scenario at 50 %
copies the main budget; the report shows budget vs. actual to date; the budget check (block)
refuses an expense posting over the annual budget, documents included, and lets it pass without
the check. Rerunnable: the budget is set relative to the actual of the year.

Run after app.seed:  python -m app.verify_budgets
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.services import budgets
from app.services import journal
from app.services.admin import B1Error, company
from app.services.journal import JournalLineRequest as JL
from app.services.journal import JournalRequest as JR

D = Decimal
Y = 2027
DAY = date(Y, 12, 20)
ACCT = "611000"


def _je(s, amount: int):
    return journal.post_entry(s, JR(ref_date=DAY, memo="Budget check", lines=[JL(account=ACCT, debit=D(amount)), JL(account="112000", credit=D(amount))]))


def main() -> None:
    s = SessionLocal()
    before_check = company(s).bgt_check
    try:
        b = budgets.save(s, "411000", Y, annual=D("100000"))
        assert b.crd_l_total == 100000 and b.deb_l_total == 0
        months = [m.crd_l_total for m in b.months]
        assert months[:11] == [D("8333.33")] * 11 and months[11] == D("8333.37")
        print("1 Revenue 411000: 1,00,000 a year on the credit side, 8,333.33 x 11 + 8,333.37")

        row = lambda r: next(x for x in r["accounts"] if x["acct_code"] == ACCT)  # noqa: E731
        budgets.save(s, ACCT, Y, annual=D(0))
        actual = row(budgets.report(s, Y))["actual"]
        b = budgets.save(s, ACCT, Y, months=[0] * 11 + [actual + 1000])
        assert b.deb_l_total == actual + 1000 and b.months[11].deb_l_total == actual + 1000
        sc = budgets.add_scenario(s, "Lean 50 %", Y, D(50))
        r50 = budgets.report(s, Y, sc.abs_id)
        assert row(r50)["annual_budget"] == ((actual + 1000) / 2).quantize(D("0.01"))
        print(f"2 Expense {ACCT}: budget = actual {actual} + 1,000 (all in December); scenario 'Lean 50 %' holds half")

        s.get(type(company(s)), 1).bgt_check = "B"
        s.commit()
        _je(s, 800)
        try:
            _je(s, 300)
            raise AssertionError("over budget accepted")
        except B1Error as exc:
            assert "Budget of account 611000" in str(exc), exc
            s.rollback()
        rep = row(budgets.report(s, Y))
        assert rep["actual"] == actual + 800 and rep["deviation"] == -200 and rep["pct"] is not None
        company(s).bgt_check = "N"
        s.commit()
        _je(s, 300)
        assert row(budgets.report(s, Y))["deviation"] == 100
        assert row(budgets.report(s, Y, upto_month=11))["budget"] == 0
        print("3 Budget check B: 800 passes, 300 more refused (over the budget); without the check it posts: deviation +100; "
              "budget to November 0")
        print("\nOK - budgets, scenarios, budget vs. actual and the budget check work.")
    finally:
        s.rollback()
        company(s).bgt_check = before_check
        s.commit()
        s.close()


if __name__ == "__main__":
    main()
