"""Run every end-to-end check in order (after app.seed):  python -m app.verify_all

Each check posts its own documents, so run this against a scratch database,
not the one you work in.
"""

from __future__ import annotations

import importlib
import time

CHECKS = [
    "verify", "verify_assets", "verify_payments", "verify_payment_run", "verify_fsv",
    "verify_documents", "verify_recurring", "verify_dunning", "verify_fx", "verify_controlling",
]


def main() -> None:
    for name in CHECKS:
        started = time.perf_counter()
        print(f"\n===== {name} =====")
        importlib.import_module(f"app.{name}").main()
        print(f"----- {name} passed ({time.perf_counter() - started:.1f}s)")
    print(f"\nALL {len(CHECKS)} CHECKS PASSED")


if __name__ == "__main__":
    main()
