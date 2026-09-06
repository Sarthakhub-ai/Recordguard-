# RecordGuard Core

This is the **functional testing build** of RecordGuard.

It contains the same major application workflows and backend/security logic as the overall project, while using a lightweight visual layer. The sidebar, top bar, workspace positions, navigation model, forms, tables, and role-aware workflow structure intentionally stay close to the polished RecordGuard UI.

The goal is to make functional/security testing easy. Visual polish is intentionally reduced and will be developed separately in `RecordGuard-UI`.

## Run
- IDE: run `main.py`
- Windows: run `Run_RecordGuard_Core.bat`

## Development tracks
- `RecordGuard-Core`: security, correctness, stability and workflow testing.
- `RecordGuard-UI`: visual/UX development.
- Final RecordGuard: combine the tested Core with the completed UI without duplicating business/security logic.


## Identity separation
Public self-registration creates only a login user account. It does not create a Patient profile. Patient registration is a separate authorized workflow. A login account may be linked to an already-registered Patient ID only through an authorized linking/provisioning workflow.
