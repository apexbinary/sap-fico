"""Data import (B1: Data Transfer Workbench): CSV / Excel files of business partners, items, prices,
opening balances (G/L accounts, business partners) and opening stock.

Every row runs through the same services as manual entry (all checks apply). The import runs on its
own connection in one outer transaction; the services' commits only release savepoints, so a
failing row is rolled back alone. A dry run (simulation) rolls everything back at the end; with
"all or nothing" any failing row rolls back the whole file. The result lists every row.
"""

from __future__ import annotations

import base64
import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.services.admin import B1Error

_engine = None


def _import_engine():
    """The import's own engine. With SQLite the pysqlite driver needs the documented workaround so that
    BEGIN / SAVEPOINT really happen (else a simulation could not be rolled back)."""
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine, event

        from app.database import engine

        url = engine.url
        if url.get_backend_name() == "sqlite":
            _engine = create_engine(url, connect_args={"check_same_thread": False})

            @event.listens_for(_engine, "connect")
            def _connect(dbapi_conn, _record):
                dbapi_conn.isolation_level = None  # let SQLAlchemy emit BEGIN

            @event.listens_for(_engine, "begin")
            def _begin(conn):
                conn.exec_driver_sql("BEGIN")
        else:
            _engine = engine
    return _engine

KINDS = {
    "partners": ["card_code", "card_name", "card_type", "group_code", "group_num", "list_num", "vat_group", "phone1", "e_mail",
                 "street", "city", "zip_code", "state", "country", "gstin", "gst_type", "credit_line"],
    "items": ["item_code", "item_name", "itms_grp_cod", "invnt_item", "sell_item", "prchse_item", "invntry_uom", "sal_unit_msr", "num_in_sale",
              "buy_unit_msr", "num_in_buy", "chapter_id", "vat_gourp_sa", "vat_group_pu", "dflt_wh", "price_1", "price_3"],
    "prices": ["item_code", "price_list", "price"],
    "gl_balances": ["account", "debit", "credit", "ref_date", "memo"],
    "bp_balances": ["card_code", "debit", "credit", "ref_date", "due_date", "ref"],
    "stock": ["item_code", "whs_code", "quantity", "price", "ref_date", "batches"],
}
TITLES = {"partners": "Business partners", "items": "Items", "prices": "Item prices", "gl_balances": "Opening balances (G/L accounts)",
          "bp_balances": "Opening balances (business partners)", "stock": "Opening stock"}


def template(kind: str) -> str:
    if kind not in KINDS:
        raise B1Error(f"Unknown import {kind}")
    return ",".join(KINDS[kind]) + "\n"


def parse(filename: str, content: bytes) -> list[dict]:
    """Rows of a CSV (comma or semicolon) or XLSX file as dicts by the header (lower case)."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        ws = load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        head = [str(h or "").strip().lower() for h in rows[0]]
        return [{head[i]: v for i, v in enumerate(r) if i < len(head) and head[i]} for r in rows[1:] if any(v not in (None, "") for v in r)]
    text = content.decode("utf-8-sig")
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t") if text.strip() else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [{(k or "").strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()} for r in reader
            if any((v or "").strip() for v in r.values() if isinstance(v, str))]


def _s(v) -> str | None:
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _d(v, what: str) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).replace(",", ""))
    except InvalidOperation as exc:
        raise B1Error(f"{what}: '{v}' is not a number") from exc


def _date(v, default: date | None = None) -> date | None:
    if v in (None, ""):
        return default
    if isinstance(v, date):
        return v if not hasattr(v, "date") else v.date()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise B1Error(f"'{s}' is not a date (YYYY-MM-DD or DD-MM-YYYY)")


def _yn(v, default: bool = True) -> bool:
    if v in (None, ""):
        return default
    return str(v).strip().upper() in {"Y", "YES", "1", "TRUE"}


def _row(session: Session, kind: str, r: dict, on: date) -> str:
    from app.services import documents, journal, masterdata

    if kind == "partners":
        code = _s(r.get("card_code"))
        req = masterdata.PartnerRequest(card_code=code or "", card_name=_s(r.get("card_name")) or "", card_type=(_s(r.get("card_type")) or "C").upper(),
                                        group_code=int(r["group_code"]) if _s(r.get("group_code")) else None,
                                        group_num=int(r["group_num"]) if _s(r.get("group_num")) else None,
                                        list_num=int(r["list_num"]) if _s(r.get("list_num")) else None, vat_group=_s(r.get("vat_group")),
                                        phone1=_s(r.get("phone1")), e_mail=_s(r.get("e_mail")), address=_s(r.get("street")), city=_s(r.get("city")),
                                        zip_code=_s(r.get("zip_code")), country=_s(r.get("country")) or "IN", lic_trad_num=_s(r.get("gstin")),
                                        credit_line=_d(r.get("credit_line"), "credit_line") or Decimal(0))
        bp = masterdata.create_partner(session, req)
        if _s(r.get("street")) or _s(r.get("state")) or _s(r.get("gstin")):
            for kind_ in ("B", "S"):
                masterdata.save_address(session, bp.card_code, kind_, "Main", {
                    "street": _s(r.get("street")), "city": _s(r.get("city")), "zip_code": _s(r.get("zip_code")), "state": _s(r.get("state")),
                    "country": _s(r.get("country")) or "IN", "gst_regn_no": _s(r.get("gstin")), "gst_type": _s(r.get("gst_type")) or ("R" if _s(r.get("gstin")) else "U")})
        return f"business partner {bp.card_code} added"
    if kind == "items":
        prices = {n: _d(r.get(f"price_{n}"), f"price_{n}") for n in (1, 2, 3) if _s(r.get(f"price_{n}"))}
        req = masterdata.ItemRequest(item_code=_s(r.get("item_code")) or "", item_name=_s(r.get("item_name")) or "",
                                     itms_grp_cod=int(r.get("itms_grp_cod") or 0), invnt_item=_yn(r.get("invnt_item")), sell_item=_yn(r.get("sell_item")),
                                     prchse_item=_yn(r.get("prchse_item")), invntry_uom=_s(r.get("invntry_uom")), sal_unit_msr=_s(r.get("sal_unit_msr")),
                                     num_in_sale=_d(r.get("num_in_sale"), "num_in_sale") or Decimal(1), buy_unit_msr=_s(r.get("buy_unit_msr")),
                                     num_in_buy=_d(r.get("num_in_buy"), "num_in_buy") or Decimal(1), chapter_id=_s(r.get("chapter_id")),
                                     vat_gourp_sa=_s(r.get("vat_gourp_sa")), vat_group_pu=_s(r.get("vat_group_pu")), dflt_wh=_s(r.get("dflt_wh")),
                                     prices=prices or None)
        item = masterdata.create_item(session, req)
        return f"item {item.item_code} added"
    if kind == "prices":
        price = _d(r.get("price"), "price")
        if price is None or price < 0:
            raise B1Error("Enter a price (not negative)")
        masterdata.set_price(session, _s(r.get("item_code")) or "", int(r.get("price_list") or 0), price)
        return f"price of {r.get('item_code')} in list {r.get('price_list')} = {price}"
    if kind in {"gl_balances", "bp_balances"}:
        from app.services.admin import company  # noqa: F401
        from app.models.finance import AccountDetermination

        when = _date(r.get("ref_date"), on)
        det = session.get(AccountDetermination, str(when.year))
        if det is None:
            raise B1Error(f"No G/L account determination for {when.year}")
        debit, credit = _d(r.get("debit"), "debit") or Decimal(0), _d(r.get("credit"), "credit") or Decimal(0)
        if (debit and credit) or not (debit or credit) or debit < 0 or credit < 0:
            raise B1Error("Enter either a debit or a credit opening balance")
        line = journal.JournalLineRequest(account=_s(r.get("account")) if kind == "gl_balances" else None,
                                          card_code=_s(r.get("card_code")) if kind == "bp_balances" else None, debit=debit, credit=credit,
                                          due_date=_date(r.get("due_date"), when) if kind == "bp_balances" else None, ref1=_s(r.get("ref")))
        offset = journal.JournalLineRequest(account=det.opening_bal, debit=credit, credit=debit, line_memo="Opening balance")
        je = journal.post_entry(session, journal.JournalRequest(ref_date=when, memo=(_s(r.get("memo")) or "Opening balance")[:50],
                                                                ref3="DTW", manual=kind == "gl_balances", lines=[line, offset]))
        return f"opening balance posted (journal entry {je.number})"
    if kind == "stock":
        nums = _s(r.get("batches"))
        batches_ = None
        if nums:  # LOT:qty@expiry; ...
            batches_ = []
            for part in nums.split(";"):
                num, _, rest = part.strip().partition(":")
                q, _, exp = rest.partition("@")
                batches_.append({"number": num.strip(), "quantity": _d(q or "1", "batch quantity"), "exp_date": exp.strip() or None})
        doc = documents.create_document(session, documents.DocumentRequest(
            obj="59", doc_date=_date(r.get("ref_date"), on), comments="Opening stock (import)", ref2="DTW",
            lines=[documents.DocLineRequest(item_code=_s(r.get("item_code")), quantity=_d(r.get("quantity"), "quantity") or Decimal(0),
                                            whs_code=_s(r.get("whs_code")), price=_d(r.get("price"), "price"), batches=batches_)]))
        return f"goods receipt {doc.doc_num}"
    raise B1Error(f"Unknown import {kind}")


def run_import(kind: str, filename: str, content_b64: str, dry_run: bool = True, all_or_nothing: bool = False,
               on: date | None = None) -> dict:
    if kind not in KINDS:
        raise B1Error(f"Unknown import {kind}")
    try:
        content = base64.b64decode(content_b64)
    except (ValueError, TypeError) as exc:
        raise B1Error("The file cannot be read") from exc
    rows = parse(filename, content)
    if not rows:
        raise B1Error("The file has no rows")
    missing = [c for c in KINDS[kind][:2] if c not in rows[0]]
    if missing:
        raise B1Error(f"Missing columns: {', '.join(missing)} (download the template)")
    results, ok = [], 0
    conn = _import_engine().connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint", autoflush=False)
    try:
        for n, r in enumerate(rows, start=2):  # row 1 is the header
            try:
                msg = _row(session, kind, r, on or date.today())
                session.commit()
                results.append({"row": n, "ok": True, "message": msg})
                ok += 1
            except (B1Error, ValueError, TypeError, KeyError) as exc:
                session.rollback()
                results.append({"row": n, "ok": False, "message": str(exc).strip("'\"")})
        failed = len(rows) - ok
        keep = not dry_run and not (all_or_nothing and failed)
        if keep:
            outer.commit()
        else:
            outer.rollback()
    finally:
        session.close()
        conn.close()
    return {"kind": kind, "title": TITLES[kind], "rows": len(rows), "ok": ok, "failed": len(rows) - ok, "dry_run": dry_run,
            "imported": ok if keep else 0, "results": results}
