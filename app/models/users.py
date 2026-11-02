"""Users, general authorizations and login sessions.

Tables modelled here (SAP Business One names where they exist):
    OUSR   Users (superuser, locked, password hash)
    USR3   General authorizations of a user: permission per area (F full, R read-only, N none)
    OUSS   Login sessions (token of the B1SESSION cookie) — not a B1 table; B1's Service Layer
           keeps its sessions in memory
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """OUSR — User."""

    __tablename__ = "ousr"

    user_id: Mapped[int] = mapped_column("USERID", primary_key=True)
    user_code: Mapped[str] = mapped_column("USER_CODE", String(25), unique=True)
    u_name: Mapped[str] = mapped_column("U_NAME", String(155))
    e_mail: Mapped[str | None] = mapped_column("E_Mail", String(100))
    department: Mapped[str | None] = mapped_column("Department", String(50))
    superuser: Mapped[str] = mapped_column("SUPERUSER", String(1), default="N")
    locked: Mapped[str] = mapped_column("Locked", String(1), default="N")
    password: Mapped[str] = mapped_column("PasswordHash", String(200))  # pbkdf2$iterations$salt$hash
    last_login: Mapped[datetime | None] = mapped_column("LastLogin", DateTime)


class UserPermission(Base):
    """USR3 — General authorization of a user for an area."""

    __tablename__ = "usr3"

    user_link: Mapped[int] = mapped_column("UserLink", ForeignKey("ousr.USERID"), primary_key=True)
    perm_id: Mapped[str] = mapped_column("PermId", String(20), primary_key=True)
    permission: Mapped[str] = mapped_column("Permission", String(1))  # F full, R read-only, N none


class UserSession(Base):
    """OUSS — Login session (not a B1 table)."""

    __tablename__ = "ouss"

    token: Mapped[str] = mapped_column("Token", String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column("UserId", ForeignKey("ousr.USERID"))
    created: Mapped[datetime] = mapped_column("Created", DateTime)
    expires: Mapped[datetime] = mapped_column("Expires", DateTime)
