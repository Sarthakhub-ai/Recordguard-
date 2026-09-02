"""Static release gate for RecordGuard production candidates.

This is intentionally conservative: it reports environment-dependent gates rather
than pretending that local absence of PostgreSQL/Node proves them passed.
"""
from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "backend/api/app.py", "backend/security.py", "functions.py", "shared/domain.py",
    "shared/contracts.py", "database/migrations/001_recordguard_web.sql",
    "AUTHORIZATION_MATRIX.md", "QA_REPORT.md", "apps/web/package.json",
]


def check(label: str, ok: bool, detail: str = "") -> tuple[bool, str]:
    return ok, f"{'PASS' if ok else 'FAIL'} | {label}" + (f" | {detail}" if detail else "")


def main() -> int:
    results: list[tuple[bool, str]] = []
    for rel in REQUIRED:
        results.append(check(f"required artifact: {rel}", (ROOT / rel).is_file()))

    # Production deployments must not use SQLite or the development CORS default.
    backend = os.getenv("RECORDGUARD_SESSION_BACKEND", "sqlite").lower()
    results.append(check("production backend selection", backend == "postgres",
                         f"RECORDGUARD_SESSION_BACKEND={backend}"))
    dsn = os.getenv("RECORDGUARD_DATABASE_URL", "")
    results.append(check("PostgreSQL DSN supplied", bool(dsn),
                         "set RECORDGUARD_DATABASE_URL for live validation"))
    origins = [x.strip() for x in os.getenv("RECORDGUARD_WEB_ORIGINS", "").split(",") if x.strip()]
    results.append(check("explicit web origins supplied", bool(origins),
                         "set RECORDGUARD_WEB_ORIGINS; do not rely on localhost defaults"))

    # Production should have Node and an installable web workspace available.
    results.append(check("Node.js available", shutil.which("node") is not None))
    results.append(check("npm available", shutil.which("npm") is not None))
    results.append(check("web dependencies installed", (ROOT / "apps/web/node_modules").is_dir(),
                         "run npm install in apps/web before the production build"))

    print("RecordGuard release readiness")
    print("=" * 32)
    for ok, line in results:
        print(line)
    failed = sum(not ok for ok, _ in results)
    print(f"\nGate status: {'READY' if failed == 0 else 'BLOCKED'} ({failed} gate(s) unresolved)")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
