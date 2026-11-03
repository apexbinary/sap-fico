"""CRM: sales stages, sales opportunities and activities.

    OOST          Sales stages: description, closing %, order
    OOPR / OPR1   Sales opportunity (partner, contact, potential amount, predicted closing, status
                  O open / W won / L lost) and its stage lines (stage, date, amount, closing %, linked
                  document)
    OCLG          Activities: call, meeting, task, note, e-mail, other — with partner, contact, date /
                  time, duration, priority, handling user, linked opportunity / document, closed
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

AMOUNT = Numeric(19, 6)


class SalesStage(Base):
    """OOST — Sales stage."""

    __tablename__ = "oost"

    num: Mapped[int] = mapped_column("Num", primary_key=True)
    descript: Mapped[str] = mapped_column("Descript", String(30))
    clo_prcnt: Mapped[Decimal] = mapped_column("CloPrcnt", AMOUNT)  # closing probability %
    step_id: Mapped[int] = mapped_column("StepId", Integer)  # order
    canceled: Mapped[str] = mapped_column("Canceled", String(1), default="N")


class Opportunity(Base):
    """OOPR — Sales opportunity."""

    __tablename__ = "oopr"

    oppr_id: Mapped[int] = mapped_column("OpprId", primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(100))
    card_code: Mapped[str] = mapped_column("CardCode", String(15), ForeignKey("ocrd.CardCode"))
    cpr_code: Mapped[int | None] = mapped_column("CprCode", Integer)  # contact person
    slp_code: Mapped[int | None] = mapped_column("SlpCode", Integer)  # sales employee
    open_date: Mapped[date] = mapped_column("OpenDate", Date)
    pred_date: Mapped[date | None] = mapped_column("PredDate", Date)  # predicted closing
    close_date: Mapped[date | None] = mapped_column("CloseDate", Date)
    max_sum_loc: Mapped[Decimal] = mapped_column("MaxSumLoc", AMOUNT, default=Decimal("0"))  # potential amount
    wt_sum_loc: Mapped[Decimal] = mapped_column("WtSumLoc", AMOUNT, default=Decimal("0"))  # weighted amount
    clo_prcnt: Mapped[Decimal] = mapped_column("CloPrcnt", AMOUNT, default=Decimal("0"))
    step_last: Mapped[int | None] = mapped_column("StepLast", Integer)  # current stage (OOST Num)
    status: Mapped[str] = mapped_column("Status", String(1), default="O")  # O open, W won, L lost
    reason: Mapped[str | None] = mapped_column("Reason", String(100))  # why lost / won
    memo: Mapped[str | None] = mapped_column("Memo", String(254))
    lines: Mapped[list["OpportunityStage"]] = relationship(cascade="all, delete-orphan", order_by="OpportunityStage.line")


class OpportunityStage(Base):
    """OPR1 — Stage lines of an opportunity."""

    __tablename__ = "opr1"

    oppr_id: Mapped[int] = mapped_column("OpprId", Integer, ForeignKey("oopr.OpprId"), primary_key=True)
    line: Mapped[int] = mapped_column("Line", primary_key=True)
    step_id: Mapped[int] = mapped_column("Step_Id", Integer)  # OOST Num
    open_date: Mapped[date] = mapped_column("OpenDate", Date)
    close_date: Mapped[date | None] = mapped_column("CloseDate", Date)
    max_sum_loc: Mapped[Decimal] = mapped_column("MaxSumLoc", AMOUNT, default=Decimal("0"))
    close_prcnt: Mapped[Decimal] = mapped_column("ClosePrcnt", AMOUNT, default=Decimal("0"))
    obj_type: Mapped[str | None] = mapped_column("ObjType", String(20))  # linked document (quotation, order ...)
    doc_number: Mapped[int | None] = mapped_column("DocNumber", Integer)  # its DocEntry
    memo: Mapped[str | None] = mapped_column("Memo", String(254))


class Activity(Base):
    """OCLG — Activity."""

    __tablename__ = "oclg"

    clg_code: Mapped[int] = mapped_column("ClgCode", primary_key=True)
    action: Mapped[str] = mapped_column("Action", String(1))  # C call, M meeting, T task, N note, E e-mail, O other
    details: Mapped[str] = mapped_column("Details", String(100))  # subject
    notes: Mapped[str | None] = mapped_column("Notes", String(1000))
    card_code: Mapped[str | None] = mapped_column("CardCode", String(15))
    cntct_code: Mapped[int | None] = mapped_column("CntctCode", Integer)
    attend_user: Mapped[int | None] = mapped_column("AttendUser", Integer)  # handled by (OUSR)
    recontact: Mapped[date] = mapped_column("Recontact", Date)  # start date
    begin_time: Mapped[str | None] = mapped_column("BeginTime", String(5))  # HH:MM
    end_date: Mapped[date | None] = mapped_column("endDate", Date)
    end_time: Mapped[str | None] = mapped_column("ENDTime", String(5))
    duration: Mapped[int | None] = mapped_column("Duration", Integer)  # minutes
    priority: Mapped[str] = mapped_column("Priority", String(1), default="1")  # 0 low, 1 normal, 2 high
    location: Mapped[str | None] = mapped_column("Location", String(100))
    opr_id: Mapped[int | None] = mapped_column("OprId", Integer)  # linked opportunity
    doc_type: Mapped[str | None] = mapped_column("DocType", String(20))  # linked document
    doc_entry: Mapped[int | None] = mapped_column("DocEntry", Integer)
    closed: Mapped[str] = mapped_column("Closed", String(1), default="N")
    close_date: Mapped[date | None] = mapped_column("CloseDate", Date)
    user_sign: Mapped[str | None] = mapped_column("UserSign", String(25))
    create_date: Mapped[datetime | None] = mapped_column("CreateDate", DateTime)
