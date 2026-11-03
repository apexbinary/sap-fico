"""Service: customer equipment cards, service contracts, service calls.

    OINS          Customer equipment card: serial no., item, customer, contract, status (A active,
                  R returned, T terminated, L loaned, I in repair lab), delivery document
    OCTR / CTR1   Service contract: customer, type (C customer, I items, S serial numbers), dates,
                  status (A approved, F on hold, D draft, T terminated), response / resolution time,
                  included parts / labor / travel; CTR1 the covered items or serial numbers
    OSCL          Service call: customer, item / serial no., subject, type, origin, priority, status
                  (-3 open, -2 pending, -1 closed), technician, contract, response / resolution deadline,
                  resolution
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CustomerEquipment(Base):
    """OINS — Customer equipment card."""

    __tablename__ = "oins"

    ins_id: Mapped[int] = mapped_column("insID", primary_key=True)
    manuf_sn: Mapped[str | None] = mapped_column("manufSN", String(36))  # manufacturer serial no.
    internal_sn: Mapped[str | None] = mapped_column("internalSN", String(36))  # serial no. of the item (OSRN)
    item_code: Mapped[str] = mapped_column("itemCode", String(50))
    item_name: Mapped[str | None] = mapped_column("itemName", String(100))
    customer: Mapped[str] = mapped_column("customer", String(15), ForeignKey("ocrd.CardCode"))
    cntct_code: Mapped[int | None] = mapped_column("cntctCode", Integer)
    contract: Mapped[int | None] = mapped_column("contract", Integer)
    status: Mapped[str] = mapped_column("status", String(1), default="A")
    dlv_date: Mapped[date | None] = mapped_column("dlvryDate", Date)
    dlv_type: Mapped[str | None] = mapped_column("dlvryType", String(20))  # delivering document type
    dlv_entry: Mapped[int | None] = mapped_column("dlvryEntry", Integer)
    street: Mapped[str | None] = mapped_column("street", String(100))  # installation address
    city: Mapped[str | None] = mapped_column("city", String(100))


class ServiceContract(Base):
    """OCTR — Service contract."""

    __tablename__ = "octr"

    contract_id: Mapped[int] = mapped_column("ContractID", primary_key=True)
    cstmr_code: Mapped[str] = mapped_column("CstmrCode", String(15), ForeignKey("ocrd.CardCode"))
    cntrc_type: Mapped[str] = mapped_column("CntrcType", String(1), default="C")  # C customer, I items, S serial numbers
    start_date: Mapped[date] = mapped_column("StartDate", Date)
    end_date: Mapped[date] = mapped_column("EndDate", Date)
    status: Mapped[str] = mapped_column("Status", String(1), default="A")  # A approved, F on hold, D draft, T terminated
    rspns_time: Mapped[int | None] = mapped_column("RspnsTime", Integer)  # hours
    resol_time: Mapped[int | None] = mapped_column("ResolTime", Integer)  # hours
    incl_parts: Mapped[str] = mapped_column("InclPart", String(1), default="Y")
    incl_labor: Mapped[str] = mapped_column("InclLabor", String(1), default="Y")
    incl_travel: Mapped[str] = mapped_column("InclTrvl", String(1), default="N")
    descriptio: Mapped[str | None] = mapped_column("Descriptio", String(254))
    lines: Mapped[list["ServiceContractLine"]] = relationship(cascade="all, delete-orphan", order_by="ServiceContractLine.line")


class ServiceContractLine(Base):
    """CTR1 — Items / serial numbers covered by a contract."""

    __tablename__ = "ctr1"

    contract_id: Mapped[int] = mapped_column("ContractID", Integer, ForeignKey("octr.ContractID"), primary_key=True)
    line: Mapped[int] = mapped_column("Line", primary_key=True)
    item_code: Mapped[str | None] = mapped_column("ItemCode", String(50))
    internal_sn: Mapped[str | None] = mapped_column("InternalSN", String(36))


class ServiceCall(Base):
    """OSCL — Service call."""

    __tablename__ = "oscl"

    call_id: Mapped[int] = mapped_column("callID", primary_key=True)
    customer: Mapped[str] = mapped_column("customer", String(15), ForeignKey("ocrd.CardCode"))
    cntct_code: Mapped[int | None] = mapped_column("contctCode", Integer)
    item_code: Mapped[str | None] = mapped_column("itemCode", String(50))
    internal_sn: Mapped[str | None] = mapped_column("internalSN", String(36))
    ins_id: Mapped[int | None] = mapped_column("insID", Integer)  # equipment card
    subject: Mapped[str] = mapped_column("subject", String(254))
    origin: Mapped[str | None] = mapped_column("origin", String(20))  # phone, e-mail, web ...
    call_type: Mapped[str | None] = mapped_column("callType", String(20))  # repair, installation, maintenance ...
    problem_typ: Mapped[str | None] = mapped_column("problemTyp", String(50))
    priority: Mapped[str] = mapped_column("priority", String(1), default="M")  # L low, M medium, H high
    status: Mapped[int] = mapped_column("status", Integer, default=-3)  # -3 open, -2 pending, -1 closed
    assignee: Mapped[int | None] = mapped_column("assignee", Integer)  # technician (OUSR)
    contract: Mapped[int | None] = mapped_column("contractID", Integer)
    create_date: Mapped[datetime] = mapped_column("createDate", DateTime)
    response_by: Mapped[datetime | None] = mapped_column("responseBy", DateTime)  # deadline from the contract
    resol_by: Mapped[datetime | None] = mapped_column("resolOnDat", DateTime)
    responded: Mapped[datetime | None] = mapped_column("respOnDate", DateTime)
    close_date: Mapped[datetime | None] = mapped_column("closeDate", DateTime)
    resolution: Mapped[str | None] = mapped_column("resolution", String(1000))
    descrption: Mapped[str | None] = mapped_column("descrption", String(1000))
