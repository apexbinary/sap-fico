"""End-to-end check for business partners and inventory master data.

Run after app.seed (rerunnable):  python -m app.verify_masterdata
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models.finance import Account
from app.models.inventory import ItemWarehouse, Warehouse
from app.models.partners import BusinessPartner
from app.services import journal, masterdata
from app.services.admin import B1Error
from app.services.journal import JournalLineRequest as L
from app.services.journal import JournalRequest

D = Decimal


def _rejects(fn, why: str) -> None:
    try:
        fn()
    except B1Error as exc:
        print(f"   rejected ({why}): {exc}")
    else:
        raise AssertionError(f"expected rejection: {why}")


def main() -> None:
    s = SessionLocal()
    try:
        # 1) business partner master data and validation
        if s.get(BusinessPartner, "CVERIFY") is None:
            masterdata.create_partner(s, masterdata.PartnerRequest(
                card_code="cverify", card_name="Verify Customer", card_type="C", group_code=100, group_num=1,
                list_num=2, vat_group="OCS18"))
        bp = s.get(BusinessPartner, "CVERIFY")
        assert bp.deb_pay_acct == "114000", "customer defaults to the A/R control account"
        print(f"1 Customer {bp.card_code} posts to control account {bp.deb_pay_acct}")
        _rejects(lambda: masterdata.create_partner(s, masterdata.PartnerRequest(
            card_code="CVERIFY", card_name="x", card_type="C")), "duplicate code")
        _rejects(lambda: masterdata.create_partner(s, masterdata.PartnerRequest(
            card_code="XBAD1", card_name="x", card_type="C", deb_pay_acct="411000")), "not a control account")
        _rejects(lambda: masterdata.create_partner(s, masterdata.PartnerRequest(
            card_code="XBAD2", card_name="x", card_type="S", group_code=100)), "customer group for a vendor")
        _rejects(lambda: masterdata.create_partner(s, masterdata.PartnerRequest(
            card_code="XBAD3", card_name="x", card_type="S", vat_group="OCS18")), "output tax group for a vendor")

        # 2) journal entry with a business partner line: control account, BP balance, open amount
        ar_before, bal_before = s.get(Account, "114000").curr_total, bp.balance
        je = journal.post_entry(s, JournalRequest(ref_date=date(2026, 4, 1), memo="Service charged", lines=[
            L(card_code="CVERIFY", debit=D("119")), L(account="412000", credit=D("100")),
            L(account="216000", credit=D("19"))]))
        line = je.lines[0]
        print(f"2 JE {je.number}: BP line {line.short_name} on {line.account}, open {line.bal_due_deb}; "
              f"BP balance {bp.balance}")
        assert line.short_name == "CVERIFY" and line.account == "114000" and line.bal_due_deb == D("119")
        assert bp.balance == bal_before + D("119")
        assert s.get(Account, "114000").curr_total == ar_before + D("119")
        assert je.lines[1].contra_act == "CVERIFY"

        rev = journal.reverse_entry(s, je.trans_id)
        assert bp.balance == bal_before and s.get(Account, "114000").curr_total == ar_before
        assert je.lines[0].bal_due_deb == 0 and rev.lines[0].bal_due_cred == 0
        print(f"   reversed by JE {rev.number}: BP balance back to {bp.balance}, open amounts settled")

        bp.frozen_for = "Y"
        s.commit()
        _rejects(lambda: journal.post_entry(s, JournalRequest(ref_date=date(2026, 4, 2), lines=[
            L(card_code="CVERIFY", debit=D("10")), L(account="412000", credit=D("10"))])), "inactive partner")
        bp.frozen_for = "N"
        s.commit()

        # 3) items: stock rows in every warehouse, prices by price list (own, base x factor, partner)
        if s.get(Warehouse, "VER") is None:
            masterdata.create_warehouse(s, "ver", "Verify Warehouse")
        code = "VERIFY-ITEM"
        if s.get(ItemWarehouse, (code, "01")) is None:
            masterdata.create_item(s, masterdata.ItemRequest(
                item_code=code, item_name="Verify item", itms_grp_cod=100, invntry_uom="Each",
                vat_gourp_sa="OCS18", vat_group_pu="ICS18", dflt_wh="01", prices={1: D("200"), 3: D("120")}))
        whs = set(s.scalars(select(Warehouse.whs_code)))
        stock = set(s.scalars(select(ItemWarehouse.whs_code).where(ItemWarehouse.item_code == code)))
        assert stock == whs, f"stock rows {stock} != warehouses {whs}"
        base, wholesale, purchase = (masterdata.item_price(s, code, n) for n in (1, 2, 3))
        print(f"3 Item {code}: stock rows in {sorted(stock)}; base {base}, wholesale {wholesale}, purchase {purchase}")
        assert (base, wholesale, purchase) == (D("200.00"), D("180.00"), D("120.00"))
        assert masterdata.partner_price(s, "CVERIFY", code) == D("180.00"), "partner uses its price list"
        _rejects(lambda: masterdata.create_item(s, masterdata.ItemRequest(
            item_code="XBAD", item_name="x", itms_grp_cod=100, vat_gourp_sa="ICS18")), "input tax group as sales tax")
        _rejects(lambda: masterdata.create_item(s, masterdata.ItemRequest(
            item_code="XBAD", item_name="x", itms_grp_cod=100, card_code="CVERIFY")), "customer as preferred vendor")
        print("\nOK - business partners post through their control accounts; items, warehouses and prices are consistent.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
