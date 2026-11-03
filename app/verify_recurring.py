"""End-to-end check for recurring postings.

Monthly rent template due on 31 January with 3 postings: executing on 15 April posts 31 Jan,
28 Feb, 31 Mar (month ends kept, catch-up) and ends the template; a quarterly template moves by 3
months; unbalanced templates are refused; nothing is due before the next due date; the postings
carry Ref3 RC:<code>.

Run after app.seed (rerunnable: fresh codes each run):  python -m app.verify_recurring
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.finance import JournalEntry
from app.models.recurring import RecurringPosting
from app.services import recurring
from app.services.admin import B1Error

D = Decimal


def main() -> None:
    assert recurring.next_date(date(2027, 1, 31), "M", 31) == date(2027, 2, 28)
    assert recurring.next_date(date(2027, 2, 28), "M", 31) == date(2027, 3, 31)
    assert recurring.next_date(date(2027, 11, 15), "Q", 15) == date(2028, 2, 15)
    assert recurring.next_date(date(2027, 1, 5), "W") == date(2027, 1, 12) and recurring.next_date(date(2027, 1, 5), "O") is None
    s = SessionLocal()
    try:
        n = s.scalar(select(func.count()).select_from(RecurringPosting)) + 1
        rent, ins = f"RENT{n:03d}", f"INS{n:03d}"
        lines = [{"account": "612000", "debit": 25000, "line_memo": "Rent"}, {"account": "112000", "credit": 25000}]
        try:
            recurring.save(s, {"rcur_code": "BAD", "rcur_desc": "x", "frequency": "M", "next_deu": "2027-01-31",
                               "lines": [{"account": "612000", "debit": 10}, {"account": "112000", "credit": 9}]})
            raise AssertionError("unbalanced template accepted")
        except B1Error:
            s.rollback()
        recurring.save(s, {"rcur_code": rent, "rcur_desc": "Office rent", "frequency": "M", "next_deu": "2027-01-31", "limit_rtrns": 3, "lines": lines})
        recurring.save(s, {"rcur_code": ins, "rcur_desc": "Insurance", "frequency": "Q", "next_deu": "2027-02-15", "lines": lines})
        assert not [d for d in recurring.due(s, date(2027, 1, 30)) if d["rcur_code"] in (rent, ins)]
        due = {d["rcur_code"]: d["dates"] for d in recurring.due(s, date(2027, 4, 15))}
        assert due[rent] == [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31)] and due[ins] == [date(2027, 2, 15)]
        nums = recurring.execute(s, rent, date(2027, 4, 15))
        rc = s.get(RecurringPosting, rent)
        assert len(nums) == 3 and rc.instance == 3 and rc.active == "N" and rc.last_date == date(2027, 3, 31)
        dates = [e.ref_date for e in s.scalars(select(JournalEntry).where(JournalEntry.ref3 == f"RC:{rent}").order_by(JournalEntry.trans_id))]
        assert dates == [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31)]
        recurring.execute(s, ins, date(2027, 9, 1))
        ri = s.get(RecurringPosting, ins)
        assert ri.instance == 3 and ri.next_deu == date(2027, 11, 15) and ri.active == "Y"
        print(f"1 {rent}: 31 Jan, 28 Feb, 31 Mar posted (month end kept, catch-up), ended after 3; {ins} quarterly: 15 Feb, 15 May, "
              "15 Aug, next 15 Nov; unbalanced template refused; nothing due before the due date")
        print("\nOK - recurring postings post on schedule.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
