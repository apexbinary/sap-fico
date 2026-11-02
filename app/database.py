"""SQLAlchemy engine, session factory, and declarative base.

All ORM models inherit from ``Base``. SAP tables are client-dependent (the MANDT
field), so most models carry a ``mandt`` column as part of their primary key,
exactly as in the SAP data dictionary.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
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
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Add nullable model columns that an existing table does not have yet.

    ``create_all`` never ALTERs existing tables, so a model that gains an
    optional SAP field would break an existing database. Anything beyond adding
    nullable columns needs a real migration (Alembic is on the roadmap).
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing or col.primary_key or not col.nullable:
                    continue
                ddl = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}"))
