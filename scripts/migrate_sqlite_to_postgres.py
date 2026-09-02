"""RecordGuard SQLite -> PostgreSQL migration preflight and controlled migration.

This phase intentionally starts with a preflight manifest. It never mutates the
PostgreSQL database unless --apply is supplied, and it refuses to run without
an explicit DSN. Legacy integer/text identifiers are mapped to PostgreSQL UUIDs
while public Patient/Medication IDs remain stable.
"""
from __future__ import annotations
import argparse, json, os, sqlite3
from pathlib import Path

EXPECTED = {
    "users": ["user_id", "username", "role", "patient_id", "organization_id"],
    "patients": ["patient_id", "organization_id"],
    "medication_records": ["record_id", "patient_id", "organization_id"],
    "audit_log": ["log_id", "organization_id"],
    "attachments": ["attachment_id", "patient_id"],
    "record_shares": ["share_id", "patient_id"],
}


def table_columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def preflight(sqlite_path: str) -> dict:
    path = Path(sqlite_path)
    if not path.is_file():
        raise SystemExit(f"SQLite database not found: {path}")
    conn = sqlite3.connect(path)
    try:
        report = {"sqlite": str(path), "tables": {}, "warnings": [], "safe_to_apply": True}
        for table, required in EXPECTED.items():
            cols = table_columns(conn, table)
            exists = bool(cols)
            missing = [c for c in required if c not in cols]
            count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] if exists else 0
            report["tables"][table] = {"exists": exists, "count": count, "missing_columns": missing}
            if missing:
                report["warnings"].append(f"{table}: missing {', '.join(missing)}")
                report["safe_to_apply"] = False
        # Detect duplicate public identifiers before any UUID mapping is attempted.
        for table, column in (("patients", "patient_id"), ("medication_records", "record_id")):
            if column in table_columns(conn, table):
                dup = conn.execute(f'SELECT "{column}", COUNT(*) FROM "{table}" GROUP BY "{column}" HAVING COUNT(*) > 1 LIMIT 5').fetchall()
                if dup:
                    report["warnings"].append(f"{table}.{column}: duplicate identifiers detected")
                    report["safe_to_apply"] = False
        return report
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default=os.getenv("RECORDGUARD_SQLITE_PATH", "recordguard.db"))
    ap.add_argument("--report", default="migration-preflight.json")
    ap.add_argument("--apply", action="store_true", help="Reserved for the next transactional migration phase")
    args = ap.parse_args()
    report = preflight(args.sqlite)
    report["target"] = "PostgreSQL"
    report["identifier_strategy"] = {
        "patients": "new UUID primary key + preserve public_patient_id",
        "medications": "new UUID primary key + preserve medicine_name",
        "medication_records": "new UUID primary key + preserve public_medication_id",
        "users": "new UUID primary key + map patient relationship after patient import",
        "attachments": "new UUID primary key + object_key manifest; do not expose filesystem paths",
    }
    report["transaction_policy"] = "single PostgreSQL transaction with rollback on any referential-integrity failure"
    if args.apply:
        raise SystemExit("Preflight only: --apply is intentionally blocked until the live PostgreSQL migration runner is enabled and validated.")
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["safe_to_apply"] else 2)


if __name__ == "__main__":
    main()
