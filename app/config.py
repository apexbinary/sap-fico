"""Application configuration.

Defaults to a local SQLite database; set DATABASE_URL for PostgreSQL, e.g.
    DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/sapb1
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SAP Business One Clone"
    database_url: str = f"sqlite:///{(_BASE_DIR / 'b1.db').as_posix()}"
    sql_echo: bool = False


settings = Settings()
