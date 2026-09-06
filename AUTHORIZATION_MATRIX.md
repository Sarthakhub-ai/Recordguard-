# RecordGuard Authorization Matrix — Core20

This is the formal parity matrix for API/repository authorization. Every resource must be tested against both SQLite and PostgreSQL paths. A check is not considered complete until the same expected decision is observed on both backends.

| Resource / Action | Owner | Admin | Doctor | Staff | Patient | Common User | Backend parity required |
|---|---|---|---|---|---|---|---|
| Patient directory | Allow | Allow | Allow | Allow | Own only | Deny | SQLite + PostgreSQL |
| Patient profile | Allow | Allow | Allow | Allow | Own only | Deny | SQLite + PostgreSQL |
| Medication history | Allow | Allow | Allow | Allow | Own only | Deny | SQLite + PostgreSQL |
| Add medication | Allow | Allow | Allow | Allow | Deny | Deny | SQLite + PostgreSQL |
| Encounters | Allow | Allow | Allow | Read/operational per policy | Own only | Deny | SQLite + PostgreSQL |
| Prescriptions | Allow | Allow | Allow | Read/operational per policy | Own only | Deny | SQLite + PostgreSQL |
| Documents | Allow | Allow | Allow | Allow | Own only | Deny | SQLite + PostgreSQL |
| Sharing management | Allow | Allow | Own patient scope | Deny unless explicitly granted by policy | Own only | Deny | SQLite + PostgreSQL |
| Family access | Allow | Allow | Deny | Deny | Own patient scope | Deny | SQLite + PostgreSQL |
| Patient linking request | Deny | Deny | Deny | Deny | N/A | Allow | SQLite + PostgreSQL |
| Patient linking review | Allow | Allow | Deny | Deny | Deny | Deny | SQLite + PostgreSQL |
| Correction request | Review/manage | Review/manage | Read/manage per policy | Deny | Own linked profile | Deny | SQLite + PostgreSQL |
| Audit log | Allow | Allow | Deny | Deny | Deny | Deny | SQLite + PostgreSQL |
| Archive | Allow | Allow | Allow | Allow (shared-domain policy) | Deny | Deny | SQLite + PostgreSQL |
| Recover archived | Allow | Allow | Deny | Deny | Deny | Deny | SQLite + PostgreSQL |
| Admin-delete | Allow | Allow | Deny | Deny | Deny | Deny | SQLite + PostgreSQL |
| Recover Admin-deleted | Allow | Deny | Deny | Deny | Deny | Deny | SQLite + PostgreSQL |
| Permanent destroy | Allow | Deny | Deny | Deny | Deny | Deny | SQLite + PostgreSQL |

## Core20 security requirements

1. Common User must not enumerate the patient directory or read medical records before an approved patient link.
2. Patient accounts must be restricted to their own linked patient profile.
3. Organization scope must be enforced on every resource read/write.
4. Backend authorization is authoritative; frontend hiding is only usability, never security.
5. Tests for authorization boundaries must run against both backend modes.
6. Share redemption must validate token hash, revocation, expiry, organization/resource ownership and active lifecycle status.
7. Attachment downloads must perform the same patient/role authorization as attachment listing.
