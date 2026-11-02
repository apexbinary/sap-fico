"""Run every end-to-end check in order (after app.seed):  python -m app.verify_all

Each check posts its own documents, so run this against a scratch database.
"""

from __future__ import annotations

import importlib
import time

CHECKS = ["verify_finance", "verify_masterdata", "verify_documents", "verify_fields", "verify_banking", "verify_fc", "verify_gst", "verify_taxsetup"]


def main() -> None:
    for name in CHECKS:
        started = time.perf_counter()
        print(f"\n===== {name} =====")
        importlib.import_module(f"app.{name}").main()
        print(f"----- {name} passed ({time.perf_counter() - started:.1f}s)")
    print(f"\nALL {len(CHECKS)} CHECKS PASSED")


if __name__ == "__main__":
    main()
