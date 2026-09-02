# RecordGuard Core18 — Functional Web Core8

Core18 moves the Web Core8 scaffold into a functional authenticated workspace while preserving the RecordGuard security boundary: the browser is a client, and the API/shared domain layer remains authoritative for authorization, tenant isolation, lifecycle rules and medical-record policy.

## Delivered

- Authenticated sign-in, `/auth/me` session restoration and sign-out.
- Persistent browser session token with failed-session cleanup.
- Role-aware navigation; audit is exposed only to Owner/Admin users in the client, while the API remains authoritative.
- Tenant-scoped patient directory and patient registration.
- Patient-specific medication history and medication record creation.
- Patient-scoped sharing activity view; bearer share tokens are never displayed by the management UI.
- Organization/account transparency in Settings.
- Responsive, calm healthcare-oriented layout with clear hierarchy and useful empty states.
- Web-specific contract tests in `test_web_core8.py`.

## Verification

- Python test suite: run `pytest -q`.
- Python compilation: `python -m compileall ...`.
- The environment did not have a reachable PostgreSQL server, so live PostgreSQL integration remains a deployment-gate task.
- Node dependencies could not be installed in the build environment before the network operation timed out; therefore `next build` could not be executed here. The source is prepared for a normal `npm install && npm run build` in an environment with npm registry access.

## Next gate

Before production-like Web work, run the API against a real PostgreSQL instance and execute browser-level tests for authentication, tenant isolation, patient access, medication creation, sharing, lifecycle actions and audit visibility. Then proceed to the remaining functional Web pages (encounters, prescriptions, documents, family access, patient-link review and lifecycle controls) rather than cosmetic expansion.
