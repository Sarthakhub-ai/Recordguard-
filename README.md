# RecordGuard Core

Lightweight functional-test build of the full RecordGuard project.

**Important:** this is not a reduced-feature backend. The application keeps the overall RecordGuard workflow structure, role-aware navigation, records, sharing, correction, audit, backup/restore, evidence and related functions. Only the visual layer is intentionally lightweight.

Run `main.py` from your IDE or `Run_RecordGuard_Core.bat` on Windows.


## Identity separation
Public self-registration creates only a login user account. It does not create a Patient profile. Patient registration is a separate authorized workflow. A login account may be linked to an already-registered Patient ID only through an authorized linking/provisioning workflow.

## Core8 compatibility note

Core8 source code is written to remain compatible with Python 3.8+ syntax. For Windows, Python 3.10 or newer is recommended. Extract the ZIP before running the application.

## Windows launchers

- `Run_RecordGuard_Core.bat` — desktop Core application.
- `Run_RecordGuard_Web.bat` — API + Next.js web application. It installs missing dependencies and opens `http://localhost:3000`.

For the web launcher, Node.js LTS and Python 3.10+ are required. An internet connection is needed the first time dependencies are installed.
