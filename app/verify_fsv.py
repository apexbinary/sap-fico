"""End-to-end check for the financial statement version, balance carryforward,
customer/vendor transaction figures, functional areas and FSV maintenance.

Posts a prior-year (2025) opening and sale, then checks the 2026 balance sheet /
P&L before and after carrying 2025 forward. Run after app.seed (works on top of
the other verify scripts' data, and can be rerun):  python -m app.verify_fsv
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.services import fsv, reporting
from app.services.posting import DocumentRequest, LineRequest, post_document

MANDT, BUKRS = "100", "1000"
D = Decimal


def _node(tree, ergsl):
    for n in tree:
        if n["ergsl"] == ergsl:
            return n
        found = _node(n["children"], ergsl)
        if found:
            return found
    return None


def _accounts(node):
    yield from node["accounts"]
    for k in node["children"]:
        yield from _accounts(k)


def _print(fs):
    print(f"\n{fs['vstxt']} — {fs['bukrs']} FY {fs['gjahr']} vs {fs['compare_gjahr']} ({fs['waers']})")

    def walk(nodes):
        for n in nodes:
            print(f"   {'  ' * n['depth']}{n['text']:<{46 - 2 * n['depth']}}{n['current']:>14}{n['previous']:>14}")
            walk(n["children"])
    walk(fs["tree"])
    print(f"   assets {fs['total_assets']}  liabilities & equity {fs['total_liabilities_equity']}"
          f"  net result {fs['net_result']}  balanced={fs['balanced']}  unassigned={fs['unassigned']}")


def main() -> None:
    s = SessionLocal()
    try:
        profit_2025_before = fsv.financial_statement(s, MANDT, BUKRS, 2025)["net_result"]
        post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="SA", bldat=date(2025, 1, 2), budat=date(2025, 1, 2), waers="EUR",
            bktxt="Capital 2025", lines=[
                LineRequest(bschl="40", account="113100", wrbtr=D("5000.00")),
                LineRequest(bschl="50", account="100000", wrbtr=D("5000.00")),
            ]))
        post_document(s, DocumentRequest(
            bukrs=BUKRS, blart="DR", bldat=date(2025, 6, 1), budat=date(2025, 6, 1), waers="EUR",
            bktxt="Sale 2025", lines=[
                LineRequest(bschl="01", account="0000010000", wrbtr=D("1190.00")),
                LineRequest(bschl="50", account="800000", wrbtr=D("1000.00"), mwskz="A1", calculate_tax=True),
            ]))

        fs = fsv.financial_statement(s, MANDT, BUKRS, 2026)
        _print(fs)
        assert fs["balanced"] and not fs["unassigned"], "every account is assigned and A = L + E"
        pl_accounts = {a["saknr"] for a in _accounts(_node(fs["tree"], "3"))}
        tb26 = reporting.trial_balance(s, MANDT, BUKRS, 2026)
        assert fs["net_result"] == -sum(l["balance"] for l in tb26["lines"] if l["saknr"] in pl_accounts)
        assert _node(fs["tree"], "22")["current"] == fs["net_result"], "net result shown in equity"
        assert _node(fs["tree"], "3")["current"] == fs["net_result"], "P&L total = net result"
        bank = next((l["balance"] for l in tb26["lines"] if l["saknr"] == "113100"), D("0"))
        bank_node = "13" if bank > 0 else "24"
        assert any(a["saknr"] == "113100" for a in _node(fs["tree"], bank_node)["accounts"]), \
            f"bank balance {bank} belongs to item {bank_node}"
        print(f"Bank 113100 balance {bank} -> item {bank_node} ({_node(fs['tree'], bank_node)['text']})")

        fs25 = fsv.financial_statement(s, MANDT, BUKRS, 2025)
        profit_2025 = fs25["net_result"]
        assert profit_2025 == profit_2025_before + D("1000.00"), (profit_2025_before, profit_2025)

        cf = fsv.carry_forward(s, MANDT, BUKRS, 2025)
        assert fsv.carry_forward(s, MANDT, BUKRS, 2025) == cf, "carryforward is repeatable"
        print(f"Carryforward 2025 -> 2026: {cf['accounts']} account(s), retained earnings {cf['retained_earnings']}")
        assert cf["retained_earnings"] == profit_2025

        after = fsv.financial_statement(s, MANDT, BUKRS, 2026)
        _print(after)
        assert after["balanced"], "balance sheet still balances with carried-forward balances"
        assert after["net_result"] == fs["net_result"], "carryforward does not change the 2026 result"
        retained = next(a for a in _node(after["tree"], "21")["accounts"] if a["saknr"] == "109000")
        assert retained["current"] == profit_2025, retained
        assert _node(after["tree"], "21")["previous"] == _node(fs25["tree"], "21")["current"]
        assert reporting.trial_balance(s, MANDT, BUKRS, 2026)["balanced"]

        # customer / vendor transaction figures reconcile with the G/L, carryforward included
        for koart in ("D", "K"):
            pb = reporting.partner_balances(s, MANDT, BUKRS, koart, 2026)
            print(f"Partner balances {koart}: {len(pb['lines'])} partner(s), reconciled={pb['reconciled']}",
                  [(r["akont"], str(r["subledger"]), str(r["gl"])) for r in pb["reconciliation"]])
            assert pb["reconciled"], pb["reconciliation"]
        alpha = next(l for l in reporting.partner_balances(s, MANDT, BUKRS, "D", 2026)["lines"] if l["partner"] == "0000010000")
        assert alpha["carryforward"] != 0, "the 2025 customer balance was carried forward"

        # P&L by functional area: same result as the FSV, admin costs under 0400
        fa = fsv.pl_by_functional_area(s, MANDT, BUKRS, 2026)
        print("P&L by functional area:", [(l["fkber"], str(l["amount"])) for l in fa["lines"]])
        assert fa["net_result"] == after["net_result"]
        assert any(l["fkber"] == "0400" and l["amount"] > 0 for l in fa["lines"])

        # FSV maintenance: a new item with a range takes the account out of its old item
        node = fsv.add_node(s, MANDT, "INT", parent=3, txt45="Bank charges")
        fsv.add_assignment(s, MANDT, "INT", node.id, vonkt="479000", biskt="479000")
        moved = fsv.financial_statement(s, MANDT, BUKRS, 2026)
        assert moved["balanced"] and not moved["unassigned"]
        print(f"FSV item {node.id} 'Bank charges' added; most specific range wins -> balanced={moved['balanced']}")
        fsv.delete_node(s, MANDT, "INT", node.id)
        try:
            fsv.delete_node(s, MANDT, "INT", 22)
        except Exception as exc:  # special item
            print("Deleting the net result item is rejected:", exc)
        else:
            raise AssertionError("special items must not be deletable")
        print("\nOK - balance sheet / P&L by FSV, carryforward (G/L and partners), functional areas and FSV maintenance.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
