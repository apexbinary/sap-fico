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

## Administration

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
| No. of installments, open incoming payment, cash discount, interest on arrears | InstNum, OpenRcpt, CdcCode, … | — | ⏸ installments, cash discount and dunning not in scope |

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
| Distribution rules, tax amount, base amount, system currency amounts | OcrCode, … | — | ⏸ cost accounting and system-currency reporting not built |

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
| Credit limit / commitment limit | CreditLine / DebtLine | number | ✅ stored; ⏸ credit-limit warning on documents |
| Interest on arrears, dunning term, priority, effective discount groups, bank details, payment methods | IntrstRate, DunTerm, … | — | ⏸ dunning, BP bank accounts and payment methods not in scope |

### Accounting tab
| Field | Column | Type | Status |
|---|---|---|---|
| Control account (A/R or A/P) | DebPayAcct | choose | ✅ |
| Tax group | VatGroup | dropdown | ✅ |
| Down payment clearing accounts, consolidating BP, withholding tax | DpmClear, FatherCard, WTLiable | — | ⏸ down payments, consolidation, withholding tax not built |

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
| Manage serial / batch numbers | ManSerNum / ManBtchNum | checkbox | 🔒 "No" (serial/batch management not built) |
| Active / inactive | frozenFor | checkbox | ✅ |
| Additional identifier, shipping type, tax type, withholding liable, valid/frozen date ranges | SWW, ShipType, … | — | ⏸ |

### Purchasing data tab
| Field | Column | Type | Status |
|---|---|---|---|
| Preferred vendor | CardCode | choose | ✅ |
| Mfr catalog no. | SuppCatNum | text | ✅ |
| Purchasing UoM name / items per purchase unit | BuyUnitMsr / NumInBuy | text / number | ✅ stored, UoM shown on purchasing documents; ⏸ quantity conversion (documents are in inventory units) |
| Tax group | VatGroupPu | dropdown | ✅ |
| Packaging UoM, quantity per package, customs group, dimensions / weight | PurPackMsr, PurPackUn, CstGrpCode, BLength1, … | — | ⏸ |

### Sales data tab
| Field | Column | Type | Status |
|---|---|---|---|
| Sales UoM name / items per sales unit | SalUnitMsr / NumInSale | text / number | ✅ stored, UoM shown on sales documents; ⏸ quantity conversion |
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
Group name and its G/L accounts (inventory, COGS, revenue, expense, price difference) — 🔒 seeded, shown on the item; ⏸ item group maintenance screen and the further OITB accounts (exchange rate differences, goods clearing, …).

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
| Freight (additional expenses), rounding, down payment, owner, shipping type, payment method, installments, indicator, cancellation date | TotalExpns, RoundDif, DpmAmnt, OwnerCode, TrnspCode, PeyMethod, Installmnt, Indicator, … | — | ⏸ freight/expenses, down payments, HR owner and payment wizard not built |

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
| Cash discount, overdue days, installment | DcntSum, InstId | — | ⏸ cash discount and installments not built |

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
| Payment wizard, payment methods, installments, cash discount, credit cards, bills of exchange, dunning | not in the agreed scope |
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
