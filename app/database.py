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

    _rebuild_tables_with_new_key_columns()
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _rebuild_tables_with_new_key_columns() -> None:
    """Recreate tables whose model gained a primary-key column, keeping their rows.

    A new key column must be a string with default '' (e.g. REGUH-KUNNR next to
    LIFNR); existing rows get '' in it. Tables with a foreign key to a rebuilt
    table are rebuilt with it, so their constraints point at the new table.
    """
    insp = inspect(engine)
    stale: dict[str, set[str]] = {}
    for table in Base.metadata.sorted_tables:  # parents before children
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        new_key = any(c.name not in existing for c in table.primary_key.columns)
        child = any(fk.column.table.name in stale for fk in table.foreign_keys)
        if new_key or child:
            stale[table.name] = existing
    if not stale:
        return

    tables = [t for t in Base.metadata.sorted_tables if t.name in stale]
    for t in tables:
        for c in t.primary_key.columns:
            if c.name not in stale[t.name] and not (c.default is not None and c.default.arg == ""):
                raise RuntimeError(f"Cannot add key column {t.name}.{c.name} automatically; migrate manually")

    with engine.begin() as conn:
        for t in tables:
            conn.execute(text(f"ALTER TABLE {t.name} RENAME TO {t.name}__old"))
            if engine.dialect.name == "postgresql":
                conn.execute(text(f"ALTER TABLE {t.name}__old RENAME CONSTRAINT {t.name}_pkey TO {t.name}__old_pkey"))
    Base.metadata.create_all(bind=engine, tables=tables)
    with engine.begin() as conn:
        for t in tables:
            kept = [c.name for c in t.columns if c.name in stale[t.name]]
            added = [c.name for c in t.primary_key.columns if c.name not in stale[t.name]]
            cols = ", ".join(kept + added)
            values = ", ".join(kept + ["''"] * len(added))
            conn.execute(text(f"INSERT INTO {t.name} ({cols}) SELECT {values} FROM {t.name}__old"))
        for t in reversed(tables):
            conn.execute(text(f"DROP TABLE {t.name}__old"))


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
