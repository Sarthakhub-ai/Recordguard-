"""Apply the RecordGuard PostgreSQL foundation migration.

Usage:
    set RECORDGUARD_DATABASE_URL=postgresql://...
    python scripts/migrate_postgres.py

The migration is intentionally separate from application startup so a
production operator explicitly controls schema changes.
"""
from pathlib import Path
import os


def main():
    dsn = os.getenv("RECORDGUARD_DATABASE_URL")
    if not dsn:
        raise SystemExit("RECORDGUARD_DATABASE_URL is required.")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Install requirements-web.txt before running the PostgreSQL migration.") from exc

    sql = (Path(__file__).resolve().parents[1] / "database" / "migrations" / "001_recordguard_web.sql").read_text(encoding="utf-8")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("RecordGuard PostgreSQL migration applied successfully.")


if __name__ == "__main__":
    main()
