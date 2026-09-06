# Core 33 — Sharing & Consent Center

Stage 6 strengthens RecordGuard's patient-controlled sharing workflow.

## Changes
- Sharing history now exposes a derived status: ACTIVE, EXPIRED, REVOKED, or INVALID_EXPIRY.
- Bearer share tokens remain excluded from management/list responses.
- Sharing UI supports medication, clinical, document, encounter, and prescription resources.
- Expiry uses a native date/time input and expired grants cannot be revoked/redeemed as active grants.
- Share opening is available in the Sharing Center and is explicitly described as a one-time disclosure boundary, not ongoing account access.
- Last-opened timestamps are surfaced for transparency.
- Existing server-side authorization, organization boundaries, audit logging, and token secrecy remain intact.

## Safety boundary
Sharing only exposes explicitly selected record resources. It does not create clinical authorization, diagnosis, prescribing, or medicine interchangeability decisions.

## Validation
`python -m pytest -q` — 148 passed, 3 skipped.
