"""List values longer than their declared VARCHAR length.

SQLite ignores String(n) limits; PostgreSQL rejects such values. Run against a
database filled by app.seed and the verify scripts before relying on Postgres:
    python -m scripts.check_lengths
"""

from __future__ import annotations

from sqlalchemy import String, func, select

from app import models  # noqa: F401  (registers all tables)
from app.database import Base, engine


def main() -> int:
    problems = 0
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            for col in table.columns:
                if not isinstance(col.type, String) or not col.type.length:
                    continue
                longest = conn.execute(select(func.max(func.length(col)))).scalar()
                if longest and longest > col.type.length:
                    sample = conn.execute(
                        select(col).where(func.length(col) > col.type.length).limit(1)).scalar()
                    print(f"{table.name}.{col.name}: VARCHAR({col.type.length}) but {longest} chars, e.g. {sample!r}")
                    problems += 1
    print("OK - all values fit" if not problems else f"{problems} column(s) too short")
    return problems


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
