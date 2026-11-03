"""End-to-end check for the data import and the Excel export.

Partners (CSV): the simulation saves nothing; the import adds the good row with its GSTIN address
and reports the bad row; "all or nothing" with a bad row imports nothing. Items (XLSX) with prices,
a price update, G/L and partner opening balances against the opening balance account, opening
stock with a batch. The export turns formatted amounts back into numbers.

Run after app.seed (rerunnable: fresh codes each run):  python -m app.verify_import
"""

from __future__ import annotations

import base64
import io
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.inventory import Item, ItemPrice
from app.models.partners import BusinessPartner, PartnerAddress
from app.services import dataimport

D = Decimal


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def main() -> None:
    s = SessionLocal()
    n = s.scalar(select(func.count()).select_from(BusinessPartner).where(BusinessPartner.card_code.like("D%"))) + 1
    good, bad, code_i = f"D{n:05d}", f"D{n:05d}X", f"IMP{n:04d}"
    s.close()
    csv_text = ("card_code,card_name,card_type,group_code,street,city,zip_code,state,gstin\n"
                f"{good},Imported Traders,C,100,5 Church Street,Bengaluru,560001,KA,29AAICI1234D1Z5\n"
                f"{bad},Broken,C,999,x,y,1,KA,\n")
    sim = dataimport.run_import("partners", "bp.csv", _b64(csv_text), dry_run=True)
    assert sim["ok"] == 1 and sim["failed"] == 1 and sim["imported"] == 0
    s = SessionLocal()
    assert s.get(BusinessPartner, good) is None
    s.close()
    aon = dataimport.run_import("partners", "bp.csv", _b64(csv_text), dry_run=False, all_or_nothing=True)
    assert aon["imported"] == 0
    real = dataimport.run_import("partners", "bp.csv", _b64(csv_text), dry_run=False)
    assert real["imported"] == 1 and not real["results"][1]["ok"] and "999" in real["results"][1]["message"]
    s = SessionLocal()
    addr = s.get(PartnerAddress, (good, "B", "Main"))
    assert addr is not None and addr.gst_regn_no == "29AAICI1234D1Z5" and addr.state == "KA"
    s.close()
    print(f"1 Partners CSV: simulation 1 ok / 1 error, nothing saved; all-or-nothing saved nothing; import added {good} "
          f"(GSTIN address), row 3 refused: {real['results'][1]['message'][:60]}")

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["item_code", "item_name", "itms_grp_cod", "invntry_uom", "chapter_id", "price_1", "price_3"])
    ws.append([code_i, "Imported stapler", 101, "Each", "84433210", 250, 140])
    buf = io.BytesIO()
    wb.save(buf)
    it = dataimport.run_import("items", "items.xlsx", base64.b64encode(buf.getvalue()).decode(), dry_run=False)
    assert it["imported"] == 1, it
    pr = dataimport.run_import("prices", "p.csv", _b64(f"item_code;price_list;price\n{code_i};1;275\n"), dry_run=False)
    assert pr["imported"] == 1
    s = SessionLocal()
    assert s.get(Item, code_i) is not None and s.get(ItemPrice, (code_i, 1)).price == 275
    s.close()
    print(f"2 Items XLSX: {code_i} with prices; price list 1 updated to 275 from a semicolon CSV")

    gl = dataimport.run_import("gl_balances", "gl.csv", _b64("account,debit,credit,ref_date\n112000,100000,,2026-04-01\n"), dry_run=False)
    bpb = dataimport.run_import("bp_balances", "bp.csv", _b64(f"card_code,debit,credit,ref_date,due_date,ref\n{good},5000,,2026-04-01,2026-05-01,OB-1\n"), dry_run=False)
    st = dataimport.run_import("stock", "st.csv", _b64(f"item_code,whs_code,quantity,price,ref_date,batches\n{code_i},01,10,140,2026-04-01,\n"), dry_run=False)
    assert gl["imported"] == bpb["imported"] == st["imported"] == 1, (gl, bpb, st)
    s = SessionLocal()
    assert s.get(BusinessPartner, good).balance == 5000 and s.get(Item, code_i).on_hand == 10
    s.close()
    print(f"3 Opening balances: bank 1,00,000 and {good} 5,000 against the opening balance account; opening stock 10 x 140")

    from app.api_import import ExportIn, SheetIn, export_xlsx
    from openpyxl import load_workbook

    resp = export_xlsx(ExportIn(title="Test", sheets=[SheetIn(name="Rows", headers=["A", "Amount"], rows=[["x", "1,23,456.50"], ["y", "-500.00"]])]))
    ws = load_workbook(io.BytesIO(resp.body)).active
    assert ws["B2"].value == 123456.5 and ws["B3"].value == -500
    print("4 Excel export: amounts formatted on screen are numbers in the workbook")
    print("\nOK - data import and Excel export work.")


if __name__ == "__main__":
    main()
