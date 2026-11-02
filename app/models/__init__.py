"""All ORM models. Importing this package registers every table on Base.metadata."""

from app.models.admin import (
    Company,
    Country,
    Currency,
    ExchangeRate,
    NumberingSeries,
    CashDiscount,
    DunningLevel,
    DunningTerm,
    CashDiscountLine,
    PaymentTerms,
    PaymentTermsInstallment,
    PostingPeriod,
    Project,
    SalesEmployee,
    State,
    HsnCode,
    TaxAuthority,
    TaxDetermination,
    TaxType,
    TaxComponent,
    TaxGroup,
    TransactionCode,
)
from app.models.finance import (Account, AccountDetermination, ExchangeRateRun, ExchangeRateRunLine, JournalEntry,
                                JournalLine)
from app.models.banking import (PAYMENT_CLASSES, Bank, BankStatement, BankStatementRow, CheckForReceipt, Deposit,
                                 ExternalReconciliation, ExternalReconciliationLine, HouseBankAccount, IncomingPayment,
                                 OutgoingPayment, DunningRun, DunningLetter, DunningLetterItem)
from app.models.documents import DOCUMENT_CLASSES, DOCUMENT_INSTALLMENTS, DOCUMENT_TABLES, WarehouseJournal
from app.models.inventory import Item, ItemGroup, ItemPrice, ItemWarehouse, Manufacturer, PriceList, Warehouse
from app.models.partners import BusinessPartner, ContactPerson, PartnerAddress, PartnerGroup

__all__ = [
    # administration
    "Company", "Currency", "ExchangeRate", "PostingPeriod", "NumberingSeries", "TaxGroup", "PaymentTerms", "PaymentTermsInstallment", "CashDiscount", "CashDiscountLine", "DunningTerm", "DunningLevel",
    "SalesEmployee", "Project", "TransactionCode", "Country", "State", "TaxAuthority", "TaxComponent", "TaxType", "HsnCode", "TaxDetermination",
    # financials
    "Account", "JournalEntry", "JournalLine", "AccountDetermination", "ExchangeRateRun", "ExchangeRateRunLine",
    # business partners
    "PartnerGroup", "BusinessPartner", "ContactPerson", "PartnerAddress",
    # inventory
    "ItemGroup", "Item", "Manufacturer", "Warehouse", "ItemWarehouse", "PriceList", "ItemPrice",
    # marketing and inventory documents (classes by object type), warehouse journal
    "DOCUMENT_CLASSES", "DOCUMENT_TABLES", "DOCUMENT_INSTALLMENTS", "WarehouseJournal",
    # banking
    "IncomingPayment", "OutgoingPayment", "PAYMENT_CLASSES", "CheckForReceipt", "Deposit",
    "DunningRun", "DunningLetter", "DunningLetterItem",
    "Bank", "HouseBankAccount", "BankStatement", "BankStatementRow", "ExternalReconciliation", "ExternalReconciliationLine",
]
