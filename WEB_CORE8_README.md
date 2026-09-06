# RecordGuard Web Core8 Foundation

This package is the transition point from the stable Core8 desktop application to a shared Web/Mobile architecture.

## Run the existing desktop app

```text
python main.py
```

The desktop application remains the compatibility client during migration.

## Run the API locally

Install the web dependencies:

```text
pip install -r requirements-web.txt
```

Then:

```text
python run_api.py
```

Open `/docs` on the local API to inspect the generated OpenAPI contract.

## Current transition storage

The API foundation uses Core8 SQLite temporarily so the desktop and web migration can be tested without prematurely moving the production database. The PostgreSQL target schema is in:

`database/migrations/001_recordguard_web.sql`

Do not use this transition SQLite API with real healthcare/PHI data.

## Security boundaries added

- API sessions use random bearer tokens; only SHA-256 token digests are stored.
- API responses use explicit allowlists and never return `password_hash`.
- API login throttling is shared through database state rather than an in-memory Python dictionary.
- Organization IDs are carried into child SQLite records during the migration phase.
- Shared domain rules are framework-independent and intended for Desktop/Web/Mobile reuse.
- PostgreSQL schema gives tenant-owned entities explicit `organization_id`.
- Attachment storage target is a private object store using `object_key`, not a public/local filesystem path.

## Next milestone

1. Move clinical operations behind repository interfaces.
2. Implement the PostgreSQL repository.
3. Migrate synthetic Core8 data.
4. Expand API authorization tests.
5. Build Next.js Web Core8.
6. Deploy the demo frontend to Vercel and API/database to a suitable backend host.
7. Build Mobile only after the API contract is stable.


## Core10 Web completion additions — 2026-09-01

The repository now contains `apps/web`, a lightweight Next.js client scaffold. It authenticates through `/auth/login` and keeps authorization/business rules in the API/shared domain layer.

The API also exposes patient-scoped attachment listing/upload endpoints and supports a PostgreSQL session repository when configured with `RECORDGUARD_SESSION_BACKEND=postgres` and `RECORDGUARD_DATABASE_URL`. The domain data repository is intentionally narrow until the complete SQLite-to-PostgreSQL migration is validated against representative data.
