"""Controlling (CO) — cost centers, cost elements, internal orders, profit centers.

Tables modelled here:
    CSKS   Cost center master (+ CSKT text folded into ktext/ltext)
    CSKA   Cost elements — chart of accounts dependent
    CSKB   Cost elements — controlling area dependent
    AUFK   Order master data (internal orders)
    CEPC   Profit center master (+ CEPCT text)
    COBK   CO document header (number range RK_BELEG per controlling area)
    T811C  Allocation cycles (assessment / distribution)
    T811S  Allocation cycle segments (senders, cost elements)
    T811K  Allocation segment receivers (tracing factors)
    COBRA  Settlement rule header of a CO object (internal order)
    COBRB  Settlement rule distribution rules (receiver, percentage, validity)
    TKEB   Operating concern (CO-PA)
    CE4IDEA  Profitability segments of operating concern IDEA (characteristics)
    COEP   CO object line items (actual postings)

When an FI line item carries a CO account assignment (cost center, order or WBS)
and the G/L account is a primary cost element, the posting engine mirrors the
amount into COEP in real time, as SAP does with real-time FI->CO integration.
Every CO posting has its own CO document (COBK); one that comes from FI points
back to it through AWTYP/REFBN/REFGJ.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.documents import AMOUNT
from app.models.organizational import MANDT


class CostCenter(Base):
    """CSKS — Cost center master data (+ CSKT text)."""

    __tablename__ = "csks"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kokrs"], ["tka01.mandt", "tka01.kokrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kokrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Controlling area
    kostl: Mapped[str] = mapped_column(String(10), primary_key=True)  # Cost center
    datbi: Mapped[date] = mapped_column(primary_key=True)  # Valid-to date
    datab: Mapped[date] = mapped_column()  # Valid-from date
    ktext: Mapped[str | None] = mapped_column(String(20))  # Short text
    ltext: Mapped[str | None] = mapped_column(String(40))  # Long text (description)
    verak: Mapped[str | None] = mapped_column(String(20))  # Person responsible
    kosar: Mapped[str | None] = mapped_column(String(1))  # Cost center category
    khinr: Mapped[str | None] = mapped_column(String(12))  # Standard hierarchy area
    bukrs: Mapped[str | None] = mapped_column(String(4))  # Company code
    gsber: Mapped[str | None] = mapped_column(String(4))  # Business area
    fkber: Mapped[str | None] = mapped_column(String(16))  # Functional area
    prctr: Mapped[str | None] = mapped_column(String(10))  # Profit center
    waers: Mapped[str | None] = mapped_column(String(5))  # Currency
    abtei: Mapped[str | None] = mapped_column(String(12))  # Department
    bkzkp: Mapped[str | None] = mapped_column(String(1))  # Lock: actual primary postings
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on


class CostElement(Base):
    """CSKA — Cost element master (chart of accounts dependent)."""

    __tablename__ = "cska"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "ktopl"], ["t004.mandt", "t004.ktopl"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    ktopl: Mapped[str] = mapped_column(String(4), primary_key=True)  # Chart of accounts
    kstar: Mapped[str] = mapped_column(String(10), primary_key=True)  # Cost element (= G/L account)
    bkzkp: Mapped[str | None] = mapped_column(String(1))  # Lock indicator
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on


class CostElementCO(Base):
    """CSKB — Cost element master (controlling area dependent)."""

    __tablename__ = "cskb"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kokrs"], ["tka01.mandt", "tka01.kokrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kokrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Controlling area
    kstar: Mapped[str] = mapped_column(String(10), primary_key=True)  # Cost element
    datbi: Mapped[date] = mapped_column(primary_key=True)  # Valid-to date
    datab: Mapped[date] = mapped_column()  # Valid-from date
    # Cost element category: 1=primary/costs, 11=revenues, 12=sales deductions,
    # 21=internal settlement, 43=internal activity allocation, 90=stat. asset/mat.
    katyp: Mapped[str] = mapped_column(String(2))
    ktext: Mapped[str | None] = mapped_column(String(20))  # Short text
    ltext: Mapped[str | None] = mapped_column(String(40))  # Long text


class InternalOrder(Base):
    """AUFK — Order master data (internal orders)."""

    __tablename__ = "aufk"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "bukrs"], ["t001.mandt", "t001.bukrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    aufnr: Mapped[str] = mapped_column(String(12), primary_key=True)  # Order number
    auart: Mapped[str] = mapped_column(String(4))  # Order type
    autyp: Mapped[str] = mapped_column(String(2), default="01")  # Order category
    ktext: Mapped[str | None] = mapped_column(String(40))  # Description
    bukrs: Mapped[str] = mapped_column(String(4))  # Company code
    kokrs: Mapped[str] = mapped_column(String(4))  # Controlling area
    werks: Mapped[str | None] = mapped_column(String(4))  # Plant
    gsber: Mapped[str | None] = mapped_column(String(4))  # Business area
    kostv: Mapped[str | None] = mapped_column(String(10))  # Responsible cost center
    prctr: Mapped[str | None] = mapped_column(String(10))  # Profit center
    waers: Mapped[str | None] = mapped_column(String(5))  # Currency
    astkz: Mapped[bool] = mapped_column(default=False)  # Statistical order
    phas0: Mapped[bool] = mapped_column(default=True)  # Status: created
    phas1: Mapped[bool] = mapped_column(default=False)  # Status: released
    loekz: Mapped[bool] = mapped_column(default=False)  # Deletion flag
    erdat: Mapped[str | None] = mapped_column(String(8))  # Created on
    ernam: Mapped[str | None] = mapped_column(String(12))  # Created by


class ProfitCenter(Base):
    """CEPC — Profit center master data (+ CEPCT text)."""

    __tablename__ = "cepc"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kokrs"], ["tka01.mandt", "tka01.kokrs"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    prctr: Mapped[str] = mapped_column(String(10), primary_key=True)  # Profit center
    datbi: Mapped[date] = mapped_column(primary_key=True)  # Valid-to date
    kokrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Controlling area
    datab: Mapped[date] = mapped_column()  # Valid-from date
    ktext: Mapped[str | None] = mapped_column(String(20))  # Short text
    ltext: Mapped[str | None] = mapped_column(String(40))  # Long text
    khinr: Mapped[str | None] = mapped_column(String(12))  # Standard hierarchy node
    verak: Mapped[str | None] = mapped_column(String(20))  # Person responsible
    bukrs: Mapped[str | None] = mapped_column(String(4))  # Company code
    waers: Mapped[str | None] = mapped_column(String(5))  # Currency
    land1: Mapped[str | None] = mapped_column(String(3))  # Country
    abtei: Mapped[str | None] = mapped_column(String(12))  # Department
    lock_ind: Mapped[bool] = mapped_column(default=False)  # Lock indicator


class COLineItem(Base):
    """COEP — CO object line items (actual/plan)."""

    __tablename__ = "coep"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kokrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Controlling area
    belnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # CO document number
    buzei: Mapped[int] = mapped_column(primary_key=True)  # CO line item
    perio: Mapped[int] = mapped_column()  # Period
    gjahr: Mapped[int] = mapped_column()  # Fiscal year
    wrttp: Mapped[str] = mapped_column(String(2), default="04")  # Value type (04=actual, 01=plan)
    versn: Mapped[str] = mapped_column(String(3), default="000")  # Version
    kstar: Mapped[str] = mapped_column(String(10))  # Cost element
    objnr: Mapped[str] = mapped_column(String(22))  # Object number (KS/OR/PR + key)
    bukrs: Mapped[str | None] = mapped_column(String(4))  # Company code
    kostl: Mapped[str | None] = mapped_column(String(10))  # Cost center
    aufnr: Mapped[str | None] = mapped_column(String(12))  # Order
    prctr: Mapped[str | None] = mapped_column(String(10))  # Profit center
    wkgbtr: Mapped[Decimal] = mapped_column(AMOUNT)  # Value in controlling area currency
    wogbtr: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Value in object currency
    wtgbtr: Mapped[Decimal | None] = mapped_column(AMOUNT)  # Value in transaction currency
    owaer: Mapped[str | None] = mapped_column(String(5))  # Object currency
    twaer: Mapped[str | None] = mapped_column(String(5))  # Transaction currency
    megbtr: Mapped[Decimal | None] = mapped_column(Numeric(13, 3))  # Quantity
    meinb: Mapped[str | None] = mapped_column(String(3))  # Unit of measure
    beltp: Mapped[str] = mapped_column(String(1), default="1")  # Document line type
    vrgng: Mapped[str | None] = mapped_column(String(4))  # CO business transaction (e.g. COIN)
    refbn: Mapped[str | None] = mapped_column(String(10))  # Reference document (FI BELNR)
    refbz: Mapped[int | None] = mapped_column()  # Reference line item (FI BUZEI)
    refgj: Mapped[int | None] = mapped_column()  # Reference fiscal year


class CODocumentHeader(Base):
    """COBK — CO document header."""

    __tablename__ = "cobk"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kokrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Controlling area
    belnr: Mapped[str] = mapped_column(String(10), primary_key=True)  # CO document number
    gjahr: Mapped[int] = mapped_column()  # Fiscal year
    versn: Mapped[str] = mapped_column(String(3), default="000")  # Version
    vrgng: Mapped[str] = mapped_column(String(4))  # CO business transaction (COIN, RKIU, RKIV, KOAO)
    perab: Mapped[int] = mapped_column()  # Period
    bldat: Mapped[date] = mapped_column()  # Document date
    budat: Mapped[date] = mapped_column()  # Posting date
    cpudt: Mapped[date] = mapped_column(default=date.today)  # Entry date
    usnam: Mapped[str] = mapped_column(String(12), default="SYSTEM")  # User
    bltxt: Mapped[str | None] = mapped_column(String(50))  # Document header text
    awtyp: Mapped[str | None] = mapped_column(String(5))  # Reference transaction (BKPF = from FI)
    refbk: Mapped[str | None] = mapped_column(String(4))  # Reference company code
    refbn: Mapped[str | None] = mapped_column(String(10))  # Reference document number (FI BELNR)
    refgj: Mapped[int | None] = mapped_column()  # Reference fiscal year
    stflg: Mapped[bool] = mapped_column(default=False)  # Document is a reversal
    stokz: Mapped[bool] = mapped_column(default=False)  # Document has been reversed
    # Allocation cycle that posted this document (assessment / distribution).
    # Not an SAP COBK column: SAP keeps the cycle reference in the allocation tables.
    kscyc: Mapped[str | None] = mapped_column(String(10))


class AllocationCycle(Base):
    """T811C — Assessment / distribution cycle.

    SAP keeps cycles generically in T811C/T811S/T811F/T811K (field values as
    rows); these tables are an explicit version of the same structure, and
    their non-key column names still need checking against the SAP DDIC.
    """

    __tablename__ = "t811c"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kokrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Controlling area
    cycle: Mapped[str] = mapped_column(String(10), primary_key=True)  # Cycle
    sdate: Mapped[date] = mapped_column(primary_key=True)  # Valid from
    edate: Mapped[date] = mapped_column()  # Valid to
    txt: Mapped[str | None] = mapped_column(String(50))  # Cycle text
    ttype: Mapped[str] = mapped_column(String(1))  # A = assessment (KSU5), D = distribution (KSV5)


class AllocationSegment(Base):
    """T811S — Segment of an allocation cycle: senders and the cost elements they send."""

    __tablename__ = "t811s"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kokrs", "cycle", "sdate"],
                             ["t811c.mandt", "t811c.kokrs", "t811c.cycle", "t811c.sdate"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kokrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Controlling area
    cycle: Mapped[str] = mapped_column(String(10), primary_key=True)  # Cycle
    sdate: Mapped[date] = mapped_column(primary_key=True)  # Valid from (of the cycle)
    seg: Mapped[int] = mapped_column(primary_key=True)  # Segment number
    txt: Mapped[str | None] = mapped_column(String(50))  # Segment text
    kostl_von: Mapped[str] = mapped_column(String(10))  # Sender cost center from
    kostl_bis: Mapped[str] = mapped_column(String(10))  # Sender cost center to
    kstar_von: Mapped[str] = mapped_column(String(10))  # Sender cost element from
    kstar_bis: Mapped[str] = mapped_column(String(10))  # Sender cost element to
    askst: Mapped[str | None] = mapped_column(String(10))  # Assessment cost element (category 42)


class AllocationReceiver(Base):
    """T811K — Receiver of a segment with its tracing factor (fixed portion)."""

    __tablename__ = "t811k"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "kokrs", "cycle", "sdate", "seg"],
                             ["t811s.mandt", "t811s.kokrs", "t811s.cycle", "t811s.sdate", "t811s.seg"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    kokrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Controlling area
    cycle: Mapped[str] = mapped_column(String(10), primary_key=True)  # Cycle
    sdate: Mapped[date] = mapped_column(primary_key=True)  # Valid from (of the cycle)
    seg: Mapped[int] = mapped_column(primary_key=True)  # Segment number
    kostl: Mapped[str] = mapped_column(String(10), primary_key=True)  # Receiver cost center
    faktor: Mapped[Decimal] = mapped_column(Numeric(13, 4))  # Tracing factor (portion)


class SettlementRule(Base):
    """COBRA — Settlement rule (header) of a CO object."""

    __tablename__ = "cobra"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    objnr: Mapped[str] = mapped_column(String(22), primary_key=True)  # Object number (OR + order)
    aprof: Mapped[str | None] = mapped_column(String(6))  # Settlement profile
    kokrs: Mapped[str] = mapped_column(String(4))  # Controlling area


class SettlementDistribution(Base):
    """COBRB — Distribution rule of a settlement rule (one receiver)."""

    __tablename__ = "cobrb"
    __table_args__ = (
        ForeignKeyConstraint(["mandt", "objnr"], ["cobra.mandt", "cobra.objnr"]),
    )

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    objnr: Mapped[str] = mapped_column(String(22), primary_key=True)  # Sender object number
    bureg: Mapped[int] = mapped_column(primary_key=True)  # Distribution rule number
    lfdnr: Mapped[int] = mapped_column(primary_key=True, default=1)  # Sequence number
    konty: Mapped[str] = mapped_column(String(2))  # Account assignment category: KS cost center, SK G/L account
    kostl: Mapped[str | None] = mapped_column(String(10))  # Receiver cost center
    hkont: Mapped[str | None] = mapped_column(String(10))  # Receiver G/L account
    prozs: Mapped[Decimal] = mapped_column(Numeric(7, 3))  # Settlement percentage
    perbz: Mapped[str] = mapped_column(String(3), default="PER")  # Settlement type (PER periodic, GES full)
    gabja: Mapped[int | None] = mapped_column()  # Valid from fiscal year
    gabpe: Mapped[int | None] = mapped_column()  # Valid from period


class OperatingConcern(Base):
    """TKEB — Operating concern (profitability analysis)."""

    __tablename__ = "tkeb"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    erkrs: Mapped[str] = mapped_column(String(4), primary_key=True)  # Operating concern
    erkrs_txt: Mapped[str | None] = mapped_column(String(25))  # Name
    waers: Mapped[str] = mapped_column(String(5))  # Operating concern currency
    xkontb: Mapped[bool] = mapped_column(default=True)  # Account-based CO-PA active
    xkalkb: Mapped[bool] = mapped_column(default=False)  # Costing-based CO-PA active


class ProfitabilitySegment(Base):
    """CE4IDEA — Profitability segments of operating concern IDEA.

    SAP generates one CE4<operating concern> table per operating concern from
    its characteristics; this is the fixed table of the demo concern IDEA.
    """

    __tablename__ = "ce4idea"

    mandt: Mapped[str] = mapped_column(MANDT, primary_key=True)
    paobjnr: Mapped[int] = mapped_column(primary_key=True)  # Profitability segment number
    kokrs: Mapped[str] = mapped_column(String(4))  # Controlling area
    bukrs: Mapped[str] = mapped_column(String(4))  # Company code
    kndnr: Mapped[str | None] = mapped_column(String(10))  # Customer
    land1: Mapped[str | None] = mapped_column(String(3))  # Country of the customer
    brsch: Mapped[str | None] = mapped_column(String(4))  # Industry
    kukla: Mapped[str | None] = mapped_column(String(2))  # Customer classification
