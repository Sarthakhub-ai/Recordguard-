# RecordGuard Core14 — PostgreSQL API Integration Foundation

Core14 advances the shared API toward the target architecture without pretending that a live PostgreSQL deployment has been validated.

## Implemented
- PostgreSQL authentication and first-time Owner creation.
- PostgreSQL-backed API sessions and database-backed login throttling.
- PostgreSQL tenant-scoped patient list/get/create operations.
- PostgreSQL tenant-scoped medication list/create operations.
- PostgreSQL tenant-scoped audit retrieval with filters.
- Stable public Patient IDs (`RG#####`) and Medication IDs (`MED-######`).
- PostgreSQL advisory locks around public-ID allocation to reduce concurrent-ID collisions.
- API selects PostgreSQL repositories when `RECORDGUARD_SESSION_BACKEND=postgres`.
- SQLite remains the default desktop/test backend.
- Common/public `user` identity remains distinct from Patient.

## Important boundary
The API is **not yet fully PostgreSQL-native**. Sharing, family, patient-link, attachment and lifecycle operations still use legacy business functions and therefore remain SQLite-backed until their repositories are extracted and verified.

## Verification
- 72 automated tests passing.
- Python compilation passes.
- Live PostgreSQL server validation is still required.

## PostgreSQL mode
Set `RECORDGUARD_SESSION_BACKEND=postgres` and `RECORDGUARD_DATABASE_URL=<DSN>`. Install `psycopg[binary]` from `requirements-web.txt`, apply `database/migrations/001_recordguard_web.sql`, then run the API.

Do not use real PHI in development/demo environments.
