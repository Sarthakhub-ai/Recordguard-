# RecordGuard Core36 — Live PostgreSQL Parity & Integration Validation Gate

Core36 continues directly from Core35. It does not replace or weaken the existing authorization/domain model.

## Completed in this build

- Re-validated the Core35 UTF-8 regression fix on the consolidated source.
- Restored the canonical `styles.css` web entrypoint and removed generated web/package artifacts from the release archive.
- Completed the Health Vault emergency-card and JSON/CSV portability controls.
- Completed the read-only FHIR-inspired interoperability UI and preserved its clinical safety boundary.
- Updated regression checks to validate current architecture rather than brittle source formatting.
- Added correction-request provenance wording and retained explicit lifecycle/tenant authorization checks.
- Re-validated PostgreSQL repository/API method binding across the web API surface.
- Added explicit Core36 release-gate tests proving that live PostgreSQL validation is configuration-gated and cannot silently count as a pass without a PostgreSQL DSN and `RECORDGUARD_SESSION_BACKEND=postgres`.
- Removed generated Python caches from the development package.
- Preserved the existing PostgreSQL implementations for family access, sharing, attachments, clinical records, corrections, lifecycle, and organization/clinic features.

## Validation performed in the build environment

`python -m pytest -q`

**162 passed, 3 skipped**.

The skipped tests are live PostgreSQL tests because this build environment does not provide Docker/PostgreSQL. They are intentionally not represented as passed.

## Required laptop gate

From a machine with Docker, Python 3, and Node/npm:

1. Copy `.env.validation.example` to `.env.validation`.
2. Set a strong local-only `POSTGRES_PASSWORD` and matching `RECORDGUARD_DATABASE_URL`.
3. Run `scripts/setup_release_validation.ps1` on Windows PowerShell, or `scripts/setup_release_validation.sh` on macOS/Linux.
4. Confirm the PostgreSQL container is healthy.
5. Confirm the schema applies successfully.
6. Confirm the Next.js production build succeeds.
7. Review `FINAL_VALIDATION_REPORT.md` and `FINAL_VALIDATION_RESULTS.json`.
8. Run the complete live PostgreSQL suite explicitly before pushing.

## Release rule

Core36 is **not release-ready** until the live PostgreSQL gates pass on the target environment. A missing PostgreSQL environment is a blocked gate, not a successful test.
