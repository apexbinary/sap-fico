"""End-to-end check that modules built later reach the screens / documents built before them.

Distribution rules on payment account lines (VPM4 OcrCode -> JDT1 ProfitCode) and on freight (xxx3 OcrCode ->
the freight revenue line); production orders with receipt warehouse, component warehouse, customer, sales order,
project (carried to the goods receipt) and distribution rule (on the variance); sales opportunities with sales
employee and contact person; activities with contact person and the user handling them; service calls with
the contact person.

Run after app.seed (rerunnable):  python -m app.verify_crossmodule
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.admin import AdditionalExpense, Project
from app.models.banking import OutgoingPaymentAccount
from app.models.documents import DOCUMENT_CLASSES, DOCUMENT_EXPENSES
from app.models.finance import JournalLine
from app.models.inventory import Item
from app.models.costacct import ProfitCenter
from app.models.partners import ContactPerson
from app.services import banking, costacct, crm, masterdata, production, service
from app.services import documents as docs
from app.services.banking import AccountLine
from app.services.banking import PaymentRequest as PR
from app.services.documents import DocLineRequest as DL
from app.services.documents import DocumentRequest as DR
from app.services.documents import ExpenseRequest

D = Decimal
DAY = date(2027, 3, 10)


def main() -> None:
    with SessionLocal() as s:
        n = s.scalar(select(func.count()).select_from(ProfitCenter)) + 1
        rule = f"X{n:04d}"
        costacct.save_center(s, {"prc_code": rule, "prc_name": "Cross-module check", "dim_code": 1})

        pay = banking.create_payment(s, PR(obj="46", doc_date=DAY, doc_type="A", trsfr_acct="112000", trsfr_sum=D(700),
                                           accounts=[AccountLine(acct_code="611000", sum_applied=D(700), descrip="Stationery", ocr_codes=[rule])]))
        row = s.scalar(select(OutgoingPaymentAccount).where(OutgoingPaymentAccount.doc_num == pay.doc_entry))
        line = s.scalar(select(JournalLine).where(JournalLine.trans_id == pay.trans_id, JournalLine.account == "611000"))
        assert row.ocr_code == rule and line.profit_code == rule, (row.ocr_code, line.profit_code)
        print(f"1 Outgoing payment {pay.doc_num} to account 611000 with distribution rule {rule}: stored on VPM4 and on the journal line")

        fr = s.scalars(select(AdditionalExpense).order_by(AdditionalExpense.expns_code)).first()
        inv = docs.create_document(s, DR(obj="13", doc_date=DAY, card_code="C10000", disc_prcnt=D(0),
                                         lines=[DL(item_code="S00001", quantity=D(1), price=D(1000))],
                                         expenses=[ExpenseRequest(expns_code=fr.expns_code, amount=D(500), ocr_codes=[rule])]))
        exp = s.scalar(select(DOCUMENT_EXPENSES["13"]).where(DOCUMENT_EXPENSES["13"].doc_entry == inv.doc_entry))
        frl = s.scalar(select(JournalLine).where(JournalLine.trans_id == inv.trans_id, JournalLine.account == fr.rev_acct))
        assert exp.ocr_code == rule and frl.profit_code == rule, (exp.ocr_code, frl.profit_code)
        print(f"2 A/R invoice {inv.doc_num} with freight {fr.expns_code} under rule {rule}: INV3 OcrCode and the freight revenue line carry it")

        k = s.scalar(select(func.count()).select_from(Item).where(Item.item_code.like("XM%"))) + 1
        prod, comp = f"XMP{k:03d}", f"XMC{k:03d}"
        for code, name in ((prod, "Cross-module product"), (comp, "Cross-module component")):
            masterdata.create_item(s, masterdata.ItemRequest(item_code=code, item_name=name, itms_grp_cod=101, invntry_uom="Each", dflt_wh="01",
                                                             chapter_id="84433210", prices={1: D(100), 3: D(60)}))
        docs.create_document(s, DR(obj="59", doc_date=DAY, lines=[DL(item_code=comp, quantity=D(10), price=D(50), whs_code="02")]))
        production.save_bom(s, prod, {"qauntity": 1, "to_wh": "01", "lines": [{"code": comp, "quantity": 2, "issue_mthd": "B"}]})
        prj = s.scalars(select(Project).where(Project.active == "Y").order_by(Project.prj_code)).first()
        po = production.create_order(s, prod, D(2), DAY, warehouse="02", card_code="C10000", comments="made to order", release=True,
                                     origin_num=4711, project=prj.prj_code if prj else None, ocr_code=rule, line_whs={"0": "02"})
        assert po.warehouse == "02" and po.lines[0].warehouse == "02" and po.card_code == "C10000" and po.origin_num == 4711 and po.ocr_code == rule
        production.receive(s, po.doc_entry, DAY, D(2))
        gr_cls = DOCUMENT_CLASSES["59"][0]
        gr = s.scalars(select(gr_cls).where(gr_cls.ref2 == f"WO{po.doc_num}").order_by(gr_cls.doc_entry.desc())).first()
        assert gr.lines[0].whs_code == "02" and gr.lines[0].project == (prj.prj_code if prj else None)
        print(f"3 Production order {po.doc_num}: receipt warehouse 02, component from 02 (backflushed), customer C10000, sales order 4711, "
              f"project {prj.prj_code if prj else '-'} on goods receipt {gr.doc_num}, rule {rule}")

        cp = s.scalars(select(ContactPerson).where(ContactPerson.card_code == "C10000")).first()
        opp = crm.create_opportunity(s, {"name": "Cross-module opportunity", "card_code": "C10000", "stage": 1, "max_sum_loc": 1000,
                                         "cpr_code": cp.cntct_code if cp else None, "slp_code": 1})
        assert opp.slp_code == 1 and opp.cpr_code == (cp.cntct_code if cp else None)
        act = crm.save_activity(s, {"action": "C", "details": "Call the contact", "card_code": "C10000", "recontact": DAY,
                                    "cntct_code": cp.cntct_code if cp else None, "attend_user": 1, "opr_id": opp.oppr_id})
        assert act.cntct_code == (cp.cntct_code if cp else None) and act.attend_user == 1 and act.opr_id == opp.oppr_id
        call = service.create_call(s, {"customer": "C10000", "subject": "Cross-module call", "cntct_code": cp.cntct_code if cp else None})
        assert call.cntct_code == (cp.cntct_code if cp else None)
        print(f"4 Opportunity {opp.oppr_id} (sales employee 1, contact {cp.name if cp else '-'}), activity {act.clg_code} (contact, handled by user 1), "
              f"service call {call.call_id} (contact) keep the contact person / employee")
    print("\nOK - later modules (distribution rules, warehouses, projects, contacts, employees) reach the earlier screens.")


if __name__ == "__main__":
    main()
