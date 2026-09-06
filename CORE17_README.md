# RecordGuard Core17 — Security & Adversarial Validation

Core17 hardens the PostgreSQL API boundary before Web Core8 UI implementation.

## Delivered

- PostgreSQL medication links are validated against both **organization and patient** for prescriptions and encounters.
- Prescription/encounter UUID relationships are validated before database writes; mismatched prescription/encounter pairs are rejected.
- Audit identifiers (`organization_id`, `actor_id`, `resource_id`, `patient_id`, `correlation_id`) are validated as UUIDs before insertion.
- Audit filters use exact matching for identifiers and controlled text fields instead of broad `ILIKE` matching, preventing ambiguous record selection.
- Patient-link approval now maintains the canonical `patient_user_links` relationship as well as the current `users.patient_id` compatibility field.
- Family duplicate handling catches only `UniqueViolation` instead of swallowing unrelated database failures.
- PostgreSQL lifecycle archive permissions are aligned with the shared policy: Owner/Admin/Doctor/Staff may archive; only Owner/Admin recover archived records; only Owner/Admin may Admin-delete; only Owner may recover Admin-deleted records or permanently destroy them.
- Login no longer silently selects an account when active credentials match multiple accounts; it fails closed with an ambiguity error.
- Tenant scope remains explicit across patient links, family access, sharing, attachments, medication lifecycle, and clinical EHR lifecycle operations.
- Added adversarial/static security tests covering tenant boundaries, lifecycle staging, credential ambiguity, UUID boundaries, canonical linking, audit filtering, and database-error handling.

## Verification

- **90 tests passed** with `pytest -q`.
- Python compilation was verified for the modified PostgreSQL repository.
- No live PostgreSQL server was available in this environment, so database integration behavior remains subject to live PostgreSQL verification.

## Important production follow-up

Core17 is a security-validation milestone, not production certification. Before deployment, run the same authorization matrix against a real PostgreSQL instance, complete SQLite→PostgreSQL migration testing, move attachments/backups to protected storage, and perform independent security/privacy testing.
