# RecordGuard Synthetic Demo Dataset

This optional dataset is intended for local QA, demonstrations and UX testing.
It contains **synthetic** data only and must not be treated as real clinical information.

## What is created

- 5 Admin accounts
- 10 Staff accounts
- 5 Doctor accounts
- 100 synthetic patient profiles
  - exactly 20 registered by each demo Admin
- 50 patient/individual login accounts
  - linked to the first 50 synthetic patients
- 1 clearly-marked demo encounter and 1 demo prescription for every patient
- audit entries for the seeded operations

The real Owner account is **never created, replaced or modified** by the seeder.

## Setup

1. Start RecordGuard normally.
2. Complete the normal first-run Owner setup using your own Owner credentials.
3. Close RecordGuard.
4. Run `Seed_Demo_Data.bat` (or `python seed_demo_data.py`).
5. Enter the Owner username and password when prompted.
6. The generated demo credentials are written to `DEMO_CREDENTIALS.txt`.

The seed is protected against accidental second execution. If demo accounts already
exist, it stops without making changes.

## Production warning

Do **not** use the demo credentials or synthetic clinical entries in a production
installation. Remove/deactivate all `demo_*` accounts and demo data before loading
real patient information.
