"""Check that no stored text is longer than its column (SQLite does not enforce VARCHAR lengths,
PostgreSQL refuses such values). Runs last in verify_all, over everything the other checks created.

Run after app.seed:  python -m app.verify_lengths
"""

from __future__ import annotations

from sqlalchemy import String, func, select

import app.models  # noqa: F401  (registers every table)
from app.database import Base, SessionLocal


def main() -> None:
    with SessionLocal() as s:
        bad = []
        for t in Base.metadata.sorted_tables:
            for c in t.columns:
                if isinstance(c.type, String) and c.type.length:
                    n = s.execute(select(func.max(func.length(c))).select_from(t)).scalar()
                    if n and n > c.type.length:
                        bad.append(f"{t.name}.{c.name}: {n} > {c.type.length}")
        assert not bad, "values longer than their column: " + "; ".join(bad)
        print(f"1 {len(Base.metadata.sorted_tables)} tables: every text value fits its column")
    print("\nOK - all stored values fit their columns (as PostgreSQL requires).")


if __name__ == "__main__":
    main()
