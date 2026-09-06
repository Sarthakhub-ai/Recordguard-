"""Apply the RecordGuard PostgreSQL schema atomically.

This installs the server schema only. It deliberately does not copy legacy
SQLite data; that remains a separate, reviewed data-migration operation.
"""
from __future__ import annotations
import argparse, os
from pathlib import Path


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.getenv("RECORDGUARD_DATABASE_URL"))
    ap.add_argument("--schema", default=str(Path(__file__).parents[1]/"database"/"migrations"/"001_recordguard_web.sql"))
    args=ap.parse_args()
    if not args.dsn:
        raise SystemExit("RECORDGUARD_DATABASE_URL/--dsn is required.")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("psycopg is required. Install requirements-web.txt first.") from exc
    sql=Path(args.schema).read_text(encoding="utf-8")
    with psycopg.connect(args.dsn) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('recordguard:schema:v1'))")
                cur.execute(sql)
    print("RecordGuard PostgreSQL schema applied successfully.")

if __name__ == "__main__":
    main()
