# RecordGuard Core19 — Gap Closure & Live Infrastructure Gate

Core19 addresses the highest-priority findings from the comprehensive audit.

## Implemented

- PostgreSQL tenant-consistency foreign keys for tenant-owned patient resources.
- Live PostgreSQL Docker Compose environment for repeatable integration testing.
- Atomic PostgreSQL schema application script with an advisory migration lock.
- Optional live PostgreSQL tests for connection and rollback behavior.
- Clinical Encounter create/list API foundation.
- Prescription create/list API foundation.
- Prescription-to-encounter and clinical resource tenant/patient validation.
- Patient correction-request creation/review foundation with provenance/audit records.
- Opaque attachment object-key storage abstraction with path traversal protection.
- Authenticated attachment download with `no-store` caching.
- Timezone-aware, future-only share expiry validation.
- Security response headers.
- Existing backup implementation verified as AES-256-GCM with PBKDF2-HMAC-SHA256 (600,000 iterations); the audit report's earlier claim that current backups are plain `.rgbackup` files is outdated for newly-created v2 backups.

## Verification

- 105 tests passed.
- 2 live PostgreSQL tests are intentionally skipped unless `RECORDGUARD_DATABASE_URL` is configured and psycopg/live PostgreSQL are available.
- Python compilation passed.
- Next.js build could not be executed because node_modules are not installed in this environment.

## Still requiring a real environment

1. Run PostgreSQL using `docker compose -f docker-compose.postgres.yml up -d` or another PostgreSQL 16+ service.
2. Install `requirements-web.txt`.
3. Set `RECORDGUARD_DATABASE_URL`.
4. Apply the schema with `python scripts/apply_postgres_schema.py`.
5. Run `pytest -q` and the live integration tests.
6. Exercise concurrency, tenant isolation, transaction rollback, and migration against real data.

The SQLite-to-PostgreSQL data migration is intentionally not claimed as complete. The existing migration preflight remains available until a reviewed data-mapping/import operation is executed against a real database.
