"""End-to-end check for recurring entries (FBD1 original + F.14 run).

Run after app.seed (rerunnable):  python -m app.verify_recurring
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.models.documents import AccountingDocumentHeader, RecurringEntrySchedule
from app.services import reporting
from app.services.posting import DocumentRequest, LineRequest
from app.services.recurring import create_recurring, delete_recurring, run_recurring

MANDT, BUKRS, VEND = "100", "1000", "0000020000"
D = Decimal


def main() -> None:
    s = SessionLocal()
    try:
        expense_before = reporting.account_balance(s, MANDT, BUKRS, 2026, "476000")["balance"]
        original = create_recurring(s, DocumentRequest(
            bukrs=BUKRS, blart="KR", bldat=date(2026, 1, 31), budat=date(2026, 1, 31), waers="EUR",
            bktxt="Monthly office rent", kokrs="1000", lines=[
                LineRequest(bschl="31", account=VEND, wrbtr=D("1190.00"), sgtxt="Rent"),
                LineRequest(bschl="40", account="476000", wrbtr=D("1000.00"), kostl="0000001000", mwskz="V1"),
                LineRequest(bschl="40", account="154000", wrbtr=D("190.00"), mwskz="V1", buzid="T"),
            ]), dbbdt=date(2026, 1, 31), dbedt=date(2026, 12, 31), dbmon=1)
        print(f"Recurring original {original.belnr}/{original.gjahr} (status {original.bstat!r})")
        assert original.bstat == "D" and original.belnr.startswith("91"), "interval X1"
        assert reporting.account_balance(s, MANDT, BUKRS, 2026, "476000")["balance"] == expense_before

        def ours(posted):
            return [p for p in posted if p["recurring"] == original.belnr]

        first = ours(run_recurring(s, MANDT, BUKRS, date(2026, 3, 31)))
        print("Run to 2026-03-31:", [str(p["budat"]) for p in first])
        assert [p["budat"] for p in first] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
        assert ours(run_recurring(s, MANDT, BUKRS, date(2026, 3, 31))) == [], "no date is posted twice"
        second = ours(run_recurring(s, MANDT, BUKRS, date(2026, 5, 31)))
        print("Run to 2026-05-31:", [str(p["budat"]) for p in second])
        assert [p["budat"] for p in second] == [date(2026, 4, 30), date(2026, 5, 31)]

        copy = s.get(AccountingDocumentHeader, (MANDT, BUKRS, second[0]["belnr"], second[0]["gjahr"]))
        assert copy.dbblg == original.belnr and copy.tcode == "F.14" and copy.bstat == " "
        assert [i.bschl for i in copy.items] == ["31", "40", "40"] and copy.items[2].buzid == "T"
        expense = reporting.account_balance(s, MANDT, BUKRS, 2026, "476000")["balance"]
        assert expense == expense_before + D("5000.00"), expense
        sched = s.get(RecurringEntrySchedule, (MANDT, BUKRS, original.belnr, original.gjahr))
        assert sched.dbatr == date(2026, 6, 30)

        delete_recurring(s, MANDT, BUKRS, original.belnr, original.gjahr)
        assert ours(run_recurring(s, MANDT, BUKRS, date(2026, 12, 31))) == [], "deleted originals stop"
        tb = reporting.trial_balance(s, MANDT, BUKRS, 2026)
        assert tb["balanced"]
        print(f"Trial balance balanced={tb['balanced']}")
        print("\nOK - recurring original, F.14 runs (month-end clamping, no duplicates) and deletion work.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
