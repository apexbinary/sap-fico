# Cross-module dependency matrix

Every master / concept that exists in the system, against every screen that needs it in SAP Business One.
A module built later must reach the screens built before it. When a concept or a screen is added, add its
rows here **in the same commit**; `tools/ui_contract.py` opens every ✅ row in the browser and fails when the
field is missing (run it with the demo server: `python tools/ui_contract.py http://127.0.0.1:8000`).

Columns: **Screen** (hash URL), **Setup** (actions before the check: `select:<css>=<value>`, `click:<css>`,
separated by `;`), **Field** (CSS selector that must exist; `a & b` = all of them, `a, b` = any of them), **Status** ✅ checked / ⏸ not built (reason).

| Concept | Screen | URL | Setup | Field | Status |
|---|---|---|---|---|---|
| Warehouse | A/R invoice line | #/doc?obj=13 | | #d-lines .l-whs | ✅ |
| Warehouse | Sales order line | #/doc?obj=17 | | #d-lines .l-whs | ✅ |
| Warehouse | Delivery line | #/doc?obj=15 | | #d-lines .l-whs | ✅ |
| Warehouse | Return line | #/doc?obj=16 | | #d-lines .l-whs | ✅ |
| Warehouse | A/R credit memo line | #/doc?obj=14 | | #d-lines .l-whs | ✅ |
| Warehouse | Sales quotation line | #/doc?obj=23 | | #d-lines .l-whs | ✅ |
| Warehouse | Purchase order line | #/doc?obj=22 | | #d-lines .l-whs | ✅ |
| Warehouse | Goods receipt PO line | #/doc?obj=20 | | #d-lines .l-whs | ✅ |
| Warehouse | Goods return line | #/doc?obj=21 | | #d-lines .l-whs | ✅ |
| Warehouse | A/P invoice line | #/doc?obj=18 | | #d-lines .l-whs | ✅ |
| Warehouse | A/P credit memo line | #/doc?obj=19 | | #d-lines .l-whs | ✅ |
| Warehouse | Purchase quotation line | #/doc?obj=540000006 | | #d-lines .l-whs | ✅ |
| Warehouse | Down payment line (items) | #/doc?obj=203 | | #d-lines .l-whs | ✅ |
| Warehouse | Goods receipt line | #/doc?obj=59 | | #d-lines .l-whs | ✅ |
| Warehouse | Goods issue line | #/doc?obj=60 | | #d-lines .l-whs | ✅ |
| Warehouse | Inventory transfer header from / to | #/doc?obj=67 | | #d-from_whs & #d-to_whs | ✅ |
| Warehouse | Inventory transfer line from / to | #/doc?obj=67 | | #d-lines .l-from & #d-lines .l-whs | ✅ |
| Warehouse | Stock per warehouse on a document line | #/doc?obj=13 | select:#d-card_code=C10000; select:#d-lines .l-item=A00001 | #d-lines .l-stock | ✅ |
| Warehouse | Item master default warehouse | #/items?code=A00001 | | #i-dflt_wh, #it-dflt_wh, [id$='-dflt_wh'] | ✅ |
| Warehouse | Item master stock per warehouse | #/items?code=A00001 | | .ow-min | ✅ |
| Warehouse | Bill of materials header / components | #/boms?code=new | click:a[href='#/boms?code='] | #bm-wh | ✅ |
| Warehouse | Production order receipt / component warehouse | #/production-orders?id= | | #no-warehouse & #no-lines .nl-whs | ✅ |
| Warehouse | Inventory counting | #/counting | | [id$='-whs_code'], .whs, select | ✅ |
| Warehouse | Opening stock | #/opening-balances?kind=items | | [id$='-whs_code'] | ✅ |
| Warehouse | Inventory audit report filter | #/inventory-audit | | #ia-whs | ✅ |
| Warehouse | Batches / serial numbers report | #/batches | | select, [id*='whs'] | ✅ |
| Warehouse | MRP: warehouses in the run | — | | — | ⏸ MRP plans all nettable warehouses together (B1 scenario warehouse selection not built) |
| Batch / serial | Document lines (managed items) | #/doc?obj=20 | select:#d-card_code=V10000 | #d-lines .l-bat | ✅ |
| Batch / serial | Goods receipt / issue lines | #/doc?obj=59 | | #d-lines .l-bat | ✅ |
| Batch / serial | Batches report | #/batches | | table | ✅ |
| Batch / serial | Production issue / receipt of managed items | — | | — | ⏸ batches / serials chosen automatically (FEFO) on production issue; receipt via API only |
| Batch / serial | Opening stock | — | | — | ⏸ managed items: enter a goods receipt with their numbers |
| Unit of measure | Document lines | #/doc?obj=13 | | #d-lines .l-uom | ✅ |
| Unit of measure | Item master purchasing / sales units | #/items?code=A00001 | | [id$='-buy_unit_msr'] & [id$='-sal_unit_msr'] | ✅ |
| Project | Sales / purchasing document header | #/doc?obj=13 | | #d-project | ✅ |
| Project | Document lines | #/doc?obj=13 | | #d-lines .l-prj | ✅ |
| Project | Inventory document lines | #/doc?obj=59 | | #d-lines .l-prj | ✅ |
| Project | Journal entry lines | #/journal-entry | | .je-prj | ✅ |
| Project | Payment header | #/payment?kind=incoming | | #p-prj_code | ✅ |
| Project | Payment account lines | #/payment?kind=outgoing | select:#p-doc_type=A | #p-acct .a-prj | ✅ |
| Project | Production order | #/production-orders?id= | | #no-project | ✅ |
| Project | Business partner master | #/partners?code=C10000 | | [id$='-project_cod'] | ✅ |
| Distribution rules | Journal entry lines | #/journal-entry | | .l-dim | ✅ |
| Distribution rules | Document lines | #/doc?obj=13 | | #d-lines .l-dim | ✅ |
| Distribution rules | Freight lines | #/doc?obj=13 | click:#d-fr-add | #d-freight .l-dim | ✅ |
| Distribution rules | Payment account lines | #/payment?kind=outgoing | select:#p-doc_type=A | #p-acct .l-dim | ✅ |
| Distribution rules | Recurring postings | #/recurring?code= | | .l-dim | ✅ |
| Distribution rules | Production order (variance) | #/production-orders?id= | | #no-ocr_code | ✅ |
| Distribution rules | Fixed asset depreciation / budgets | — | | — | ⏸ depreciation and budgets by distribution rule not built |
| Sales employee | Sales / purchasing documents | #/doc?obj=13 | | #d-slp_code | ✅ |
| Sales employee | Business partner master | #/partners?code=C10000 | | [id$='-slp_code'] | ✅ |
| Sales employee | Sales opportunity | #/opportunities?id= | | #op-slp | ✅ |
| Contact person | Sales / purchasing documents | #/doc?obj=13 | | #d-cntct_code | ✅ |
| Contact person | Payments | #/payment?kind=incoming | | #p-cntct_code | ✅ |
| Contact person | Sales opportunity | #/opportunities?id= | | #op-cpr | ✅ |
| Contact person | Activity | #/activities?id= | | #ac-cntct_code | ✅ |
| Contact person | Service call | #/service-calls?id= | | #sc-cntct_code | ✅ |
| User | Activity handled by | #/activities?id= | | #ac-attend_user | ✅ |
| User | Service call technician | #/service-calls?id= | | #sc-assignee | ✅ |
| Currency | Sales / purchasing documents | #/doc?obj=13 | | #d-doc_cur | ✅ |
| Currency | Payments | #/payment?kind=incoming | | #p-doc_curr | ✅ |
| Currency | Journal entry lines | #/journal-entry | | .je-cur | ✅ |
| Currency | Business partner master | #/partners?code=C10000 | | [id$='-currency'] | ✅ |
| Tax code | Document lines | #/doc?obj=13 | | #d-lines .l-vat | ✅ |
| Tax code | Freight lines | #/doc?obj=13 | click:#d-fr-add | #d-freight .fr-vat | ✅ |
| Tax code | Item master sales / purchase tax code | #/items?code=A00001 | | [id$='-vat_gourp_sa'] & [id$='-vat_group_pu'] | ✅ |
| Tax code | Business partner master | #/partners?code=C10000 | | [id$='-vat_group'] | ✅ |
| Payment terms | Business partner master | #/partners?code=C10000 | | [id$='-group_num'] | ✅ |
| Payment terms | Documents | #/doc?obj=13 | | #d-group_num | ✅ |
| Price list | Business partner master | #/partners?code=C10000 | | [id$='-list_num'] | ✅ |
| Price list | Inventory documents | #/doc?obj=59 | | #d-price_list | ✅ |
| TDS / TCS | Business partner master | #/partners?code=V10000 | | [id$='-wt_liable'] & [id$='-wt_codes'] | ✅ |
| TDS | Outgoing payment (advance) | #/payment?kind=outgoing | | #p-wt_on_account | ✅ |
| Customer / BP | Production order (made to order) | #/production-orders?id= | | #no-card_code | ✅ |
| Customer / BP | Service call / equipment / contract | #/service-calls?id= | | #sc-customer | ✅ |
| Item | Service call | #/service-calls?id= | | #sc-item_code | ✅ |
| Choose from list | Business partner fields | #/doc?obj=13 | | #d-card_code.cfl-field | ✅ |
| Choose from list | Item fields | #/doc?obj=13 | | #d-lines .l-item.cfl-field | ✅ |
| Choose from list | Account fields | #/journal-entry | | .je-acct.cfl-field | ✅ |
| Choose from list | Warehouse fields | #/doc?obj=13 | | #d-lines .l-whs.cfl-field | ✅ |
