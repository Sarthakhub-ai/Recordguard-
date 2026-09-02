"""PostgreSQL repositories for the RecordGuard Web API."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib, secrets, os
from uuid import UUID
from typing import Optional
from database import hash_password, verify_password
from shared.domain import AuthorizationError
try:
    import psycopg
    from psycopg.rows import dict_row
    try:
        from psycopg.errors import UniqueViolation
    except ImportError:
        UniqueViolation = Exception
except ImportError:
    psycopg = None
    dict_row = None
    UniqueViolation = Exception

class PostgreSQLUnavailable(RuntimeError):
    pass

class PostgreSQLSessionRepository:
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("RECORDGUARD_DATABASE_URL")
        if not self.dsn or psycopg is None:
            raise PostgreSQLUnavailable("PostgreSQL support requires RECORDGUARD_DATABASE_URL and psycopg.")
    def _connect(self): return psycopg.connect(self.dsn, row_factory=dict_row)
    @staticmethod
    def _hash(token): return hashlib.sha256(token.encode()).hexdigest()
    def create_session(self, user_id, organization_id, ttl_seconds=3600):
        token=secrets.token_urlsafe(48); now=datetime.now(timezone.utc); exp=now+timedelta(seconds=max(60,int(ttl_seconds)))
        with self._connect() as c: c.execute("INSERT INTO api_sessions(organization_id,user_id,token_hash,created_at,expires_at) VALUES(%s,%s,%s,%s,%s)",(organization_id,user_id,self._hash(token),now,exp))
        return token
    def get_session_user(self, token):
        if not token: return None
        with self._connect() as c:
            row=c.execute("""SELECT u.user_id,u.username,u.email,u.role,u.patient_id,u.full_name,u.active,u.organization_id,u.created_at,s.session_id,s.expires_at FROM api_sessions s JOIN users u ON u.user_id=s.user_id WHERE s.token_hash=%s AND s.revoked_at IS NULL AND u.active=TRUE""",(self._hash(token),)).fetchone()
            if not row: return None
            if row['expires_at'] <= datetime.now(timezone.utc):
                c.execute("UPDATE api_sessions SET revoked_at=%s WHERE session_id=%s",(datetime.now(timezone.utc),row['session_id'])); return None
            return {k:row[k] for k in ('user_id','username','email','role','patient_id','full_name','active','organization_id','created_at')}
    def revoke_session(self, token):
        if not token: return
        with self._connect() as c: c.execute("UPDATE api_sessions SET revoked_at=%s WHERE token_hash=%s AND revoked_at IS NULL",(datetime.now(timezone.utc),self._hash(token)))

class PostgreSQLRepository:
    """PostgreSQL persistence for API-owned domain operations.

    Every query takes organization scope explicitly. Public identifiers remain
    stable across the SQLite -> PostgreSQL migration while internal primary
    keys are UUIDs.
    """
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("RECORDGUARD_DATABASE_URL")
        if not self.dsn or psycopg is None:
            raise PostgreSQLUnavailable("PostgreSQL support requires RECORDGUARD_DATABASE_URL and psycopg.")

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    # ---------- authentication / sessions ----------
    def has_owner(self, organization_id=None) -> bool:
        with self._connect() as c:
            if organization_id is None:
                return c.execute("SELECT EXISTS(SELECT 1 FROM users WHERE role='owner' AND active=TRUE)", ()).fetchone()["exists"]
            return c.execute("SELECT EXISTS(SELECT 1 FROM users WHERE organization_id=%s AND role='owner' AND active=TRUE)", (organization_id,)).fetchone()["exists"]

    def create_initial_owner(self, username: str, password: str, full_name: str):
        username = username.strip()
        if not username or not password:
            raise ValueError("Username and password are required.")
        with self._connect() as c:
            if c.execute("SELECT 1 FROM users WHERE lower(username)=lower(%s)", (username,)).fetchone():
                raise ValueError("Username is already in use.")
            org = c.execute(
                "INSERT INTO organizations(organization_code,name) VALUES(%s,%s) RETURNING organization_id",
                ("DEFAULT", "RecordGuard")
            ).fetchone()
            org_id = org["organization_id"]
            user = c.execute(
                """INSERT INTO users(organization_id,username,password_hash,role,full_name,active)
                   VALUES(%s,%s,%s,'owner',%s,TRUE)
                   RETURNING user_id,username,email,role,patient_id,full_name,active,organization_id,created_at""",
                (org_id, username, hash_password(password), full_name.strip())
            ).fetchone()
            return dict(user)

    def authenticate_user(self, username: str, password: str):
        username = (username or "").strip()
        with self._connect() as c:
            matches = c.execute(
                """SELECT user_id,username,email,role,patient_id,full_name,active,organization_id,created_at,password_hash
                   FROM users WHERE (username=%s OR lower(email)=lower(%s)) AND active=TRUE
                   ORDER BY created_at ASC""",
                (username, username)
            ).fetchall()
        if len(matches) > 1:
            raise ValueError("Multiple active accounts match these credentials. Sign in with an organization-scoped account identifier.")
        user = matches[0] if matches else None
        if not user or not verify_password(password, user["password_hash"]):
            raise ValueError("Invalid username or password.")
        return {k: user[k] for k in ("user_id","username","email","role","patient_id","full_name","active","organization_id","created_at")}

    # ---------- login throttling ----------
    @staticmethod
    def _throttle_key(username: str, client_ip: str) -> str:
        raw = f"{username.strip().lower()}|{client_ip.strip()}".encode()
        return hashlib.sha256(raw).hexdigest()

    def check_login_rate(self, username: str, client_ip: str, window_seconds=60, lock_seconds=30, max_attempts=5):
        key = self._throttle_key(username, client_ip)
        now = datetime.now(timezone.utc)
        with self._connect() as c:
            row = c.execute("SELECT failures,locked_until,updated_at FROM api_login_attempts WHERE key=%s", (key,)).fetchone()
            if not row:
                return
            if row["locked_until"] and row["locked_until"] > now:
                remaining = max(1, int((row["locked_until"] - now).total_seconds() + .999))
                raise PermissionError(f"Too many failed sign-in attempts. Try again in {remaining} seconds.")
            if row["updated_at"] and (now - row["updated_at"]).total_seconds() > window_seconds:
                c.execute("DELETE FROM api_login_attempts WHERE key=%s", (key,))

    def record_login_failure(self, username: str, client_ip: str, window_seconds=60, lock_seconds=30, max_attempts=5):
        key = self._throttle_key(username, client_ip)
        now = datetime.now(timezone.utc)
        with self._connect() as c:
            row = c.execute("SELECT failures,updated_at FROM api_login_attempts WHERE key=%s", (key,)).fetchone()
            failures = int(row["failures"]) if row and row["updated_at"] and (now-row["updated_at"]).total_seconds() <= window_seconds else 0
            failures += 1
            locked = now + timedelta(seconds=lock_seconds) if failures >= max_attempts else None
            c.execute("""INSERT INTO api_login_attempts(key,failures,locked_until,updated_at) VALUES(%s,%s,%s,%s)
                        ON CONFLICT(key) DO UPDATE SET failures=EXCLUDED.failures,locked_until=EXCLUDED.locked_until,updated_at=EXCLUDED.updated_at""",
                      (key, failures, locked, now))

    def clear_login_failures(self, username: str, client_ip: str):
        with self._connect() as c:
            c.execute("DELETE FROM api_login_attempts WHERE key=%s", (self._throttle_key(username, client_ip),))

    # ---------- patients / medications ----------
    def list_patients(self, actor, query=None):
        """List only patients the authenticated actor is allowed to enumerate."""
        role = _pg_role(actor)
        with self._connect() as c:
            if role == "user":
                raise PermissionError("Common User accounts cannot access the patient directory until linked and authorized.")
            if role == "patient":
                linked = c.execute(
                    "SELECT patient_id FROM users WHERE organization_id=%s AND user_id=%s AND patient_id IS NOT NULL AND active=TRUE",
                    (actor.organization_id, actor.user_id),
                ).fetchone()
                if not linked:
                    return []
                rows = c.execute(
                    "SELECT * FROM patients WHERE organization_id=%s AND patient_id=%s ORDER BY created_at DESC",
                    (actor.organization_id, linked["patient_id"]),
                ).fetchall()
                return [dict(r) for r in rows]
            if role not in {"owner", "admin", "doctor", "staff"}:
                raise PermissionError("You are not authorized to view the patient directory.")
            q = str(query or "").strip()
            if q:
                like = f"%{q}%"
                rows = c.execute(
                    "SELECT * FROM patients WHERE organization_id=%s AND (public_patient_id ILIKE %s OR name ILIKE %s OR COALESCE(phone_number,'') ILIKE %s) ORDER BY created_at DESC LIMIT 200",
                    (actor.organization_id, like, like, like),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM patients WHERE organization_id=%s ORDER BY created_at DESC LIMIT 1000",
                    (actor.organization_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_patient(self, actor, patient_id):
        role = _pg_role(actor)
        with self._connect() as c:
            row = c.execute(
                "SELECT * FROM patients WHERE organization_id=%s AND public_patient_id=%s",
                (actor.organization_id, str(patient_id).strip().upper()),
            ).fetchone()
            if not row:
                return None
            if role == "user":
                raise PermissionError("Common User accounts cannot access medical records until linked and authorized.")
            if role == "patient":
                linked = c.execute(
                    "SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s AND active=TRUE",
                    (actor.organization_id, actor.user_id, row["patient_id"]),
                ).fetchone()
                if not linked:
                    raise PermissionError("Patients can only access their own linked Patient profile.")
            elif role not in {"owner", "admin", "doctor", "staff"}:
                raise PermissionError("You are not authorized to view this Patient profile.")
            return dict(row)

    def create_patient(self, actor, name, age, sex, date_of_birth=None, permanent_address=None,
                       current_address=None, phone_number=None, blood_group=None):
        if actor.role.value not in {"owner", "admin", "doctor", "staff"}:
            raise PermissionError("You are not authorized to register patients.")
        with self._connect() as c:
            # Serialize public-ID allocation per organization to avoid duplicate
            # RG identifiers under concurrent registrations.
            c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"patient:{actor.organization_id}",))
            row = c.execute("""SELECT COALESCE(MAX(CAST(SUBSTRING(public_patient_id FROM 3) AS INTEGER)),0) AS n
                              FROM patients WHERE organization_id=%s AND public_patient_id ~ '^RG[0-9]+$'""", (actor.organization_id,)).fetchone()
            public_id = f"RG{int(row['n']) + 1:05d}"
            row = c.execute("""INSERT INTO patients(organization_id,public_patient_id,name,age,sex,date_of_birth,
                              permanent_address,current_address,phone_number,blood_group,registered_by)
                              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                              RETURNING *""", (actor.organization_id,public_id,name,age,sex,date_of_birth,
                                                permanent_address,current_address,phone_number,blood_group,actor.user_id)).fetchone()
            return dict(row)

    def list_medications(self, actor, patient_id, include_archived=False):
        with self._connect() as c:
            p = c.execute(
                "SELECT patient_id FROM patients WHERE organization_id=%s AND public_patient_id=%s",
                (actor.organization_id, str(patient_id).strip().upper()),
            ).fetchone()
            if not p:
                raise ValueError("Patient not found.")
            _pg_require_patient_read(c, actor, p["patient_id"])
            sql = """SELECT mr.*,m.medicine_name FROM medication_records mr JOIN medications m ON m.medication_id=mr.medication_id
                     WHERE mr.organization_id=%s AND mr.patient_id=%s"""
            params = [actor.organization_id, p["patient_id"]]
            if not include_archived:
                sql += " AND mr.lifecycle_status='ACTIVE'"
            sql += " ORDER BY mr.record_date DESC"
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def create_medication(self, actor, patient_id, medicine_name, response_type, reaction=None, severity=None,
                          reason=None, notes=None, prescription_id=None, encounter_id=None):
        # PostgreSQL resource links are UUIDs. Legacy integer IDs must never be
        # passed directly into UUID columns; reject them explicitly instead of
        # allowing an opaque database adapter error.
        for label, value in (("prescription_id", prescription_id), ("encounter_id", encounter_id)):
            if value is not None:
                try:
                    UUID(str(value))
                except (ValueError, AttributeError):
                    raise ValueError(f"{label} must be a PostgreSQL UUID when using the PostgreSQL API.")
        if actor.role.value not in {"owner", "admin", "doctor", "staff"}:
            raise PermissionError("You are not authorized to add medical records.")
        with self._connect() as c:
            patient = c.execute("SELECT patient_id FROM patients WHERE organization_id=%s AND public_patient_id=%s", (actor.organization_id, patient_id)).fetchone()
            if not patient:
                raise ValueError("Patient not found.")
            patient_uuid = patient["patient_id"]
            if prescription_id is not None:
                rx = c.execute("SELECT patient_id,organization_id FROM prescriptions WHERE prescription_id=%s", (str(prescription_id),)).fetchone()
                if not rx or rx["organization_id"] != actor.organization_id or rx["patient_id"] != patient_uuid:
                    raise ValueError("The prescription does not belong to this organization and patient.")
            if encounter_id is not None:
                enc = c.execute("SELECT patient_id,organization_id FROM encounters WHERE encounter_id=%s", (str(encounter_id),)).fetchone()
                if not enc or enc["organization_id"] != actor.organization_id or enc["patient_id"] != patient_uuid:
                    raise ValueError("The encounter does not belong to this organization and patient.")
            if prescription_id is not None and encounter_id is not None:
                rx_enc = c.execute("SELECT encounter_id FROM prescriptions WHERE prescription_id=%s", (str(prescription_id),)).fetchone()
                if rx_enc and rx_enc["encounter_id"] is not None and rx_enc["encounter_id"] != UUID(str(encounter_id)):
                    raise ValueError("The prescription and encounter do not match.")
            med = c.execute("SELECT medication_id FROM medications WHERE medicine_name=%s", (medicine_name.strip(),)).fetchone()
            if not med:
                med = c.execute("INSERT INTO medications(medicine_name) VALUES(%s) RETURNING medication_id", (medicine_name.strip(),)).fetchone()
            c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"medication:{actor.organization_id}",))
            seq = c.execute("""SELECT COALESCE(MAX(CAST(SUBSTRING(public_medication_id FROM 5) AS INTEGER)),0) AS n
                              FROM medication_records WHERE organization_id=%s AND public_medication_id ~ '^MED-[0-9]+$'""", (actor.organization_id,)).fetchone()["n"]
            public_id = f"MED-{int(seq)+1:06d}"
            row = c.execute("""INSERT INTO medication_records(organization_id,public_medication_id,patient_id,medication_id,
                              prescription_id,encounter_id,response_type,reaction,severity,reason,notes,record_date)
                              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) RETURNING *""",
                            (actor.organization_id,public_id,patient["patient_id"],med["medication_id"],prescription_id,
                             encounter_id,response_type,reaction,severity,reason,notes)).fetchone()
            result = dict(row)
            result["medicine_name"] = medicine_name.strip()
            return result

    # ---------- audit ----------
    def list_audit_events(self, organization_id, filters=None):
        filters = filters or {}
        sql = "SELECT * FROM audit_events WHERE organization_id=%s"
        params = [_pg_uuid(organization_id, "organization_id")]
        text_filters = {"actor_role":"actor_role","action":"action","category":"category",
                        "resource_type":"resource_type","result":"result"}
        for key, col in text_filters.items():
            value = str(filters.get(key) or "").strip()
            if value:
                sql += f" AND {col}=%s"; params.append(value)
        uuid_filters = {"actor_id":"actor_id","resource_id":"resource_id","patient_id":"patient_id"}
        for key, col in uuid_filters.items():
            value = filters.get(key)
            if value not in (None, ""):
                sql += f" AND {col}=%s"; params.append(_pg_uuid(value, key))
        if filters.get("date_from"):
            sql += " AND timestamp >= %s"; params.append(filters["date_from"])
        if filters.get("date_to"):
            sql += " AND timestamp <= %s"; params.append(filters["date_to"])
        sql += " ORDER BY timestamp DESC"
        with self._connect() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

# ---------- Core15 shared tenant-owned operations ----------
# These methods intentionally live beside the PostgreSQL repository so API
# routes no longer need to call the SQLite-centric functions.py for these areas.

def _pg_role(actor):
    return getattr(getattr(actor, "role", None), "value", getattr(actor, "role", None))

def _pg_require_role(actor, roles, message):
    if _pg_role(actor) not in set(roles):
        raise AuthorizationError(message)

def _pg_require_patient_read(c, actor, patient_uuid):
    """Enforce role and linked-patient scope for all PostgreSQL patient reads."""
    role = _pg_role(actor)
    if role in {"owner", "admin", "doctor", "staff"}:
        return
    if role == "patient":
        linked = c.execute(
            "SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s AND active=TRUE",
            (actor.organization_id, actor.user_id, patient_uuid),
        ).fetchone()
        if linked:
            return
        raise PermissionError("Patients can only access their own linked Patient profile.")
    raise PermissionError("This account is not authorized to access patient medical records.")

def _pg_now():
    return datetime.now(timezone.utc)

def _pg_patient_uuid(c, actor, public_id):
    row = c.execute("SELECT patient_id FROM patients WHERE organization_id=%s AND public_patient_id=%s", (actor.organization_id, str(public_id).strip().upper())).fetchone()
    if not row:
        raise ValueError("Patient not found.")
    return row["patient_id"]

def _pg_user_uuid(c, actor, user_id):
    row = c.execute("SELECT user_id FROM users WHERE organization_id=%s AND user_id=%s AND active=TRUE", (actor.organization_id, str(user_id))).fetchone()
    if not row:
        raise ValueError("User account not found.")
    return row["user_id"]

def _pg_uuid(value, label):
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{label} must be a PostgreSQL UUID.") from exc


def _pg_audit(c, actor, action, category, resource_type=None, resource_id=None, patient_id=None, result="SUCCESS", reason_context=None, correlation_id=None):
    resource_uuid = _pg_uuid(resource_id, "resource_id")
    patient_uuid = _pg_uuid(patient_id, "patient_id")
    correlation_uuid = _pg_uuid(correlation_id, "correlation_id")
    actor_uuid = _pg_uuid(actor.user_id, "actor_id")
    organization_uuid = _pg_uuid(actor.organization_id, "organization_id")
    c.execute("""INSERT INTO audit_events(organization_id,actor_id,actor_role,action,category,resource_type,resource_id,patient_id,result,reason_context,source,correlation_id)
                 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'api',%s)""",
              (organization_uuid, actor_uuid, _pg_role(actor), action, category, resource_type,
               resource_uuid, patient_uuid, result, reason_context, correlation_uuid))

def _pg_share_resource(c, actor, patient_uuid, resource_type, resource_id):
    typ = str(resource_type or "medication").strip().lower()
    table_map = {"medication": ("medication_records", "record_id"), "encounter": ("encounters", "encounter_id"),
                 "prescription": ("prescriptions", "prescription_id"), "document": ("attachments", "attachment_id")}
    if typ not in table_map:
        raise ValueError("Unsupported share resource type.")
    table, key = table_map[typ]
    row = c.execute(f"SELECT lifecycle_status, patient_id FROM {table} WHERE organization_id=%s AND {key}=%s", (actor.organization_id, str(resource_id))).fetchone()
    if not row or row["patient_id"] != patient_uuid:
        raise ValueError("The selected record does not belong to this patient or is unavailable.")
    if row["lifecycle_status"] != "ACTIVE":
        raise ValueError("Archived or deleted records are not available for new shares.")

def _pg_lifecycle_status(c, table, key, actor, rid):
    return c.execute(f"SELECT * FROM {table} WHERE organization_id=%s AND {key}=%s", (actor.organization_id, str(rid))).fetchone()


def _core15_request_patient_link(self, actor, patient_id, reason=""):
    _pg_require_role(actor, {"user"}, "Only an unlinked common user account can request patient linking.")
    if getattr(actor, "patient_id", None):
        raise ValueError("This account is already linked to a Patient profile.")
    with self._connect() as c:
        p = c.execute("SELECT patient_id FROM patients WHERE organization_id=%s AND public_patient_id=%s", (actor.organization_id, str(patient_id).strip().upper())).fetchone()
        if not p: raise ValueError("Patient record could not be verified.")
        if c.execute("SELECT 1 FROM users WHERE organization_id=%s AND patient_id=%s AND active=TRUE", (actor.organization_id, p["patient_id"])).fetchone():
            raise ValueError("That Patient profile is already linked to an account.")
        pending = c.execute("SELECT request_id FROM patient_link_requests WHERE organization_id=%s AND user_id=%s AND patient_id=%s AND status='PENDING'", (actor.organization_id, actor.user_id, p["patient_id"])).fetchone()
        if pending: return str(pending["request_id"])
        row = c.execute("""INSERT INTO patient_link_requests(organization_id,user_id,patient_id,requested_by,status,reason_context)
                           VALUES(%s,%s,%s,%s,'PENDING',%s) RETURNING request_id""", (actor.organization_id,actor.user_id,p["patient_id"],actor.user_id,str(reason or "").strip())).fetchone()
        _pg_audit(c, actor, "LINK_REQUESTED", "identity", "patient", p["patient_id"], p["patient_id"], reason_context=reason, correlation_id=row["request_id"])
        return str(row["request_id"])


def _core15_list_patient_link_requests(self, actor, status=None):
    _pg_require_role(actor, {"owner", "admin"}, "Only Owner or Admin can review linking requests.")
    sql="""SELECT r.request_id,r.organization_id,r.user_id,r.patient_id,r.requested_by,r.status,r.reason_context,r.created_at,r.reviewed_by,r.reviewed_at,r.review_notes,u.username,p.public_patient_id,p.name
           FROM patient_link_requests r JOIN users u ON u.user_id=r.user_id JOIN patients p ON p.patient_id=r.patient_id
           WHERE r.organization_id=%s"""; params=[actor.organization_id]
    if status: sql += " AND r.status=%s"; params.append(str(status).upper())
    sql += " ORDER BY r.created_at DESC"
    with self._connect() as c: return [dict(x) for x in c.execute(sql, params).fetchall()]


def _core15_review_patient_link_request(self, actor, request_id, decision, notes=""):
    _pg_require_role(actor, {"owner", "admin"}, "Only Owner or Admin can verify patient linking requests.")
    decision=str(decision or "").strip().upper()
    if decision not in {"APPROVED","REJECTED"}: raise ValueError("Decision must be APPROVED or REJECTED.")
    with self._connect() as c:
        row=c.execute("SELECT * FROM patient_link_requests WHERE organization_id=%s AND request_id=%s",(actor.organization_id,str(request_id))).fetchone()
        if not row: raise ValueError("Link request not found.")
        if row["status"] != "PENDING": raise ValueError("This link request has already been reviewed.")
        if decision == "APPROVED":
            if c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id IS NOT NULL AND active=TRUE",(actor.organization_id,row["user_id"])).fetchone(): raise ValueError("User account is already linked to a Patient profile.")
            if c.execute("SELECT 1 FROM users WHERE organization_id=%s AND patient_id=%s AND active=TRUE",(actor.organization_id,row["patient_id"])).fetchone(): raise ValueError("Patient profile is already linked to another account.")
            c.execute("UPDATE users SET patient_id=%s, role='patient' WHERE organization_id=%s AND user_id=%s",(row["patient_id"],actor.organization_id,row["user_id"]))
            c.execute("INSERT INTO patient_user_links(organization_id,user_id,patient_id,status) VALUES(%s,%s,%s,'ACTIVE') ON CONFLICT(organization_id,user_id,patient_id) DO UPDATE SET status='ACTIVE'", (actor.organization_id,row["user_id"],row["patient_id"]))
            action="LINK_VERIFIED"; result="SUCCESS"
            c.execute("UPDATE patient_link_requests SET status='APPROVED',reviewed_by=%s,reviewed_at=%s,review_notes=%s WHERE request_id=%s",(actor.user_id,_pg_now(),str(notes or ""),row["request_id"]))
            _pg_audit(c,actor,"PATIENT_LINKED","identity","patient",row["patient_id"],row["patient_id"],reason_context=f"Link request {request_id}",correlation_id=row["request_id"])
        else:
            action="LINK_VERIFIED"; result="FAILURE"
            c.execute("UPDATE patient_link_requests SET status='REJECTED',reviewed_by=%s,reviewed_at=%s,review_notes=%s WHERE request_id=%s",(actor.user_id,_pg_now(),str(notes or ""),row["request_id"]))
        _pg_audit(c,actor,action,"identity","patient",row["patient_id"],row["patient_id"],result=result,reason_context=notes,correlation_id=row["request_id"])
        return True


def _core15_create_family_relationship(self, actor, patient_id, related_patient_id, relationship_type):
    typ=str(relationship_type or "").strip().lower()
    allowed={"spouse_partner","parent","child","guardian","dependent","sibling","caregiver","other"}
    if typ not in allowed: raise ValueError("Invalid family relationship type.")
    with self._connect() as c:
        p1=_pg_patient_uuid(c,actor,patient_id); p2=_pg_patient_uuid(c,actor,related_patient_id)
        if p1==p2: raise ValueError("A Patient cannot be related to itself.")
        if _pg_role(actor) not in {"owner","admin"}:
            linked = c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s",(actor.organization_id,actor.user_id,p1)).fetchone()
            if not linked: raise PermissionError("Only the linked Patient or an Owner/Admin can manage family relationships.")
        try:
            row=c.execute("""INSERT INTO family_relationships(organization_id,patient_id,related_patient_id,relationship_type,created_by)
                             VALUES(%s,%s,%s,%s,%s) RETURNING relationship_id""",(actor.organization_id,p1,p2,typ,actor.user_id)).fetchone()
        except UniqueViolation as exc:
            raise ValueError("That family relationship already exists.") from exc
        _pg_audit(c,actor,"FAMILY_MEMBER_ADDED","family","family_relationship",row["relationship_id"],p1,reason_context=typ)
        return str(row["relationship_id"])


def _core15_list_family_relationships(self, actor, patient_id):
    with self._connect() as c:
        p=_pg_patient_uuid(c,actor,patient_id)
        role=_pg_role(actor)
        if role not in {"owner","admin"} and not c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s",(actor.organization_id,actor.user_id,p)).fetchone():
            raise PermissionError("You are not authorized to view this patient's family relationships.")
        return [dict(r) for r in c.execute("""SELECT fr.*,p.public_patient_id,p.name AS related_name FROM family_relationships fr JOIN patients p ON p.patient_id=fr.related_patient_id
                                                WHERE fr.organization_id=%s AND fr.patient_id=%s ORDER BY fr.created_at DESC""",(actor.organization_id,p)).fetchall()]


def _core15_grant_family_access(self, actor, patient_id, grantee_user_id, resource_type, permission):
    resource=str(resource_type or "").strip().lower(); perm=str(permission or "").strip().lower()
    if resource not in {"medication","appointments","documents","ehr"}: raise ValueError("Unsupported family resource type.")
    if perm not in {"view","restrict"}: raise ValueError("Permission must be view or restrict.")
    with self._connect() as c:
        p=_pg_patient_uuid(c,actor,patient_id)
        role=_pg_role(actor)
        if role not in {"owner","admin"} and not c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s",(actor.organization_id,actor.user_id,p)).fetchone():
            raise PermissionError("Only the linked Patient or an Owner/Admin can grant family access.")
        g=_pg_user_uuid(c,actor,grantee_user_id)
        if g==actor.user_id: raise ValueError("You cannot create a family grant to yourself.")
        row=c.execute("""INSERT INTO family_access_grants(organization_id,patient_id,grantee_user_id,resource_type,permission,status,granted_by)
                         VALUES(%s,%s,%s,%s,%s,'ACTIVE',%s)
                         ON CONFLICT(organization_id,patient_id,grantee_user_id,resource_type,permission)
                         DO UPDATE SET status='ACTIVE',revoked_at=NULL,granted_by=EXCLUDED.granted_by,created_at=now()
                         RETURNING grant_id""",(actor.organization_id,p,g,resource,perm,actor.user_id)).fetchone()
        _pg_audit(c,actor,"FAMILY_ACCESS_GRANTED","family","family_access",row["grant_id"],p,reason_context=f"{resource}:{perm}")
        return str(row["grant_id"])


def _core15_revoke_family_access(self, actor, grant_id):
    with self._connect() as c:
        row=c.execute("SELECT * FROM family_access_grants WHERE organization_id=%s AND grant_id=%s",(actor.organization_id,str(grant_id))).fetchone()
        if not row: raise ValueError("Family access grant not found.")
        role=_pg_role(actor)
        if role not in {"owner","admin"} and not c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s",(actor.organization_id,actor.user_id,row["patient_id"])).fetchone():
            raise PermissionError("Only the linked Patient or an Owner/Admin can revoke family access.")
        c.execute("UPDATE family_access_grants SET status='REVOKED',revoked_at=now() WHERE organization_id=%s AND grant_id=%s",(actor.organization_id,row["grant_id"]))
        _pg_audit(c,actor,"FAMILY_ACCESS_REVOKED","family","family_access",row["grant_id"],row["patient_id"]); return True


def _core15_list_family_access(self, actor, patient_id):
    with self._connect() as c:
        p=_pg_patient_uuid(c,actor,patient_id)
        role=_pg_role(actor)
        if role not in {"owner","admin"} and not c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s",(actor.organization_id,actor.user_id,p)).fetchone():
            raise PermissionError("You are not authorized to view family access settings.")
        return [dict(r) for r in c.execute("""SELECT g.*,u.username,u.full_name FROM family_access_grants g JOIN users u ON u.user_id=g.grantee_user_id
                                                WHERE g.organization_id=%s AND g.patient_id=%s ORDER BY g.created_at DESC""",(actor.organization_id,p)).fetchall()]


def _core15_create_record_shares_batch(self, actor, patient_id, items, shared_with, expires_at=None):
    if not str(shared_with or "").strip(): raise ValueError("Recipient is required.")
    with self._connect() as c:
        p=_pg_patient_uuid(c,actor,patient_id)
        role=_pg_role(actor)
        if role not in {"owner","admin"} and not c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s",(actor.organization_id,actor.user_id,p)).fetchone():
            raise PermissionError("You are not authorized to share this patient's record.")
        expiry=None
        if expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid share expiration.") from exc
            if expiry.tzinfo is None:
                raise ValueError("Share expiration must include a timezone.")
            expiry = expiry.astimezone(timezone.utc)
            if expiry <= _pg_now():
                raise ValueError("Share expiration must be in the future.")
        clean=[]
        for item in items or []:
            typ,rid=(item if isinstance(item,(tuple,list)) else (item.get("resource_type"),item.get("resource_id")))
            if typ and rid: _pg_share_resource(c,actor,p,typ,rid); clean.append((str(typ).lower(),str(rid)))
        if not clean: raise ValueError("No shareable resources were selected.")
        out=[]
        for typ,rid in clean:
            token=secrets.token_urlsafe(32); token_hash=hashlib.sha256(token.encode()).hexdigest()
            row=c.execute("""INSERT INTO record_shares(organization_id,patient_id,resource_type,resource_id,shared_by,shared_with,token_hash,expires_at)
                             VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING share_id,expires_at,created_at""",(actor.organization_id,p,typ,rid,actor.user_id,shared_with.strip(),token_hash,expiry)).fetchone()
            _pg_audit(c,actor,"SHARE_CREATED","sharing","record_share",row["share_id"],p,reason_context=f"{typ}:{rid}")
            out.append({"share_id":str(row["share_id"]),"token":token,"expires_at":row["expires_at"],"resource_type":typ,"resource_id":rid})
        return out


def _core15_list_record_shares(self, actor, patient_id):
    with self._connect() as c:
        p=_pg_patient_uuid(c,actor,patient_id)
        role=_pg_role(actor)
        if role not in {"owner","admin"} and not c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s",(actor.organization_id,actor.user_id,p)).fetchone():
            raise PermissionError("You are not authorized to view sharing information.")
        rows=c.execute("""SELECT share_id,organization_id,patient_id,resource_type,resource_id,shared_by,shared_with,expires_at,revoked_at,created_at
                          FROM record_shares WHERE organization_id=%s AND patient_id=%s ORDER BY created_at DESC""",(actor.organization_id,p)).fetchall()
        return [dict(r) for r in rows]


def _core15_revoke_record_share(self, actor, share_id):
    with self._connect() as c:
        row=c.execute("SELECT * FROM record_shares WHERE organization_id=%s AND share_id=%s",(actor.organization_id,str(share_id))).fetchone()
        if not row: raise ValueError("Share not found.")
        if row["shared_by"] != actor.user_id and _pg_role(actor) != "owner": raise PermissionError("Only the creator or Owner can revoke this share.")
        c.execute("UPDATE record_shares SET revoked_at=COALESCE(revoked_at,now()) WHERE organization_id=%s AND share_id=%s",(actor.organization_id,row["share_id"]))
        _pg_audit(c,actor,"SHARE_REVOKED","sharing","record_share",row["share_id"],row["patient_id"]); return True


def _core15_lifecycle_medication(self, actor, record_id, action, password=None):
    role=_pg_role(actor)
    if action in {"admin_delete","permanent_destroy"}:
        _pg_require_role(actor,{"admin","owner"},"You are not authorized to perform this destructive action.")
        if not password or not self._verify_actor_password(actor,password): raise PermissionError("Current password is incorrect.")
    elif action == "owner_recover": _pg_require_role(actor,{"owner"},"Only Owner can recover Admin-deleted records.")
    elif action == "recover": _pg_require_role(actor,{"owner","admin"},"You are not authorized to recover archived records.")
    elif action == "archive": _pg_require_role(actor,{"owner","admin","doctor","staff"},"You are not authorized to archive records.")
    with self._connect() as c:
        row=_pg_lifecycle_status(c,"medication_records","record_id",actor,record_id)
        if not row: raise ValueError("Medication record not found.")
        status=row["lifecycle_status"]
        transitions={"archive":("ACTIVE","ARCHIVED"),"recover":("ARCHIVED","ACTIVE"),"admin_delete":("ARCHIVED","ADMIN_DELETED"),"owner_recover":("ADMIN_DELETED","ACTIVE"),"permanent_destroy":("ADMIN_DELETED",None)}
        expected,new=transitions[action]
        if status != expected: raise ValueError(f"Invalid lifecycle transition from {status}.")
        if action=="permanent_destroy": c.execute("DELETE FROM medication_records WHERE organization_id=%s AND record_id=%s",(actor.organization_id,row["record_id"]))
        else: c.execute("UPDATE medication_records SET lifecycle_status=%s, archived_at=CASE WHEN %s='ARCHIVED' THEN now() WHEN %s='ACTIVE' THEN NULL ELSE archived_at END, archived_by=CASE WHEN %s='ARCHIVED' THEN %s ELSE NULL END, admin_deleted_at=CASE WHEN %s='ADMIN_DELETED' THEN now() WHEN %s='ACTIVE' THEN NULL ELSE admin_deleted_at END, admin_deleted_by=CASE WHEN %s='ADMIN_DELETED' THEN %s ELSE NULL END WHERE organization_id=%s AND record_id=%s",(new,new,new,new,actor.user_id,new,new,new,actor.user_id,actor.organization_id,row["record_id"]))
        _pg_audit(c,actor,action.upper(),"lifecycle","medication",row["record_id"],row["patient_id"],reason_context="Core15 lifecycle transition")
        return True


def _core15_lifecycle_ehr(self, actor, resource_type, resource_id, action, password=None):
    role=_pg_role(actor)
    if action in {"admin_delete","permanent_destroy"}:
        _pg_require_role(actor,{"admin","owner"},"You are not authorized to perform this destructive action.")
        if not password or not self._verify_actor_password(actor,password): raise PermissionError("Current password is incorrect.")
    elif action == "owner_recover": _pg_require_role(actor,{"owner"},"Only Owner can recover Admin-deleted records.")
    elif action == "recover": _pg_require_role(actor,{"owner","admin"},"You are not authorized to recover archived records.")
    elif action == "archive": _pg_require_role(actor,{"owner","admin","doctor","staff"},"You are not authorized to archive records.")
    cfg={"encounter":("encounters","encounter_id"),"prescription":("prescriptions","prescription_id"),"document":("attachments","attachment_id")}
    typ=str(resource_type).strip().lower()
    if typ not in cfg: raise ValueError("Unsupported clinical record type.")
    table,key=cfg[typ]
    with self._connect() as c:
        row=_pg_lifecycle_status(c,table,key,actor,resource_id)
        if not row: raise ValueError("Clinical record not found.")
        transitions={"archive":("ACTIVE","ARCHIVED"),"recover":("ARCHIVED","ACTIVE"),"admin_delete":("ARCHIVED","ADMIN_DELETED"),"owner_recover":("ADMIN_DELETED","ACTIVE"),"permanent_destroy":("ADMIN_DELETED",None)}
        expected,new=transitions[action]
        if row["lifecycle_status"] != expected: raise ValueError(f"Invalid lifecycle transition from {row['lifecycle_status']}.")
        if action=="permanent_destroy": c.execute(f"DELETE FROM {table} WHERE organization_id=%s AND {key}=%s",(actor.organization_id,row[key]))
        else: c.execute(f"UPDATE {table} SET lifecycle_status=%s WHERE organization_id=%s AND {key}=%s",(new,actor.organization_id,row[key]))
        _pg_audit(c,actor,action.upper(),"lifecycle",typ,row[key],row["patient_id"],reason_context="Core15 lifecycle transition")
        return True


def _core15_verify_actor_password(self, actor, password):
    with self._connect() as c:
        row=c.execute("SELECT password_hash FROM users WHERE organization_id=%s AND user_id=%s AND active=TRUE",(actor.organization_id,actor.user_id)).fetchone()
    return bool(row and verify_password(password, row["password_hash"]))


def _core15_list_attachments(self, actor, patient_id):
    with self._connect() as c:
        p=_pg_patient_uuid(c,actor,patient_id)
        role=_pg_role(actor)
        allowed=role in {"owner","admin","doctor","staff"} or bool(c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s",(actor.organization_id,actor.user_id,p)).fetchone())
        if not allowed: raise PermissionError("You are not authorized to view this patient's documents.")
        rows=c.execute("""SELECT attachment_id,organization_id,patient_id,encounter_id,record_id,original_name,mime_type,uploaded_by,created_at,lifecycle_status
                          FROM attachments WHERE organization_id=%s AND patient_id=%s ORDER BY created_at DESC""",(actor.organization_id,p)).fetchall()
        return [dict(r) for r in rows]


def _validate_attachment_content(source_path):
    import os as _os, zipfile as _zipfile
    path = _os.fspath(source_path)
    ext = _os.path.splitext(path)[1].lower()
    with open(path, "rb") as fh:
        head = fh.read(16)
        fh.seek(0)
        sample = fh.read(4096)
    signatures = {
        ".pdf": head.startswith(b"%PDF-"),
        ".png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": head.startswith(b"\xff\xd8\xff"),
        ".jpeg": head.startswith(b"\xff\xd8\xff"),
        ".webp": head.startswith(b"RIFF") and len(head) >= 12 and head[8:12] == b"WEBP",
        ".doc": head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
        ".docx": False,
        ".txt": b"\x00" not in sample,
    }
    if ext == ".docx":
        try:
            with _zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
                signatures[ext] = "[Content_Types].xml" in names and "word/document.xml" in names
        except _zipfile.BadZipFile:
            signatures[ext] = False
    if not signatures.get(ext, False):
        raise ValueError("Attachment content does not match its declared file type.")


def _core15_add_attachment(self, actor, patient_id, source_path, encounter_id=None, record_id=None):
    import os as _os, mimetypes as _mimetypes
    from backend.storage import LocalObjectStorage, StorageError
    _pg_require_role(actor,{"owner","admin","doctor","staff","patient"},"You are not authorized to add attachments.")
    if not source_path or not _os.path.isfile(source_path): raise ValueError("Attachment file was not found.")
    if _os.path.getsize(source_path) > 20*1024*1024: raise ValueError("Attachment is too large. Maximum size is 20 MB.")
    _validate_attachment_content(source_path)
    with self._connect() as c:
        p=_pg_patient_uuid(c,actor,patient_id); role=_pg_role(actor)
        if role=="patient" and not c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s",(actor.organization_id,actor.user_id,p)).fetchone():
            raise PermissionError("Patients can only add attachments to their linked profile.")
        enc_uuid = _pg_uuid(encounter_id, "encounter_id") if encounter_id else None
        rec_uuid = _pg_uuid(record_id, "record_id") if record_id else None
        if enc_uuid:
            er=c.execute("SELECT patient_id,lifecycle_status FROM encounters WHERE organization_id=%s AND encounter_id=%s",(actor.organization_id,enc_uuid)).fetchone()
            if not er or er["patient_id"]!=p: raise ValueError("The encounter does not belong to this patient.")
            if er["lifecycle_status"]!="ACTIVE": raise ValueError("Attachments cannot be linked to an archived or deleted encounter.")
        if rec_uuid:
            rr=c.execute("SELECT patient_id,lifecycle_status FROM medication_records WHERE organization_id=%s AND record_id=%s",(actor.organization_id,rec_uuid)).fetchone()
            if not rr or rr["patient_id"]!=p: raise ValueError("The record does not belong to this patient.")
            if rr["lifecycle_status"]!="ACTIVE": raise ValueError("Attachments cannot be linked to an archived or deleted medication record.")
        try:
            storage=LocalObjectStorage()
            object_key, original_name=storage.put_file(source_path, actor.organization_id, p, _os.path.basename(source_path))
        except StorageError as exc:
            raise ValueError(str(exc)) from exc
        mime=_mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        try:
            row=c.execute("""INSERT INTO attachments(organization_id,patient_id,encounter_id,record_id,original_name,object_key,mime_type,uploaded_by)
                             VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING attachment_id""",(actor.organization_id,p,enc_uuid,rec_uuid,original_name,object_key,mime,actor.user_id)).fetchone()
            _pg_audit(c,actor,"ATTACHMENT_UPLOADED","document","attachment",row["attachment_id"],p)
            return str(row["attachment_id"])
        except Exception:
            storage.delete(object_key)
            raise


def _core20_redeem_share(self, token):
    token = str(token or "").strip()
    if not token:
        raise ValueError("Share token is required.")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with self._connect() as c:
        row = c.execute(
            "SELECT * FROM record_shares WHERE token_hash=%s", (token_hash,)
        ).fetchone()
        if not row or row["revoked_at"] is not None:
            raise ValueError("This share link is invalid or no longer available.")
        if row["expires_at"] is not None and row["expires_at"] <= _pg_now():
            raise ValueError("This share link has expired.")
        typ = str(row["resource_type"]).strip().lower()
        key_map = {"medication": ("medication_records", "record_id"), "encounter": ("encounters", "encounter_id"),
                   "prescription": ("prescriptions", "prescription_id"), "document": ("attachments", "attachment_id")}
        if typ not in key_map:
            raise ValueError("This share contains an unsupported resource.")
        table, key = key_map[typ]
        resource = c.execute(
            f"SELECT * FROM {table} WHERE organization_id=%s AND {key}=%s AND patient_id=%s",
            (row["organization_id"], row["resource_id"], row["patient_id"]),
        ).fetchone()
        if not resource or resource.get("lifecycle_status", "ACTIVE") != "ACTIVE":
            raise ValueError("The shared record is no longer available.")
        result = {"share_id": str(row["share_id"]), "resource_type": typ, "shared_with": row["shared_with"],
                  "expires_at": row["expires_at"], "resource": {}}
        allowed = {"medication": {"record_id","public_medication_id","patient_id","medication_id","medicine_id","response_type","reaction","severity","reason","notes","record_date","created_at"},
                   "encounter": {"encounter_id","patient_id","visit_date","visit_type","chief_complaint","visit_notes","diagnoses","created_at"},
                   "prescription": {"prescription_id","patient_id","encounter_id","medicine_name","dosage","frequency","duration","instructions","prescribed_by","created_at"},
                   "document": {"attachment_id","patient_id","encounter_id","record_id","original_name","mime_type","uploaded_by","created_at"}}[typ]
        result["resource"] = {k: resource[k] for k in allowed if k in resource}
        c.execute("""INSERT INTO audit_events(organization_id,actor_id,actor_role,action,category,resource_type,resource_id,patient_id,result,reason_context,source)
                     VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'api')""",
                  (row["organization_id"], None, "external_share_recipient", "SHARE_REDEEMED", "sharing", "record_share", row["share_id"], row["patient_id"], "SUCCESS", "Bearer share redeemed"))
        return result


def _core19_get_attachment_path(self, actor, attachment_id):
    from backend.storage import LocalObjectStorage, StorageError
    with self._connect() as c:
        aid=_pg_uuid(attachment_id,"attachment_id")
        row=c.execute("SELECT attachment_id,patient_id,original_name,mime_type,object_key,lifecycle_status FROM attachments WHERE organization_id=%s AND attachment_id=%s",(actor.organization_id,aid)).fetchone()
        if not row: raise ValueError("Attachment not found.")
        if row["lifecycle_status"]!="ACTIVE": raise ValueError("Attachment is not available.")
        role=_pg_role(actor)
        if role=="patient" and not c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s",(actor.organization_id,actor.user_id,row["patient_id"])).fetchone():
            raise PermissionError("You are not authorized to access this attachment.")
        path=LocalObjectStorage()._safe_path(row["object_key"])
        if not path.is_file(): raise ValueError("Attachment content is unavailable.")
        _pg_audit(c,actor,"ATTACHMENT_VIEWED","document","attachment",row["attachment_id"],row["patient_id"])
        return {"path":str(path),"filename":row["original_name"],"mime_type":row["mime_type"] or "application/octet-stream"}


# Bind Core15 methods to the repository class. Keeping the implementation in
# this module makes the extraction easy to replace with separate domain files.
PostgreSQLRepository._verify_actor_password = _core15_verify_actor_password
PostgreSQLRepository.request_patient_link = _core15_request_patient_link
PostgreSQLRepository.review_patient_link_request = _core15_review_patient_link_request
PostgreSQLRepository.list_patient_link_requests = _core15_list_patient_link_requests
PostgreSQLRepository.create_family_relationship = _core15_create_family_relationship
PostgreSQLRepository.list_family_relationships = _core15_list_family_relationships
PostgreSQLRepository.grant_family_access = _core15_grant_family_access
PostgreSQLRepository.revoke_family_access = _core15_revoke_family_access
PostgreSQLRepository.list_family_access = _core15_list_family_access
PostgreSQLRepository.create_record_shares_batch = _core15_create_record_shares_batch
PostgreSQLRepository.list_record_shares = _core15_list_record_shares
PostgreSQLRepository.revoke_record_share = _core15_revoke_record_share
PostgreSQLRepository.lifecycle_medication = _core15_lifecycle_medication
PostgreSQLRepository.lifecycle_ehr = _core15_lifecycle_ehr
PostgreSQLRepository.add_attachment = _core15_add_attachment
PostgreSQLRepository.get_attachment_path = _core19_get_attachment_path
PostgreSQLRepository.redeem_share = _core20_redeem_share
PostgreSQLRepository.list_attachments = _core15_list_attachments

# ---------- Core19 clinical modules / corrections ----------
def _core19_create_encounter(self, actor, patient_id, visit_date, visit_type=None, chief_complaint=None, visit_notes=None, diagnoses=None):
    _pg_require_role(actor, {"owner", "admin", "doctor"}, "Only Owner, Admin or Doctor can create clinical encounters.")
    with self._connect() as c:
        p = _pg_patient_uuid(c, actor, patient_id)
        if not str(visit_date or "").strip():
            raise ValueError("Visit date is required.")
        row = c.execute("""INSERT INTO encounters(organization_id,patient_id,visit_date,visit_type,chief_complaint,visit_notes,diagnoses,created_by)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                        (actor.organization_id,p,str(visit_date).strip(),visit_type,chief_complaint,visit_notes,diagnoses,actor.user_id)).fetchone()
        _pg_audit(c, actor, "ENCOUNTER_CREATED", "clinical", "encounter", row["encounter_id"], p)
        return dict(row)


def _core19_list_encounters(self, actor, patient_id, include_archived=False):
    with self._connect() as c:
        p = _pg_patient_uuid(c, actor, patient_id)
        _pg_require_patient_read(c, actor, p)
        sql = "SELECT * FROM encounters WHERE organization_id=%s AND patient_id=%s"
        params = [actor.organization_id, p]
        if not include_archived:
            sql += " AND lifecycle_status='ACTIVE'"
        sql += " ORDER BY visit_date DESC, created_at DESC"
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
        return rows


def _core19_create_prescription(self, actor, patient_id, medicine_name, dosage=None, frequency=None, duration=None, instructions=None, encounter_id=None):
    _pg_require_role(actor, {"owner", "admin", "doctor", "staff"}, "You are not authorized to add prescriptions.")
    with self._connect() as c:
        p = _pg_patient_uuid(c, actor, patient_id)
        if not str(medicine_name or "").strip():
            raise ValueError("Medicine name is required.")
        enc = None
        if encounter_id:
            enc = _pg_uuid(encounter_id, "encounter_id")
            erow = c.execute("SELECT patient_id,organization_id,lifecycle_status FROM encounters WHERE organization_id=%s AND encounter_id=%s", (actor.organization_id, enc)).fetchone()
            if not erow or erow["patient_id"] != p:
                raise ValueError("The encounter does not belong to this organization and patient.")
            if erow["lifecycle_status"] != "ACTIVE":
                raise ValueError("Prescriptions cannot be attached to an archived or deleted encounter.")
        row = c.execute("""INSERT INTO prescriptions(organization_id,patient_id,encounter_id,medicine_name,dosage,frequency,duration,instructions,prescribed_by)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                        (actor.organization_id,p,enc,str(medicine_name).strip(),dosage,frequency,duration,instructions,actor.user_id)).fetchone()
        _pg_audit(c, actor, "PRESCRIPTION_CREATED", "clinical", "prescription", row["prescription_id"], p)
        return dict(row)


def _core19_list_prescriptions(self, actor, patient_id, include_archived=False):
    with self._connect() as c:
        p = _pg_patient_uuid(c, actor, patient_id)
        _pg_require_patient_read(c, actor, p)
        sql = "SELECT * FROM prescriptions WHERE organization_id=%s AND patient_id=%s"
        params = [actor.organization_id, p]
        if not include_archived:
            sql += " AND lifecycle_status='ACTIVE'"
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def _core19_create_correction_request(self, actor, patient_id, resource_type, resource_id, requested_change, reason=None):
    _pg_require_role(actor, {"patient", "user"}, "Only patient accounts can submit correction requests.")
    with self._connect() as c:
        p = _pg_patient_uuid(c, actor, patient_id)
        linked = c.execute("SELECT 1 FROM users WHERE organization_id=%s AND user_id=%s AND patient_id=%s AND active=TRUE", (actor.organization_id, actor.user_id, p)).fetchone()
        if not linked:
            raise PermissionError("You can only request corrections for your own linked Patient profile.")
        rid = _pg_uuid(resource_id, "resource_id")
        table_map = {"encounter": "encounters", "prescription": "prescriptions", "medication": "medication_records", "document": "attachments"}
        table = table_map.get(str(resource_type).strip().lower())
        if not table:
            raise ValueError("Unsupported correction resource type.")
        key = {"encounter":"encounter_id","prescription":"prescription_id","medication":"record_id","document":"attachment_id"}[str(resource_type).strip().lower()]
        row = c.execute(f"SELECT patient_id FROM {table} WHERE organization_id=%s AND {key}=%s", (actor.organization_id, rid)).fetchone()
        if not row or row["patient_id"] != p:
            raise ValueError("The selected record does not belong to this patient.")
        req = c.execute("""INSERT INTO correction_requests(organization_id,patient_id,requested_by,resource_type,resource_id,requested_change,reason)
                           VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                        (actor.organization_id,p,actor.user_id,str(resource_type).strip().lower(),rid,str(requested_change).strip(),reason)).fetchone()
        _pg_audit(c, actor, "CORRECTION_REQUESTED", "correction", "correction_request", req["request_id"], p, reason_context=reason, correlation_id=req["request_id"])
        return dict(req)


def _core19_list_correction_requests(self, actor, patient_id=None, status=None):
    role = _pg_role(actor)
    if role not in {"owner", "admin", "patient"}:
        raise PermissionError("Only Owner, Admin or the linked Patient can view correction requests.")
    with self._connect() as c:
        sql = "SELECT * FROM correction_requests WHERE organization_id=%s"
        params = [actor.organization_id]
        if role == "patient":
            own = c.execute("SELECT patient_id FROM users WHERE organization_id=%s AND user_id=%s AND active=TRUE", (actor.organization_id, actor.user_id)).fetchone()
            if not own or own["patient_id"] is None:
                return []
            own_uuid = own["patient_id"]
            if patient_id and _pg_patient_uuid(c, actor, patient_id) != own_uuid:
                raise PermissionError("Patients can only view correction requests for their own profile.")
            sql += " AND patient_id=%s"; params.append(own_uuid)
        elif patient_id:
            sql += " AND patient_id=%s"; params.append(_pg_patient_uuid(c, actor, patient_id))
        if status:
            sql += " AND status=%s"; params.append(str(status).upper())
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def _core19_review_correction_request(self, actor, request_id, decision, notes=None):
    _pg_require_role(actor, {"owner", "admin"}, "Only Owner or Admin can review correction requests.")
    decision = str(decision or "").strip().upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("Decision must be APPROVED or REJECTED.")
    with self._connect() as c:
        rid = _pg_uuid(request_id, "request_id")
        row = c.execute("SELECT * FROM correction_requests WHERE organization_id=%s AND request_id=%s FOR UPDATE", (actor.organization_id,rid)).fetchone()
        if not row: raise ValueError("Correction request not found.")
        if row["status"] != "PENDING": raise ValueError("This correction request has already been reviewed.")
        # Approval records the requested change as reviewed; it does not silently mutate
        # clinical data. A dedicated, authorized edit must make the actual correction.
        c.execute("UPDATE correction_requests SET status=%s,reviewed_by=%s,reviewed_at=now(),review_notes=%s WHERE request_id=%s", (decision,actor.user_id,notes,rid))
        _pg_audit(c, actor, "CORRECTION_REVIEWED", "correction", "correction_request", rid, row["patient_id"], reason_context=notes)
        return True


PostgreSQLRepository.create_encounter = _core19_create_encounter
PostgreSQLRepository.list_encounters = _core19_list_encounters
PostgreSQLRepository.create_prescription = _core19_create_prescription
PostgreSQLRepository.list_prescriptions = _core19_list_prescriptions
PostgreSQLRepository.create_correction_request = _core19_create_correction_request
PostgreSQLRepository.list_correction_requests = _core19_list_correction_requests
PostgreSQLRepository.review_correction_request = _core19_review_correction_request
