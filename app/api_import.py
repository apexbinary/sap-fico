"""REST endpoints: data import (templates, simulation, import) and Excel export of tables."""

from __future__ import annotations

import io
import re
from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api_finance import run
from app.services import dataimport

router = APIRouter()


@router.get("/import/kinds", tags=["Data import"], summary="What can be imported, with the columns")
def kinds() -> dict:
    return {k: {"title": dataimport.TITLES[k], "columns": v} for k, v in dataimport.KINDS.items()}


@router.get("/import/{kind}/template", tags=["Data import"], summary="CSV template of an import")
def template(kind: str) -> Response:
    text = run(lambda: dataimport.template(kind))
    return Response(text, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="import_{kind}.csv"'})


class ImportIn(BaseModel):
    filename: str = Field(..., max_length=200)
    content: str  # base64
    dry_run: bool = True
    all_or_nothing: bool = False
    on: date | None = None  # default posting date of balances / stock


@router.post("/import/{kind}", tags=["Data import"], summary="Simulate or run an import (CSV / XLSX)")
def do_import(kind: str, body: ImportIn) -> dict:
    return run(lambda: dataimport.run_import(kind, body.filename, body.content, body.dry_run, body.all_or_nothing, body.on))


class SheetIn(BaseModel):
    name: str = Field("Sheet", max_length=60)
    headers: list[str]
    rows: list[list]


class ExportIn(BaseModel):
    title: str = Field("export", max_length=80)
    sheets: list[SheetIn]


def _cell(v):
    """Numbers formatted on screen ('1,23,456.00', '-500.00') become numbers again."""
    if isinstance(v, str):
        s = v.strip()
        if re.fullmatch(r"-?[\d,]+(\.\d+)?", s) and any(ch.isdigit() for ch in s):
            try:
                return float(s.replace(",", ""))
            except ValueError:
                return v
    return v


@router.post("/export/xlsx", tags=["Export"], summary="Excel workbook of tables (one sheet each)")
def export_xlsx(body: ExportIn) -> Response:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)
    used = set()
    for sh in body.sheets or [SheetIn(headers=[], rows=[])]:
        name = re.sub(r"[\[\]\*\?/\\:]", " ", sh.name)[:31] or "Sheet"
        base, k = name, 2
        while name in used:
            name = f"{base[:28]} {k}"
            k += 1
        used.add(name)
        ws = wb.create_sheet(name)
        ws.append(sh.headers)
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in sh.rows:
            ws.append([_cell(v) for v in r])
        for col in ws.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(60, max(8, width + 2))
    buf = io.BytesIO()
    wb.save(buf)
    fname = re.sub(r"[^A-Za-z0-9_-]+", "_", body.title).strip("_") or "export"
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'})
