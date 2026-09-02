# RecordGuard Core12 — Web Security & Governance

Core12 continues the Web Foundation work from Core11.

## Completed

- Added Web API patient-link request/review endpoints.
- Added family relationship and family-access endpoints.
- Added sharing create, batch-create, list and revoke endpoints.
- Hardened sharing list responses so bearer share tokens/token hashes are never disclosed by management APIs.
- Added explicit Pydantic request contracts with `extra="forbid"` for new security-sensitive endpoints.
- Improved API error classification for organization-boundary authorization failures.
- Fixed the medication API contract so `record_date` is optional because the existing domain layer assigns the server timestamp.
- Made the PostgreSQL `users_patient_fk` migration safe to rerun.
- Added an explicit PostgreSQL migration runner (`scripts/migrate_postgres.py`).
- Added PostgreSQL migration structure/idempotence tests.
- Added session revocation, patient-link, family-boundary, sharing disclosure, role-escalation and audit append-only acceptance tests.

## Verification

**64 tests passing.**

Python source files compile successfully.

## PostgreSQL

The PostgreSQL migration remains an explicit deployment operation. Set `RECORDGUARD_DATABASE_URL`, install `requirements-web.txt`, then run:

```text
python scripts/migrate_postgres.py
```

The local test environment used for Core12 does not include a live PostgreSQL server, so live PostgreSQL execution is intentionally not claimed as verified.

## Next gate

1. Run the migration against an isolated PostgreSQL instance.
2. Validate PostgreSQL repositories end-to-end.
3. Add repository-backed API mode rather than continuing to route Web requests through the legacy SQLite domain functions.
4. Complete attachment object storage authorization and migration/restore tests.
5. Complete full family/sharing lifecycle API coverage.
6. Perform full GUI/web acceptance and security review.

## Core13 — API governance and migration groundwork

Core13 continues from Core12 with security/correctness-first changes:
- common/public `user` is now a first-class shared-domain identity role; it cannot add medical records;
- audit API supports structured filters and record-specific audit retrieval;
- medication and clinical EHR lifecycle actions are exposed through explicit API endpoints;
- destructive lifecycle API actions require the current password plus exact `DELETE` confirmation;
- sharing secrets are stripped in the domain-level listing function as well as the API boundary;
- SQLite→PostgreSQL migration preflight now produces a schema/count/identifier-strategy manifest and deliberately blocks `--apply` until live PostgreSQL migration validation exists.

This does **not** claim end-to-end PostgreSQL completion. The existing legacy business functions remain SQLite-backed and must be migrated behind repositories before PostgreSQL can become the sole API datastore.
