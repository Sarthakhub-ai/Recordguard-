# RecordGuard Core21 — Audit Hardening & Web Session Safety

Core21 builds on Core20 and closes the remaining concrete hardening items identified during the Core20 remediation pass.

## Changes

- **Browser bearer-token exposure reduced:** web login now uses the HttpOnly `rg_session` cookie and returns `access_token: null` for `client=web`. API clients retain bearer-token compatibility.
- **Correction-review route cleanup:** removed an accidental extra parameter from the correction-review endpoint signature.
- **External-share audit semantics corrected:** bearer-share redemption is audited as `external_share_recipient` with no fabricated `actor_id` pointing at the share creator.
- **Medication share response completeness:** stable `medication_id` is included in the explicit resource allowlist.
- **Regression coverage:** added Core21 tests plus an end-to-end SQLite web-login cookie test.

## Validation

- Python compilation: passed
- Test suite: **119 passed, 3 skipped**
- PostgreSQL live tests: skipped locally because PostgreSQL/psycopg are not installed in this environment; CI remains configured to run them.
- Next.js production build: not run because web dependencies are not installed locally.

## Security boundary

The browser client does not persist or read a bearer token. The server-issued session cookie is HttpOnly and SameSite=Lax. API bearer authentication remains available for non-browser clients.
