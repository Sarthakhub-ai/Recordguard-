# RecordGuard Core28 — Final Integration & Release QA

Core28 is the final planned development gate for the current RecordGuard product scope.
It does not certify the system for clinical production. It establishes repeatable release
checks and documents what still requires an appropriate deployment environment or external
security assessment.

## Release gates

- Full Python regression suite must pass.
- Python source compilation must pass.
- PostgreSQL schema/migration and live authorization matrix must execute against PostgreSQL 16.
- Web dependencies must install and the Next.js production build must pass.
- Production configuration must explicitly select PostgreSQL and configured web origins.
- Browser session must remain HttpOnly and bearer tokens must not be persisted by the web UI.
- Security headers, request correlation IDs and cookie-session CSRF/origin controls must remain enabled.
- Role × resource × lifecycle × organization authorization tests must pass.
- Backup creation must use encrypted v2 backups; restore must verify integrity and rollback safely.
- Dependency/SCA scanning, penetration testing, accessibility/performance testing and pilot validation
  remain external release gates and are not substituted by unit tests.

## Local validation status

The repository's local automated suite is the authoritative regression baseline. Environment-dependent
PostgreSQL and frontend build gates must be reported as skipped/not-run when their dependencies are absent;
never mark them passed by inference.

## Production-only requirements

Before a real deployment, configure secrets outside source control, use protected object storage for
attachments, enable monitoring/alerting and centralized logs, establish backup retention and restore drills,
review dependencies for known vulnerabilities, and perform an independent penetration/security assessment.
