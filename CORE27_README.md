# RecordGuard Core27 — Security & Production Hardening

Core27 is the security-hardening stage following Core26 Product & UX Refinement.
It does not add unrelated product features. The focus is deterministic authorization,
safer browser-session behavior, request traceability, and regression validation.

## Implemented

- Typed `AuthorizationRecordGuardError` for legacy SQLite/domain authorization failures.
- Removed HTTP status inference based on matching authorization words in error messages.
- Deterministic API mapping: typed authorization failures return HTTP 403; ordinary
  expected application errors return HTTP 400.
- Server-generated `X-Request-ID` correlation identifier on every HTTP response.
- Cookie-session CSRF/origin guard for state-changing browser requests when the
  HttpOnly `rg_session` cookie is present.
- Existing security headers retained: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, and HTTPS HSTS.
- Web login continues to avoid returning a bearer token to browser JavaScript;
  browser authentication uses the HttpOnly `rg_session` cookie.
- Core27 regression tests cover typed authorization, request IDs, security headers,
  and cross-site mutation blocking.

## Validation

- Full local suite: **132 passed, 3 skipped**.
- Python compilation: passed.
- PostgreSQL live tests remain environment/CI dependent when PostgreSQL and `psycopg`
  are unavailable locally.
- Next.js production build remains environment dependent when web dependencies are
  not installed locally.

## Remaining production gates

Core27 is not a declaration of production certification. Before a real deployment,
RecordGuard still needs live PostgreSQL authorization-matrix execution, dependency/SCA
review, penetration testing, operational secret management, production object storage,
monitoring/alerting, backup/restore drills, accessibility/performance testing, and
an end-to-end pilot validation.
