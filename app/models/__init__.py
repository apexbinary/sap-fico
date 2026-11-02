"""All ORM models. Importing this package registers every table on Base.metadata."""

from app.models.admin import (
    Company,
    Currency,
    ExchangeRate,
    NumberingSeries,
    PaymentTerms,
    PostingPeriod,
    TaxGroup,
)
from app.models.finance import Account, AccountDetermination, JournalEntry, JournalLine
from app.models.inventory import Item, ItemGroup, ItemPrice, ItemWarehouse, PriceList, Warehouse
from app.models.partners import BusinessPartner, ContactPerson, PartnerGroup

__all__ = [
    # administration
    "Company", "Currency", "ExchangeRate", "PostingPeriod", "NumberingSeries", "TaxGroup", "PaymentTerms",
    # financials
    "Account", "JournalEntry", "JournalLine", "AccountDetermination",
    # business partners
    "PartnerGroup", "BusinessPartner", "ContactPerson",
    # inventory
    "ItemGroup", "Item", "Warehouse", "ItemWarehouse", "PriceList", "ItemPrice",
]
