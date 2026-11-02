"""Balance sheet / P&L by financial statement version, and balance carryforward.

``financial_statement`` projects the trial balance onto an FSV tree
(T011 / FAGL_011PC / FAGL_011ZC):

  * each account's balance goes to the item whose account range contains it and
    whose debit/credit flag (SOLL/HABEN) matches the sign of the balance;
  * the P&L total is also shown as the net result (special item N) inside
    liabilities & equity, so assets = liabilities & equity;
  * accounts that no assignment covers land in the "not assigned" item (U);
  * every node carries the current year, a comparison year and the difference.

``carry_forward`` (FAGLGVTR / F.16) opens the next fiscal year: balance sheet
accounts carry their closing balance into GLT0-HSLVT, P&L accounts are closed
to the retained earnings account (T030 key BIL, modifier = P&L statement
account type SKA1-GVTYP).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import GLAccountTotals
from app.models.fsv import FinancialStatementVersion, FSVAccountAssignment, FSVNode
from app.models.gl_master import GLAccountCOA
from app.models.payments import AutomaticAccountDetermination
from app.services import reporting
from app.services.fiscal import PostingError, company_code

ZERO = Decimal("0")


def financial_statement(
    session: Session, mandt: str, bukrs: str, gjahr: int, *, versn: str | None = None,
    period_to: int = 16, compare_gjahr: int | None = None,
) -> dict:
    cc = company_code(session, mandt, bukrs)
    version = _version(session, mandt, cc.ktopl, versn)
    nodes = session.scalars(select(FSVNode).where(
        FSVNode.mandt == mandt, FSVNode.versn == version.versn).order_by(FSVNode.seqno, FSVNode.id)).all()
    assignments = session.scalars(select(FSVAccountAssignment).where(
        FSVAccountAssignment.mandt == mandt, FSVAccountAssignment.versn == version.versn,
        FSVAccountAssignment.ktopl == cc.ktopl)).all()
    balance_sheet = {a.saknr: a.xbilk for a in session.scalars(select(GLAccountCOA).where(
        GLAccountCOA.mandt == mandt, GLAccountCOA.ktopl == cc.ktopl))}
    compare = compare_gjahr if compare_gjahr is not None else gjahr - 1

    by_key = {n.ergsl: n for n in nodes}
    special = {n.kind: n for n in nodes if n.kind}
    for kind in "ALPNU":
        if kind not in special:
            raise PostingError(f"FSV {version.versn} has no special item of kind '{kind}'")

    # node id -> {"cur": .., "prev": .., "accounts": {saknr: {...}}}
    amounts: dict[int, dict] = defaultdict(lambda: {"cur": ZERO, "prev": ZERO, "accounts": {}})

    for col, year in (("cur", gjahr), ("prev", compare)):
        tb = reporting.trial_balance(session, mandt, bukrs, year, period_to)
        pl_total = ZERO
        for line in tb["lines"]:
            bal = line["balance"]
            if not bal:
                continue
            node = _assign(assignments, by_key, line["saknr"], bal) or special["U"]
            acc = amounts[node.id]["accounts"].setdefault(
                line["saknr"], {"saknr": line["saknr"], "name": line["name"], "cur": ZERO, "prev": ZERO})
            acc[col] += bal
            amounts[node.id][col] += bal
            if not balance_sheet.get(line["saknr"], True):
                pl_total += bal
        amounts[special["N"].id][col] += pl_total

    children: dict[int | None, list[FSVNode]] = defaultdict(list)
    for n in nodes:
        children[n.parent].append(n)

    def build(node: FSVNode, depth: int, sign: int) -> dict:
        sign = node.sign if node.parent is None or node.sign != 1 else sign
        kids = [build(k, depth + 1, sign) for k in children[node.id]]
        own = amounts[node.id]
        cur = own["cur"] + sum((k["raw_cur"] for k in kids), ZERO)
        prev = own["prev"] + sum((k["raw_prev"] for k in kids), ZERO)
        accounts = sorted(own["accounts"].values(), key=lambda a: a["saknr"])
        return {
            "id": node.id, "ergsl": node.ergsl, "text": node.txt45, "kind": node.kind, "depth": depth,
            "raw_cur": cur, "raw_prev": prev,
            "current": _signed(cur, sign), "previous": _signed(prev, sign),
            "difference": _signed(cur - prev, sign),
            "pct": (((cur - prev) / abs(prev)) * 100).quantize(Decimal("0.1")) if prev else None,
            "accounts": [{**a, "current": _signed(a["cur"], sign), "previous": _signed(a["prev"], sign)}
                         for a in accounts],
            "children": kids,
        }

    tree = [build(n, 0, n.sign) for n in children[None]]
    top = {n["kind"]: n for n in tree}
    assets = top["A"]["raw_cur"] if "A" in top else ZERO
    liabilities = top["L"]["raw_cur"] if "L" in top else ZERO
    net = amounts[special["N"].id]["cur"]
    return {
        "bukrs": bukrs, "gjahr": gjahr, "compare_gjahr": compare, "period_to": period_to,
        "versn": version.versn, "vstxt": version.vstxt, "waers": cc.waers,
        "total_assets": assets, "total_liabilities_equity": -liabilities,
        "net_result": -net,  # profit positive
        "balanced": assets + liabilities == 0,
        "unassigned": [a["saknr"] for a in amounts[special["U"].id]["accounts"].values()],
        "tree": tree,
    }


def _signed(amount: Decimal, sign: int) -> Decimal:
    return amount * sign + ZERO  # + 0 turns Decimal('-0') into 0


def _version(session: Session, mandt: str, ktopl: str, versn: str | None) -> FinancialStatementVersion:
    if versn:
        v = session.get(FinancialStatementVersion, (mandt, versn))
        if v is None:
            raise PostingError(f"Financial statement version {versn} does not exist")
        return v
    v = session.scalars(select(FinancialStatementVersion).where(
        FinancialStatementVersion.mandt == mandt, FinancialStatementVersion.ktopl == ktopl)).first()
    if v is None:
        raise PostingError(f"No financial statement version for chart of accounts {ktopl}")
    return v


def _assign(assignments, by_key, saknr: str, balance: Decimal) -> FSVNode | None:
    """FSV item for an account and the sign of its balance (most specific range wins)."""
    hits = [
        a for a in assignments
        if a.vonkt <= saknr <= a.biskt and ((balance > 0 and a.soll) or (balance < 0 and a.haben))
    ]
    if not hits:
        return None
    best = min(hits, key=lambda a: (int(a.biskt) - int(a.vonkt)) if a.biskt.isdigit() and a.vonkt.isdigit() else 0)
    return by_key.get(best.ergsl)


def carry_forward(session: Session, mandt: str, bukrs: str, gjahr: int) -> dict:
    """Carry the balances of fiscal year ``gjahr`` forward into ``gjahr + 1`` (repeatable)."""
    cc = company_code(session, mandt, bukrs)
    accounts = {a.saknr: a for a in session.scalars(select(GLAccountCOA).where(
        GLAccountCOA.mandt == mandt, GLAccountCOA.ktopl == cc.ktopl))}
    rows = session.scalars(select(GLAccountTotals).where(
        GLAccountTotals.mandt == mandt, GLAccountTotals.bukrs == bukrs, GLAccountTotals.gjahr == gjahr)).all()

    balances: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    for r in rows:
        total = reporting._sum_periods(r, 16)
        balances[(r.racct, r.rbusa)] += total if r.drcrk == "S" else -total

    carried: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    retained = ZERO
    for (racct, rbusa), bal in balances.items():
        coa = accounts.get(racct)
        if coa is not None and not coa.xbilk:  # P&L account -> retained earnings
            target = _retained_earnings(session, mandt, cc.ktopl, coa.gvtyp or "X")
            carried[(target, rbusa)] += bal
            retained += bal
        else:
            carried[(racct, rbusa)] += bal

    nxt = gjahr + 1
    for r in session.scalars(select(GLAccountTotals).where(
            GLAccountTotals.mandt == mandt, GLAccountTotals.bukrs == bukrs, GLAccountTotals.gjahr == nxt)):
        r.hslvt = ZERO  # rerun-safe: rebuild the carryforward from scratch
    for (racct, rbusa), bal in carried.items():
        if not bal:
            continue
        drcrk = "S" if bal > 0 else "H"
        key = (mandt, "0", "00", bukrs, nxt, racct, rbusa, drcrk)
        row = session.get(GLAccountTotals, key)
        if row is None:
            row = GLAccountTotals(mandt=mandt, rrcty="0", rldnr="00", bukrs=bukrs, gjahr=nxt,
                                  racct=racct, rbusa=rbusa, drcrk=drcrk, rtcur=cc.waers)
            for p in range(1, 17):
                setattr(row, f"tsl{p:02d}", ZERO)
            session.add(row)
        row.hslvt = abs(bal)
    session.commit()
    return {
        "bukrs": bukrs, "from_gjahr": gjahr, "to_gjahr": nxt,
        "accounts": sum(1 for b in carried.values() if b),
        "retained_earnings": -retained,  # profit positive
    }


def _retained_earnings(session: Session, mandt: str, ktopl: str, gvtyp: str) -> str:
    row = session.get(AutomaticAccountDetermination, (mandt, ktopl, "BIL", "", gvtyp, ""))
    if row is None:
        raise PostingError(f"No retained earnings account (T030 BIL / {gvtyp}) in chart of accounts {ktopl}")
    return row.konts
