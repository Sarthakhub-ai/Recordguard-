"""Web/API security services shared across API workers through SQLite/PostgreSQL-compatible state."""
from datetime import datetime, timedelta, timezone
import hashlib

from database import get_connection


def _now():
    return datetime.now(timezone.utc).isoformat()

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60
LOCK_SECONDS = 30


def _key(username: str, client_ip: str) -> str:
    raw = f"{username.strip().lower()}|{client_ip.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def check_login_rate(username: str, client_ip: str) -> None:
    key = _key(username, client_ip)
    conn = get_connection()
    try:
        row = conn.execute("SELECT failures, locked_until, updated_at FROM api_login_attempts WHERE key=?", (key,)).fetchone()
        if not row:
            return
        now = datetime.now(timezone.utc)
        if row["locked_until"]:
            try:
                locked = datetime.fromisoformat(str(row["locked_until"]).replace("Z", "+00:00"))
            except ValueError:
                locked = now
            if locked > now:
                remaining = max(1, int((locked - now).total_seconds() + 0.999))
                raise PermissionError(f"Too many failed sign-in attempts. Try again in {remaining} seconds.")
        # Expire stale counters so an old burst cannot affect a later login.
        try:
            updated = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
            if (now - updated).total_seconds() > WINDOW_SECONDS:
                conn.execute("DELETE FROM api_login_attempts WHERE key=?", (key,))
                conn.commit()
        except ValueError:
            pass
    finally:
        conn.close()


def record_login_failure(username: str, client_ip: str) -> None:
    key = _key(username, client_ip)
    now = datetime.now(timezone.utc)
    conn = get_connection()
    try:
        row = conn.execute("SELECT failures, updated_at FROM api_login_attempts WHERE key=?", (key,)).fetchone()
        failures = 0
        if row:
            try:
                updated = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
                if (now - updated).total_seconds() <= WINDOW_SECONDS:
                    failures = int(row["failures"])
            except ValueError:
                pass
        failures += 1
        locked_until = (now + timedelta(seconds=LOCK_SECONDS)).isoformat() if failures >= MAX_ATTEMPTS else None
        conn.execute(
            "INSERT INTO api_login_attempts(key,failures,locked_until,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET failures=excluded.failures,locked_until=excluded.locked_until,updated_at=excluded.updated_at",
            (key, failures, locked_until, now.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def clear_login_failures(username: str, client_ip: str) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM api_login_attempts WHERE key=?", (_key(username, client_ip),))
        conn.commit()
    finally:
        conn.close()
