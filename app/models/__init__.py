"""All ORM models. Importing this package registers every table on Base.metadata."""

from app.models.admin import (
    Company,
    Country,
    Currency,
    ExchangeRate,
    NumberingSeries,
    CashDiscount,
    CockpitWidget,
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
                                 OutgoingPayment, DunningRun, DunningLetter, DunningLetterItem, PaymentRun,
                                 PaymentRunItem)
from app.models.documents import DOCUMENT_CLASSES, DOCUMENT_INSTALLMENTS, DOCUMENT_TABLES, WarehouseJournal
from app.models.inventory import Item, ItemGroup, ItemPrice, ItemWarehouse, Manufacturer, PriceList, Warehouse
from app.models.users import User, UserPermission, UserSession
from app.models.edocs import EDocument
from app.models.batches import Batch, BatchQuantity, InventoryLog, InventoryLogLine, SerialNumber, SerialQuantity
from app.models.counting import InventoryCounting, InventoryCountingLine, InventoryPosting, InventoryPostingLine
from app.models.costacct import Dimension, DistributionRule, DistributionShare, ProfitCenter
from app.models.budgets import Budget, BudgetMonth, BudgetScenario
from app.models.recurring import RecurringPosting, RecurringPostingLine
from app.models.assets import AssetClass, AssetTransaction, FixedAsset
from app.models.production import BillOfMaterials, BomLine, ProductionOrder, ProductionOrderLine
from app.models.crm import Activity, Opportunity, OpportunityStage, SalesStage
from app.models.service import CustomerEquipment, ServiceCall, ServiceContract, ServiceContractLine
from app.models.approvals import (Alert, AlertRecipient, ApprovalDecision, ApprovalRequest, ApprovalStage, ApprovalStageUser,
                                  ApprovalTemplate, ApprovalTemplateCondition, ApprovalTemplateDocument, ApprovalTemplateStage,
                                  ApprovalTemplateUser)
from app.models.partners import BusinessPartner, ContactPerson, PartnerAddress, PartnerGroup

__all__ = [
    # administration
    "Company", "Currency", "ExchangeRate", "PostingPeriod", "NumberingSeries", "TaxGroup", "PaymentTerms", "PaymentTermsInstallment", "CashDiscount", "CashDiscountLine", "CockpitWidget", "DunningTerm", "DunningLevel",
    "SalesEmployee", "Project", "TransactionCode", "Country", "State", "TaxAuthority", "TaxComponent", "TaxType", "HsnCode", "TaxDetermination",
    # financials
    "Account", "JournalEntry", "JournalLine", "AccountDetermination", "ExchangeRateRun", "ExchangeRateRunLine",
    # users
    "User", "UserPermission", "UserSession",
    # business partners
    "PartnerGroup", "BusinessPartner", "ContactPerson", "PartnerAddress",
    # inventory
    "ItemGroup", "Item", "Manufacturer", "Warehouse", "ItemWarehouse", "PriceList", "ItemPrice",
    # marketing and inventory documents (classes by object type), warehouse journal
    "DOCUMENT_CLASSES", "DOCUMENT_TABLES", "DOCUMENT_INSTALLMENTS", "WarehouseJournal",
    # banking
    "IncomingPayment", "OutgoingPayment", "PAYMENT_CLASSES", "CheckForReceipt", "Deposit",
    "DunningRun", "DunningLetter", "DunningLetterItem", "PaymentRun", "PaymentRunItem",
    "Bank", "HouseBankAccount", "BankStatement", "BankStatementRow", "ExternalReconciliation", "ExternalReconciliationLine",
]
