# RecordGuard Core22 — Clinical Web Workflows & Lifecycle Controls

Core22 continues from Core21 by moving the Web Core8 workspace from a read-only clinical shell toward an operational, role-aware workflow.

## Delivered

- Added Web **Clinical** workspace with Encounter and Prescription views.
- Added encounter creation for Owner/Admin/Doctor/Staff.
- Added prescription creation for Owner/Admin/Doctor/Staff.
- Added `include_archived` visibility to medication, encounter and prescription list API routes.
- Added Web lifecycle controls for medication, encounter and prescription records.
- Lifecycle actions remain server-authorized; the UI only exposes actions appropriate to the authenticated role and current status.
- Destructive Web actions require current password and exact `DELETE` confirmation.
- Owner-only recovery of Admin-deleted records and permanent destruction are preserved.
- Patient users can review their linked clinical records but do not receive clinical write controls.
- Web bearer tokens remain out of localStorage and web login uses the HttpOnly session cookie.
- Added regression coverage for the new API/UI surface.

## Lifecycle UI

`ACTIVE -> ARCHIVED -> ADMIN_DELETED -> OWNER recovery / permanent destruction`

The Web UI does not attempt to bypass this state machine. Invalid transitions are rejected by the API/repository.

## Validation

Targeted security and Web regression suite: **47 passed**.

Python compilation passed.

TypeScript build was not executed in this environment because `apps/web/node_modules` is not installed. PostgreSQL live tests remain environment-dependent and were not claimed as locally passed.

## Next boundary

The next development stage should complete the Web governance workflows: patient-link review, correction-request review/action, family access, sharing creation/revocation/redeem UI, attachment/document workflows, and a full role × resource × lifecycle integration matrix against live PostgreSQL.
