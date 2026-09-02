"""SQLite session repository used during the Core8 -> Web transition.

The business/domain rules do not depend on this module. A PostgreSQL
implementation can satisfy the same SessionRepository contract later.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid

from database import get_connection


def _now():
    return datetime.now(timezone.utc).isoformat()


class SQLiteSessionRepository:
    def create_session(self, user_id: int, organization_id: str, ttl_seconds: int = 3600) -> str:
        token = secrets.token_urlsafe(48)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        session_id = "SES-" + uuid.uuid4().hex[:16].upper()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(60, int(ttl_seconds)))
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO api_sessions(session_id,token_hash,user_id,organization_id,created_at,expires_at) VALUES(?,?,?,?,?,?)",
                (session_id, digest, int(user_id), str(organization_id or "DEFAULT"), now.isoformat(), expires.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        return token

    def get_session_user(self, token: str):
        if not token:
            return None
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT u.user_id,u.username,u.email,u.role,u.patient_id,u.full_name,u.active,
                          u.permanent_delete_authorized,u.organization_id,u.created_at,s.session_id,s.expires_at
                   FROM api_sessions s JOIN users u ON u.user_id=s.user_id
                   WHERE s.token_hash=? AND s.revoked_at IS NULL AND u.active=1""",
                (digest,),
            ).fetchone()
            if not row:
                return None
            try:
                expires = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
            except ValueError:
                return None
            if expires <= datetime.now(timezone.utc):
                conn.execute("UPDATE api_sessions SET revoked_at=? WHERE session_id=?", (_now(), row["session_id"]))
                conn.commit()
                return None
            user = {k: row[k] for k in (
                "user_id","username","email","role","patient_id","full_name","active",
                "permanent_delete_authorized","organization_id","created_at"
            )}
            return user
        finally:
            conn.close()

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn = get_connection()
        try:
            conn.execute("UPDATE api_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL", (_now(), digest))
            conn.commit()
        finally:
            conn.close()
