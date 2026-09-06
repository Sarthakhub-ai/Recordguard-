# RecordGuard Core20 — Audit Remediation & Authorization Parity

Core20 addresses the findings from the static audit of Core18/Core19, with emphasis on the critical PostgreSQL authorization parity defect.

## Fixed

- PostgreSQL patient directory now enforces role authorization.
- PostgreSQL patient profile reads now enforce role + linked-patient scope.
- PostgreSQL medication history now enforces the same patient-read policy.
- Encounter and prescription reads use the same patient-read authorization guard.
- Common User accounts cannot enumerate or browse patient records before approved linking.
- Patient accounts are limited to their own linked profile.
- Web frontend no longer stores bearer tokens in localStorage; web sessions use an HttpOnly cookie.
- Web navigation is role-aware as a usability layer while server authorization remains authoritative.
- Patient search supports server-side query filtering and result limits.
- Share redemption endpoint added with hash, revocation, expiry, organization/patient/resource and lifecycle checks.
- Share redemption response uses an explicit resource-field allowlist.
- Attachment content is checked against file signatures/container structure, not only filename extension.
- Formal authorization matrix added in `AUTHORIZATION_MATRIX.md`.
- Live PostgreSQL authorization parity tests added and run automatically when `RECORDGUARD_DATABASE_URL` is available.
- GitHub Actions workflow added with PostgreSQL 16 service, schema application, and full test execution.
- Typed `AuthorizationError` introduced for new API/repository authorization paths.
- Existing SQLite compatibility error mapping remains unchanged while legacy `functions.py` errors are migrated incrementally.

## Verification

- Python compilation: PASS
- Automated tests: 114 passed
- Live PostgreSQL tests: skipped locally because no PostgreSQL service/DSN is available in this environment
- CI workflow: configured to run live PostgreSQL tests on GitHub Actions

## Important limitation

Core20 cannot claim live PostgreSQL readiness from local testing alone. The CI/live environment must execute the PostgreSQL authorization suite before the infrastructure gate is considered complete.

## Next

Core21 should focus on the full live authorization matrix across all six roles and all healthcare resources, then complete the remaining Web clinical lifecycle/editing workflows.
