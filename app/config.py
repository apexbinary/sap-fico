"""Application configuration.

Defaults to a local SQLite database so the project runs with zero setup.
Set DATABASE_URL to a PostgreSQL DSN for a production-like backend, e.g.:

    DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/sapfico
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SAP FI/CO Clone"
    database_url: str = f"sqlite:///{(_BASE_DIR / 'sapfico.db').as_posix()}"

    # Default client (MANDT) the API operates under when none is supplied.
    default_client: str = "100"

    # Echo SQL for debugging.
    sql_echo: bool = False


settings = Settings()
