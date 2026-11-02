"""SQLAlchemy engine, session factory, declarative base and schema setup (Alembic)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, echo=settings.sql_echo, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


class Base(DeclarativeBase):
    """Declarative base for all B1 tables."""


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Bring the schema to the newest Alembic revision (``alembic upgrade head``)."""
    from alembic import command
    from alembic.config import Config

    from app import models  # noqa: F401  (registers all tables)

    cfg = Config(str(_ALEMBIC_INI))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
