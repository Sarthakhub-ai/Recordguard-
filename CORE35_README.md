# RecordGuard Core35 — PostgreSQL Parity & UTF-8 Regression Closure

## Purpose
Core35 is a direct development continuation of the Core34 consolidated build. It does not replace the product vision or reset earlier work.

## Changes in Core35
- Fixed the Windows/CP1252 regression in `tests_web/test_core26_ux.py` by making source reads explicitly UTF-8.
- Added Core35 regression tests covering:
  - every `data_repository.*` method referenced by the Web API is bound by `PostgreSQLRepository`;
  - the Core26 UX test uses explicit UTF-8 decoding;
  - organization/clinic assignment routes use the PostgreSQL repository when PostgreSQL mode is enabled;
  - clinic administration normalizes the Actor role through `_pg_role()`.
- Closed a PostgreSQL-mode organization/clinic parity gap:
  - `list_user_clinics`
  - `assign_user_to_clinic`
  - `list_patient_clinics`
  - `assign_patient_to_clinic`
- Fixed the Core34 clinic authorization bug caused by comparing `str(Role.ADMIN)`/`str(Role.OWNER)` with plain role strings.
- Preserved tenant scoping, audit logging, and UUID validation for the new PostgreSQL clinic operations.

## Validation
Targeted Core35 + Core26 UX tests:

    7 passed

Python compilation completed successfully before the final package was assembled.

A full-suite run was started, but the consolidated environment stalled during an existing Core13 lifecycle test when executed after the earlier suite tests. That test passes independently in 2.39s. Therefore the full suite is **not claimed as a completed Core35 validation** from this environment.

## Remaining PostgreSQL parity work
Core35 begins systematic parity closure; it does not claim the PostgreSQL path is production-ready yet. The next checks should exercise the live PostgreSQL service for every repository operation and authorization path, including:

- user/account lifecycle
- patient and medication CRUD
- encounters and prescriptions
- correction requests
- patient linking
- family relationships/access
- record sharing/redemption/revocation
- attachments and object storage
- medication/EHR lifecycle transitions
- organization/clinic administration
- audit immutability and tenant isolation

## Release rule
Do not push Core35 to `main`. After local/live PostgreSQL validation succeeds, review the complete diff and push to the development branch first.
