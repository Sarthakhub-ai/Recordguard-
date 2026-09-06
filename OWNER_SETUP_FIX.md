# RecordGuard Core10 — First-time Owner Setup Fix

## What changed

Fresh installations now treat Owner setup as a startup state rather than an optional sign-in link.

Startup:

    python main.py
        ↓
    initialize database
        ↓
    show Sign in
        ↓
    check for active Owner after Tk is idle
        ↓
    no Owner → automatically open First-time Owner setup

The setup window is centered, raised, focused, and modal. A visible `First-time setup — Create Owner account` button is also present whenever no active Owner exists.

If the Owner check itself fails, the sign-in screen still exposes a visible setup action instead of silently hiding it.

## Validation

- Python compile check: passed
- Fresh database owner check: `False`
- Initial Owner creation: passed
- Owner password hash is not returned in the authenticated session: passed
- Full regression suite: **52 passed**
