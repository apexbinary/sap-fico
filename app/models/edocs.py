"""E-documents (India): e-invoice registration (IRN) and e-way bills of marketing documents.

Not B1-verified: B1 keeps electronic documents in its own tables (electronic file manager);
this register keeps one row per IRN / e-way bill with its status and transport details.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EDocument(Base):
    """EDOC — IRN (Kind I) or e-way bill (Kind E) of a document; Status A active, C canceled."""

    __tablename__ = "edoc"

    abs_entry: Mapped[int] = mapped_column("AbsEntry", primary_key=True)
    obj_type: Mapped[str] = mapped_column("ObjType", String(20), index=True)
    doc_entry: Mapped[int] = mapped_column("DocEntry", Integer, index=True)
    kind: Mapped[str] = mapped_column("Kind", String(1))  # I e-invoice (IRN), E e-way bill
    status: Mapped[str] = mapped_column("Status", String(1), default="A")  # A active, C canceled
    mode: Mapped[str] = mapped_column("Mode", String(1))  # T test (generated here), L live (portal response)
    irn: Mapped[str | None] = mapped_column("Irn", String(64), index=True)
    ack_no: Mapped[str | None] = mapped_column("AckNo", String(20))
    ack_date: Mapped[datetime | None] = mapped_column("AckDate", DateTime)
    signed_qr: Mapped[str | None] = mapped_column("SignedQR", Text)
    ewb_no: Mapped[str | None] = mapped_column("EwbNo", String(12), index=True)
    ewb_date: Mapped[datetime | None] = mapped_column("EwbDate", DateTime)
    valid_until: Mapped[datetime | None] = mapped_column("ValidUntil", DateTime)
    trans_mode: Mapped[str | None] = mapped_column("TransMode", String(1))  # 1 road, 2 rail, 3 air, 4 ship
    distance: Mapped[int | None] = mapped_column("Distance", Integer)  # km
    transporter_id: Mapped[str | None] = mapped_column("TransId", String(15))
    transporter_name: Mapped[str | None] = mapped_column("TransName", String(100))
    vehicle_no: Mapped[str | None] = mapped_column("VehicleNo", String(20))
    vehicle_type: Mapped[str | None] = mapped_column("VehicleTyp", String(1))  # R regular, O over-dimensional cargo
    trans_doc_no: Mapped[str | None] = mapped_column("TransDocNo", String(15))
    trans_doc_date: Mapped[date | None] = mapped_column("TransDocDt", Date)
    cancel_reason: Mapped[str | None] = mapped_column("CnclReason", String(1))
    cancel_remark: Mapped[str | None] = mapped_column("CnclRemark", String(100))
    cancel_date: Mapped[datetime | None] = mapped_column("CnclDate", DateTime)
    payload: Mapped[str | None] = mapped_column("Payload", Text)  # JSON sent / to be sent to the portal
    user_sign: Mapped[str | None] = mapped_column("UserSign", String(25))
    created: Mapped[datetime] = mapped_column("CreateDate", DateTime)
