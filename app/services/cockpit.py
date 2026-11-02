"""Cockpit: KPIs, analyses, open documents and alerts for the home screen."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.banking import BankStatementRow, PaymentRun
from app.models.documents import DOCUMENT_CLASSES
from app.models.finance import Account, JournalLine
from app.models.inventory import Item
from app.models.partners import BusinessPartner
from app.services import reports

ZERO = Decimal("0")
WIDGETS = [  # (id, title) in the default order
    ("kpis", "Key figures"), ("sales_chart", "Sales and purchases (12 months)"), ("aging_ar", "Customer aging"),
    ("aging_ap", "Vendor aging"), ("top_customers", "Top 5 customers"), ("top_items", "Top 5 items"),
    ("open_docs", "Open documents"), ("alerts", "Alerts"), ("cash", "Cash and bank"), ("links", "Common functions"),
]


def _net_sales(session: Session, obj: str, start: date, end: date) -> Decimal:
    """Net (excl. tax) LC total of documents of a type in a period, canceled ones left out."""
    cls = DOCUMENT_CLASSES[obj][0]
    total = session.scalar(select(func.coalesce(func.sum(cls.doc_total - cls.vat_sum), 0)).where(
        cls.canceled == "N", cls.doc_date >= start, cls.doc_date <= end))
    return Decimal(total or 0)


def _months_back(on: date, n: int) -> date:
    m = on.month - 1 - n
    return date(on.year + m // 12, m % 12 + 1, 1)


def _aging(session: Session, on: date, customers: bool) -> dict:
    buckets = {"current": ZERO, "1-30": ZERO, "31-60": ZERO, "61-90": ZERO, "90+": ZERO}
    side = JournalLine.bal_due_deb if customers else JournalLine.bal_due_cred
    codes = select(BusinessPartner.card_code).where(BusinessPartner.card_type == ("C" if customers else "S"))
    for l in session.scalars(select(JournalLine).where(JournalLine.short_name.in_(codes), side > 0,
                                                       JournalLine.short_name != JournalLine.account)):
        days = (on - l.due_date).days
        key = "current" if days <= 0 else "1-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        buckets[key] += l.bal_due_deb if customers else l.bal_due_cred
    return buckets


def _open_docs(session: Session, obj: str, limit: int = 5) -> dict:
    cls = DOCUMENT_CLASSES[obj][0]
    q = select(cls).where(cls.doc_status == "O", cls.canceled == "N")
    docs = session.scalars(q.order_by(cls.doc_due_date)).all()
    return {"count": len(docs), "value": sum((d.doc_total for d in docs), ZERO),
            "top": [{"doc_entry": d.doc_entry, "doc_num": d.doc_num, "card_code": d.card_code, "card_name": d.card_name,
                     "doc_due_date": d.doc_due_date, "doc_total": d.doc_total} for d in docs[:limit]]}


def cockpit(session: Session, on: date | None = None) -> dict:
    on = on or date.today()
    month0, year0 = on.replace(day=1), on.replace(month=1, day=1)
    customers = select(BusinessPartner.card_code).where(BusinessPartner.card_type == "C")
    vendors = select(BusinessPartner.card_code).where(BusinessPartner.card_type == "S")

    sales_mtd = _net_sales(session, "13", month0, on) - _net_sales(session, "14", month0, on)
    sales_ytd = _net_sales(session, "13", year0, on) - _net_sales(session, "14", year0, on)
    purch_mtd = _net_sales(session, "18", month0, on) - _net_sales(session, "19", month0, on)
    purch_ytd = _net_sales(session, "18", year0, on) - _net_sales(session, "19", year0, on)
    receivable = Decimal(session.scalar(select(func.coalesce(func.sum(BusinessPartner.balance), 0)).where(
        BusinessPartner.card_type == "C")) or 0)
    payable = -Decimal(session.scalar(select(func.coalesce(func.sum(BusinessPartner.balance), 0)).where(
        BusinessPartner.card_type == "S")) or 0)
    overdue_lines = session.scalars(select(JournalLine).where(
        JournalLine.short_name.in_(customers), JournalLine.bal_due_deb > 0, JournalLine.due_date < on,
        JournalLine.short_name != JournalLine.account).order_by(JournalLine.due_date)).all()
    due_soon = Decimal(session.scalar(select(func.coalesce(func.sum(JournalLine.bal_due_cred), 0)).where(
        JournalLine.short_name.in_(vendors), JournalLine.bal_due_cred > 0, JournalLine.due_date <= on + timedelta(days=7),
        JournalLine.short_name != JournalLine.account)) or 0)
    cash_accounts = session.scalars(select(Account).where(Account.finanse == "Y", Account.postable == "Y")
                                    .order_by(Account.acct_code)).all()
    pl = reports.profit_and_loss(session, year0, on)
    tax = reports.tax_report(session, month0, on)

    # 12 months of sales and purchases
    months = []
    for n in range(11, -1, -1):
        start = _months_back(on, n)
        end = _months_back(on, n - 1) - timedelta(days=1)
        months.append({"month": start.strftime("%Y-%m"),
                       "sales": _net_sales(session, "13", start, end) - _net_sales(session, "14", start, end),
                       "purchases": _net_sales(session, "18", start, end) - _net_sales(session, "19", start, end)})

    # top 5 customers and items (net sales this year)
    inv, inv_line = DOCUMENT_CLASSES["13"]
    by_customer: dict[str, Decimal] = defaultdict(lambda: ZERO)
    names = {}
    for d in session.scalars(select(inv).where(inv.canceled == "N", inv.doc_date >= year0, inv.doc_date <= on)):
        by_customer[d.card_code] += d.doc_total - d.vat_sum
        names[d.card_code] = d.card_name
    top_customers = [{"card_code": k, "card_name": names[k], "sales": v}
                     for k, v in sorted(by_customer.items(), key=lambda kv: -kv[1])[:5]]
    item_rows = session.execute(select(inv_line.item_code, inv_line.dscription, func.sum(inv_line.line_total),
                                       func.sum(inv_line.quantity)).join(inv, inv.doc_entry == inv_line.doc_entry).where(
        inv.canceled == "N", inv.doc_date >= year0, inv.doc_date <= on, inv_line.item_code.is_not(None))
        .group_by(inv_line.item_code, inv_line.dscription).order_by(func.sum(inv_line.line_total).desc()).limit(5)).all()
    top_items = [{"item_code": r[0], "item_name": r[1], "sales": Decimal(r[2] or 0), "quantity": Decimal(r[3] or 0)}
                 for r in item_rows]

    # alerts
    low_stock = session.scalars(select(Item).where(Item.invnt_item == "Y", Item.frozen_for == "N", Item.min_level > 0,
                                                   Item.on_hand < Item.min_level).order_by(Item.item_code)).all()
    over_limit = [bp for bp in session.scalars(select(BusinessPartner).where(BusinessPartner.card_type == "C",
                                                                              BusinessPartner.credit_line > 0))
                  if bp.balance + bp.orders_bal > bp.credit_line]
    unreconciled = session.scalar(select(func.count()).select_from(BankStatementRow).where(BankStatementRow.bank_match.is_(None))) or 0
    saved_runs = session.scalar(select(func.count()).select_from(PaymentRun).where(PaymentRun.status == "S")) or 0

    return {
        "on": on,
        "kpis": {"sales_mtd": sales_mtd, "sales_ytd": sales_ytd, "purchases_mtd": purch_mtd, "purchases_ytd": purch_ytd,
                 "receivable": receivable, "overdue": sum((l.bal_due_deb for l in overdue_lines), ZERO), "payable": payable,
                 "payable_due_7d": due_soon, "cash": sum((a.curr_total for a in cash_accounts), ZERO),
                 "inventory_value": Decimal(session.scalar(select(func.coalesce(func.sum(Item.stock_value), 0))) or 0),
                 "gross_profit_ytd": pl["gross_profit"], "net_profit_ytd": pl["net_profit"],
                 "open_orders": Decimal(session.scalar(select(func.coalesce(func.sum(BusinessPartner.orders_bal), 0)).where(
                     BusinessPartner.card_type == "C")) or 0),
                 "tax_payable_mtd": tax["net_payable"]},
        "sales_chart": months,
        "aging_ar": _aging(session, on, True),
        "aging_ap": _aging(session, on, False),
        "top_customers": top_customers,
        "top_items": top_items,
        "open_docs": {"sales_orders": _open_docs(session, "17"), "deliveries": _open_docs(session, "15"),
                      "purchase_orders": _open_docs(session, "22"), "goods_receipts": _open_docs(session, "20")},
        "alerts": {"low_stock": [{"item_code": i.item_code, "item_name": i.item_name, "on_hand": i.on_hand,
                                  "min_level": i.min_level} for i in low_stock[:10]], "low_stock_count": len(low_stock),
                   "overdue": [{"trans_id": l.trans_id, "trans_type": l.trans_type, "created_by": l.created_by,
                                "doc_num": l.base_ref, "card_code": l.short_name, "due_date": l.due_date,
                                "days": (on - l.due_date).days, "open": l.bal_due_deb} for l in overdue_lines[:10]],
                   "overdue_count": len(overdue_lines),
                   "credit_limit": [{"card_code": bp.card_code, "card_name": bp.card_name, "exposure": bp.balance + bp.orders_bal,
                                     "credit_line": bp.credit_line} for bp in over_limit],
                   "unreconciled_bank_rows": unreconciled, "saved_payment_runs": saved_runs},
        "cash": [{"acct_code": a.acct_code, "acct_name": a.acct_name, "balance": a.curr_total} for a in cash_accounts],
    }
