"""Cost accounting: dimensions (ODIM), profit centers (OPRC), distribution rules (OOCR / OCR1) and the
profit center report.

Journal lines carry one distribution rule per dimension (JDT1 ProfitCode, OcrCode2 .. 5); each
profit center has a direct rule with its own code (Direct Y, 100 %). Postings keep the codes only on
revenue and expense accounts (ActType I / E). The report splits every such line by the rule's
shares (PrcAmount / OcrTotal); lines without a rule of the dimension are "not assigned".
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.costacct import Dimension, DistributionRule, DistributionShare, ProfitCenter
from app.models.finance import Account, JournalLine
from app.services.admin import B1Error

ZERO = Decimal("0")
JDT1_COLS = ("profit_code", "ocr_code2", "ocr_code3", "ocr_code4", "ocr_code5")  # dimension 1 .. 5
LINE_COLS = ("ocr_code", "ocr_code2", "ocr_code3", "ocr_code4", "ocr_code5")


def check_codes(session: Session, codes, on: date | None = None) -> tuple:
    """Validate (dim1 .. dim5) rule codes: existing, active, of the right dimension; returns a 5-tuple."""
    codes = tuple((list(codes or []) + [None] * 5)[:5])
    for n, code in enumerate(codes, start=1):
        if not code:
            continue
        r = session.get(DistributionRule, code)
        if r is None or r.dim_code != n:
            raise B1Error(f"{code} is not a distribution rule of dimension {n}")
        if r.active != "Y":
            raise B1Error(f"Distribution rule {code} is inactive")
        dim = session.get(Dimension, n)
        if dim is None or dim.dim_active != "Y":
            raise B1Error(f"Dimension {n} is not active")
    return tuple(c or None for c in codes)


def pl_account(session: Session, account: str, cache: dict | None = None) -> bool:
    """Revenue / expense accounts keep the distribution rules."""
    if cache is not None and account in cache:
        return cache[account]
    a = session.get(Account, account)
    result = a is not None and a.act_type in {"I", "E"}
    if cache is not None:
        cache[account] = result
    return result


# ------------------------------------------------------------- setup
def setup(session: Session) -> dict:
    return {"dimensions": [{"dim_code": d.dim_code, "dim_name": d.dim_name, "dim_desc": d.dim_desc, "active": d.dim_active == "Y"}
                           for d in session.scalars(select(Dimension).order_by(Dimension.dim_code))],
            "centers": [{"prc_code": p.prc_code, "prc_name": p.prc_name, "dim_code": p.dim_code, "active": p.active == "Y",
                         "valid_from": p.valid_from, "valid_to": p.valid_to}
                        for p in session.scalars(select(ProfitCenter).order_by(ProfitCenter.dim_code, ProfitCenter.prc_code))],
            "rules": [{"ocr_code": r.ocr_code, "ocr_name": r.ocr_name, "dim_code": r.dim_code, "ocr_total": r.ocr_total,
                       "direct": r.direct == "Y", "active": r.active == "Y",
                       "shares": [{"prc_code": s.prc_code, "prc_amount": s.prc_amount} for s in r.shares]}
                      for r in session.scalars(select(DistributionRule).order_by(DistributionRule.dim_code, DistributionRule.ocr_code))]}


def save_dimension(session: Session, code: int, data: dict) -> None:
    d = session.get(Dimension, code)
    if d is None:
        raise B1Error(f"Dimension {code} does not exist")
    if data.get("dim_name"):
        d.dim_name = data["dim_name"].strip()[:30]
    if "dim_desc" in data:
        d.dim_desc = data["dim_desc"]
    if data.get("active") is not None:
        d.dim_active = "Y" if data["active"] else "N"
    session.commit()


def save_center(session: Session, data: dict, code: str | None = None) -> ProfitCenter:
    if code is None:
        code = (data.get("prc_code") or "").strip().upper()
        if not re.match(r"^[A-Z0-9_-]{1,8}$", code):
            raise B1Error("A profit center code has 1-8 letters, digits, '_' or '-'")
        if session.get(ProfitCenter, code) is not None or session.get(DistributionRule, code) is not None:
            raise B1Error(f"{code} is already a profit center or distribution rule")
        dim = int(data.get("dim_code") or 1)
        if session.get(Dimension, dim) is None:
            raise B1Error(f"Dimension {dim} does not exist")
        if not (data.get("prc_name") or "").strip():
            raise B1Error("Enter the profit center name")
        p = ProfitCenter(prc_code=code, prc_name=data["prc_name"].strip()[:30], dim_code=dim, active="Y")
        session.add(p)
        session.flush()
        # the direct distribution rule of the center (same code, 100 %)
        session.add(DistributionRule(ocr_code=code, ocr_name=(data.get("prc_name") or code)[:30], dim_code=dim, ocr_total=Decimal(100),
                                     direct="Y", active="Y", shares=[DistributionShare(prc_code=code, prc_amount=Decimal(100))]))
    else:
        p = session.get(ProfitCenter, code)
        if p is None:
            raise B1Error(f"Profit center {code} does not exist")
    if data.get("prc_name"):
        p.prc_name = data["prc_name"].strip()[:30]
        direct = session.get(DistributionRule, p.prc_code)
        if direct is not None and direct.direct == "Y":
            direct.ocr_name = p.prc_name
    if not p.prc_name:
        raise B1Error("Enter the profit center name")
    for key in ("valid_from", "valid_to"):
        if key in data:
            setattr(p, key, data[key])
    if data.get("active") is not None:
        p.active = "Y" if data["active"] else "N"
        direct = session.get(DistributionRule, p.prc_code)
        if direct is not None and direct.direct == "Y":
            direct.active = p.active
    session.commit()
    return p


def save_rule(session: Session, data: dict, code: str | None = None) -> DistributionRule:
    if code is None:
        code = (data.get("ocr_code") or "").strip().upper()
        if not re.match(r"^[A-Z0-9_-]{1,8}$", code):
            raise B1Error("A distribution rule code has 1-8 letters, digits, '_' or '-'")
        if session.get(DistributionRule, code) is not None:
            raise B1Error(f"Distribution rule {code} already exists")
        r = DistributionRule(ocr_code=code, dim_code=int(data.get("dim_code") or 1), direct="N", active="Y")
        session.add(r)
    else:
        r = session.get(DistributionRule, code)
        if r is None:
            raise B1Error(f"Distribution rule {code} does not exist")
        if r.direct == "Y" and data.get("shares") is not None:
            raise B1Error("A direct rule belongs to its profit center; its share cannot change")
        used = session.scalar(select(JournalLine.trans_id).where(getattr(JournalLine, JDT1_COLS[r.dim_code - 1]) == code).limit(1))
        if used is not None and data.get("shares") is not None:
            raise B1Error(f"Distribution rule {code} is used in postings: create a new rule instead of changing the shares")
    if data.get("ocr_name"):
        r.ocr_name = data["ocr_name"].strip()[:30]
    if not r.ocr_name:
        raise B1Error("Enter the rule name")
    if data.get("active") is not None:
        r.active = "Y" if data["active"] else "N"
    if data.get("shares") is not None:
        shares = [s for s in data["shares"] if Decimal(str(s.get("prc_amount") or 0)) != 0]
        if not shares:
            raise B1Error("A distribution rule needs at least one profit center share")
        rows = []
        for s in shares:
            p = session.get(ProfitCenter, s["prc_code"])
            if p is None or p.dim_code != r.dim_code:
                raise B1Error(f"{s['prc_code']} is not a profit center of dimension {r.dim_code}")
            amount = Decimal(str(s["prc_amount"]))
            if amount < 0:
                raise B1Error("Shares cannot be negative")
            rows.append(DistributionShare(prc_code=p.prc_code, prc_amount=amount))
        if len({x.prc_code for x in rows}) != len(rows):
            raise B1Error("A profit center appears twice in the rule")
        r.shares = rows
        r.ocr_total = sum((x.prc_amount for x in rows), ZERO)
    session.commit()
    return r


# ------------------------------------------------------------- report
def report(session: Session, date_from: date, date_to: date, dim: int = 1) -> dict:
    """Profit center report: revenue / expenses per profit center of a dimension, by account."""
    if dim not in range(1, 6):
        raise B1Error("Dimension 1 - 5")
    col = getattr(JournalLine, JDT1_COLS[dim - 1])
    rules = {r.ocr_code: r for r in session.scalars(select(DistributionRule).where(DistributionRule.dim_code == dim))}
    centers = {p.prc_code: p.prc_name for p in session.scalars(select(ProfitCenter).where(ProfitCenter.dim_code == dim))}
    rows = session.execute(select(JournalLine.account, col, JournalLine.debit, JournalLine.credit, Account.act_type, Account.acct_name)
                           .join(Account, Account.acct_code == JournalLine.account)
                           .where(JournalLine.ref_date >= date_from, JournalLine.ref_date <= date_to, Account.act_type.in_(["I", "E"]))).all()
    out: dict[str, dict] = defaultdict(lambda: {"revenue": ZERO, "expenses": ZERO, "accounts": defaultdict(lambda: ZERO)})
    names = {}
    for account, code, debit, credit, act_type, acct_name in rows:
        names[account] = acct_name
        net = credit - debit  # revenue positive, expense negative
        rule = rules.get(code) if code else None
        parts = [(s.prc_code, s.prc_amount / rule.ocr_total) for s in rule.shares] if rule is not None and rule.ocr_total else [(None, Decimal(1))]
        for prc, share in parts:
            amount = (net * share).quantize(Decimal("0.01"))
            bucket = out[prc or "-"]
            bucket["revenue" if act_type == "I" else "expenses"] += amount if act_type == "I" else -amount
            bucket["accounts"][account] += amount
    result = []
    for prc in sorted(out, key=lambda k: (k == "-", k)):
        b = out[prc]
        result.append({"prc_code": None if prc == "-" else prc, "prc_name": centers.get(prc, "Not assigned"),
                       "revenue": b["revenue"], "expenses": b["expenses"], "result": b["revenue"] - b["expenses"],
                       "accounts": [{"account": a, "acct_name": names[a], "amount": v} for a, v in sorted(b["accounts"].items()) if v]})
    return {"date_from": date_from, "date_to": date_to, "dimension": dim, "centers": result,
            "total": {"revenue": sum((c["revenue"] for c in result), ZERO), "expenses": sum((c["expenses"] for c in result), ZERO),
                      "result": sum((c["result"] for c in result), ZERO)}}
