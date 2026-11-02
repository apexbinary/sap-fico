"""Sub-ledger master data — Accounts Receivable (customers) and Payable (vendors).

Tables modelled here:
    KNA1   Customer master — general (client) data
    KNB1   Customer master — company code data
    LFA1   Vendor master   — general (client) data
    LFB1   Vendor master   — company code data
    LFBK   Vendor master   — bank details
    KNBK   Customer master — bank details
    SEPA_MANDATE  SEPA direct debit mandates (customer -> our creditor ID)
    KNB5   Customer master — dunning data per company code and dunning area
    LFB5   Vendor master — dunning data per company code and dunning area
    KNC1   Customer transaction figures per company code and fiscal year
    LFC1   Vendor transaction figures per company code and fiscal year

Open items are not stored in separate BSID/BSIK index tables here; they are
derived from BSEG line items where the account type is D/K and the clearing
document (AUGBL) is empty. This keeps a single owner for every posted fact.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.documents import AMOUNT
from app.models.organizational import MANDT


class Customer(Base):
    """KNA1 — Customer master, general data (client level)."""

    __tablename__ = "kna1"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kunnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Customer number
    ktokd: Mapped[str] = mapped_column(String(4))  # Customer account group
    name1: Mapped[str] = mapped_column(String(35))  # Name 1
    name2: Mapped[str | None] = mapped_column(String(35))  # Name 2
    sortl: Mapped[str | None] = mapped_column(String(10))  # Sort field
    land1: Mapped[str] = mapped_column(String(3))  # Country key
    ort01: Mapped[str | None] = mapped_column(String(35))  # City
    pstlz: Mapped[str | None] = mapped_column(String(10))  # Postal code
    regio: Mapped[str | None] = mapped_column(String(3))  # Region (state/province)
    stras: Mapped[str | None] = mapped_column(String(35))  # Street and house number
    telf1: Mapped[str | None] = mapped_column(String(16))  # Telephone 1
    spras: Mapped[str] = mapped_column(String(1), default="E")  # Language
    anred: Mapped[str | None] = mapped_column(String(15))  # Title
    adrnr: Mapped[str | None] = mapped_column(String(10))  # Address number
    stcd1: Mapped[str | None] = mapped_column(String(16))  # Tax number 1
    stcd2: Mapped[str | None] = mapped_column(String(11))  # Tax number 2
    stceg: Mapped[str | None] = mapped_column(String(20))  # VAT registration number
    brsch: Mapped[str | None] = mapped_column(String(4))  # Industry key
    kukla: Mapped[str | None] = mapped_column(String(2))  # Customer classification
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on
    ernam: Mapped[str | None] = mapped_column(String(12))  # Created by
    sperr: Mapped[bool] = mapped_column(default=False)  # Central posting block
    loevm: Mapped[bool] = mapped_column(default=False)  # Central deletion flag


class CustomerCompanyCode(Base):
    """KNB1 — Customer master, company code data."""

    __tablename__ = "knb1"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kunnr"], ["kna1.mandt", "kna1.kunnr"]),
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kunnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Customer number
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    akont: Mapped[str] = mapped_column(String(10))  # Reconciliation account in G/L
    zuawa: Mapped[str | None] = mapped_column(String(3))  # Sort key
    zterm: Mapped[str | None] = mapped_column(String(4))  # Terms of payment key
    zwels: Mapped[str | None] = mapped_column(String(10))  # List of payment methods
    zahls: Mapped[str | None] = mapped_column(String(1))  # Payment block
    busab: Mapped[str | None] = mapped_column(String(2))  # Accounting clerk
    fdgrv: Mapped[str | None] = mapped_column(String(10))  # Cash management group
    knrzb: Mapped[str | None] = mapped_column(String(10))  # Alternative payer
    togru: Mapped[str | None] = mapped_column(String(4))  # Tolerance group
    vzskz: Mapped[str | None] = mapped_column(String(2))  # Interest indicator
    altkn: Mapped[str | None] = mapped_column(String(10))  # Previous account number
    mahna: Mapped[str | None] = mapped_column(String(4))  # Dunning procedure
    mgruo: Mapped[str | None] = mapped_column(String(2))  # Dunning group
    eikto: Mapped[str | None] = mapped_column(String(12))  # Our account number at the customer
    xverr: Mapped[bool] = mapped_column(default=False)  # Clearing between customer and vendor
    sperr: Mapped[bool] = mapped_column(default=False)  # Posting block for this company code
    loevm: Mapped[bool] = mapped_column(default=False)  # Deletion flag for this company code
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on


class Vendor(Base):
    """LFA1 — Vendor master, general data (client level)."""

    __tablename__ = "lfa1"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Vendor number
    ktokk: Mapped[str] = mapped_column(String(4))  # Vendor account group
    name1: Mapped[str] = mapped_column(String(35))  # Name 1
    name2: Mapped[str | None] = mapped_column(String(35))  # Name 2
    sortl: Mapped[str | None] = mapped_column(String(10))  # Sort field
    land1: Mapped[str] = mapped_column(String(3))  # Country key
    ort01: Mapped[str | None] = mapped_column(String(35))  # City
    pstlz: Mapped[str | None] = mapped_column(String(10))  # Postal code
    regio: Mapped[str | None] = mapped_column(String(3))  # Region
    stras: Mapped[str | None] = mapped_column(String(35))  # Street
    telf1: Mapped[str | None] = mapped_column(String(16))  # Telephone
    spras: Mapped[str] = mapped_column(String(1), default="E")  # Language
    adrnr: Mapped[str | None] = mapped_column(String(10))  # Address number
    stcd1: Mapped[str | None] = mapped_column(String(16))  # Tax number 1
    stcd2: Mapped[str | None] = mapped_column(String(11))  # Tax number 2
    stceg: Mapped[str | None] = mapped_column(String(20))  # VAT registration number
    brsch: Mapped[str | None] = mapped_column(String(4))  # Industry key
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on
    ernam: Mapped[str | None] = mapped_column(String(12))  # Created by
    sperr: Mapped[bool] = mapped_column(default=False)  # Central posting block
    sperm: Mapped[bool] = mapped_column(default=False)  # Central purchasing block
    loevm: Mapped[bool] = mapped_column(default=False)  # Central deletion flag


class VendorCompanyCode(Base):
    """LFB1 — Vendor master, company code data."""

    __tablename__ = "lfb1"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "lifnr"], ["lfa1.mandt", "lfa1.lifnr"]),
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Vendor number
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    akont: Mapped[str] = mapped_column(String(10))  # Reconciliation account in G/L
    zuawa: Mapped[str | None] = mapped_column(String(3))  # Sort key
    zterm: Mapped[str | None] = mapped_column(String(4))  # Terms of payment key
    zwels: Mapped[str | None] = mapped_column(String(10))  # List of payment methods
    zahls: Mapped[str | None] = mapped_column(String(1))  # Payment block
    busab: Mapped[str | None] = mapped_column(String(2))  # Accounting clerk
    fdgrv: Mapped[str | None] = mapped_column(String(10))  # Cash management group
    lnrzb: Mapped[str | None] = mapped_column(String(10))  # Alternative payee
    togru: Mapped[str | None] = mapped_column(String(4))  # Tolerance group
    reprf: Mapped[bool] = mapped_column(default=False)  # Check for double invoices
    vzskz: Mapped[str | None] = mapped_column(String(2))  # Interest indicator
    zgrup: Mapped[str | None] = mapped_column(String(2))  # Payment grouping key
    xpore: Mapped[bool] = mapped_column(default=False)  # Pay all items separately
    sperr: Mapped[bool] = mapped_column(default=False)  # Posting block for this company code
    loevm: Mapped[bool] = mapped_column(default=False)  # Deletion flag for this company code
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on
    mindk: Mapped[str | None] = mapped_column(String(2))  # Memo (minority indicator)
    qland: Mapped[str | None] = mapped_column(String(3))  # Withholding tax country


class VendorBankDetails(Base):
    """LFBK — Vendor master, bank details (IBAN from TIBAN folded into iban)."""

    __tablename__ = "lfbk"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "lifnr"], ["lfa1.mandt", "lfa1.lifnr"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Vendor number
    banks: Mapped[str] = mapped_column(String(3), primary_key=True)  # Bank country key
    bankl: Mapped[str] = mapped_column(String(15), primary_key=True)  # Bank key (-> BNKA)
    bankn: Mapped[str] = mapped_column(String(18), primary_key=True)  # Bank account number
    bkont: Mapped[str | None] = mapped_column(String(2))  # Bank control key
    bvtyp: Mapped[str | None] = mapped_column(String(4))  # Partner bank type
    koinh: Mapped[str | None] = mapped_column(String(60))  # Account holder name
    xezer: Mapped[bool] = mapped_column(default=False)  # Collection authorization
    iban: Mapped[str | None] = mapped_column(String(34))  # IBAN (TIBAN)


class CustomerBankDetails(Base):
    """KNBK — Customer master, bank details (IBAN from TIBAN folded into iban)."""

    __tablename__ = "knbk"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kunnr"], ["kna1.mandt", "kna1.kunnr"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kunnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Customer number
    banks: Mapped[str] = mapped_column(String(3), primary_key=True)  # Bank country key
    bankl: Mapped[str] = mapped_column(String(15), primary_key=True)  # Bank key (-> BNKA)
    bankn: Mapped[str] = mapped_column(String(18), primary_key=True)  # Bank account number
    bkont: Mapped[str | None] = mapped_column(String(2))  # Bank control key
    bvtyp: Mapped[str | None] = mapped_column(String(4))  # Partner bank type
    koinh: Mapped[str | None] = mapped_column(String(60))  # Account holder name
    xezer: Mapped[bool] = mapped_column(default=False)  # Collection authorization
    iban: Mapped[str | None] = mapped_column(String(34))  # IBAN (TIBAN)


class SepaMandate(Base):
    """SEPA_MANDATE — SEPA direct debit mandate (debtor = customer)."""

    __tablename__ = "sepa_mandate"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    mndid: Mapped[str] = mapped_column(String(35), primary_key=True)  # Mandate reference
    snd_type: Mapped[str] = mapped_column(String(10), default="BUS3007")  # Sender object type (customer)
    snd_id: Mapped[str] = mapped_column(String(70))  # Sender ID (customer number)
    snd_name1: Mapped[str | None] = mapped_column(String(70))  # Debtor name
    snd_iban: Mapped[str] = mapped_column(String(34))  # Debtor IBAN
    snd_bic: Mapped[str | None] = mapped_column(String(11))  # Debtor BIC
    rec_type: Mapped[str] = mapped_column(String(10), default="BUS0002")  # Receiver object type (company code)
    rec_id: Mapped[str] = mapped_column(String(70))  # Receiver ID (company code)
    rec_crdid: Mapped[str] = mapped_column(String(35))  # Creditor identifier (SEPA CI)
    rec_name1: Mapped[str | None] = mapped_column(String(70))  # Creditor name
    sign_date: Mapped[date] = mapped_column()  # Date of signature
    sign_city: Mapped[str | None] = mapped_column(String(35))  # Place of signature
    pay_type: Mapped[str] = mapped_column(String(4), default="RCUR")  # RCUR recurring / OOFF one-off
    status: Mapped[str] = mapped_column(String(1), default="1")  # 0 entered, 1 active, 4 locked, 5 cancelled
    firstuse_date: Mapped[date | None] = mapped_column()  # Date of first use (FRST collection)
    firstuse_docid: Mapped[str | None] = mapped_column(String(10))  # Payment document of the first use


class CustomerDunningData(Base):
    """KNB5 — Customer master, dunning data (per company code and dunning area)."""

    __tablename__ = "knb5"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kunnr", "bukrs"], ["knb1.mandt", "knb1.kunnr", "knb1.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kunnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Customer number
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    maber: Mapped[str] = mapped_column(String(2), primary_key=True, default="")  # Dunning area
    mahna: Mapped[str] = mapped_column(String(4))  # Dunning procedure
    mansp: Mapped[str | None] = mapped_column(String(1))  # Dunning block
    madat: Mapped[date | None] = mapped_column()  # Last dunned on
    mahns: Mapped[int] = mapped_column(default=0)  # Dunning level
    knrma: Mapped[str | None] = mapped_column(String(10))  # Dunning recipient


class CustomerTotals(Base):
    """KNC1 — Customer transaction figures: balance carried forward (UMSAV) and debit (UMnnS) and
    credit (UMnnH) postings in local currency for periods 01-16; kept by the
    posting engine and the balance carryforward."""

    __tablename__ = "knc1"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kunnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Customer number
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    gjahr: Mapped[int] = mapped_column(primary_key=True)  # Fiscal year
    umsav: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Balance carried forward
    um01s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 01
    um02s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 02
    um03s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 03
    um04s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 04
    um05s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 05
    um06s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 06
    um07s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 07
    um08s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 08
    um09s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 09
    um10s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 10
    um11s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 11
    um12s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 12
    um13s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 13
    um14s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 14
    um15s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 15
    um16s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 16
    um01h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 01
    um02h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 02
    um03h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 03
    um04h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 04
    um05h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 05
    um06h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 06
    um07h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 07
    um08h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 08
    um09h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 09
    um10h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 10
    um11h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 11
    um12h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 12
    um13h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 13
    um14h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 14
    um15h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 15
    um16h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 16


class VendorTotals(Base):
    """LFC1 — Vendor transaction figures: balance carried forward (UMSAV) and debit (UMnnS) and
    credit (UMnnH) postings in local currency for periods 01-16; kept by the
    posting engine and the balance carryforward."""

    __tablename__ = "lfc1"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Vendor number
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    gjahr: Mapped[int] = mapped_column(primary_key=True)  # Fiscal year
    umsav: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Balance carried forward
    um01s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 01
    um02s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 02
    um03s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 03
    um04s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 04
    um05s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 05
    um06s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 06
    um07s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 07
    um08s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 08
    um09s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 09
    um10s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 10
    um11s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 11
    um12s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 12
    um13s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 13
    um14s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 14
    um15s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 15
    um16s: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Debit period 16
    um01h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 01
    um02h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 02
    um03h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 03
    um04h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 04
    um05h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 05
    um06h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 06
    um07h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 07
    um08h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 08
    um09h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 09
    um10h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 10
    um11h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 11
    um12h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 12
    um13h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 13
    um14h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 14
    um15h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 15
    um16h: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))  # Credit period 16


class VendorDunningData(Base):
    """LFB5 — Vendor master, dunning data (vendors with debit balances)."""

    __tablename__ = "lfb5"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "lifnr", "bukrs"], ["lfb1.mandt", "lfb1.lifnr", "lfb1.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    lifnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Vendor number
    bukrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Company code
    maber: Mapped[str] = mapped_column(String(2), primary_key=True, default="")  # Dunning area
    mahna: Mapped[str] = mapped_column(String(4))  # Dunning procedure
    mansp: Mapped[str | None] = mapped_column(String(1))  # Dunning block
    madat: Mapped[date | None] = mapped_column()  # Last dunned on
    mahns: Mapped[int] = mapped_column(default=0)  # Dunning level
