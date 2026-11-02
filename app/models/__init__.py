"""All ORM models. Importing this package registers every table on Base.metadata."""

from app.models.assets import (
    Asset,
    AssetAccountDetermination,
    AssetAllocation,
    AssetClass,
    AssetDepreciationTerms,
    AssetDocumentHeader,
    AssetLineItem,
    AssetTransactionType,
    AssetValues,
    DepreciationArea,
    DepreciationPosting,
)
from app.models.bank import (
    Bank,
    BankStatementHeader,
    BankStatementItem,
    HouseBank,
    HouseBankAccount,
)
from app.models.controlling import (
    AllocationCycle,
    AllocationReceiver,
    ActivityPrice,
    ActivityType,
    AllocationSegment,
    CODocumentHeader,
    COTotals,
    CostingBasedPALineItem,
    COLineItem,
    CostCenter,
    CostElement,
    CostElementCO,
    FunctionalArea,
    InternalOrder,
    OperatingConcern,
    ProfitabilitySegment,
    ProfitCenter,
    SettlementDistribution,
    SettlementRule,
)
from app.models.documents import (
    AccountingDocumentHeader,
    AccountingDocumentItem,
    DocumentType,
    GLAccountTotals,
    NumberRange,
    PostingKey,
    RecurringEntrySchedule,
)
from app.models.dunning import (
    DunningAccount,
    DunningArea,
    DunningCharge,
    DunningItem,
    DunningLevel,
    DunningProcedure,
    DunningRunControl,
    InterestIndicator,
    InterestRate,
)
from app.models.fsv import FinancialStatementVersion, FSVAccountAssignment, FSVNode
from app.models.gl_master import (
    FieldStatusGroup,
    FieldStatusVariant,
    GLAccountCOA,
    GLAccountCompanyCode,
    GLAccountGroup,
    GLAccountText,
)
from app.models.organizational import (
    AdditionalLocalCurrencies,
    BusinessArea,
    ChartOfAccounts,
    Client,
    CompanyCode,
    ControllingArea,
    ControllingAreaAssignment,
    CreditControlArea,
    Currency,
    ExchangeRate,
    FiscalYearPeriod,
    FiscalYearVariant,
    PostingPeriodControl,
)
from app.models.partners import (
    Customer,
    CustomerBankDetails,
    CustomerCompanyCode,
    CustomerDunningData,
    CustomerTotals,
    SepaMandate,
    Vendor,
    VendorBankDetails,
    VendorCompanyCode,
    VendorDunningData,
    VendorTotals,
)
from app.models.payment_run import PaymentRunControl, PaymentRunItem, PaymentRunPayee
from app.models.payments import (
    AutomaticAccountDetermination,
    AvailableAmount,
    BankDetermination,
    CheckLot,
    CheckRegister,
    CompanyCodePaymentMethod,
    CustomerVendorTolerance,
    EmployeeTolerance,
    ExchangeDifferenceAccounts,
    PaymentDifferenceReason,
    PaymentMethod,
    PaymentTerms,
    UserToleranceGroup,
    ValuationMethod,
)
from app.models.tax import (
    Country,
    TaxAccount,
    TaxCode,
    TaxRate,
    WithholdingTaxCode,
    WithholdingTaxType,
)

__all__ = [
    # organizational
    "Client", "CompanyCode", "ChartOfAccounts", "FiscalYearVariant",
    "FiscalYearPeriod", "ControllingArea", "ControllingAreaAssignment",
    "BusinessArea", "CreditControlArea", "Currency", "ExchangeRate",
    "PostingPeriodControl", "AdditionalLocalCurrencies",
    # gl master
    "GLAccountCOA", "GLAccountText", "GLAccountCompanyCode", "GLAccountGroup",
    "FieldStatusVariant", "FieldStatusGroup",
    # documents
    "DocumentType", "PostingKey", "NumberRange", "AccountingDocumentHeader",
    "AccountingDocumentItem", "GLAccountTotals", "RecurringEntrySchedule",
    # tax
    "Country", "TaxCode", "TaxRate", "TaxAccount", "WithholdingTaxType",
    "WithholdingTaxCode",
    # partners
    "Customer", "CustomerCompanyCode", "Vendor", "VendorCompanyCode", "VendorBankDetails",
    "CustomerBankDetails", "SepaMandate", "CustomerDunningData", "CustomerTotals", "VendorTotals",
    # dunning
    "DunningProcedure", "DunningLevel", "DunningCharge", "DunningRunControl",
    "DunningAccount", "DunningItem", "DunningArea", "InterestIndicator", "InterestRate",
    "VendorDunningData",
    # payments
    "PaymentTerms", "AutomaticAccountDetermination", "PaymentMethod",
    "CompanyCodePaymentMethod", "BankDetermination", "CustomerVendorTolerance",
    "ExchangeDifferenceAccounts", "UserToleranceGroup", "EmployeeTolerance", "PaymentDifferenceReason",
    "AvailableAmount", "CheckLot", "CheckRegister", "ValuationMethod",
    # financial statement version
    "FinancialStatementVersion", "FSVNode", "FSVAccountAssignment",
    # payment run (F110)
    "PaymentRunControl", "PaymentRunPayee", "PaymentRunItem",
    # controlling
    "CostCenter", "CostElement", "CostElementCO", "InternalOrder",
    "ProfitCenter", "COLineItem", "CODocumentHeader",
    "AllocationCycle", "AllocationSegment", "AllocationReceiver",
    "SettlementRule", "SettlementDistribution", "OperatingConcern", "ProfitabilitySegment", "FunctionalArea",
    "COTotals", "ActivityType", "ActivityPrice", "CostingBasedPALineItem",
    # assets
    "AssetClass", "DepreciationArea", "AssetAccountDetermination",
    "AssetTransactionType", "Asset", "AssetDepreciationTerms", "AssetAllocation",
    "AssetValues", "AssetDocumentHeader", "AssetLineItem", "DepreciationPosting",
    # bank
    "Bank", "HouseBank", "HouseBankAccount", "BankStatementHeader",
    "BankStatementItem",
]
