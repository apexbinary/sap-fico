# Field coverage register — SAP Business One forms

This register lists, form by form, the standard SAP Business One fields of every
feature built so far: the B1 table column, the **input type** (the UI keeps B1's
type: number fields are numeric inputs, B1 dropdowns are dropdowns, B1 checkboxes
are checkboxes, dates are date pickers, choose-from-list fields are selection
lists) and the status.

Status: **✅** implemented (stored, shown and editable where B1 allows it) ·
**🔒** shown read-only (system-maintained in B1 too) · **⏸** not built yet, with
the reason (see also *Excluded B1 functions* at the end).

Types: `text` · `number` · `date` · `dropdown` · `checkbox` · `choose` (choose-from
list: BP, item, G/L account) · `textarea`.

Keep this file current: when a feature is added, add its form here; when a ⏸ field
is built, change its status.

---

## Cockpit (home screen)

| Widget | Content | Status |
|---|---|---|
| Key figures | sales and purchases (month / year, net), receivables (overdue), payables (due in 7 days), cash and bank, inventory value, gross / net profit (year), open sales orders, tax payable this month; each tile opens its screen | ✅ |
| Sales and purchases (12 months) | monthly net sales vs purchases (bar chart) | ✅ |
| Customer aging / vendor aging | open items: not yet due, 1-30, 31-60, 61-90, 90+ days | ✅ |
| Top 5 customers / top 5 items | net sales of the year | ✅ |
| Open documents | sales orders to deliver, deliveries to invoice, purchase orders to receive, goods receipts to invoice | ✅ |
| Alerts | overdue items, credit limit exceeded, items below minimum stock, bank rows to reconcile, payment runs not executed | ✅ |
| Cash and bank | balance per cash / bank account | ✅ |
| Common functions | quick links to the most used forms | ✅ |
| Customize: show / hide and order widgets per user | OCPT (UserSign, WidgetId, Position, Visible) | ✅ ⚠ OCPT is not a verified B1 table name |
| Several cockpits per user, drag and drop, widget gallery / SAP Analytics (pervasive analytics designer), calendar and activities | | ⏸ |

---

## Administration

### Users and authorizations (OUSR / USR3)
| Field | Column | Type | Status |
|---|---|---|---|
| User code / user name / e-mail / department | USER_CODE / U_NAME / E_Mail / Department | text | ✅ |
| Superuser / locked | SUPERUSER / Locked | checkbox | ✅ at least one unlocked superuser remains; nobody locks himself |
| Password | PasswordHash (PBKDF2-SHA256, salted) | password | ✅ 8+ characters with letters and digits; own password changeable; reset by the administrator ends the user's sessions |
| Last login | LastLogin | — | 🔒 |
| General authorizations per area: full / read only / none | USR3 PermId / Permission | dropdown | ✅ enforced on every API call (read needs R or F, change needs F); reference data readable by all logged-in users |
| Login / logout, session cookie B1SESSION (or bearer token), 12 hours | OUSS (not a B1 table) | — | ✅ |
| Posting user | OJDT UserSign (user code), documents UserSign (user id) | — | 🔒 |
| Authorization groups, data ownership, branches, licenses, single sign-on, password expiry / history | | — | ⏸ |

### Company details (OADM)
| Field | Column | Type | Status |
|---|---|---|---|
| Company name | CompnyName | text | ✅ |
| Address | CompnyAddr | text | ✅ |
| Country | Country (OCRY) | dropdown | ✅ |
| State (GST place of business) | State (OCST) | dropdown | ✅ |
| Federal tax ID / GSTIN | TaxIdNum | text | ✅ |
| Telephone 1 / 2 | Phone1 / Phone2 | text | ✅ |
| Fax | Fax | text | ✅ |
| E-mail | E_Mail | text | ✅ |
| Manager | Manager | text | ✅ |
| Local currency | MainCurncy | dropdown | 🔒 fixed after setup (as in B1) |
| System currency | SysCurrncy | dropdown | 🔒 fixed after setup (as in B1) |
| Printing header, logo, alias name, accounting/basic-init tabs | various | — | ⏸ printing and localization settings are not in scope |

### Currencies (OCRN) and exchange rates (ORTT)
| Field | Column | Type | Status |
|---|---|---|---|
| Currency code / name / ISO code / decimals | CurrCode, CurrName, ISOCurrCod, Decimals | text / number | ✅ (seeded; rates maintained) |
| Rate date / currency / rate | RateDate, Currency, Rate | date / dropdown / number | ✅ |

### Posting periods (OFPR)
| Field | Column | Type | Status |
|---|---|---|---|
| Period code / name | Code, Name | text | 🔒 created by the system (monthly) |
| Posting date from / to | F_RefDate / T_RefDate | date | 🔒 |
| Due date from / to | F_DueDate / T_DueDate | date | ✅ enforced on postings |
| Document date from / to | F_TaxDate / T_TaxDate | date | ✅ enforced on postings |
| Fiscal year | Category | dropdown (filter) | ✅ |
| Period status | PeriodStat (N unlocked, C closing, Y locked) | dropdown | ✅ (closing period blocks postings like a lock; B1's authorization-based posting in closing periods is not built) |

### Numbering series (NNM1)
| Field | Column | Type | Status |
|---|---|---|---|
| Series / name / first / next / last number / default | Series, SeriesName, InitialNum, NextNumber, LastNum, IsDefault | — | 🔒 one default series "Primary" per document type; shown as the **Series** dropdown on every document and journal entry. ⏸ maintaining additional series |

### Tax setup (Administration -> Tax Setup)
B1 for India keeps tax codes in OSTC; here the tax codes are OVTG rows whose components are
STC1 lines (one tax authority each). Every part is maintained on the Tax Setup screen.

| Field | Column | Type | Status |
|---|---|---|---|
| Tax type code / name | OSTT Code / Name | text | ✅ |
| Tax authority code / name / tax type | OSTA Code / Name / Type | text / dropdown | ✅ |
| Output / input tax account | OSTA SalesTax / PurchTax | choose | ✅ validated: active, not a control account |
| Tax code / name / category (output / input) / inactive | OVTG Code / Name / Category / Inactive | text / dropdown / checkbox | ✅ |
| Components: tax authority / rate | STC1 STACode / EfctivRate | dropdown / number | ✅ rate of the code = sum of the components; each component rounded on its own |
| Rate / tax account of a code without components | OVTG Rate / Account | number / choose | ✅ |
| Used code locked (category, rate, components) | — | — | ✅ as in B1: create a new code and set the old one inactive |
| Effective from | EffecDate | date | ✅ column; ⏸ rate history (VTG1) |
| HSN / SAC code / description / goods or services | OCHP ChapterID / Dscription / ItemType | text / text / dropdown | ✅ items choose from it |
| Tax code determination: priority, sales / purchasing, BP, BP group, item, item group, HSN / SAC, place-of-supply state, intra / inter-state, tax code, description, active | OTCD | number / dropdown / choose / checkbox | ✅ first matching active rule (lowest priority); an entered code wins. ⚠ OTCD column names are descriptive (B1 uses generic key fields) |
| GST place of supply | OADM State vs CRD1 State | — | ✅ intra-state code (CGST + SGST) and inter-state code (IGST) of the same rate are switched automatically |
| Tax report (GST summary): output, input, net payable by component and tax code | — | report | ✅ |
| GSTR-1 / GSTR-3B filing formats, e-invoicing (IRN), e-way bill, TDS / TCS (withholding tax), reverse charge | — | — | ⏸ not built |

### Payment terms (OCTG)
| Field | Column | Type | Status |
|---|---|---|---|
| Payment terms code | PymntGroup | text | ✅ |
| Due date based on (posting / document / system date) | BslineDate | dropdown | ✅ used in due dates |
| Start from (month start / half month / month end) | PayDuMonth | dropdown | ✅ used in due dates |
| + Months / + Days | ExtraMonth / ExtraDays | number | ✅ |
| Tolerance days | TolDays | number | ✅ |
| Total discount % | VolumDscnt | number | ✅ |
| Price list | ListNum | dropdown | ✅ |
| Max. credit / commitment limit | CredLimit / ObligLimit | number | ✅ |
| Cash discount | CdcCode (OCDC) | dropdown | ✅ |
| Installments: number and plan (+ months, + days, share %) | InstNum / CTG1 InstMonth, InstDays, InstPrcnt | number | ✅ shares total 100 % |
| Open incoming payment, interest on arrears | OpenRcpt, … | — | ⏸ interest with dunning |

### Cash discounts (OCDC / CDC1)
| Field | Column | Type | Status |
|---|---|---|---|
| Code / name | Code / Name | text | ✅ |
| Tiers: within days / discount % | CDC1 NumOfDays / Discount | number | ✅ the first tier the payment date falls into applies (days from the document date) |
| Discount by date, VAT on cash discount, discount on freight | ByDate, … | — | ⏸ |

### Sales employees / buyers (OSLP)
| Field | Column | Type | Status |
|---|---|---|---|
| Name / commission % / telephone / e-mail / remarks / active | SlpName, Commission, Telephone, Email, Memo, Active | text / number / checkbox | ✅ |
| Commission group, employee link | GroupCode, EmpID | — | ⏸ commission groups and HR (OHEM) not in scope |

### Projects (OPRJ), manufacturers (OMRC), transaction codes (OTRC), countries (OCRY), states (OCST)
| Field | Column | Type | Status |
|---|---|---|---|
| Project code / name / valid from / to / active | PrjCode, PrjName, ValidFrom, ValidTo, Active | text / date / checkbox | ✅ validated on postings |
| Manufacturer name | FirmName | text | ✅ |
| Transaction code / description | TrnsCode, TrnsCodDsc | text | ✅ |
| Country code / name; state code / name / country / GST state code | Code, Name; Code, Name, Country, GSTCode | dropdown sources | ✅ (seeded; all Indian states with GST codes) |

---

## Financials

### Chart of accounts — G/L account (OACT)
| Field | Column | Type | Status |
|---|---|---|---|
| Level / drawer | Levels / GroupMask | — | 🔒 from the tree |
| G/L account | AcctCode | text | ✅ |
| Name / foreign name | AcctName / FrgnName | text | ✅ |
| Title / active account | Postable | checkbox | ✅ |
| Parent (title account) | FatherNum | dropdown | ✅ |
| Account type (sales / expenditure / other) | ActType | dropdown | ✅ |
| Currency | ActCurr | dropdown | ✅ |
| Control account | LocManTran | checkbox | ✅ |
| Cash account | Finanse | checkbox | ✅ |
| Block manual posting | BlocManPos | checkbox | ✅ enforced on manual JEs |
| Inactive | FrozenFor | checkbox | ✅ |
| Project | Project | dropdown | ✅ |
| Remarks | Details | textarea | ✅ |
| Balance | CurrTotal | number | 🔒 |
| Confidential, revaluation, relevant for cost accounting, dimensions, external code, valid/frozen date ranges | Protected, RevalMatch, Dim1Relvnt, ExportCode, … | — | ⏸ cost accounting and exchange-rate revaluation not in scope |

### Journal entry — header (OJDT)
| Field | Column | Type | Status |
|---|---|---|---|
| Series | Series | dropdown | 🔒 default series |
| Number | Number | — | 🔒 |
| Posting date / due date / document date | RefDate / DueDate / TaxDate | date | ✅ |
| Remarks | Memo | text | ✅ |
| Trans. code | TransCode (OTRC) | dropdown | ✅ |
| Ref. 1 / 2 / 3 | Ref1 / Ref2 / Ref3 | text | ✅ |
| Project | Project | dropdown | ✅ |
| Origin / origin no. / trans. no. | TransType / BaseRef / TransId | text | 🔒 (link to the source document) |
| Reverse / reversal date | AutoStorno / StornoDate | checkbox / date | ✅ the reversal is posted on the reversal date |
| Reversal link | StornoToTr | — | 🔒 |
| Total (LC / FC), transaction currency | LocTotal / FcTotal / TransCurr | number | 🔒 |
| Indicator, template (recurring / percentage), blanket agreement, stamp tax, fixed exchange rate | Indicator, … | — | ⏸ localization and recurring postings not built |

### Journal entry — lines (JDT1)
| Field | Column | Type | Status |
|---|---|---|---|
| G/L acct / BP code | Account / ShortName | choose | ✅ |
| G/L acct / BP name | — | text | 🔒 |
| Control account (BP lines) | Account | — | 🔒 |
| Debit / credit (LC) | Debit / Credit | number | ✅ |
| Due date | DueDate | date | ✅ |
| Line remarks | LineMemo | text | ✅ |
| Ref. 1 / 2 / 3 (line) | Ref1 / Ref2 / Ref3Line | text | ✅ (Ref. 3 line via API) |
| Project | Project | dropdown | ✅ |
| Contra account | ContraAct | — | 🔒 |
| Tax group | VatGroup | — | 🔒 set on automatic tax lines |
| Open amount (BP lines) | BalDueDeb / BalDueCred | — | 🔒 |
| Currency / debit (FC) / credit (FC) | FCCurrency / FCDebit / FCCredit | dropdown / number | ✅ local amounts at the rate of the posting date |
| Open amount (FC) of partner lines | BalFcDeb / BalFcCred | — | 🔒 reduced by payments and reconciliations |
| Distribution rules, tax amount, base amount, system currency amounts | OcrCode, … | — | ✅ distribution rules (see Cost accounting); ⏸ system-currency reporting |

### Dunning (Business Partners -> Dunning Wizard)
| Field | Column | Type | Status |
|---|---|---|---|
| Dunning term code / name / interest % p.a. / straight to highest level / minimum days between letters | ODUT Code / Name / Interest / Highest / DaysBtwn | text / number / checkbox | ✅ |
| Levels: after days overdue / fee / minimum balance / letter text | DUT1 Days / Fee / MinBal / LetterText | number / text | ✅ |
| Dunning level / last dunning date of an open item | JDT1 DunnLevel / DunDate | — | 🔒 invoices, installments and journal entries |
| Wizard: date / customer / straight to highest / post interest and fees | ODWZ DunDate / — / Highest / PostFees | date / dropdown / checkbox | ✅ preview, then execute |
| Letters per customer: level, overdue total, interest, fee, posted journal entry; items with days overdue and old -> new level | DWZ1 / DWZ2 | — | 🔒 printable letter |
| ⚠ DWZ1 / DWZ2 (letters and their items) are not verified B1 table names | | | |
| Letter templates (layouts), e-mail sending, dunning of vendors with debit balances, interest by item days since due when not dunned before | | — | ⏸ interest runs from the due date for the first letter, then from the last dunning |

### Exchange rate differences (Financials)
| Field | Column | Type | Status |
|---|---|---|---|
| Execution date | OEXR RunDate | date | ✅ |
| Revalue: business partner open items / G/L accounts in FC | Category | dropdown | ✅ |
| Reversal date (business partners; default next day) | StornoDate | date | ✅ unrealized difference reversed automatically |
| Currencies | — | dropdown | ✅ one or all foreign currencies |
| Preview lines: BP / account, currency, open FC, open LC, rate, new LC, difference | EXR1 | — | 🔒 |
| Journal entry, total gain / loss | TransId / TotalGain / TotalLoss | — | 🔒 BP: control accounts vs unrealized gain / loss (713000 / 714000); G/L: account vs realized gain / loss |
| ⚠ OEXR / EXR1 (run and its lines) are not verified B1 tables; B1 keeps only the journal entries | | | |
| Conversion differences (system currency), revaluation of FC G/L accounts per open item | | — | ⏸ |

### Financial reports
Trial balance, balance sheet, profit and loss: period / as-of selection (date), account tree with title accounts — ✅.

---

## Business partners

### Business partner master data — header (OCRD)
| Field | Column | Type | Status |
|---|---|---|---|
| BP code | CardCode | text | ✅ |
| Type (customer / vendor / lead) | CardType | dropdown | ✅ |
| Name / foreign name | CardName / CardFName | text | ✅ |
| Group | GroupCode (OCRG) | dropdown | ✅ |
| Currency | Currency | dropdown | ✅ |
| Federal tax ID | LicTradNum | text | ✅ |
| Account balance / deliveries / orders | Balance / DNotesBal / OrdersBal | number | 🔒 |

### General tab
| Field | Column | Type | Status |
|---|---|---|---|
| Tel 1 / Tel 2 / mobile / fax | Phone1 / Phone2 / Cellular / Fax | text | ✅ |
| E-mail / web site | E_Mail / IntrntSite | text | ✅ |
| Contact person | CntctPrsn | dropdown | ✅ |
| Sales employee / buyer | SlpCode (OSLP) | dropdown | ✅ default on documents |
| BP project | ProjectCod | dropdown | ✅ default on documents |
| Remarks | Notes | text | ✅ |
| Active / inactive | FrozenFor | checkbox | ✅ |
| Shipping type, password, industry, territory, BP channel, language, alias, factoring, technician, valid/frozen date ranges | ShipType, Password, IndustryC, Territory, … | — | ⏸ sales-opportunity / service / shipping master data not in scope |

### Addresses tab (CRD1)
| Field | Column | Type | Status |
|---|---|---|---|
| Type (bill to / ship to) | AdresType | dropdown | ✅ |
| Address ID | Address | text | ✅ |
| Street / block / building / zip / city / county | Street, Block, Building, ZipCode, City, County | text | ✅ |
| Country / state | Country (OCRY) / State (OCST) | dropdown (state follows country) | ✅ |
| GSTIN / GST type (regular, unregistered, composition, SEZ) | GSTRegnNo / GstType | text / dropdown | ✅ GSTIN validated (format, state code) |
| Default bill-to / ship-to | BillToDef / ShipToDef | dropdown | ✅ default on documents |
| Street no., GLN, tax office | StreetNo, GlbLocNum, TaxOffice | — | ⏸ localization |

### Contact persons tab (OCPR)
| Field | Column | Type | Status |
|---|---|---|---|
| Contact ID | Name | text | ✅ |
| Title / first / middle / last name | Title, FirstName, MiddleName, LastName | text | ✅ |
| Position / address | Position / Address | text | ✅ |
| Tel 1 / Tel 2 / mobile / fax / e-mail | Tel1, Tel2, Cellolar, Fax, E_MailL | text | ✅ |
| Remarks 1 | Notes1 | text | ✅ |
| Active | Active | checkbox | ✅ |
| Date of birth, gender, profession, place of birth, password | BirthDate, Gender, Profession, … | — | ⏸ CRM personal data not in scope |

### Payment terms tab
| Field | Column | Type | Status |
|---|---|---|---|
| Payment terms | GroupNum (OCTG) | dropdown | ✅ due dates on invoices |
| Price list | ListNum (OPLN) | dropdown | ✅ default prices |
| Total discount % | Discount | number | ✅ default document discount |
| Credit limit / commitment limit | CreditLine / DebtLine | number | ✅ checked on documents (see Credit / commitment limit check) |
| Dunning term | DunTerm (ODUT) | dropdown | ✅ customers |
| Interest on arrears % p.a. | IntrstRate | number | ✅ else the dunning term's rate |
| Priority, effective discount groups, bank details, payment methods | … | — | ⏸ BP bank accounts and payment methods not in scope |

### Accounting tab
| Field | Column | Type | Status |
|---|---|---|---|
| Control account (A/R or A/P) | DebPayAcct | choose | ✅ |
| Tax group | VatGroup | dropdown | ✅ |
| Down payment clearing accounts, consolidating BP | DpmClear, FatherCard | — | ⏸ clearing account (down payments reconcile with the payment on account instead) and consolidation not built (withholding tax: see Withholding tax / TDS) |

### Remarks tab
| Field | Column | Type | Status |
|---|---|---|---|
| Remarks | Free_Text | textarea | ✅ |

Properties (64 checkbox properties), attachments and user-defined fields — ⏸ (not in scope).

---

## Inventory

### Item master data — header (OITM)
| Field | Column | Type | Status |
|---|---|---|---|
| Item No. / description / foreign name | ItemCode / ItemName / FrgnName | text | ✅ |
| Item type (items / labor / travel) | ItemType | dropdown | ✅ |
| Item group | ItmsGrpCod (OITB) | dropdown | ✅ |
| Inventory / sales / purchase item | InvntItem / SellItem / PrchseItem | checkbox | ✅ (inventory item fixed after creation, as in B1) |
| Bar code | CodeBars | text | ✅ |
| HSN / SAC code | ChapterID (OCHP) | dropdown | ✅ |
| UoM group, price list + unit price in the header | UgpEntry | — | ⏸ UoM groups; prices are maintained in the Prices grid |

### General tab
| Field | Column | Type | Status |
|---|---|---|---|
| Manufacturer | FirmCode (OMRC) | dropdown | ✅ |
| Manage serial / batch numbers | ManSerNum / ManBtchNum | checkbox | ✅ only without stock (see Batches and serial numbers) |
| Active / inactive | frozenFor | checkbox | ✅ |
| Additional identifier, shipping type, tax type, withholding liable, valid/frozen date ranges | SWW, ShipType, … | — | ⏸ |

### Purchasing data tab
| Field | Column | Type | Status |
|---|---|---|---|
| Preferred vendor | CardCode | choose | ✅ |
| Mfr catalog no. | SuppCatNum | text | ✅ |
| Purchasing UoM name / items per purchase unit | BuyUnitMsr / NumInBuy | text / number | ✅ purchasing documents: quantity in purchase units, NumPerMsr = NumInBuy, stock in inventory units (documents are in inventory units) |
| Tax group | VatGroupPu | dropdown | ✅ |
| Packaging UoM, quantity per package, customs group, dimensions / weight | PurPackMsr, PurPackUn, CstGrpCode, BLength1, … | — | ⏸ |

### Sales data tab
| Field | Column | Type | Status |
|---|---|---|---|
| Sales UoM name / items per sales unit | SalUnitMsr / NumInSale | text / number | ✅ sales documents: quantity in sales units, NumPerMsr = NumInSale, stock in inventory units |
| Tax group | VatGourpSa | dropdown | ✅ |
| Packaging UoM, quantity per package, dimensions / weight | SalPackMsr, SalPackUn, … | — | ⏸ |

### Inventory data tab
| Field | Column | Type | Status |
|---|---|---|---|
| Set G/L accounts by | GLMethod | dropdown | 🔒 item group |
| Inventory UoM | InvntryUom | text | ✅ |
| Default warehouse | DfltWH | dropdown | ✅ |
| Manage inventory by warehouse | ByWh | checkbox | ✅ |
| Minimum / maximum / required inventory | MinLevel / MaxLevel / ReorderQty | number | ✅ |
| Valuation method | EvalSystem | dropdown | 🔒 moving average (FIFO / standard ⏸) |
| Item cost / inventory value / last purchase price | AvgPrice / StockValue / LastPurPrc | number | 🔒 |
| Warehouse grid: in stock / committed / ordered / available | OITW OnHand / IsCommited / OnOrder | number | 🔒 |
| Warehouse grid: minimum / maximum / locked | OITW MinStock / MaxStock / Locked | number / checkbox | ✅ |

### Planning data tab
| Field | Column | Type | Status |
|---|---|---|---|
| Lead time | LeadTime | number | ✅ |
| Minimum order quantity | MinOrdrQty | number | ✅ |
| Planning method, procurement method, order interval, order multiple, tolerance days | PlaningSys, PrcrmntMtd, OrdrIntrvl, OrdrMulti, … | — | ⏸ MRP not in scope |

### Remarks
| Field | Column | Type | Status |
|---|---|---|---|
| Remarks | UserText | textarea | ✅ |

Production data, properties, attachments, picture — ⏸.

### Prices (ITM1) and price lists (OPLN)
| Field | Column | Type | Status |
|---|---|---|---|
| Item price per price list | ITM1 Price | number | ✅ |
| Price list name | ListName | text | ✅ |
| Base price list | BASE_NUM | dropdown | ✅ |
| Factor | Factor | number | ✅ |
| Primary currency | PrimCurr | dropdown | ✅ |
| Active | ValidFor | checkbox | ✅ inactive lists cannot be assigned |
| Rounding method, group, additional currencies, valid from/to, authorization | RoundSys, GroupCode, AddCurr1, … | — | ⏸ |

### Warehouses (OWHS)
| Field | Column | Type | Status |
|---|---|---|---|
| Warehouse code / name | WhsCode / WhsName | text | ✅ |
| Street / block / building / zip / city / county | Street, Block, Building, ZipCode, City, County | text | ✅ |
| Country / state | Country / State | dropdown | ✅ |
| Drop-ship | DropShip | checkbox | ✅ |
| Nettable | Nettable | checkbox | ✅ |
| Location, warehouse accounts tab, bin locations, use tax | Location, BalInvntAc (per whs), BinActivat, … | — | ⏸ accounts are set by item group; bin locations not built |

### Item groups (OITB)
Group name and its G/L accounts (inventory, COGS, revenue, expense, price difference) — 🔒 seeded, shown on the item; ✅ maintained under Inventory -> Item Groups; ⏸ the further OITB accounts (exchange rate differences, goods clearing, …).

---

## Marketing documents (sales A/R and purchasing A/P)

Applies to sales quotation, order, delivery, return, A/R invoice, A/R credit memo,
purchase quotation, order, goods receipt PO, goods return, A/P invoice, A/P credit memo.

### Header, Logistics and Accounting tabs, footer (OQUT … ORPC)
| Field | Column | Type | Status |
|---|---|---|---|
| Customer / vendor | CardCode | choose | ✅ |
| Name | CardName | — | 🔒 |
| Contact person | CntctCode (OCPR) | dropdown | ✅ default from the BP |
| Customer / vendor ref. no. | NumAtCard | text | ✅ |
| Currency / rate | DocCur / DocRate | dropdown / number | ✅ default from the base document or the BP currency; rate of the posting date (ORTT) |
| No. / series | DocNum / Series | dropdown | 🔒 |
| Status | DocStatus / CANCELED | — | 🔒 |
| Posting date / delivery (due) date / document date | DocDate / DocDueDate / TaxDate | date | ✅ due date from payment terms |
| Item / service type | DocType | dropdown | ✅ |
| Sales employee / buyer | SlpCode | dropdown | ✅ default from the BP |
| Project | Project | dropdown | ✅ default from the BP |
| Bill to (address ID) / bill-to address | PayToCode / Address | dropdown / textarea | ✅ |
| Ship to (address ID) / ship-to address | ShipToCode / Address2 | dropdown / textarea | ✅ |
| Payment terms | GroupNum | dropdown | 🔒 from the BP (⏸ changing terms per document) |
| Federal tax ID | LicTradNum | text | 🔒 from the BP |
| Journal remark | JrnlMemo | text | ✅ |
| Remarks | Comments | textarea | ✅ |
| Total before discount / discount % / discount / tax / total | — / DiscPrcnt / DiscSum / VatSum / DocTotal | number | ✅ discount % default from the BP |
| Discount / tax / total in the document currency | DiscSumFC / VatSumFC / DocTotalFC | number | 🔒 FC documents |
| Paid to date (FC) | PaidFC | number | 🔒 |
| Applied amount / balance due (invoices, credit memos) | PaidToDate | number | 🔒 |
| Rounding, down payment, owner, shipping type, payment method, installments, indicator, cancellation date | RoundDif, DpmAmnt, OwnerCode, TrnspCode, PeyMethod, Installmnt, Indicator, … | — | ⏸ HR owner not built (down payments: see Down payments; freight: see Freight; installments: see Cash discount and installments) |

### Contents tab — lines (QUT1 … RPC1)
| Field | Column | Type | Status |
|---|---|---|---|
| Item No. / description | ItemCode / Dscription | choose / text | ✅ |
| Quantity / open quantity | Quantity / OpenQty | number | ✅ / 🔒 |
| UoM name | unitMsr | text | 🔒 sales / purchasing UoM of the item |
| Unit price / discount % / price after discount | PriceBefDi / DiscPrcnt / Price | number | ✅ / ✅ / 🔒 |
| Tax code / tax amount | VatGroup / VatSum | dropdown / number | ✅ / 🔒 |
| Total (LC) / gross price / gross total | LineTotal / PriceAfVAT / GTotal | number | 🔒 |
| Total (FC) / tax amount (FC) / gross total (FC) / currency / rate | TotalFrgn / VatSumFrgn / GTotalFC / Currency / Rate | number | 🔒 FC documents; prices are in the document currency |
| Warehouse | WhsCode | dropdown | ✅ |
| Delivery date (line) | ShipDate | date | ✅ |
| Project (line) | Project | dropdown | ✅ |
| Free text | FreeTxt | text | ✅ |
| Sales employee (line) | SlpCode | dropdown | ✅ via API (defaults to the header) |
| G/L account (service documents) | AcctCode | choose | ✅ |
| Item cost / gross profit | StockPrice / GrssProfit | number | 🔒 |
| Base document / target document | BaseType, BaseEntry, BaseLine, BaseRef / TargetType, TrgetEntry | — | 🔒 copy-from / copy-to |
| Row status | LineStatus | — | 🔒 |
| Distribution rules, tax only, blanket agreement, serial/batch numbers, BOM, alternative items | OcrCode, TaxOnly, AgrNo, … | — | ⏸ |

### Installments of invoices (INV6 / PCH6)
| Field | Column | Type | Status |
|---|---|---|---|
| Installment no. / due date / share % / amount (LC, FC) / paid (LC, FC) / status | InstlmntID / DueDate / InstPrcnt / InsTotal, InsTotalFC / PaidToDate, PaidFC / Status | — | 🔒 from the payment terms; one partner journal line per installment |
| Credit memo copied from an installment invoice | — | — | reconciled with the installments in a payment (no automatic reconciliation) |
| Installments of credit memos and other documents | RIN6, … | — | ⏸ |

### Approval procedures and alerts (Administration -> Approvals, Approval Procedures, Alert Settings; bell)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Approval stage: name, authorizers, approvals / rejections required | OWST, WST1 | text / multi-select / number | ✅ |
| Approval template: name, active, originators, document types, stages in order, conditions (document total, discount %, gross profit % with > >= < <=; none = always) | OWTM, WTM1-WTM4 | text / multi-select / dropdown / number | ✅ |
| Request: document validated and held (no document, no number), status pending / approved / rejected / added, reason, decisions with remarks | OWDD, WDD1 | — | ✅ the held document is kept as JSON (B1: draft ODRF) |
| Approve / reject per stage, next stage, originator adds the approved document | | button | ✅ |
| Alerts: items below minimum stock, overdue customer items (days), customers over the credit limit, batches expiring (days), approval requests; recipients, active | OALT, ALT1 | checkbox / number / multi-select | ✅ evaluated when opened; bell with count |
| User-defined query alerts, alert frequency / e-mail / SMS, approvals of payments / journal entries / item master, drafts editable before approval | | — | ⏸ |

### Aging, account statement, cash flow (Financial Reports)
| Report | Source | Status |
|---|---|---|
| Customer / vendor aging on a date: not due, 1-30, 31-60, 61-90, 91-120, over 120 days by due date, netted per partner, document detail | JDT1 BalDueDeb / BalDueCred / DueDate | ✅ |
| Account statement of a business partner: opening balance, movements with running balance, closing balance, open items, print / PDF | JDT1 partner lines | ✅ |
| Cash flow (direct): opening / closing cash and bank (OACT Finanse), receipts and payments by origin and by account | JDT1 | ✅ |
| Aging by document date, in FC, statements by e-mail, cash flow forecast (open items, orders), indirect cash flow statement | | ⏸ |

### Fixed assets (Financials -> Fixed Assets)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Asset class: accounts (asset, accumulated depreciation, depreciation expense, retirement gain / loss), method straight line / written-down value, useful life / rate | OACS | text / dropdown / number | ✅ seeded OFFEQ, COMP, FURN (not B1-verified: B1 uses items of type F and depreciation areas) |
| Asset: number, description, class, serial no., location, salvage value, status | OFAS | text / dropdown / number | ✅ |
| Capitalization (date, amount, offset account) | FAS1 TranType C | date / number / dropdown | ✅ |
| Depreciation run per month (preview, post, reverse latest), pro rata from the capitalization month, last SL month takes the rest | FAS1 TranType D | month | ✅ months in order |
| Retirement (sale / scrap) with gain / loss | FAS1 TranType R | date / number / dropdown | ✅ needs depreciation up to the previous month |
| Asset register (cost, accumulated depreciation, book value) | | — | ✅ |
| Capitalization from A/P invoices, partial retirement, transfers, several depreciation areas (books / tax), unplanned depreciation, Income Tax Act block-of-assets report | | — | ⏸ |

### Period-end closing (Administration -> Period-End Closing)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Financial year, closing account (retained earnings, drawer 3), lock the periods | | number / dropdown / checkbox | ✅ |
| Closing entry: every P&L account's balance of the year to zero against the closing account, on the last day | OJDT TransType -3, Ref3 PEC:<year> | — | ✅ one per year; P&L report excludes it, balance sheet includes it |
| Cancel the closing (reversal, the year's periods unlocked) | | button | ✅ |
| Closing per period range, closing of BP / inventory accounts, opening balance transfer to a new company database | | — | ⏸ balance sheet accounts carry forward in one database |

### Recurring postings (Financials -> Recurring Postings)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Code, description, frequency (daily, weekly, monthly, quarterly, semiannually, annually, one time), next due date, valid until, number of postings, memo, active | ORCR RcurCode / RcurDesc / Frequency / NextDeu / ValidUntil / LimitRtrns / Memo / Active (+ Day) | text / dropdown / date / number / checkbox | ✅ |
| Template lines: G/L account or business partner, debit / credit, line memo, distribution rules (dimensions 1-2) | RCR1 | dropdown / number / text | ✅ balanced, at least two lines |
| Due postings up to a date, execution with catch-up, month ends kept, postings made / last posted | ORCR Instance / LastDate | — | ✅ journal entries with Ref3 RC:<code> |
| Reminder at login, recurring transactions of documents (A/R / A/P invoices), templates with tax codes | | — | ⏸ |

### Budgets (Financial Reports -> Budgets)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Budget scenario: name, financial year, ratio of the main budget, main budget | OBGS Name / FinancYear / InitRatio / MainBudget | text / number | ✅ the main budget of a year is created with its first budget |
| Account budget: annual debit / credit, monthly amounts | OBGT AcctCode / Instance / DebLTotal / CrdLTotal, BGT1 Line_ID / DebLTotal / CrdLTotal | dropdown / number | ✅ annual split equally or 12 months; credit side for revenue / liability accounts |
| Budget vs. actual per account, by month, to date, deviation and % | | — | ✅ |
| Budget check of postings: none / block expense accounts over the annual main budget | OADM BgtCheck | dropdown | ✅ warn mode, monthly / quarterly checks, purchase documents before posting ⏸ |
| Budget distribution methods (ascending / descending), budgets per profit center, budget report by project | | — | ⏸ |

### Cost accounting (Administration -> Cost Accounting, Financial Reports -> Profit Center Report)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Dimensions 1-5: name, description, active | ODIM DimCode / DimName / DimDesc / DimActive | text / checkbox | ✅ seeded: 1 Department, 2 Region active |
| Profit center: code, name, dimension, valid from / to, active (gets a direct rule) | OPRC PrcCode / PrcName / DimCode / ValidFrom / ValidTo / Active | text / dropdown / date / checkbox | ✅ |
| Distribution rule: code, name, dimension, shares per profit center, total, direct, active | OOCR OcrCode / OcrName / DimCode / OcrTotal / Direct / Active, OCR1 PrcCode / PrcAmount | text / dropdown / number | ✅ shares cannot change once the rule is used |
| Rules on journal entry lines and document lines (copied from the base line) | JDT1 ProfitCode / OcrCode2-5, xxx1 OcrCode-OcrCode5 | dropdown per active dimension | ✅ kept on revenue / expense postings |
| Profit center report: revenue, expenses, result per center (split by the shares), accounts, not assigned | | — | ✅ |
| Rules on payment / deposit lines, default rules per user / item / BP / warehouse, rule validity periods, budgets per center, cost accounting summary report | | — | ⏸ |

### Inventory counting and inventory posting (Inventory -> Inventory Counting)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Counting: number, count date, remarks, status; lines item / warehouse with the quantity in the warehouse when created | OINC DocNum / CountDate / Remarks / Status, INC1 ItemCode / WhsCode / InWhsQty | date / text / dropdowns | ✅ items, or a whole warehouse (and item group) |
| Counted, counted quantity, difference, batches / serial numbers of a surplus | INC1 Counted / CountQty / Difference / Batches | checkbox / number / text | ✅ |
| Inventory posting of the differences: surplus at item cost (goods receipt), shortage (goods issue), against the inventory offset accounts; counting closed | OIQR / IQR1 (GrEntry / GiEntry) | date | ✅ B1 posts the inventory posting itself; here through goods receipt / issue |
| Recount when the item moved after the counting was created; one open counting per item / warehouse | | — | ✅ |
| Multiple counters, counting by UoM, freeze items during counting, inventory opening balances, cycle count determination | | — | ⏸ |

### Item groups (Inventory -> Item Groups)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Code, name, inventory / COGS / revenue / expense / price difference accounts | OITB ItmsGrpCod / ItmsGrpNam / BalInvntAc / SaleCostAc / RevenuesAc / ExpensesAc / PriceDifAc | text / dropdown | ✅ the inventory account cannot change while items of the group have stock |
| Further accounts (variance, returns, exchange ...), planning data, default UoM group, cycle counting | | — | ⏸ |

### Batches and serial numbers (Item master, document lines, Inventory -> Batches and Serial Numbers)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Manage batch numbers / serial numbers (only without stock, not both) | OITM ManBtchNum / ManSerNum | checkbox | ✅ management method: on every transaction |
| Batch / serial number, expiry date, manufacturing date, admission date, notes | OBTN / OSRN DistNumber / ExpDate / MnfDate / InDate / Notes | text / date | ✅ entered on the receiving line (number:qty@expiry) |
| Quantity per warehouse | OBTQ / OSRQ Quantity | — | 🔒 always equals OITW OnHand |
| Allocation of every stock move (receipts, issues, transfers, returns), automatic selection (earliest expiry, not expired), base document's numbers on copied lines | OITL / ITL1 | — | ✅ |
| History of a number (traceability), canceled documents reverse their logs | OITL Reversed | — | ✅ |
| Batch attributes (attribute 1 / 2, status released / locked / not accessible), serial numbers on release only, bin locations, batch / serial number reports by date | | — | ⏸ |

### Units of measure on document lines
| Field / function | Column | Type | Status |
|---|---|---|---|
| UoM of the line (sales / purchase unit of the item, inventory unit on inventory documents; copied lines keep the base line's) | xxx1 unitMsr | text | 🔒 |
| Items per unit of the line | xxx1 NumPerMsr | number | 🔒 from OITM NumInSale / NumInBuy; stock, commitments and costs use Quantity x NumPerMsr |
| Default price = price list price (per inventory unit) x NumPerMsr; last purchase price per inventory unit | | — | ✅ |
| UoM groups (OUGP / UGP1), several UoMs per item, UoM chosen per line, packaging UoMs | | — | ⏸ |

### Down payments (A/R Down Payment ODPI 203, A/P Down Payment ODPO 204)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Down payment request: header, lines and tax like an invoice; not posted | ODPI / DPI1, ODPO / DPO1 | as invoices | ✅ |
| Paid by incoming / outgoing payment: amount on account, request PaidToDate | RCT2 / VPM2 InvType 203 / 204 | checkbox / number | ✅ local currency |
| Drawn on the final invoice: partner lines reconciled with the payment's amount on account, invoice PaidToDate, total drawn; request DpmAppl, closed when drawn | INV9 / PCH9 BaseAbs / DrawnSum (+ PayType / PayEntry / PayTrans / PayLine / DocLine), OINV / OPCH DpmAmnt, ODPI / ODPO DpmAppl | checkbox / number | ✅ partial draws; cancel of the invoice releases the down payment |
| Down payment invoice (posted, GST on advances), down payment percentage, clearing account (DpmClear), FC down payments, copy from orders | DpmPrcnt, DpmClear | — | ⏸ |

### Freight / additional expenses (Administration -> Freight, document form)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Code, name, revenue account, expense account, output / input tax code, SAC code, default amount | OEXD ExpnsCode / ExpnsName / RevAcct / ExpnsAcct / VatGroupO / VatGroupI / SACCode / FixAmnt | text / dropdown / number | ✅ seeded: 1 Freight, 2 Insurance, 3 Packing |
| Document freight lines: code, net amount, tax code, tax, gross; header total freight | QUT3 ... RPC3 ExpnsCode / LineTotal / TotalFrgn / VatGroup / VatPrcnt / VatSum / GrsAmount; TotalExpns / TotalExpFC | dropdown / number | ✅ no header discount, GST kind switched like lines, posted on invoices / credit memos |
| Freight in GST returns (SAC, taxable value), e-invoice (service item), print | | — | ✅ |
| Distribution method (to item cost / landed costs), freight copied from the base document, freight in installments by line, freight on inventory documents | DistrbMthd | — | ⏸ |

### Credit / commitment limit check (Administration Setup -> BP credit limit check)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Credit limit check: none / warn / block; document types (sales orders, deliveries, A/R invoices) | OADM CrdLmtChk / CrdLmtDocs | dropdown / multi-select | ✅ exposure = balance + open deliveries + open orders; copied value is not new exposure |
| Commitment limit check (balance, A/R invoices) | OADM CmtLmtChk | dropdown | ✅ |
| Warn mode: "Add anyway" on the document form | | button | ✅ |
| Approval procedure for exceeded limits, open checks in the commitment | | — | ⏸ |

### Withholding tax / TDS (Administration -> Withholding Tax, BP Accounting, A/P documents, TDS Report)
| Field / function | Column | Type | Status |
|---|---|---|---|
| Code, name, section, rate, rate without PAN (206AA), TDS account | OWHT WTCode / WTName / Section / Rate / RateNoPAN / Account | text / number / dropdown | ✅ seeded: 194C, 194H, 194I(a)/(b), 194J(a)/(b), 194Q (FY 2025-26 rates and thresholds) |
| Thresholds per invoice / per financial year, whole amount once crossed or only the excess | OWHT ThrSingle / ThrAnnual / ThrType | number / dropdown | ✅ |
| Category (invoice), base type (net excl. GST), inactive | OWHT Category / BaseType / Inactive | — / checkbox | ✅ payment category ⏸ |
| BP: subject to withholding tax, PAN, withholding tax codes | OCRD WTLiable / PANNo, CRD4 | checkbox / text / multi-select | ✅ PAN from the GSTIN when empty |
| Document: TDS lines (code, section, rate, base, amount, account, no PAN), total TDS, total payment due | PCH5 / RPC5, OPCH / ORPC WTSum / WTSumFC | — | 🔒 computed on posting; codes can be overridden through the API (wt_codes) — ⏸ in the form |
| Credit memo copied from an A/P invoice reverses its TDS in proportion | RPC5 | — | ✅ |
| TDS report: register, summary per section and month, deposit due date | | — | ✅ |
| TDS on payments, TCS (206C) on sales, lower deduction certificates (197), Form 26Q / 16A, challan entry | | — | ⏸ |

### E-documents: e-invoice (IRN) and e-way bill (Administration -> E-Documents, document panel)
| Field / function | Column | Type | Status |
|---|---|---|---|
| E-invoicing active, e-way bills active, mode test / live | OADM EInvoice / EWayBill / EDocMode | checkbox / dropdown | ✅ |
| Company street, city, PIN code | ADM1 Street / City / ZipCode | text | ✅ PIN checked (6 digits) |
| E-invoice JSON (INV-01 v1.1: TranDtls, DocDtls, SellerDtls, BuyerDtls, ShipDtls, ItemList, ValDtls, ExpDtls) of A/R invoices / credit memos | | download | ✅ B2B, SEZ, export; B2C refused |
| IRN (SHA-256 of GSTIN, FY, type, number), ack. no. / date, signed QR code | EDOC Irn / AckNo / AckDate / SignedQR | — | 🔒 test: made here (QR marked TEST); live: IRP response imported and its IRN checked |
| Cancel IRN: reason (1-4), remark, within 24 hours; document cancel blocked while an IRN / e-way bill is active | EDOC CnclReason / CnclRemark / CnclDate | dropdown / text | ✅ |
| E-way bill of A/R invoices and deliveries: transport mode, distance, vehicle no. / type, transporter ID / name, transport doc. no. / date | EDOC TransMode / Distance / VehicleNo / VehicleTyp / TransId / TransName / TransDocNo / TransDocDt | dropdown / number / text / date | ✅ required flag above 50,000 (goods) |
| E-way bill no., date, valid until (1 day per 200 km, ODC 20 km, until 23:59:59), Part B vehicle update, cancel within 24 hours | EDOC EwbNo / EwbDate / ValidUntil | — | ✅ Part A only (no vehicle) is not valid until Part B |
| IRN, ack. and QR code / e-way bill on the printed invoice | | — | ✅ |
| Register and documents still needing an IRN / e-way bill | | — | ✅ |
| Direct GSP / IRP API connection, e-way bill extension / consolidation / rejection, inward e-way bills, multi-vehicle | | — | ⏸ needs GSP credentials |

### GST returns (Financial Reports -> GST Returns)
| Table / element | Source | Status |
|---|---|---|
| Period: year, month | | number / dropdown | ✅ |
| GSTR-1 4A B2B (GSTIN, invoice no. / date / value, POS, reverse charge N, type R / SEZWP / SEZWOP, items by rate) | OINV / INV1, CRD1 GSTRegnNo / GstType, OCST GSTCode | ✅ |
| GSTR-1 5 B2CL (unregistered, inter-state, value > 1,00,000) and 7 B2CS (by POS, supply type and rate) | | ✅ |
| GSTR-1 6A exports (WPAY / WOPAY, POS 96), 9B CDNR / CDNUR (credit notes from A/R credit memos) | ORIN / RIN1 | ✅ shipping bill no. / port not kept |
| GSTR-1 8 nil-rated / exempt / non-GST, 12 HSN summary (B2B and B2C, UQC, qty), 13 documents issued (from-to, canceled) | OITM ChapterID, NNM1 | ✅ exempt and non-GST tax codes are reported as nil-rated |
| GSTR-3B 3.1 (a)-(e), 3.2 inter-state to unregistered / composition, 4 ITC (A/P invoices less A/P credit memos), 5 exempt inward, 6.1 payment with ITC set-off (IGST first, rule 88A) | OPCH / ORPC | ✅ |
| JSON for the GST portal offline tool (GSTR-1, GSTR-3B) | | download | ✅ layout of the offline tool, not validated against the portal |
| Checks before filing: GSTIN format, missing HSN / SAC, unknown place of supply, mixed intra / inter codes | | ✅ |
| Reverse charge, imports (IMPG / IMPS), ITC reversals / ineligible ITC, amendments (B2BA ...), GSTR-2B matching, e-invoice IRN / e-way bill, filing on the portal | | ⏸ |

### Printed documents (Print / PDF)
| Element | Source | Status |
|---|---|---|
| Title by type: Quotation, Sales Order, Delivery Challan, Sales Return, Tax Invoice, Credit Note, Request for Quotation, Purchase Order, Goods Receipt Note, Purchase Return, Purchase Invoice, Debit Note | ObjType | ✅ |
| Company with address, GSTIN, state and state code | OADM, OCST | ✅ |
| No., date, due / delivery date, customer reference, place of supply (intra / inter-state), currency and rate | document header | ✅ |
| Bill to / ship to with address, GSTIN and state | CRD1 | ✅ |
| Lines: description, item, HSN / SAC, quantity, UoM, rate, discount, taxable value, CGST + SGST or IGST (rate, amount), total | lines, OITM ChapterID, STC1 | ✅ delivery challans, receipts and returns print quantities only |
| HSN / SAC-wise tax summary; totals; amount in words (Indian lakh / crore, rupees and paise) | | ✅ |
| Payment terms, bank details (house bank), remarks, authorised signatory | OCTG, DSC1 | ✅ A4 print styling; PDF through the browser |
| Several layouts per document type, default layout, layout chosen in the print preview | RDOC DocCode / DocName / TypeCode / Default | ✅ |
| Template style (classic / modern / compact), accent colour | RDOC Style / Color | dropdown / colour picker | ✅ |
| Print company logo, HSN / SAC summary, bank details, authorised signatory, footer text | RDOC ShowLogo / ShowHSN / ShowBank / ShowSign / Footer | checkbox / text | ✅ |
| Company logo (PNG / JPEG / GIF, at most 512 KB) | OADM LogoImage | file upload | ✅ |
| Print Layout Designer (free field placement) / Crystal templates, default layout per user or BP, e-mailing | | ⏸ |

## Inventory documents (goods receipt OIGN, goods issue OIGE, inventory transfer OWTR)
| Field | Column | Type | Status |
|---|---|---|---|
| No. / series | DocNum / Series | dropdown | 🔒 |
| Posting date / document date | DocDate / TaxDate | date | ✅ |
| Ref. 2 | Ref2 | text | ✅ |
| Price list (goods receipt / issue) | — | dropdown | ✅ sets the default unit cost |
| From / to warehouse (transfer) | Filler / ToWhsCode, line FromWhsCod / WhsCode | dropdown | ✅ |
| Journal remark / remarks | JrnlMemo / Comments | text / textarea | ✅ |
| Lines: item, description, quantity, UoM, warehouse, unit cost, total, G/L account (offset), project | ItemCode, Dscription, Quantity, unitMsr, WhsCode, Price, LineTotal, AcctCode, Project | choose / text / number / dropdown | ✅ |
| Transfer: business partner, contact, ship-to, sales employee | CardCode, … | — | ⏸ |

## Inventory audit report (OINM)
Document, date, item, warehouse, in/out quantity, price, value change, item cost after, BP, journal entry — ✅ (filter by item: dropdown).

## Banking

### Incoming payment (ORCT) / outgoing payment (OVPM) — header
| Field | Column | Type | Status |
|---|---|---|---|
| Type (customer / vendor / account) | DocType | dropdown | ✅ |
| Code / name | CardCode / CardName | choose | ✅ |
| Contact person | CntctCode | dropdown | ✅ |
| Bill-to address | Address | — | 🔒 from the BP |
| No. / series | DocNum / Series | dropdown | 🔒 |
| Posting date / due date / document date | DocDate / DocDueDate / TaxDate | date | ✅ |
| Currency / rate | DocCurr / DocRate | dropdown / — | ✅ (rate from ORTT) |
| Reference | CounterRef | text | ✅ |
| Ref. 2 | Ref2 | text | ✅ |
| Project | PrjCode | dropdown | ✅ |
| Journal remarks | JrnlMemo | text | ✅ |
| Remarks | Comments | textarea | ✅ |
| Payment on account / amount / still open | PayNoDoc / NoDocSum / OpenBal | checkbox / number | ✅ |
| Overall amount (LC / FC) | DocTotal / DocTotalFC | number | 🔒 |
| Canceled | Canceled | — | 🔒 |
| Blanket agreement, payment wizard run, cash flow line items, withholding tax, VAT on payments, address 2 | AgrNo, PayWizard, CfwId, WtCode, … | — | ⏸ not in scope |

### Paid items (RCT2 / VPM2)
| Field | Column | Type | Status |
|---|---|---|---|
| Selected | — | checkbox | ✅ |
| Document type / no. / posting date / due date / remarks | InvType / DocEntry / — | — | 🔒 every open partner line: invoices, credit memos, journal entries, payments on account |
| Total / balance due | — | number | 🔒 |
| Total payment | SumApplied (LC) / AppliedFC (FC part of the item) | number | ✅ partial payments; an FC item is paid in its currency when the payment is in that currency (realized exchange difference) |
| Journal entry / line of the item | DocTransId / DocLine | — | 🔒 |
| Cash discount | DcntSum | number | ✅ pre-filled with the discount allowed on the payment date; the item is then settled completely; posted to cash discount allowed (615000) / received (722000) |
| Installment | InstId | — | 🔒 |
| Overdue days | — | — | ⏸ |

### G/L account lines of an account payment (RCT4 / VPM4)
| Field | Column | Type | Status |
|---|---|---|---|
| G/L account | AcctCode | choose | ✅ |
| Description | Descrip | text | ✅ |
| Project | PrjCode | dropdown | ✅ |
| Amount | SumApplied / AppliedFC | number | ✅ |
| Tax group, distribution rule | VatGroup, OcrCode | — | ⏸ VAT on account payments and cost accounting not built |

### Payment means
| Field | Column | Type | Status |
|---|---|---|---|
| Check G/L account | CheckAcct | choose | ✅ (incoming: checks received 117000) |
| Check lines: due date, amount, country, bank, branch, account, check no., endorse | RCT1/VPM1 DueDate, CheckSum, CountryCod, BankCode, Branch, AcctNum, CheckNum, Trnsfrable | date / number / dropdown / text / number / checkbox | ✅ |
| Bank transfer G/L account / date / reference / amount | TrsfrAcct / TrsfrDate / TrsfrRef / TrsfrSum (TrsfrSumFC) | choose / date / text / number | ✅ |
| Bank charges | BankChrg | number | ✅ posted to the bank charges account |
| Cash G/L account / amount | CashAcct / CashSum (CashSumFC) | choose / number | ✅ |
| Credit cards, bills of exchange, house bank selection for checks | RCT3, BoeAcc, … | — | ⏸ credit card and bill-of-exchange setup not in scope |

### Payment wizard (OPWZ / PWZ1)
| Field | Column | Type | Status |
|---|---|---|---|
| Run name / payment date / due date up to | WizardName / PmntDate / DueDateTo | text / date | ✅ |
| Pay vendors (outgoing) or customers (incoming) | PayType | dropdown | ✅ |
| Payment means (bank transfer, check) / bank G/L account / first check no. | PayMeans / BankAcct / FirstCheck | dropdown / choose / number | ✅ checks numbered per payment |
| Business partner selection | — | dropdown | ✅ one or all |
| Take cash discount | TakeDisc | checkbox | ✅ discount allowed on the payment date |
| Recommendation: items per BP (due date, open, discount, to pay; credit memos and payments on account offset), select / deselect | PWZ1 | checkbox | ✅ saved, editable until executed |
| Execute: one payment per BP with a positive net; outdated items refused; cancel a saved run | Status | — | ✅ |
| ⚠ PWZ1 is not a verified B1 table name (B1 keeps the wizard data in OPWZ and several PWZ tables) | | | |
| Payment methods (OPYM), bank file export, payment blocks, vendor bank accounts, multi-currency runs | | — | ⏸ |

### Checks for receipt (OCHH) and deposits (ODPS)
| Field | Column | Type | Status |
|---|---|---|---|
| Check no. / bank / branch / account / due date / amount / customer / incoming payment / G/L account | CheckNum, BankCode, Branch, AcctNum, CheckDate, CheckSum, CardCode, RcptNum, CheckAct | — | 🔒 created by incoming payments |
| Deposited / deposit | Deposited / DpstAbs | — | 🔒 |
| Deposit type (checks / cash) | DeposType | — | ✅ (two sections) |
| Deposit date | DeposDate | date | ✅ |
| Bank G/L account | BanckAcct | choose | ✅ |
| Bank account no. | BankAccNum | text | ✅ |
| Cash G/L account / amount (cash deposit) | AllocAcct / LocTotal | choose / number | ✅ |
| Project | Project | dropdown | ✅ |
| Journal remarks | Memo | text | ✅ |
| Journal entry / canceled | TransAbs / Canceled | — | 🔒 cancel reverses it |
| Credit card deposits, postdated checks, bank reconciliation | DeposType V, … | — | ⏸ |

### Banks and house bank accounts (ODSC / DSC1)
| Field | Column | Type | Status |
|---|---|---|---|
| Bank code / name / country / SWIFT | ODSC BankCode / BankName / CountryCod / SwiftNum | text / dropdown | ✅ |
| House bank account: bank / account no. / branch (IFSC) / IBAN / G/L account / name / currency | DSC1 BankCode / Account / Branch / IBAN / GLAccount / AcctName / Currency | dropdown / text / choose | ✅ |

### Bank statements (OBNH / OBNK)
| Field | Column | Type | Status |
|---|---|---|---|
| G/L bank account / house bank account | AcctCode / HouseBank | choose / dropdown | ✅ |
| Statement no. / date | StatemNo / StatDate | — / date | ✅ number per account |
| Opening / closing balance | StartBal / EndBal | number | ✅ opening = previous closing; closing = opening + in - out |
| Rows: value date / reference / narration / money in / money out | OBNK DueDate / Ref / Memo / CredAmnt / DebAmount | date / text / number | ✅ |
| Import of a bank export (CSV: date, reference, narration, amount or withdrawal / deposit; DD/MM/YYYY or ISO) | DataSource | file | ✅ |
| Bank transaction code / BP of a row | ExternCode / CardCode | text | ✅ (API) |
| Reconciliation number / document posted from the row | BankMatch / DocNumType, DocNum | — | 🔒 |
| ⚠ OBNH (statement header with balances) is not a verified B1 table name; B1 groups rows by StatemNo | | | |
| MT940 / camt.053 / bank-specific formats, bank statement templates, payment engine | | — | ⏸ |

### Bank statement processing and external reconciliation (OMTH / MTH1)
| Field | Column | Type | Status |
|---|---|---|---|
| Post a row as incoming payment (BP, open items or on account), outgoing payment or journal entry (offset G/L account: charges, interest) | — | dropdown / choose | ✅ reconciled at once |
| Manual reconciliation of selected rows and journal lines (sums must agree) | OMTH, MTH1 TransId / TransRowId / BankSeq / ReconSum, JDT1 ExtrMatch / MthDate | checkbox | ✅ |
| Automatic reconciliation: same amount and direction within N days, reference decides between candidates | OMTH Auto | number | ✅ |
| Cancel a reconciliation | Canceled | — | ✅ rows and lines open again |
| Bank reconciliation statement: balance per bank / books, deposits in transit, outstanding payments, bank items not booked, difference | — | report | ✅ |
| Reconciliation of foreign-currency bank accounts, partial matches by amount, matching rules | | — | ⏸ |

---

## Excluded B1 functions (not part of the agreed scope or of a later phase)

| B1 function | Why not (yet) |
|---|---|
| Payment methods (OPYM), bank payment files | not built yet |
| Payment methods, credit cards, bills of exchange | not in scope |
| Bank statement formats (MT940, camt.053), FC bank account reconciliation | not built yet |
| Conversion differences (system currency) | not built yet |
| Freight / additional expenses (OEXD), document rounding, down payments | not in the agreed scope |
| Units of measure groups and quantity conversion on documents | not in the agreed scope; UoM names are stored and shown |
| Serial and batch numbers, bin locations, FIFO / standard costing, inventory counting | not in the agreed scope |
| Cost accounting (dimensions, distribution rules, profit centers) | not in the agreed scope |
| Production, MRP, bills of materials, service, CRM opportunities, HR (employees, owners) | not in the agreed scope |
| Properties, attachments, pictures, user-defined fields, document printing / layouts, approval procedures, drafts, authorizations | not in the agreed scope |
| Localization fields (indicator, stamp tax, GLN, tax office) | not in the agreed scope |
| India: GSTR filing formats, e-invoicing (IRN / QR), e-way bill, TDS / TCS, reverse charge | not built yet |
