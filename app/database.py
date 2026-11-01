"""SQLAlchemy engine, session factory, and declarative base.

All ORM models inherit from ``Base``. SAP tables are client-dependent (the MANDT
field), so most models carry a ``mandt`` column as part of their primary key,
exactly as in the SAP data dictionary.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    echo=settings.sql_echo,
    connect_args=_connect_args,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all SAP FI/CO ORM models."""


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a scoped session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_all() -> None:
    """Create every mapped table. Imports models so metadata is populated."""
    from app import models  # noqa: F401  (registers all models on Base.metadata)

    Base.metadata.create_all(bind=engine)
