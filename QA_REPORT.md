# RecordGuard QA Report — Core27

## Scope

Security and production-hardening validation after Core26 UX refinement.

## Results

| Check | Result |
|---|---|
| Full pytest suite | **132 passed, 3 skipped** |
| Python compilation | **Passed** |
| Typed legacy authorization | **Passed** |
| HTTP status mapping regression | **Passed** |
| Request correlation ID | **Passed** |
| Security headers | **Passed** |
| Cookie-session cross-site mutation guard | **Passed** |
| Web bearer-token browser persistence | **Passed** |
| PostgreSQL live authorization tests | **Skipped locally; CI configured** |
| Next.js production build | **Not run locally; dependencies unavailable** |

## Security notes

Authorization is no longer classified by searching human-readable exception text.
Legacy SQLite authorization failures use a dedicated exception type, while ordinary
RecordGuard errors remain validation/application errors.

Browser state-changing requests authenticated by the HttpOnly session cookie are
checked against the configured allowed Origin when an Origin header is supplied.
Bearer-token API clients are not affected by this browser-specific guard.

The `X-Request-ID` value is generated server-side for traceability and is not copied
from arbitrary client input.

## Not yet a production certification

Live PostgreSQL tests, dependency/SCA scanning, penetration testing, production secret
management, object-storage controls, monitoring/alerting, backup/restore drills,
and performance/accessibility validation remain release gates.
