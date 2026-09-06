# RecordGuard Core15 — Shared Repository Extraction

Core15 moves the remaining tenant-owned API operations onto the PostgreSQL repository boundary while keeping SQLite/desktop compatibility intact.

## Included
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
A live PostgreSQL server was not available in the development environment, so live database execution/migration remains unverified. Core15 validates routing, contracts, static tenant predicates, and the existing full regression suite.

## Next phase
After Core15, complete adversarial authorization testing and then begin functional Web Core8 on top of the stable API.
