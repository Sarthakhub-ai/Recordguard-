# RecordGuard Core8

Core8 hardens the Core7 foundation around identity separation, verified patient linking, stable medication identities, structured append-only auditing, family-access foundations, and security regression coverage.

## Identity
- Public signup creates a **User Account only** (`role=user`, no Patient profile, no Patient ID).
- Patient registration remains a separate medical-profile operation.
- Existing Patient profiles can be linked later only through a pending request reviewed by an Owner/Admin.
- Patient ID alone never grants access.
- Unlinking removes the account-to-patient association without deleting the Patient profile.
- Login accepts username or optional email; password hashes are never returned in session state.

## Roles
- Owner: full organization control.
- Admin: creates Doctor/Staff/Patient accounts, but cannot create Owner/Admin accounts.
- Doctor: clinical workflows; cannot create privileged accounts.
- Staff: permitted operational workflows; cannot create privileged accounts.
- User: unlinked common account; no medical access until verified linking.
- Patient: access only to its linked Patient profile and permitted workflows.

## Medication identity
Each medication record now has a stable human-facing identifier such as `MED-000001` while the internal SQLite row id remains available for relational compatibility. Optional `prescription_id` and `encounter_id` relationships are supported.

## Audit
Audit events are structured with:
- Event ID
- Timestamp
- Actor ID / role
- Organization
- Action / category
- Resource type / resource ID
- Patient ID
- Result
- Reason/context
- Source
- Correlation ID

Audit rows are protected by SQLite append-only triggers. Corrections are represented by new events rather than edits/deletions.

## Family foundation
Core8 adds normalized family relationships and explicit family-access grants. Family relationship does not itself grant medical access.

## Backup/security
Core7's encrypted `.rgbackup` path remains in place using AES-256-GCM with PBKDF2-HMAC-SHA256. Owner authentication is required for restore.

## Validation
Run:

```text
python -m pytest -q test_core8.py
python -m pytest -q test_security_hardening.py
python -m pytest -q test_gap_closure.py
python -m pytest -q test_engineering_safeguards.py
python -m pytest -q test_search_alerts.py
python -m pytest -q test_patient_validation.py
python -m pytest -q test_role_security.py
```

`core_ui.py`, `functions.py`, `models.py`, and `database.py` also pass Python compilation checks.

## Core8 completion additions

### Medication organization
Medication records now expose a human-facing MED identifier plus a controlled lifecycle status:
- ACTIVE
- COMPLETED
- DISCONTINUED
- ARCHIVED
- ADMIN-DELETED is represented by the existing recoverable deletion state and cannot be permanently destroyed until that state exists.

The UI presents medication information as Summary → Details → History/Evidence rather than exposing all internal metadata at once.

### Family access
Family relationships are independently managed from medical permissions. Supported relationship types are spouse/partner, parent, child, guardian, dependent, sibling, caregiver and other.

Explicit delegated resources are medication, appointments, documents and EHR. Access can be granted, restricted/revoked and audited. A relationship never implies medical access.

### Account recovery
Owner/Admin-assisted password reset is available from User Management. The existing password is never displayed or returned; only a newly generated password hash is stored, and the reset is recorded in the structured audit log.

### Completion tests
`test_core8_complete.py` covers family relationship/access enforcement, medication lifecycle status, and assisted password recovery.
