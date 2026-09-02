# RecordGuard Web Core8 — Functional Foundation

This Next.js client now provides a functional authenticated workspace over the RecordGuard API:

- Sign in / sign out with persisted session token.
- Role-aware navigation for Dashboard, Patients, Medications, Sharing, Audit and Settings.
- Tenant-scoped patient directory and patient registration through the API.
- Patient medication history and medication-record creation through the API.
- Sharing-center read view that never displays bearer share tokens.
- Owner/Admin audit-trail view.
- Account, organization and patient-link transparency.

The web client intentionally does **not** duplicate authorization, lifecycle policy, tenant checks, or medical business rules. The API/domain layer remains authoritative.

## Run

```bash
npm install
npm run dev
```

Set `NEXT_PUBLIC_RECORDGUARD_API` when the API is not at `http://localhost:8000`.
