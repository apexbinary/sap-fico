"""Approval procedures and alerts.

    OWST / WST1   Approval stages: approvals / rejections required, the authorizers
    OWTM          Approval templates (active)
    WTM1          Originators of a template (users whose documents need approval)
    WTM2          Stages of a template, in order
    WTM3          Document types of a template
    WTM4          Conditions: document total / discount % compared with a value (any condition met
                  -> approval needed; no condition = always)
    OWDD / WDD1   Approval requests (the held document) and the decisions per stage / authorizer
    OALT / ALT1   Alerts (system alert types) and their recipients
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ApprovalStage(Base):
    """OWST — Approval stage."""

    __tablename__ = "owst"

    wst_code: Mapped[int] = mapped_column("WstCode", primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(30))
    remarks: Mapped[str | None] = mapped_column("Remarks", String(100))
    max_reqr: Mapped[int] = mapped_column("MaxReqr", Integer, default=1)  # approvals required
    max_rej_reqr: Mapped[int] = mapped_column("MaxRejReqr", Integer, default=1)  # rejections required
    authorizers: Mapped[list["ApprovalStageUser"]] = relationship(cascade="all, delete-orphan")


class ApprovalStageUser(Base):
    """WST1 — Authorizers of a stage."""

    __tablename__ = "wst1"

    wst_code: Mapped[int] = mapped_column("WstCode", Integer, ForeignKey("owst.WstCode"), primary_key=True)
    user_id: Mapped[int] = mapped_column("UserID", Integer, ForeignKey("ousr.USERID"), primary_key=True)


class ApprovalTemplate(Base):
    """OWTM — Approval template."""

    __tablename__ = "owtm"

    wtm_code: Mapped[int] = mapped_column("WtmCode", primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(50))
    remarks: Mapped[str | None] = mapped_column("Remarks", String(100))
    active: Mapped[str] = mapped_column("Active", String(1), default="Y")
    originators: Mapped[list["ApprovalTemplateUser"]] = relationship(cascade="all, delete-orphan")
    stages: Mapped[list["ApprovalTemplateStage"]] = relationship(cascade="all, delete-orphan", order_by="ApprovalTemplateStage.sort_id")
    documents: Mapped[list["ApprovalTemplateDocument"]] = relationship(cascade="all, delete-orphan")
    conditions: Mapped[list["ApprovalTemplateCondition"]] = relationship(cascade="all, delete-orphan")


class ApprovalTemplateUser(Base):
    """WTM1 — Originators of a template."""

    __tablename__ = "wtm1"

    wtm_code: Mapped[int] = mapped_column("WtmCode", Integer, ForeignKey("owtm.WtmCode"), primary_key=True)
    user_id: Mapped[int] = mapped_column("UserID", Integer, ForeignKey("ousr.USERID"), primary_key=True)


class ApprovalTemplateStage(Base):
    """WTM2 — Stages of a template."""

    __tablename__ = "wtm2"

    wtm_code: Mapped[int] = mapped_column("WtmCode", Integer, ForeignKey("owtm.WtmCode"), primary_key=True)
    sort_id: Mapped[int] = mapped_column("SortId", primary_key=True)
    wst_code: Mapped[int] = mapped_column("WstCode", Integer, ForeignKey("owst.WstCode"))


class ApprovalTemplateDocument(Base):
    """WTM3 — Document types of a template."""

    __tablename__ = "wtm3"

    wtm_code: Mapped[int] = mapped_column("WtmCode", Integer, ForeignKey("owtm.WtmCode"), primary_key=True)
    trans_type: Mapped[str] = mapped_column("TransType", String(20), primary_key=True)


class ApprovalTemplateCondition(Base):
    """WTM4 — Conditions of a template."""

    __tablename__ = "wtm4"

    wtm_code: Mapped[int] = mapped_column("WtmCode", Integer, ForeignKey("owtm.WtmCode"), primary_key=True)
    line_id: Mapped[int] = mapped_column("LineId", primary_key=True)
    cond_id: Mapped[str] = mapped_column("CondId", String(10))  # TOTAL document total (LC), DISC discount %, GPPCT gross profit %
    op_code: Mapped[str] = mapped_column("OpCode", String(2))  # GT, GE, LT, LE
    value: Mapped[Decimal] = mapped_column("Value", Numeric(19, 6))


class ApprovalRequest(Base):
    """OWDD — Approval request: the held document and its status."""

    __tablename__ = "owdd"

    wdd_code: Mapped[int] = mapped_column("WddCode", primary_key=True)
    wtm_code: Mapped[int] = mapped_column("WtmCode", Integer, ForeignKey("owtm.WtmCode"))
    obj_type: Mapped[str] = mapped_column("ObjType", String(20))
    draft: Mapped[str] = mapped_column("Draft", Text)  # the document request (JSON; B1 keeps a draft ODRF)
    status: Mapped[str] = mapped_column("Status", String(1), default="W")  # W pending, Y approved, N rejected, A added
    current_stage: Mapped[int | None] = mapped_column("CurrStep", Integer)  # WTM2 SortId
    owner_id: Mapped[int] = mapped_column("OwnerID", Integer)  # originator (OUSR)
    card_code: Mapped[str | None] = mapped_column("CardCode", String(15))
    doc_total: Mapped[Decimal] = mapped_column("DocTotal", Numeric(19, 6), default=Decimal("0"))
    reason: Mapped[str | None] = mapped_column("Reason", String(254))  # conditions met
    remarks: Mapped[str | None] = mapped_column("Remarks", String(254))
    doc_entry: Mapped[int | None] = mapped_column("DocEntry", Integer)  # document added from the request
    create_date: Mapped[datetime] = mapped_column("CreateDate", DateTime)
    decisions: Mapped[list["ApprovalDecision"]] = relationship(cascade="all, delete-orphan", order_by="ApprovalDecision.line_id")


class ApprovalDecision(Base):
    """WDD1 — Decision of an authorizer at a stage."""

    __tablename__ = "wdd1"

    wdd_code: Mapped[int] = mapped_column("WddCode", Integer, ForeignKey("owdd.WddCode"), primary_key=True)
    line_id: Mapped[int] = mapped_column("LineId", primary_key=True)
    step_code: Mapped[int] = mapped_column("StepCode", Integer)  # stage (OWST)
    user_id: Mapped[int] = mapped_column("UserID", Integer)
    status: Mapped[str] = mapped_column("Status", String(1))  # Y approved, N rejected
    remarks: Mapped[str | None] = mapped_column("Remarks", String(254))
    update_date: Mapped[datetime] = mapped_column("UpdateDate", DateTime)


class Alert(Base):
    """OALT — Alert (system alert type with a parameter) and whether it is active."""

    __tablename__ = "oalt"

    code: Mapped[int] = mapped_column("Code", primary_key=True)
    name: Mapped[str] = mapped_column("Name", String(50))
    alert_type: Mapped[str] = mapped_column("Type", String(10))  # MINSTOCK, OVERDUE, CREDIT, APPROVAL, NEGSTOCK, EXPIRY
    param: Mapped[int | None] = mapped_column("Param", Integer)  # days (overdue / expiry)
    active: Mapped[str] = mapped_column("Active", String(1), default="Y")
    recipients: Mapped[list["AlertRecipient"]] = relationship(cascade="all, delete-orphan")


class AlertRecipient(Base):
    """ALT1 — Recipients of an alert."""

    __tablename__ = "alt1"

    code: Mapped[int] = mapped_column("Code", Integer, ForeignKey("oalt.Code"), primary_key=True)
    user_id: Mapped[int] = mapped_column("UserId", Integer, ForeignKey("ousr.USERID"), primary_key=True)
