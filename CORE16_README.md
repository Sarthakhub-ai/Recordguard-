# RecordGuard Core16 — Security Validation Foundation

Core16 hardens the shared API boundary after repository extraction, focusing on destructive-action confirmation, PostgreSQL UUID correctness, PostgreSQL-only attachment routing, upload-size enforcement, and adversarial security-test foundations while keeping SQLite/desktop compatibility intact.

## Included
- Core15 repository extraction retained as the foundation.
- Destructive medication/EHR API actions require exact `DELETE` confirmation and current password before dispatch.
- PostgreSQL medication relationship IDs are explicitly validated as UUIDs; legacy integer IDs are rejected with a clear API error.
- PostgreSQL attachment upload no longer performs a SQLite patient pre-check.
- Attachment uploads are capped at 20 MB while streaming into temporary storage.
- Core16 security-validation tests for tenant scope, lifecycle confirmation, UUID boundaries, and attachment handling.

## Retained from Core15
- Patient-link request/list/review repository operations.
- Family relationship and access-grant repository operations.
- Secure record-sharing create/list/revoke operations.
- Medication and clinical EHR staged lifecycle operations using PostgreSQL `lifecycle_status`.
- Attachment list/upload persistence with organization-scoped object keys and no filesystem path exposure in API responses.
- PostgreSQL audit writes for extracted operations.
- Append-only PostgreSQL audit protection trigger.
- API routing for extracted operations when `RECORDGUARD_SESSION_BACKEND=postgres`.
- Identifier contracts accept both legacy integer IDs and PostgreSQL UUID/public identifiers during transition.

## Lifecycle
`ACTIVE → ARCHIVED → ADMIN_DELETED → OWNER_PERMANENTLY_DESTROYED`

Destructive actions require current-password verification and the API's `DELETE` confirmation.

## Security boundary
All PostgreSQL operations include explicit `organization_id` predicates. Patient IDs, share IDs, request IDs, grants, and record IDs never bypass tenant scope.

Share bearer tokens are returned only on creation and are not returned by management/list operations.

## Important limitation
A live PostgreSQL server was not available in the development environment, so live database execution/migration remains unverified. Core16 validates routing, contracts, static tenant predicates, destructive-action confirmation, UUID boundaries, attachment handling, and the full regression suite. Live PostgreSQL behavior is still unverified.

## Next phase
Run live PostgreSQL adversarial authorization/integration tests when PostgreSQL is available, then begin functional Web Core8 on top of the stable API.
