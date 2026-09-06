"""
functions.py
------------
RecordGuard application logic.

Role model
----------
owner
    Full control. Can recover admin-deleted records and permanently
    destroy records/patients.

admin
    Can view, add, edit and archive records.
    Can recover archived records.
    Can perform recoverable deletion.

doctor
    Can view, add, edit and archive records.
    Cannot recover or delete records.

staff
    Can view and add records.
    Cannot edit, archive, recover or delete.

patient
    Can view only their own active records.
    Cannot add, edit, archive, recover or delete.

Record lifecycle
----------------
ACTIVE
    |
    v
ARCHIVED
    |
    v
ADMIN DELETED
    |
    +---- Owner can recover
    |
    v
OWNER PERMANENT DELETE
    |
    +---- Record itself is destroyed
    +---- Audit entry remains
"""

from datetime import datetime
import sqlite3
from pathlib import Path
import os
import shutil
import mimetypes
import zipfile
import tempfile
import secrets
import time
import hashlib
import re
import uuid
from io import BytesIO

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:
    # Keep the application importable if optional dependencies are not installed.
    # Backup/restore will raise a clear dependency error when used.
    AESGCM = None

from database import (
    get_connection,
    hash_password,
    verify_password,
)

from models import (
    generate_patient_id,
    patient_row_to_dict,
    get_or_create_medication,
    medication_record_row_to_dict,
)

from validation import (
    validate_patient_registration,
    validate_medication_record,
)


# ======================================================================
# ERROR
# ======================================================================

class RecordGuardError(Exception):
    """Expected user-facing application error."""
    pass


class AuthorizationRecordGuardError(RecordGuardError):
    """Typed authorization failure for the legacy SQLite/domain layer."""
    pass


# Lightweight per-process login throttling.
_LOGIN_FAILURES = {}
_LOGIN_MAX_FAILURES = 5
_LOGIN_LOCK_SECONDS = 30

def _check_login_throttle(username):
    state = _LOGIN_FAILURES.get(username)
    if not state:
        return
    failures, locked_until = state
    if locked_until and time.monotonic() < locked_until:
        remaining = max(1, int(locked_until - time.monotonic() + 0.999))
        raise RecordGuardError(f"Too many failed sign-in attempts. Try again in {remaining} seconds.")
    if locked_until:
        _LOGIN_FAILURES.pop(username, None)

def _record_login_failure(username):
    failures, _ = _LOGIN_FAILURES.get(username, (0, 0))
    failures += 1
    _LOGIN_FAILURES[username] = (failures, time.monotonic() + _LOGIN_LOCK_SECONDS if failures >= _LOGIN_MAX_FAILURES else 0)

def _clear_login_failures(username):
    _LOGIN_FAILURES.pop(username, None)

def _audit_login_failure(username, reason="Invalid credentials"):
    try:
        conn=get_connection(); cur=conn.cursor(); _write_audit(cur,"LOGIN_FAILED",result="FAILURE",reason_context=reason,source="authentication"); conn.commit(); conn.close()
    except Exception:
        pass


# ======================================================================
# HELPERS
# ======================================================================

def _now():
    """Returns the current local timestamp."""
    return datetime.now().isoformat(
        timespec="seconds"
    )


def _require_user(user):
    """Validate that the supplied session still represents an active DB user."""

    if not isinstance(user, dict):
        raise RecordGuardError(
            "You must be logged in to perform this action."
        )

    user_id = user.get("user_id")
    username = str(user.get("username", "")).strip()

    if not user_id or not username:
        raise RecordGuardError("Invalid logged-in user.")

    try:
        db_user = _get_user_by_id(user_id)
    except Exception as exc:
        raise RecordGuardError(
            "Unable to verify the logged-in account."
        ) from exc

    if db_user is None:
        raise RecordGuardError("The logged-in account is inactive or no longer exists.")

    db_username = str(db_user.get("username", "")).strip()
    db_role = str(db_user.get("role", "")).strip().lower()
    supplied_role = str(user.get("role", "")).strip().lower()
    db_org = str(db_user.get("organization_id") or "DEFAULT").strip()
    supplied_org = str(user.get("organization_id") or "DEFAULT").strip()

    if db_username != username or db_role != supplied_role or db_org != supplied_org:
        raise RecordGuardError("The logged-in account could not be verified.")

    return db_user


def _get_user_by_id(user_id):

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
              AND active = 1
            """,
            (user_id,)
        )

        row = cursor.fetchone()

    finally:

        conn.close()

    return dict(row) if row else None


def _audit_classify(action, resource_type=None):
    text = str(action or '').upper()
    action_map = [
        ('LOGIN_SUCCESS', 'AUTHENTICATION'), ('LOGIN_FAILED', 'AUTHENTICATION'),
        ('USER_CREATED', 'USER_MANAGEMENT'), ('USER_PASSWORD_RESET', 'USER_MANAGEMENT'), ('PATIENT_REGISTERED', 'PATIENT'),
        ('PATIENT_LINKED', 'PATIENT'), ('PATIENT_UNLINKED', 'PATIENT'),
        ('LINK_REQUESTED', 'PATIENT'), ('LINK_VERIFIED', 'PATIENT'),
        ('RECORD_CREATED', 'CLINICAL_RECORD'), ('RECORD_VIEWED', 'CLINICAL_RECORD'),
        ('RECORD_UPDATED', 'CLINICAL_RECORD'), ('RECORD_ARCHIVED', 'CLINICAL_RECORD'),
        ('RECORD_RECOVERED', 'CLINICAL_RECORD'), ('RECORD_ADMIN_DELETED', 'CLINICAL_RECORD'),
        ('RECORD_PERMANENTLY_DESTROYED', 'CLINICAL_RECORD'),
        ('MEDICATION_CREATED', 'MEDICATION'), ('MEDICATION_UPDATED', 'MEDICATION'),
        ('SHARE_CREATED', 'SHARING'), ('SHARE_REVOKED', 'SHARING'),
        ('FAMILY_CREATED', 'FAMILY'), ('FAMILY_MEMBER_ADDED', 'FAMILY'),
        ('FAMILY_MEMBER_REMOVED', 'FAMILY'), ('FAMILY_RELATIONSHIP_CHANGED', 'FAMILY'),
        ('FAMILY_ACCESS_REQUESTED', 'FAMILY'), ('FAMILY_ACCESS_GRANTED', 'FAMILY'),
        ('FAMILY_ACCESS_REVOKED', 'FAMILY'),
        ('BACKUP_CREATED', 'BACKUP'), ('BACKUP_RESTORED', 'BACKUP'),
    ]
    for key, category in action_map:
        if key in text:
            return key, category
    if 'CREAT' in text and resource_type == 'medication': return 'MEDICATION_CREATED', 'MEDICATION'
    if 'ADDED MEDICATION' in text: return 'MEDICATION_CREATED', 'MEDICATION'
    if 'ARCHIV' in text: return 'RECORD_ARCHIVED', 'CLINICAL_RECORD'
    if 'RECOVER' in text: return 'RECORD_RECOVERED', 'CLINICAL_RECORD'
    if 'PERMANENT' in text or 'DESTROY' in text: return 'RECORD_PERMANENTLY_DESTROYED', 'CLINICAL_RECORD'
    if 'DELETE' in text: return 'RECORD_ADMIN_DELETED', 'CLINICAL_RECORD'
    if 'VIEW' in text or 'ACCESS' in text: return 'RECORD_VIEWED', 'CLINICAL_RECORD'
    if 'USER' in text or 'ACCOUNT' in text: return 'USER_CREATED', 'USER_MANAGEMENT'
    if 'PATIENT' in text: return 'PATIENT', 'PATIENT'
    if 'BACKUP' in text: return 'BACKUP_CREATED', 'BACKUP'
    return 'SYSTEM_EVENT', 'SYSTEM'

def _write_audit(cursor, action, record_id=None, timestamp=None, user=None, *, patient_id=None, resource_type=None, resource_id=None, result='SUCCESS', reason_context=None, source='application', correlation_id=None):
    """Write one structured, append-only audit event."""
    std_action, category = _audit_classify(action, resource_type)
    actor_id, actor_role, organization_id = 'SYSTEM', 'system', 'DEFAULT'
    if user:
        actor_id = str(user.get('user_id') or 'SYSTEM')
        actor_role = str(user.get('role') or 'system').strip().lower()
        organization_id = str(user.get('organization_id') or 'DEFAULT')
    else:
        m = re.search(r"(?:by|user=)\s*['\"]?([A-Za-z0-9_.@-]+)", str(action or ''), re.I)
        if m:
            row = cursor.execute("SELECT user_id, role, organization_id FROM users WHERE username=?", (m.group(1),)).fetchone()
            if row:
                actor_id, actor_role, organization_id = str(row['user_id']), str(row['role']), str(row['organization_id'] or 'DEFAULT')
    rid = resource_id if resource_id is not None else record_id
    if patient_id is None and rid is not None and resource_type in {'medication','encounter','prescription','document'}:
        tables = {'medication':'medication_records','encounter':'encounters','prescription':'prescriptions','document':'attachments'}
        keys = {'medication':'record_id','encounter':'encounter_id','prescription':'prescription_id','document':'attachment_id'}
        try:
            row = cursor.execute(f"SELECT patient_id FROM {tables[resource_type]} WHERE {keys[resource_type]}=?", (rid,)).fetchone()
            patient_id = row['patient_id'] if row else None
        except Exception:
            pass
    event_id = 'EVT-' + uuid.uuid4().hex[:12].upper()
    cursor.execute("""INSERT INTO audit_log
        (event_id,timestamp,actor_id,actor_role,organization_id,action,category,resource_type,resource_id,record_id,patient_id,result,reason_context,source,correlation_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (event_id, timestamp or _now(), actor_id, actor_role, organization_id, std_action, category, resource_type, str(rid) if rid is not None else None, record_id, patient_id, result, reason_context, source, correlation_id))
    return event_id


def _verify_current_user_password(user, password):

    _require_user(user)

    if not password:

        raise RecordGuardError(
            "Password is required."
        )

    username = user.get("username")

    if not username:

        raise RecordGuardError(
            "Invalid logged-in user."
        )

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT password_hash
            FROM users
            WHERE user_id = ?
              AND username = ?
              AND active = 1
            """,
            (
                user["user_id"],
                username
            )
        )

        row = cursor.fetchone()

    finally:

        conn.close()

    if row is None:

        raise RecordGuardError(
            "The logged-in account could not be verified."
        )

    if not verify_password(
        password,
        row["password_hash"]
    ):

        raise RecordGuardError(
            "Incorrect account password."
        )

    return True


# ======================================================================
# PATIENT FUNCTIONS
# ======================================================================

def register_patient(
    user,
    name,
    age_str,
    sex,
    date_of_birth="",
    permanent_address="",
    current_address="",
    phone_number="",
    blood_group=""
):

    if not can_register_patients(user):
        raise RecordGuardError(
            "You are not authorized to register patients."
        )

    errors = validate_patient_registration(
        name,
        age_str,
        sex,
        date_of_birth,
        permanent_address,
        current_address,
        phone_number,
        blood_group
    )

    if errors:
        raise RecordGuardError(" ".join(errors))

    patient_id = generate_patient_id()
    created_at = _now()
    age = int(str(age_str).strip())

    clean_name = str(name).strip()
    clean_sex = str(sex).strip()
    clean_dob = str(date_of_birth or "").strip()
    clean_permanent_address = str(permanent_address or "").strip()
    clean_current_address = str(current_address or "").strip()
    clean_phone = str(phone_number or "").strip()
    clean_blood_group = str(blood_group or "").strip().upper()

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO patients
                (
                    patient_id, name, age, sex, date_of_birth,
                    permanent_address, current_address, phone_number,
                    blood_group, registered_by, organization_id, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id, clean_name, age, clean_sex, clean_dob,
                clean_permanent_address, clean_current_address,
                clean_phone, clean_blood_group, str(user.get("username") or ""),
                str(user.get("organization_id") or "DEFAULT"), created_at
            )
        )
        _write_audit(cursor, "PATIENT_REGISTERED", user=user, patient_id=patient_id, resource_type="patient", resource_id=patient_id)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RecordGuardError(
            "Could not register patient. Please try again."
        ) from exc
    finally:
        conn.close()

    return {
        "patient_id": patient_id,
        "name": clean_name,
        "age": age,
        "sex": clean_sex,
        "date_of_birth": clean_dob,
        "permanent_address": clean_permanent_address,
        "current_address": clean_current_address,
        "phone_number": clean_phone,
        "blood_group": clean_blood_group,
        "created_at": created_at,
    }


def create_public_user_account(username, password, full_name, email=None):
    """Create a self-service login account only.

    No patient profile is created or linked by public signup. A patient
    profile can be linked later through an authorized workflow.
    """
    username = str(username or "").strip()
    password = str(password or "")
    full_name = str(full_name or "").strip()
    email = str(email or "").strip().lower() or None
    if not username or not full_name:
        raise RecordGuardError("Username and full name are required.")
    if len(password) < 8:
        raise RecordGuardError("Password must be at least 8 characters long.")

    conn = get_connection()
    try:
        cur = conn.cursor()
        if cur.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise RecordGuardError("Username already exists. Please choose another.")
        if email and cur.execute("SELECT 1 FROM users WHERE lower(email)=lower(?)", (email,)).fetchone():
            raise RecordGuardError("Email is already associated with an account.")
        cur.execute(
            """INSERT INTO users
               (username,email,password_hash,role,patient_id,full_name,active,organization_id,created_at)
               VALUES (?,?,?,?,?,?,1,?,?)""",
            (username, email, hash_password(password), "user", None, full_name, "DEFAULT", _now())
        )
        user_id = cur.lastrowid
        _write_audit(cur, "USER_CREATED", user=None, resource_type="user", resource_id=user_id, reason_context="Public self-service account created without patient profile")
        conn.commit()
    except RecordGuardError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise RecordGuardError("Could not create user account.") from exc
    finally:
        conn.close()
    return user_id


def create_public_patient_account(username, password, full_name, *args, **kwargs):
    """Legacy compatibility wrapper: Core8 public signup creates only a User Account."""
    return create_public_user_account(username, password, full_name)

def request_patient_link(user, patient_id, reason=""):
    """Create a verifiable request to link an existing Patient profile to a login account."""
    user = _require_user(user)
    if _role(user) not in {"user"}:
        raise RecordGuardError("Only an unlinked common user account can request patient linking.")
    if user.get("patient_id"):
        raise RecordGuardError("This account is already linked to a Patient profile.")
    pid=str(patient_id or "").strip().upper()
    if not pid:
        raise RecordGuardError("Patient ID is required.")
    conn=get_connection()
    try:
        cur=conn.cursor(); prow=cur.execute("SELECT patient_id, organization_id FROM patients WHERE patient_id=?",(pid,)).fetchone()
        if not prow or str(prow["organization_id"] or "DEFAULT") != str(user.get("organization_id") or "DEFAULT"):
            raise RecordGuardError("Patient record could not be verified.")
        existing=cur.execute("SELECT user_id FROM users WHERE patient_id=? AND active=1",(pid,)).fetchone()
        if existing:
            raise RecordGuardError("That Patient profile is already linked to an account.")
        pending=cur.execute("SELECT request_id FROM patient_link_requests WHERE user_id=? AND patient_id=? AND status='PENDING'",(user["user_id"],pid)).fetchone()
        if pending: return int(pending["request_id"])
        cur.execute("INSERT INTO patient_link_requests(user_id,patient_id,requested_by,status,reason_context,created_at) VALUES(?,?,?,?,?,?)",(user["user_id"],pid,user["user_id"],"PENDING",str(reason or "").strip(),_now()))
        rid=cur.lastrowid; _write_audit(cur,"LINK_REQUESTED",user=user,patient_id=pid,resource_type="patient",resource_id=pid,reason_context=reason,correlation_id=f"COR-LINK-{rid}"); conn.commit(); return rid
    except RecordGuardError: conn.rollback(); raise
    finally: conn.close()

def review_patient_link_request(actor, request_id, decision, notes=""):
    actor=_require_user(actor)
    if _role(actor) not in {"owner","admin"}: raise AuthorizationRecordGuardError("Only Owner or Admin can verify patient linking requests.")
    decision=str(decision or "").strip().upper()
    if decision not in {"APPROVED","REJECTED"}: raise RecordGuardError("Decision must be APPROVED or REJECTED.")
    conn=get_connection()
    try:
        cur=conn.cursor(); row=cur.execute("SELECT * FROM patient_link_requests WHERE request_id=?",(int(request_id),)).fetchone()
        if not row: raise RecordGuardError("Link request not found.")
        if row["status"] != "PENDING": raise RecordGuardError("This link request has already been reviewed.")
        user_row=cur.execute("SELECT user_id,patient_id,organization_id FROM users WHERE user_id=? AND active=1",(row["user_id"],)).fetchone()
        pat_row=cur.execute("SELECT patient_id,organization_id FROM patients WHERE patient_id=?",(row["patient_id"],)).fetchone()
        if not user_row or not pat_row or str(user_row["organization_id"] or "DEFAULT") != str(actor.get("organization_id") or "DEFAULT") or str(pat_row["organization_id"] or "DEFAULT") != str(actor.get("organization_id") or "DEFAULT"):
            raise AuthorizationRecordGuardError("Request is outside your organization scope.")
        now=_now()
        if decision == "APPROVED":
            if user_row["patient_id"]: raise RecordGuardError("User account is already linked to a Patient profile.")
            if cur.execute("SELECT 1 FROM users WHERE patient_id=? AND active=1",(row["patient_id"],)).fetchone(): raise RecordGuardError("Patient profile is already linked to another account.")
            cur.execute("UPDATE users SET patient_id=?, role='patient' WHERE user_id=?",(row["patient_id"],row["user_id"]))
            cur.execute("UPDATE patient_link_requests SET status='APPROVED',reviewed_by=?,reviewed_at=?,review_notes=? WHERE request_id=?",(actor["user_id"],now,str(notes or ""),request_id))
            _write_audit(cur,"LINK_VERIFIED",user=actor,patient_id=row["patient_id"],resource_type="patient",resource_id=row["patient_id"],reason_context=notes,correlation_id=f"COR-LINK-{request_id}")
            _write_audit(cur,"PATIENT_LINKED",user=actor,patient_id=row["patient_id"],resource_type="patient",resource_id=row["patient_id"],reason_context=f"Link request #{request_id}",correlation_id=f"COR-LINK-{request_id}")
        else:
            cur.execute("UPDATE patient_link_requests SET status='REJECTED',reviewed_by=?,reviewed_at=?,review_notes=? WHERE request_id=?",(actor["user_id"],now,str(notes or ""),request_id))
            _write_audit(cur,"LINK_VERIFIED",user=actor,patient_id=row["patient_id"],resource_type="patient",resource_id=row["patient_id"],result="FAILURE",reason_context=f"Rejected: {notes or ''}",correlation_id=f"COR-LINK-{request_id}")
        conn.commit(); return True
    except RecordGuardError: conn.rollback(); raise
    finally: conn.close()

def unlink_patient_account(user, password=None, target_user_id=None):
    actor=_require_user(user)
    role=_role(actor)
    if target_user_id is not None and role not in {"owner","admin"}: raise AuthorizationRecordGuardError("Only Owner or Admin can unlink another account.")
    if target_user_id is None:
        target_user_id=actor["user_id"]
        if not password: raise RecordGuardError("Account password is required to unlink your Patient profile.")
        _verify_current_user_password(actor,password)
    conn=get_connection()
    try:
        cur=conn.cursor(); row=cur.execute("SELECT user_id,patient_id,organization_id FROM users WHERE user_id=? AND active=1",(int(target_user_id),)).fetchone()
        if not row: raise RecordGuardError("User account not found.")
        if str(row["organization_id"] or "DEFAULT") != str(actor.get("organization_id") or "DEFAULT"): raise AuthorizationRecordGuardError("Account is outside your organization scope.")
        pid=row["patient_id"]
        if not pid: return False
        cur.execute("UPDATE users SET patient_id=NULL, role=CASE WHEN role='patient' THEN 'user' ELSE role END WHERE user_id=?",(target_user_id,))
        cur.execute("UPDATE patient_link_requests SET status='CANCELLED',reviewed_by=?,reviewed_at=? WHERE user_id=? AND status='PENDING'",(actor["user_id"],_now(),target_user_id))
        _write_audit(cur,"PATIENT_UNLINKED",user=actor,patient_id=pid,resource_type="patient",resource_id=pid,reason_context=f"Account user_id={target_user_id}")
        conn.commit(); return True
    except RecordGuardError: conn.rollback(); raise
    finally: conn.close()

def list_patient_link_requests(actor, status=None):
    actor=_require_user(actor)
    if _role(actor) not in {"owner","admin"}: raise AuthorizationRecordGuardError("Only Owner or Admin can review linking requests.")
    conn=get_connection()
    try:
        q="SELECT r.*,u.username,p.name FROM patient_link_requests r JOIN users u ON u.user_id=r.user_id JOIN patients p ON p.patient_id=r.patient_id WHERE u.organization_id=?"; params=[str(actor.get("organization_id") or "DEFAULT")]
        if status: q+=" AND r.status=?"; params.append(str(status).upper())
        q+=" ORDER BY r.created_at DESC"
        return [dict(r) for r in conn.execute(q,params).fetchall()]
    finally: conn.close()

FAMILY_RELATIONSHIP_TYPES={"spouse_partner","parent","child","guardian","dependent","sibling","caregiver","other"}
FAMILY_RESOURCE_TYPES={"medication","appointments","documents","ehr"}
FAMILY_PERMISSIONS={"view","restrict"}

def create_family_relationship(user, patient_id, related_patient_id, relationship_type):
    user=_require_user(user); pid=str(patient_id or "").strip().upper(); rid=str(related_patient_id or "").strip().upper(); typ=str(relationship_type or "").strip().lower()
    if typ not in FAMILY_RELATIONSHIP_TYPES: raise RecordGuardError("Invalid family relationship type.")
    if not pid or not rid: raise RecordGuardError("Both Patient IDs are required.")
    if pid==rid: raise RecordGuardError("A Patient cannot be related to itself.")
    if _role(user) not in {"owner","admin"} and str(user.get("patient_id") or "").strip().upper()!=pid: raise AuthorizationRecordGuardError("Only the linked Patient or an Owner/Admin can manage family relationships.")
    conn=get_connection()
    try:
        cur=conn.cursor(); rows=cur.execute("SELECT patient_id,organization_id FROM patients WHERE patient_id IN (?,?)",(pid,rid)).fetchall()
        if len(rows)!=2: raise RecordGuardError("Both Patient profiles must exist.")
        orgs={str(x["organization_id"] or "DEFAULT") for x in rows}
        if len(orgs)!=1 or next(iter(orgs))!=str(user.get("organization_id") or "DEFAULT"): raise AuthorizationRecordGuardError("Family members must belong to the same organization.")
        cur.execute("INSERT INTO family_relationships(patient_id,related_patient_id,relationship_type,created_by,created_at) VALUES(?,?,?,?,?)",(pid,rid,typ,str(user["user_id"]),_now()))
        rel=cur.lastrowid; _write_audit(cur,"FAMILY_MEMBER_ADDED",user=user,patient_id=pid,resource_type="family_relationship",resource_id=rel,reason_context=typ); conn.commit(); return rel
    except sqlite3.IntegrityError as exc:
        conn.rollback(); raise RecordGuardError("That family relationship already exists.") from exc
    except RecordGuardError:
        conn.rollback(); raise
    finally: conn.close()

def list_family_relationships(user, patient_id):
    user=_require_user(user); pid=str(patient_id or "").strip().upper()
    if not can_view_patient(user,pid): raise AuthorizationRecordGuardError("You are not authorized to view this patient's family relationships.")
    conn=get_connection()
    try:
        rows=conn.execute("SELECT fr.*,p.name AS related_name FROM family_relationships fr JOIN patients p ON p.patient_id=fr.related_patient_id WHERE fr.patient_id=? ORDER BY fr.created_at DESC,fr.relationship_id DESC",(pid,)).fetchall(); return [dict(r) for r in rows]
    finally: conn.close()

def change_family_relationship(user, relationship_id, relationship_type):
    user=_require_user(user); typ=str(relationship_type or "").strip().lower()
    if typ not in FAMILY_RELATIONSHIP_TYPES: raise RecordGuardError("Invalid family relationship type.")
    conn=get_connection()
    try:
        cur=conn.cursor(); row=cur.execute("SELECT * FROM family_relationships WHERE relationship_id=?",(int(relationship_id),)).fetchone()
        if not row: raise RecordGuardError("Family relationship not found.")
        if _role(user) not in {"owner","admin"} and str(user.get("patient_id") or "").strip().upper()!=str(row["patient_id"]).upper(): raise AuthorizationRecordGuardError("Only the linked Patient or an Owner/Admin can change this relationship.")
        cur.execute("UPDATE family_relationships SET relationship_type=? WHERE relationship_id=?",(typ,int(relationship_id))); _write_audit(cur,"FAMILY_RELATIONSHIP_CHANGED",user=user,patient_id=row["patient_id"],resource_type="family_relationship",resource_id=relationship_id,reason_context=typ); conn.commit(); return True
    except RecordGuardError: conn.rollback(); raise
    finally: conn.close()

def remove_family_relationship(user, relationship_id):
    user=_require_user(user); conn=get_connection()
    try:
        cur=conn.cursor(); row=cur.execute("SELECT * FROM family_relationships WHERE relationship_id=?",(int(relationship_id),)).fetchone()
        if not row: raise RecordGuardError("Family relationship not found.")
        if _role(user) not in {"owner","admin"} and str(user.get("patient_id") or "").strip().upper()!=str(row["patient_id"]).upper(): raise AuthorizationRecordGuardError("Only the linked Patient or an Owner/Admin can remove this relationship.")
        cur.execute("DELETE FROM family_relationships WHERE relationship_id=?",(int(relationship_id),)); _write_audit(cur,"FAMILY_MEMBER_REMOVED",user=user,patient_id=row["patient_id"],resource_type="family_relationship",resource_id=relationship_id); conn.commit(); return True
    except RecordGuardError: conn.rollback(); raise
    finally: conn.close()

def grant_family_access(user, patient_id, grantee_user_id, resource_type, permission):
    user=_require_user(user); pid=str(patient_id or "").strip().upper(); resource=str(resource_type or "").strip().lower(); perm=str(permission or "").strip().lower()
    own_patient=str(user.get("patient_id") or "").strip().upper()==pid
    if _role(user) not in {"owner","admin"} and not own_patient: raise AuthorizationRecordGuardError("Only the linked Patient or an Owner/Admin can grant family access.")
    if perm not in FAMILY_PERMISSIONS: raise RecordGuardError("Permission must be view or restrict.")
    if resource not in FAMILY_RESOURCE_TYPES: raise RecordGuardError("Unsupported family resource type.")
    conn=get_connection()
    try:
        cur=conn.cursor(); gr=cur.execute("SELECT user_id,organization_id FROM users WHERE user_id=? AND active=1",(int(grantee_user_id),)).fetchone(); pat=cur.execute("SELECT organization_id FROM patients WHERE patient_id=?",(pid,)).fetchone()
        if not gr or not pat or str(gr["organization_id"] or "DEFAULT")!=str(user.get("organization_id") or "DEFAULT") or str(pat["organization_id"] or "DEFAULT")!=str(user.get("organization_id") or "DEFAULT"): raise AuthorizationRecordGuardError("Family access target is outside your organization scope.")
        if int(grantee_user_id)==int(user["user_id"]): raise RecordGuardError("You cannot create a family grant to yourself.")
        cur.execute("INSERT INTO family_access_grants(patient_id,grantee_user_id,resource_type,permission,status,granted_by,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(patient_id,grantee_user_id,resource_type,permission) DO UPDATE SET status='ACTIVE',revoked_at=NULL,granted_by=excluded.granted_by,created_at=excluded.created_at",(pid,int(grantee_user_id),resource,perm,"ACTIVE",user["user_id"],_now()))
        gid=cur.execute("SELECT grant_id FROM family_access_grants WHERE patient_id=? AND grantee_user_id=? AND resource_type=? AND permission=?",(pid,int(grantee_user_id),resource,perm)).fetchone()["grant_id"]
        _write_audit(cur,"FAMILY_ACCESS_GRANTED",user=user,patient_id=pid,resource_type="family_access",resource_id=gid,reason_context=f"{resource}:{perm}"); conn.commit(); return int(gid)
    except RecordGuardError: conn.rollback(); raise
    finally: conn.close()

def revoke_family_access(user, grant_id):
    user=_require_user(user); conn=get_connection()
    try:
        cur=conn.cursor(); row=cur.execute("SELECT * FROM family_access_grants WHERE grant_id=?",(int(grant_id),)).fetchone()
        if not row: raise RecordGuardError("Family access grant not found.")
        own_patient=str(user.get("patient_id") or "").strip().upper()==str(row["patient_id"]).upper()
        if _role(user) not in {"owner","admin"} and not own_patient: raise AuthorizationRecordGuardError("Only the linked Patient or an Owner/Admin can revoke family access.")
        cur.execute("UPDATE family_access_grants SET status='REVOKED',revoked_at=? WHERE grant_id=?",(_now(),int(grant_id))); _write_audit(cur,"FAMILY_ACCESS_REVOKED",user=user,patient_id=row["patient_id"],resource_type="family_access",resource_id=grant_id); conn.commit(); return True
    except RecordGuardError: conn.rollback(); raise
    finally: conn.close()

def list_family_access(user, patient_id):
    user=_require_user(user); pid=str(patient_id or "").strip().upper()
    if not can_view_patient(user,pid): raise AuthorizationRecordGuardError("You are not authorized to view family access settings.")
    conn=get_connection()
    try:
        rows=conn.execute("SELECT g.*,u.username,u.full_name FROM family_access_grants g JOIN users u ON u.user_id=g.grantee_user_id WHERE g.patient_id=? ORDER BY g.created_at DESC,g.grant_id DESC",(pid,)).fetchall(); return [dict(r) for r in rows]
    finally: conn.close()

def has_family_permission(user, patient_id, resource_type, permission="view"):
    user=_require_user(user); pid=str(patient_id or "").strip().upper(); resource=str(resource_type or "").strip().lower(); perm=str(permission or "view").strip().lower()
    if str(user.get("patient_id") or "").strip().upper()==pid: return True
    conn=get_connection()
    try:
        row=conn.execute("SELECT 1 FROM family_access_grants WHERE patient_id=? AND grantee_user_id=? AND resource_type=? AND permission=? AND status='ACTIVE'",(pid,int(user["user_id"]),resource,perm)).fetchone(); return bool(row)
    finally: conn.close()


def can_access_family_resource(user, patient_id, resource_type, permission="view"):
    user=_require_user(user)
    role=_role(user)
    if role in {"owner","admin","doctor","staff"}:
        return can_view_patient(user, patient_id)
    return has_family_permission(user, patient_id, resource_type, permission)


def get_patient_by_id(user, patient_id):
    """Return one patient after verifying the caller is authenticated and authorized."""
    _require_user(user)

    if not patient_id or not str(patient_id).strip():
        raise RecordGuardError("Patient ID is required.")

    clean_id = str(patient_id).strip().upper()

    if not can_view_patient(user, clean_id):
        raise AuthorizationRecordGuardError(
            "You are not authorized to view this patient's information."
        )

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM patients WHERE patient_id = ?",
            (clean_id,)
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    return patient_row_to_dict(row)

def list_all_patients(user):

    if not can_view_all_records(user):
        raise AuthorizationRecordGuardError("You are not authorized to view all patients.")

    conn = get_connection()

    try:

        cursor = conn.cursor()

        org = str(user.get("organization_id") or "DEFAULT").strip()
        cursor.execute(
            """
            SELECT * FROM patients
            WHERE organization_id = ?
            ORDER BY created_at DESC
            """, (org,)
        )

        rows = cursor.fetchall()

    finally:

        conn.close()

    return [
        patient_row_to_dict(row)
        for row in rows
    ]


# ======================================================================
# PATIENT PERMISSIONS
# ======================================================================

def _role(user):
    """Return the normalized role for a validated logged-in user."""
    _require_user(user)
    return str(user.get("role", "")).strip().lower()


def can_register_patients(user):
    return _role(user) in {"owner", "admin", "doctor", "staff"}


def can_view_patient(user, patient_id):

    _require_user(user)

    role = _role(user)

    # Staff, Doctor, Admin and Owner can access patients in their organization.
    if role in {"owner", "admin", "doctor", "staff"}:
        conn = get_connection()
        try:
            row = conn.execute("SELECT organization_id FROM patients WHERE patient_id=?", (patient_id.strip().upper(),)).fetchone()
        finally:
            conn.close()
        if row is None:
            return False
        return str(row["organization_id"] or "DEFAULT") == str(user.get("organization_id") or "DEFAULT")

    # Patient can only see their own records.
    if role == "patient":

        linked_patient = user.get(
            "patient_id"
        )

        if not linked_patient:
            return False

        return (
            linked_patient.strip().upper()
            ==
            patient_id.strip().upper()
        )

    return False


def _ensure_patient_scope(user, patient_id):
    """Fail closed unless the authenticated user can access this patient."""
    _require_user(user)
    clean_id = str(patient_id or "").strip().upper()
    if not clean_id or not can_view_patient(user, clean_id):
        raise AuthorizationRecordGuardError("You are not authorized to access this patient's records.")
    return clean_id


def _ensure_record_scope(user, record_id):
    """Verify medication record ownership/scope before mutation."""
    _require_user(user)
    try: rid = int(record_id)
    except (TypeError, ValueError): raise RecordGuardError("A valid record ID is required.")
    conn=get_connection()
    try: row=conn.execute("SELECT patient_id FROM medication_records WHERE record_id=?",(rid,)).fetchone()
    finally: conn.close()
    if not row: raise RecordGuardError("Medication record not found.")
    _ensure_patient_scope(user, row["patient_id"])
    return row["patient_id"]


# ======================================================================
# MEDICATION HELPERS
# ======================================================================
# ======================================================================
# MEDICATION RECORDS
# ======================================================================

def add_medication_record(
    user,
    patient_id,
    medicine_name,
    response_type,
    reaction="",
    severity="",
    reason="",
    notes="",
    prescription_id=None,
    encounter_id=None
):

    if not can_add_records(user):
        raise RecordGuardError(
            "You are not authorized to add medication records."
        )

    patient = get_patient_by_id(
        user,
        patient_id
    )

    if patient is None:

        raise RecordGuardError(
            f"No patient found with ID '{patient_id}'."
        )

    errors = validate_medication_record(
        medicine_name,
        response_type,
        severity
    )

    if errors:

        raise RecordGuardError(
            " ".join(errors)
        )

    clean_medicine = (
        medicine_name or ""
    ).strip()

    clean_response = (
        response_type or ""
    ).strip()

    clean_reaction = (
        reaction or ""
    ).strip()

    clean_severity = (
        severity or ""
    ).strip()

    clean_reason = (
        reason or ""
    ).strip()

    clean_notes = (
        notes or ""
    ).strip()

    record_date = _now()

    medication_id = get_or_create_medication(
        clean_medicine
    )

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO medication_records
            (
                medication_uid,
                patient_id,
                medication_id,
                response_type,
                reaction,
                severity,
                reason,
                notes,
                record_date,
                is_archived,
                deleted_by_admin,
                prescription_id,
                encounter_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (
                f"MED-{int(record_id):06d}" if False else None,
                patient["patient_id"],
                medication_id,
                clean_response,
                clean_reaction,
                clean_severity,
                clean_reason,
                clean_notes,
                record_date,
                prescription_id,
                encounter_id
            )
        )

        record_id = cursor.lastrowid
        medication_uid = f"MED-{int(record_id):06d}"
        cursor.execute("UPDATE medication_records SET medication_uid=? WHERE record_id=?", (medication_uid, record_id))
        _write_audit(cursor, "MEDICATION_CREATED", record_id, user=user, patient_id=patient["patient_id"], resource_type="medication", resource_id=medication_uid)
        conn.commit()

    except Exception as exc:

        conn.rollback()

        raise RecordGuardError(
            "Could not save medication record."
        ) from exc

    finally:

        conn.close()

    return {
        "record_id": record_id,
        "medication_uid": f"MED-{int(record_id):06d}",
        "patient_id": patient["patient_id"],
        "medicine_name": clean_medicine,
        "response_type": clean_response,
        "reaction": clean_reaction,
        "severity": clean_severity,
        "reason": clean_reason,
        "notes": clean_notes,
        "record_date": record_date,
        "is_archived": 0,
        "deleted_by_admin": 0,
        "prescription_id": prescription_id,
        "encounter_id": encounter_id,
    }


# ======================================================================
# RECORD QUERY
# ======================================================================

def get_medication_records_for_patient(
    patient_id,
    include_archived=False,
    include_admin_deleted=False,
    user=None
):

    _require_user(user)

    if not patient_id or not patient_id.strip():

        raise RecordGuardError(
            "Patient ID is required."
        )

    if _role(user) == "patient":
        include_archived = False
        include_admin_deleted = False

    if user is not None:

        if not can_access_family_resource(user, patient_id, "medication"):


            raise RecordGuardError(
                "You are not authorized to view "
                "this patient's records."
            )

    clean_id = patient_id.strip().upper()

    conn = get_connection()

    try:

        cursor = conn.cursor()

        conditions = [
            "mr.patient_id = ?"
        ]

        params = [
            clean_id
        ]

        if not include_archived:

            conditions.append(
                "mr.is_archived = 0"
            )

        if not include_admin_deleted:

            conditions.append(
                "mr.deleted_by_admin = 0"
            )

        where_clause = " AND ".join(
            conditions
        )

        cursor.execute(
            f"""
            SELECT
                mr.record_id,
                mr.medication_uid,
                mr.patient_id,
                m.medicine_name,
                mr.response_type,
                mr.reaction,
                mr.severity,
                mr.reason,
                mr.notes,
                mr.record_date,
                mr.status,
                mr.is_archived,
                mr.archived_at,
                mr.archived_by,
                mr.deleted_by_admin,
                mr.admin_deleted_at,
                mr.admin_deleted_by,
                mr.prescription_id,
                mr.encounter_id
            FROM medication_records mr
            JOIN medications m
                ON mr.medication_id =
                   m.medication_id
            WHERE {where_clause}
            ORDER BY
                mr.record_date DESC,
                mr.record_id DESC
            """,
            tuple(params)
        )

        rows = cursor.fetchall()

    finally:

        conn.close()

    result = [
        medication_record_row_to_dict(row)
        for row in rows
    ]

    # Record successful reads for patient-facing transparency.
    for item in result:
        try:
            _log_record_access(user, clean_id, item.get("record_id"), "Viewed record")
        except Exception:
            pass

    return result


def set_medication_status(user, record_id, status):
    if not can_edit_records(user):
        raise AuthorizationRecordGuardError("You are not authorized to change medication status.")
    _ensure_record_scope(user, record_id)
    status=str(status or "").strip().upper()
    if status not in {"ACTIVE","COMPLETED","DISCONTINUED"}:
        raise RecordGuardError("Status must be Active, Completed or Discontinued.")
    conn=get_connection()
    try:
        cur=conn.cursor(); row=cur.execute("SELECT patient_id,deleted_by_admin,is_archived FROM medication_records WHERE record_id=?",(int(record_id),)).fetchone()
        if not row: raise RecordGuardError("Medication record not found.")
        if row["deleted_by_admin"] or row["is_archived"]: raise RecordGuardError("Archived or Admin-deleted records cannot change medication status.")
        cur.execute("UPDATE medication_records SET status=? WHERE record_id=?",(status,int(record_id)))
        _write_audit(cur,"MEDICATION_UPDATED",user=user,patient_id=row["patient_id"],resource_type="medication",resource_id=record_id,reason_context=f"Status changed to {status}")
        conn.commit(); return True
    except RecordGuardError: conn.rollback(); raise
    finally: conn.close()


# ======================================================================
# MEDICINE SEARCH
# ======================================================================

def search_medication_history(
    medicine_name,
    include_archived=False,
    include_admin_deleted=False,
    user=None
):

    _require_user(user)

    medicine_name = (
        medicine_name or ""
    ).strip()

    if not medicine_name:

        raise RecordGuardError(
            "Medicine name is required."
        )

    if _role(user) == "patient":
        include_archived = False
        include_admin_deleted = False

    conn = get_connection()

    try:

        cursor = conn.cursor()

        conditions = [
            """
            m.medicine_name = ?
            COLLATE NOCASE
            """
        ]

        params = [
            medicine_name
        ]

        if not include_archived:

            conditions.append(
                "mr.is_archived = 0"
            )

        if not include_admin_deleted:

            conditions.append(
                "mr.deleted_by_admin = 0"
            )

        where_clause = " AND ".join(
            conditions
        )

        cursor.execute(
            f"""
            SELECT
                mr.record_id,
                mr.patient_id,
                m.medicine_name,
                mr.response_type,
                mr.reaction,
                mr.severity,
                mr.reason,
                mr.notes,
                mr.record_date,
                mr.is_archived,
                mr.archived_at,
                mr.archived_by,
                mr.deleted_by_admin,
                mr.admin_deleted_at,
                mr.admin_deleted_by
            FROM medication_records mr
            JOIN medications m
                ON mr.medication_id =
                   m.medication_id
            WHERE {where_clause}
            ORDER BY
                mr.record_date DESC,
                mr.record_id DESC
            """,
            tuple(params)
        )

        rows = cursor.fetchall()

    finally:

        conn.close()

    records = [
        medication_record_row_to_dict(row)
        for row in rows
    ]

    if _role(user) == "patient":

        patient_id = user.get(
            "patient_id"
        )

        if not patient_id:

            return []

        records = [
            record
            for record in records
            if record["patient_id"].upper()
            ==
            patient_id.upper()
        ]

    return records


# ======================================================================
# PATIENT + MEDICINE SEARCH
# ======================================================================

def search_medicine_with_alerts(
    patient_id,
    medicine_name,
    user=None
):

    _require_user(user)

    patient_id = (
        patient_id or ""
    ).strip().upper()

    medicine_name = (
        medicine_name or ""
    ).strip()

    if not patient_id:

        raise RecordGuardError(
            "Patient ID is required."
        )

    if not medicine_name:

        raise RecordGuardError(
            "Medicine name is required."
        )

    if user is not None:

        if not can_view_patient(
            user,
            patient_id
        ):

            raise RecordGuardError(
                "You are not authorized to view "
                "this patient's records."
            )

    patient = get_patient_by_id(
        user,
        patient_id
    )

    if patient is None:

        raise RecordGuardError(
            f"No patient found with ID '{patient_id}'."
        )

    records = search_medication_history(
        medicine_name,
        user=user
    )

    records = [
        record
        for record in records
        if record["patient_id"].upper()
        ==
        patient_id.upper()
    ]

    alerts = []

    allergy_found = False
    adverse_found = False
    ineffective_found = False

    for record in records:

        response = (
            record["response_type"]
            or ""
        ).strip().lower()

        if response == "allergy":

            allergy_found = True

        elif response == "adverse reaction":

            adverse_found = True

        elif response == "ineffective":

            ineffective_found = True

    if allergy_found:

        alerts.append({
            "level": "danger",
            "response_type": "Allergy",
            "message":
                "ALLERGY ALERT — Previous allergy "
                "recorded for this patient and medicine.",
            "historical_note":
                "Historical medication record only. "
                "This is not an independent medical "
                "recommendation."
        })

    if adverse_found:

        alerts.append({
            "level": "warning",
            "response_type": "Adverse reaction",
            "message":
                "ADVERSE REACTION ALERT — Previous "
                "reaction recorded for this patient "
                "and medicine.",
            "historical_note":
                "Historical medication record only. "
                "This is not an independent medical "
                "recommendation."
        })

    if ineffective_found:

        alerts.append({
            "level": "info",
            "response_type": "Ineffective",
            "message":
                "PREVIOUSLY INEFFECTIVE — Previous "
                "record indicates limited/non-effective "
                "response for this patient and medicine.",
            "historical_note":
                "Historical medication record only. "
                "This is not an independent medical "
                "recommendation."
        })

    return {
        "records": records,
        "alerts": alerts
    }


# ======================================================================
# SAFETY ALERTS
# ======================================================================

def get_medication_safety_alerts(
    user,
    patient_id,
    medicine_name
):
    """Return historical medication safety alerts for one patient.

    Safety alerts are patient-scoped and require an authenticated user.
    """
    _require_user(user)

    if not can_view_patient(user, patient_id):
        raise RecordGuardError(
            "You are not authorized to view this patient's records."
        )

    result = search_medicine_with_alerts(
        patient_id=patient_id,
        medicine_name=medicine_name,
        user=user
    )

    # Keep the public helper focused on alerts.  Accept a list as well for
    # compatibility with lightweight unit-test mocks and older callers.
    if isinstance(result, dict):
        return result.get("alerts", [])

    return result or []



# ======================================================================
# PATIENT TRANSPARENCY / SHARING
# ======================================================================

def _log_record_access(user, patient_id, record_id, action):
    db_user = _require_user(user)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO record_access_log
                (patient_id, record_id, username, role, action, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            patient_id.strip().upper(), record_id,
            db_user["username"], str(db_user["role"]).lower(), action, _now()
        ))
        conn.commit()
    finally:
        conn.close()


def get_patient_access_history(user, patient_id):
    _require_user(user)
    clean_id = str(patient_id or "").strip().upper()
    if not can_view_patient(user, clean_id):
        raise AuthorizationRecordGuardError("You are not authorized to view this patient's access history.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT access_id, username, role, action, timestamp, record_id
            FROM record_access_log
            WHERE patient_id = ?
            ORDER BY timestamp DESC, access_id DESC
        """, (clean_id,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _validate_patient_record_link(patient_id, record_id, *, include_deleted=False):
    """Ensure a medication record exists and belongs to the requested patient."""
    try:
        rid = int(record_id)
    except (TypeError, ValueError):
        raise RecordGuardError("A valid record ID is required.")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT record_id, patient_id, is_archived, deleted_by_admin FROM medication_records WHERE record_id = ?",
            (rid,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise RecordGuardError("Medication record not found.")
    if str(row["patient_id"]).strip().upper() != patient_id:
        raise RecordGuardError("The selected record does not belong to this patient.")
    if not include_deleted and row["deleted_by_admin"]:
        raise RecordGuardError("This record is no longer available for sharing or correction.")
    if not include_deleted and row["is_archived"]:
        raise RecordGuardError("Archived records are not available for this action.")
    return dict(row)

def _validate_share_resource(patient_id, resource_type, resource_id):
    typ=str(resource_type or "medication").strip().lower(); rid=int(resource_id)
    tables={"medication":("medication_records","record_id"),"encounter":("encounters","encounter_id"),"prescription":("prescriptions","prescription_id"),"document":("attachments","attachment_id")}
    if typ not in tables: raise RecordGuardError("Unsupported share resource type.")
    table,key=tables[typ]; conn=get_connection()
    # table/key come only from the fixed internal whitelist above, never user input.
    try:
        row=conn.execute(f"SELECT * FROM {table} WHERE {key}=? AND patient_id=?",(rid,patient_id)).fetchone()
    finally: conn.close()
    if not row: raise RecordGuardError("The selected record does not belong to this patient or is unavailable.")
    if "deleted_by_admin" in row.keys() and row["deleted_by_admin"]: raise RecordGuardError("This record is no longer available for sharing.")
    if "is_archived" in row.keys() and row["is_archived"]: raise RecordGuardError("Archived records are not available for new shares.")
    return dict(row)

def create_record_share(user, patient_id, record_id, shared_with, expires_at=None, resource_type="medication"):
    """Compatibility wrapper; all share creation uses the atomic batch implementation."""
    result=create_record_shares_batch(user, patient_id, [(resource_type, record_id)], shared_with, expires_at)
    return result[0]

def create_record_shares_batch(user, patient_id, items, shared_with, expires_at=None):
    """Create multiple resource shares atomically. No partial share set is committed."""
    _require_user(user)
    clean_id=str(patient_id or "").strip().upper()
    if not can_view_patient(user,clean_id):
        raise AuthorizationRecordGuardError("You are not authorized to share this patient's record.")
    shared_with=str(shared_with or "").strip()
    if not shared_with: raise RecordGuardError("Recipient is required.")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at)<=datetime.now(): raise RecordGuardError("Share expiration must be in the future.")
        except ValueError: raise RecordGuardError("Invalid share expiration.")
    normalized=[(str(t or "medication").strip().lower(),int(r)) for t,r in (items or []) if r]
    if not normalized: raise RecordGuardError("No shareable resources were selected.")
    # Prevalidate every resource before opening the write transaction.
    for typ,rid in normalized:
        if typ=="medication": _validate_patient_record_link(clean_id,rid)
        else: _validate_share_resource(clean_id,typ,rid)
    conn=get_connection()
    created=[]
    try:
        cur=conn.cursor()
        for typ,rid in normalized:
            token=secrets.token_urlsafe(32)
            cur.execute("""INSERT INTO record_shares(patient_id,record_id,shared_by,shared_with,expires_at,created_at,share_token,resource_type,resource_id) VALUES(?,?,?,?,?,?,?,?,?)""",(clean_id,rid,user["username"],shared_with,expires_at,_now(),token,typ,rid))
            sid=cur.lastrowid
            _write_audit(cur,f"Created secure {typ} share #{sid} for patient {clean_id}",rid)
            created.append({"share_id":sid,"token":token,"expires_at":expires_at,"resource_type":typ,"resource_id":rid})
        conn.commit()
        return created
    except Exception as exc:
        conn.rollback()
        if isinstance(exc,RecordGuardError): raise
        raise RecordGuardError("Could not create the secure shares. No partial shares were committed.") from exc
    finally:
        conn.close()

def list_record_shares(user, patient_id=None):
    _require_user(user); pid=str(patient_id or "").strip().upper()
    if _role(user)=="patient": pid=user.get("patient_id","").strip().upper()
    if not pid or not can_view_patient(user,pid): raise AuthorizationRecordGuardError("You are not authorized to view sharing information.")
    conn=get_connection()
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM record_shares WHERE patient_id=? ORDER BY created_at DESC,share_id DESC",(pid,)).fetchall()]
        secret_keys = {"token", "share_token", "token_hash"}
        now = datetime.now().astimezone()
        result = []
        for row in rows:
            if row.get("revoked"):
                row["status"] = "REVOKED"
            elif row.get("expires_at"):
                try:
                    expiry = datetime.fromisoformat(str(row["expires_at"]))
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=now.tzinfo)
                    row["status"] = "EXPIRED" if expiry <= now else "ACTIVE"
                except ValueError:
                    row["status"] = "INVALID_EXPIRY"
            else:
                row["status"] = "ACTIVE"
            result.append({k: v for k, v in row.items() if k not in secret_keys})
        return result
    finally: conn.close()

def revoke_record_share(user, share_id):
    _require_user(user); conn=get_connection()
    try:
        cur=conn.cursor(); row=cur.execute("SELECT * FROM record_shares WHERE share_id=?",(int(share_id),)).fetchone()
        if not row: raise RecordGuardError("Share not found.")
        _ensure_patient_scope(user, row["patient_id"])
        if row["shared_by"]!=user["username"] and _role(user)!="owner": raise AuthorizationRecordGuardError("Only the creator or Owner can revoke this share.")
        if row["revoked"]: return True
        cur.execute("UPDATE record_shares SET revoked=1,revoked_at=? WHERE share_id=?",(_now(),int(share_id))); _write_audit(cur,f"Revoked secure share #{share_id}",row["resource_id"] or row["record_id"]); conn.commit(); return True
    finally: conn.close()

def access_shared_record(token):
    token=str(token or "").strip()
    if not token: raise RecordGuardError("Share token is required.")
    conn=get_connection()
    try:
        cur=conn.cursor(); row=cur.execute("SELECT * FROM record_shares WHERE share_token=?",(token,)).fetchone()
        if not row: raise RecordGuardError("This share link is invalid or no longer available.")
        if row["revoked"]: raise RecordGuardError("This share has been revoked.")
        if row["expires_at"] and datetime.fromisoformat(row["expires_at"])<=datetime.now(): raise RecordGuardError("This share has expired.")
        typ=row["resource_type"] or "medication"; rid=row["resource_id"] or row["record_id"]; tables={"medication":("medication_records","record_id"),"encounter":("encounters","encounter_id"),"prescription":("prescriptions","prescription_id"),"document":("attachments","attachment_id")}
        if typ not in tables: raise RecordGuardError("This share contains an unsupported resource.")
        table,key=tables[typ]; record=cur.execute(f"SELECT * FROM {table} WHERE {key}=? AND patient_id=?",(rid,row["patient_id"])).fetchone()
        if not record: raise RecordGuardError("The shared record is no longer available.")
        # Share links are an external disclosure boundary. Return only fields
        # intentionally useful to the recipient; never dump internal DB columns.
        allowed_fields={
            "medication": {"record_id","medicine_id","response_type","reaction","severity","reason","notes","record_date"},
            "encounter": {"encounter_id","visit_date","visit_type","chief_complaint","visit_notes","diagnoses","created_at"},
            "prescription": {"prescription_id","medicine_name","dosage","frequency","duration","instructions","created_at"},
            "document": {"attachment_id","original_name","mime_type","created_at"},
        }
        allowed=allowed_fields.get(typ,set())
        record={k: record[k] for k in record.keys() if k in allowed}
        if "deleted_by_admin" in record.keys() and record["deleted_by_admin"]: raise RecordGuardError("The shared record is no longer available.")
        if "is_archived" in record.keys() and record["is_archived"]: raise RecordGuardError("The shared record is no longer available.")
        cur.execute("UPDATE record_shares SET viewed_at=? WHERE share_id=?",(_now(),row["share_id"])); _write_audit(cur,f"Viewed secure share #{row['share_id']}",rid); conn.commit(); return {"share":dict(row),"record":dict(record)}
    finally: conn.close()

def request_record_correction(user, patient_id, record_id, reason):
    _require_user(user)
    clean_id = str(patient_id or "").strip().upper()
    if _role(user) != "patient" or not can_view_patient(user, clean_id):
        raise AuthorizationRecordGuardError("Only the linked patient can request a correction.")
    _validate_patient_record_link(clean_id, record_id)
    reason = str(reason or "").strip()
    if len(reason) < 5:
        raise RecordGuardError("Please provide a meaningful correction reason.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO correction_requests
                (patient_id, record_id, requested_by, reason, status, created_at)
            VALUES (?, ?, ?, ?, 'Pending', ?)
        """, (clean_id, record_id, user["username"], reason, _now()))
        request_id = cur.lastrowid
        _write_audit(cur, f"Correction requested for record #{record_id} by {user['username']}", record_id)
        conn.commit()
        return request_id
    except Exception as exc:
        conn.rollback()
        raise RecordGuardError("Could not submit correction request.") from exc
    finally:
        conn.close()


def get_correction_requests(user, status=None):
    _require_user(user)
    if _role(user) not in {"owner","admin","doctor"}: raise AuthorizationRecordGuardError("You are not authorized to view correction requests.")
    conn=get_connection()
    try:
        org=str(user.get("organization_id") or "DEFAULT")
        q="SELECT cr.* FROM correction_requests cr JOIN patients p ON p.patient_id=cr.patient_id WHERE p.organization_id=?"; params=[org]
        if status: q += " AND status=?"; params.append(status)
        q += " ORDER BY created_at DESC"
        return [dict(r) for r in conn.execute(q,params).fetchall()]
    finally: conn.close()

def review_correction_request(user, request_id, decision, notes=""):
    _require_user(user)
    if _role(user) not in {"owner","admin","doctor"}: raise AuthorizationRecordGuardError("You are not authorized to review correction requests.")
    decision=str(decision or "").strip().title()
    if decision not in {"Approved","Rejected","Resolved"}: raise RecordGuardError("Decision must be Approved, Rejected or Resolved.")
    conn=get_connection()
    try:
        cur=conn.cursor(); row=cur.execute("SELECT * FROM correction_requests WHERE request_id=?",(int(request_id),)).fetchone()
        if not row: raise RecordGuardError("Correction request not found.")
        _ensure_patient_scope(user, row["patient_id"])
        if row["status"] in {"Rejected","Resolved"}: raise RecordGuardError("This correction request is already closed.")
        cur.execute("UPDATE correction_requests SET status=?,reviewed_by=?,reviewed_at=?,review_notes=? WHERE request_id=?",(decision,user["username"],_now(),str(notes or "").strip(),int(request_id)))
        _write_audit(cur,f"Correction request #{request_id} {decision.lower()} by {user['username']}",row["record_id"]); conn.commit(); return True
    finally: conn.close()


def has_owner_account():
    """Return True when at least one active Owner account exists."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 FROM users WHERE role='owner' AND active=1 LIMIT 1").fetchone()
        return row is not None
    finally:
        conn.close()


def create_initial_owner(username, password, full_name="RecordGuard Owner"):
    """Create the first Owner account during GUI first-run setup."""
    username = str(username or "").strip()
    full_name = str(full_name or "").strip()
    password = str(password or "")
    if not username or not full_name:
        raise RecordGuardError("Username and full name are required.")
    if len(password) < 8:
        raise RecordGuardError("Owner password must be at least 8 characters long.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        if cur.execute("SELECT 1 FROM users WHERE role='owner' LIMIT 1").fetchone():
            raise RecordGuardError("An Owner account already exists. Please sign in.")
        if cur.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise RecordGuardError("Username already exists. Please choose another.")
        cur.execute("""INSERT INTO users(username,password_hash,role,patient_id,full_name,active,permanent_delete_authorized,organization_id,created_at)
                       VALUES(?,?,?,?,?,1,0,'DEFAULT',?)""",
                    (username, hash_password(password), "owner", None, full_name, _now()))
        _write_audit(cur, f"Initial Owner account '{username}' created")
        conn.commit()
    except RecordGuardError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise RecordGuardError("Could not create the initial Owner account.") from exc
    finally:
        conn.close()
    return authenticate_user(username, password)


# ======================================================================
# AUTHENTICATION
# ======================================================================

def authenticate_user(
    username,
    password
):

    username = (
        username or ""
    ).strip()

    if not username or not password:

        raise RecordGuardError(
            "Username and password are required."
        )

    _check_login_throttle(username)

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT user_id, username, email, role, patient_id, full_name, active,
                   permanent_delete_authorized, organization_id, created_at, password_hash
            FROM users
            WHERE (username = ? OR lower(email) = lower(?))
              AND active = 1
            """,
            (username, username)
        )

        user = cursor.fetchone()

    finally:

        conn.close()

    if user is None:
        _record_login_failure(username)
        _audit_login_failure(username)
        raise RecordGuardError("Invalid username or password.")

    if not verify_password(password, user["password_hash"]):
        _record_login_failure(username)
        _audit_login_failure(username)
        raise RecordGuardError("Invalid username or password.")

    _clear_login_failures(username)
    try:
        conn2=get_connection(); cur2=conn2.cursor(); _write_audit(cur2, "LOGIN_SUCCESS", user={"user_id":user["user_id"],"role":user["role"],"organization_id":user["organization_id"]}, source="authentication"); conn2.commit(); conn2.close()
    except Exception:
        pass
    return {key: user[key] for key in (
        "user_id", "username", "email", "role", "patient_id", "full_name",
        "active", "permanent_delete_authorized", "organization_id", "created_at"
    )}


# ======================================================================
# ROLE PERMISSIONS
# ======================================================================

def can_view_all_records(user):
    return _role(user) in {"owner", "admin", "doctor", "staff"}


def can_add_records(user):
    return _role(user) in {"owner", "admin", "doctor", "staff"}


def can_edit_records(user):
    return _role(user) in {"owner", "admin", "doctor"}


def can_archive_records(user):
    return _role(user) in {"doctor", "admin", "owner"}


def can_recover_archived_records(user):
    return _role(user) in {"admin", "owner"}


def can_admin_delete_records(user):
    return _role(user) in {"admin", "owner"}


def can_recover_admin_deleted_records(user):
    return _role(user) == "owner"


def can_permanently_delete(user):
    return _role(user) == "owner"


def can_delete_patients(user):
    return _role(user) == "owner"


def is_owner(user):
    return _role(user) == "owner"


# ======================================================================
# EDIT MEDICATION RECORD
# ======================================================================

def edit_medication_record(
    user,
    record_id,
    medicine_name,
    response_type,
    reaction="",
    severity="",
    reason="",
    notes=""
):

    if not can_edit_records(user):

        raise RecordGuardError(
            "You are not authorized to edit records."
        )

    _ensure_record_scope(user, record_id)

    errors = validate_medication_record(
        medicine_name,
        response_type,
        severity
    )

    if errors:

        raise RecordGuardError(
            " ".join(errors)
        )

    clean_medicine = (
        medicine_name or ""
    ).strip()

    clean_response = (
        response_type or ""
    ).strip()

    clean_reaction = (
        reaction or ""
    ).strip()

    clean_severity = (
        severity or ""
    ).strip()

    clean_reason = (
        reason or ""
    ).strip()

    clean_notes = (
        notes or ""
    ).strip()

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                record_id,
                patient_id,
                is_archived,
                deleted_by_admin
            FROM medication_records
            WHERE record_id = ?
            """,
            (record_id,)
        )

        record = cursor.fetchone()

        if record is None:

            raise RecordGuardError(
                "Medication record not found."
            )

        if record["deleted_by_admin"]:

            raise RecordGuardError(
                "Admin-deleted records cannot be edited."
            )

        if record["is_archived"]:

            raise RecordGuardError(
                "Archived records must be recovered before editing."
            )

        medication_id = get_or_create_medication(
            clean_medicine
        )

        cursor.execute(
            """
            UPDATE medication_records
            SET
                medication_id = ?,
                response_type = ?,
                reaction = ?,
                severity = ?,
                reason = ?,
                notes = ?
            WHERE record_id = ?
            """,
            (
                medication_id,
                clean_response,
                clean_reaction,
                clean_severity,
                clean_reason,
                clean_notes,
                record_id
            )
        )

        _write_audit(
            cursor,
            f"Edited record by {user['username']}",
            record_id
        )
        conn.commit()

    except RecordGuardError:

        conn.rollback()
        raise

    except Exception as exc:

        conn.rollback()

        raise RecordGuardError(
            "Could not edit the medication record."
        ) from exc

    finally:

        conn.close()


# ======================================================================
# ARCHIVE RECORD
# ======================================================================

def archive_medication_record(
    user,
    record_id
):

    if not can_archive_records(user):

        raise RecordGuardError(
            "You are not authorized to archive records."
        )

    _ensure_record_scope(user, record_id)

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                record_id,
                is_archived,
                deleted_by_admin
            FROM medication_records
            WHERE record_id = ?
            """,
            (record_id,)
        )

        record = cursor.fetchone()

        if record is None:

            raise RecordGuardError(
                "Medication record not found."
            )

        if record["deleted_by_admin"]:

            raise RecordGuardError(
                "Admin-deleted records cannot be archived."
            )

        if record["is_archived"]:

            raise RecordGuardError(
                "Record is already archived."
            )

        archived_at = _now()

        cursor.execute(
            """
            UPDATE medication_records
            SET
                is_archived = 1,
                status = 'ARCHIVED',
                archived_at = ?,
                archived_by = ?
            WHERE record_id = ?
            """,
            (archived_at, user["username"], record_id)
        )
        _write_audit(cursor, f"RECORD_ARCHIVED", record_id, archived_at)
        conn.commit()

    except RecordGuardError:

        conn.rollback()
        raise

    finally:

        conn.close()



# ======================================================================
# RECOVER ARCHIVED RECORD
# ======================================================================

def recover_archived_medication_record(
    user,
    record_id
):

    if not can_recover_archived_records(user):

        raise RecordGuardError(
            "Only Admin or Owner can recover archived records."
        )

    _ensure_record_scope(user, record_id)

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                record_id,
                is_archived,
                deleted_by_admin
            FROM medication_records
            WHERE record_id = ?
            """,
            (record_id,)
        )

        record = cursor.fetchone()

        if record is None:

            raise RecordGuardError(
                "Medication record not found."
            )

        if record["deleted_by_admin"]:

            raise RecordGuardError(
                "This record was deleted by an Admin. "
                "Only the Owner can recover it."
            )

        if not record["is_archived"]:

            raise RecordGuardError(
                "This record is not archived."
            )

        cursor.execute(
            """
            UPDATE medication_records
            SET
                is_archived = 0,
                status = CASE WHEN status = 'ARCHIVED' THEN 'ACTIVE' ELSE status END,
                archived_at = NULL,
                archived_by = NULL
            WHERE record_id = ?
            """,
            (record_id,)
        )
        _write_audit(cursor, f"RECORD_RECOVERED", record_id)
        conn.commit()

    except RecordGuardError:

        conn.rollback()
        raise

    finally:

        conn.close()



# ======================================================================
# ADMIN DELETE
# ======================================================================

def admin_delete_medication_record(
    user,
    record_id,
    password
):

    if not can_admin_delete_records(user):

        raise RecordGuardError(
            "You are not authorized to delete records."
        )

    _ensure_record_scope(user, record_id)

    _verify_current_user_password(
        user,
        password
    )

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                mr.record_id,
                mr.patient_id,
                m.medicine_name,
                mr.response_type,
                mr.is_archived,
                mr.deleted_by_admin
            FROM medication_records mr
            JOIN medications m
                ON mr.medication_id =
                   m.medication_id
            WHERE mr.record_id = ?
            """,
            (record_id,)
        )

        record = cursor.fetchone()

        if record is None:

            raise RecordGuardError(
                "Medication record not found."
            )

        if record["deleted_by_admin"]:

            raise RecordGuardError(
                "This record has already been deleted."
            )

        if not record["is_archived"]:
            raise RecordGuardError(
                "A record must be archived before Admin deletion."
            )

        deleted_at = _now()

        cursor.execute(
            """
            UPDATE medication_records
            SET
                deleted_by_admin = 1,
                status = 'ADMIN_DELETED',
                admin_deleted_at = ?,
                admin_deleted_by = ?,
                is_archived = 0
            WHERE record_id = ?
            """,
            (
                deleted_at,
                user["username"],
                record_id
            )
        )

        action = (
            "ADMIN DELETE | "
            f"user={user['username']} | "
            f"patient={record['patient_id']} | "
            f"medicine={record['medicine_name']} | "
            f"response={record['response_type']} | "
            "recoverable_by=owner"
        )

        cursor.execute(
            """
            INSERT INTO audit_log
                (
                    action,
                    record_id,
                    timestamp
                )
            VALUES (?, ?, ?)
            """,
            (
                action,
                record_id,
                deleted_at
            )
        )

        conn.commit()

    except RecordGuardError:

        conn.rollback()
        raise

    except Exception as exc:

        conn.rollback()

        raise RecordGuardError(
            "Could not delete the medication record."
        ) from exc

    finally:

        conn.close()


# ======================================================================
# OWNER RECOVER ADMIN-DELETED RECORD
# ======================================================================

def recover_admin_deleted_medication_record(
    user,
    record_id
):

    if not can_recover_admin_deleted_records(user):

        raise RecordGuardError(
            "Only the Owner can recover Admin-deleted records."
        )

    _ensure_record_scope(user, record_id)

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                record_id,
                deleted_by_admin,
                admin_deleted_by
            FROM medication_records
            WHERE record_id = ?
            """,
            (record_id,)
        )

        record = cursor.fetchone()

        if record is None:

            raise RecordGuardError(
                "Medication record not found."
            )

        if not record["deleted_by_admin"]:

            raise RecordGuardError(
                "This record is not an Admin-deleted record."
            )

        cursor.execute(
            """
            UPDATE medication_records
            SET
                deleted_by_admin = 0,
                status = 'ACTIVE',
                admin_deleted_at = NULL,
                admin_deleted_by = NULL,
                is_archived = 0,
                archived_at = NULL,
                archived_by = NULL
            WHERE record_id = ?
            """,
            (record_id,)
        )
        _write_audit(
            cursor,
            f"Owner recovered Admin-deleted record (originally deleted by {record['admin_deleted_by']})",
            record_id
        )
        conn.commit()

    except RecordGuardError:

        conn.rollback()
        raise

    finally:

        conn.close()



# ======================================================================
# OWNER PERMANENT DELETE MEDICATION RECORD
# ======================================================================

def permanently_delete_medication_record(
    user,
    record_id,
    password
):

    if not can_permanently_delete(user):

        raise AuthorizationRecordGuardError(
            "Only the Owner can permanently delete records."
        )

    _ensure_record_scope(user, record_id)

    _verify_current_user_password(
        user,
        password
    )

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                mr.record_id,
                mr.patient_id,
                mr.deleted_by_admin,
                m.medicine_name,
                mr.response_type
            FROM medication_records mr
            JOIN medications m
                ON mr.medication_id =
                   m.medication_id
            WHERE mr.record_id = ?
            """,
            (record_id,)
        )

        record = cursor.fetchone()

        if record is None:

            raise RecordGuardError(
                "Medication record not found."
            )

        if not record["deleted_by_admin"]:

            raise RecordGuardError(
                "Permanent destruction requires an Admin-deleted record."
            )

        action = (
            "OWNER PERMANENT DELETE | "
            f"user={user['username']} | "
            f"patient={record['patient_id']} | "
            f"medicine={record['medicine_name']} | "
            f"response={record['response_type']} | "
            "UNRECOVERABLE"
        )

        timestamp = _now()

        cursor.execute(
            """
            INSERT INTO audit_log
                (
                    action,
                    record_id,
                    timestamp
                )
            VALUES (?, ?, ?)
            """,
            (
                action,
                record_id,
                timestamp
            )
        )

        cursor.execute(
            """
            DELETE FROM medication_records
            WHERE record_id = ?
            """,
            (record_id,)
        )

        conn.commit()

    except RecordGuardError:

        conn.rollback()
        raise

    except Exception as exc:

        conn.rollback()

        raise RecordGuardError(
            "Could not permanently delete the record."
        ) from exc

    finally:

        conn.close()


# ======================================================================
# OWNER DELETE PATIENT
# ======================================================================

def permanently_delete_patient(
    user,
    patient_id,
    password
):

    if not can_delete_patients(user):

        raise RecordGuardError(
            "Only the Owner can permanently delete patients."
        )

    _verify_current_user_password(
        user,
        password
    )

    clean_id = (
        patient_id or ""
    ).strip().upper()

    if not clean_id:

        raise RecordGuardError(
            "Patient ID is required."
        )

    _ensure_patient_scope(user, clean_id)

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                patient_id,
                name
            FROM patients
            WHERE patient_id = ?
            """,
            (clean_id,)
        )

        patient = cursor.fetchone()

        if patient is None:

            raise RecordGuardError(
                "Patient not found."
            )

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM medication_records
            WHERE patient_id = ?
            """,
            (clean_id,)
        )

        count_row = cursor.fetchone()

        total_records = count_row["total"]

        action = (
            "OWNER PERMANENT PATIENT DELETE | "
            f"user={user['username']} | "
            f"patient={patient['patient_id']} | "
            f"name={patient['name']} | "
            f"records={total_records} | "
            "UNRECOVERABLE"
        )

        timestamp = _now()

        cursor.execute(
            """
            INSERT INTO audit_log
                (
                    action,
                    record_id,
                    timestamp
                )
            VALUES (?, NULL, ?)
            """,
            (
                action,
                timestamp
            )
        )

        # Remove non-FK-linked security/workflow rows explicitly so deleting a patient
        # cannot leave orphaned access logs, shares, or correction requests.
        cursor.execute("DELETE FROM record_access_log WHERE patient_id = ?", (clean_id,))
        cursor.execute("DELETE FROM record_shares WHERE patient_id = ?", (clean_id,))
        cursor.execute("DELETE FROM correction_requests WHERE patient_id = ?", (clean_id,))

        attachment_rows = cursor.execute("SELECT stored_path FROM attachments WHERE patient_id = ?", (clean_id,)).fetchall()
        cursor.execute("DELETE FROM patients WHERE patient_id = ?", (clean_id,))

        # Database cascades remove linked clinical/personal rows. Remove their files too.
        base=os.path.dirname(os.path.abspath(__file__))
        for row in attachment_rows:
            stored=row["stored_path"]
            if stored:
                full=os.path.abspath(os.path.join(base, stored))
                try:
                    if os.path.commonpath([base, full]) == os.path.abspath(base) and os.path.isfile(full):
                        os.remove(full)
                except (OSError, ValueError):
                    pass
        patient_attachment_dir=os.path.join(base,"attachments",clean_id)
        if os.path.isdir(patient_attachment_dir):
            shutil.rmtree(patient_attachment_dir, ignore_errors=True)

        conn.commit()

    except RecordGuardError:

        conn.rollback()
        raise

    except Exception as exc:

        conn.rollback()

        raise RecordGuardError(
            "Could not permanently delete the patient."
        ) from exc

    finally:

        conn.close()


# ======================================================================
# AUDIT LOG RETRIEVAL
# ======================================================================

def get_audit_log(user, filters=None):
    _require_user(user)
    if _role(user) not in {"owner", "admin"}: raise AuthorizationRecordGuardError("Only Owner or Admin can view the audit log.")
    filters=filters or {}
    conn=get_connection()
    try:
        clauses=[]; params=[]
        mapping={"actor_id":"actor_id","actor_role":"actor_role","action":"action","category":"category","resource_type":"resource_type","result":"result","patient_id":"patient_id"}
        for key,col in mapping.items():
            value=str(filters.get(key) or "").strip()
            if value: clauses.append(f"{col} LIKE ?"); params.append(f"%{value}%")
        if filters.get("date_from"): clauses.append("timestamp >= ?"); params.append(str(filters["date_from"]))
        if filters.get("date_to"): clauses.append("timestamp <= ?"); params.append(str(filters["date_to"]))
        # Every authenticated Owner/Admin audit view is organization-scoped.
        # Owner is not a global superuser in the multi-tenant model.
        clauses.append("organization_id = ?")
        params.append(str(user.get("organization_id") or "DEFAULT"))
        where=(" WHERE "+" AND ".join(clauses)) if clauses else ""
        rows=conn.execute(f"SELECT * FROM audit_log{where} ORDER BY timestamp DESC, log_id DESC",params).fetchall()
        return [dict(r) for r in rows]
    finally: conn.close()


def get_audit_log_for_record(
    user,
    record_id
):

    _require_user(user)
    if _role(user) not in {"owner", "admin"}:
        raise AuthorizationRecordGuardError("Only Owner or Admin can view the audit log.")

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute("SELECT log_id,event_id,timestamp,actor_id,actor_role,organization_id,action,category,resource_type,resource_id,record_id,patient_id,result,reason_context,source,correlation_id FROM audit_log WHERE record_id=? AND organization_id=? ORDER BY timestamp DESC, log_id DESC", (record_id, str(user.get("organization_id") or "DEFAULT")))

        rows = cursor.fetchall()

    finally:

        conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ======================================================================
# OWNER USER MANAGEMENT
# ======================================================================
def create_new_user(
    creator_user,
    new_username,
    new_password,
    role,
    full_name,
    patient_id=None,
    email=None
):
    _require_user(creator_user)

    creator_role = str(creator_user.get("role", "")).strip().lower()
    role = role.lower().strip()

    if creator_role not in ["owner", "admin"]:
        raise RecordGuardError(
            "Only Owners or Admins can create new users."
        )

    if creator_role == "admin" and role in ["owner", "admin"]:
        raise RecordGuardError(
            "Admins cannot create Owner or Admin accounts."
        )

    valid_roles = ["admin", "doctor", "staff", "patient"]
    if role not in valid_roles:
        raise RecordGuardError(
            f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )

    new_username = (new_username or "").strip()
    full_name = (full_name or "").strip()
    email = str(email or "").strip().lower() or None
    new_password = (new_password or "").strip()

    if not new_username or not new_password or not full_name:
        raise RecordGuardError(
            "Username, password, and full name are required."
        )

    if len(new_password) < 8:
        raise RecordGuardError("Password must be at least 8 characters long.")

    # Patient login accounts may be created unlinked; linking is a separate verified workflow.
    if role != "patient" and patient_id:
        raise AuthorizationRecordGuardError("Only patient accounts can be linked to a Patient ID.")

    organization_id = str(creator_user.get("organization_id") or "DEFAULT").strip()
    if role == "patient" and patient_id:
        conn_check=get_connection()
        try:
            prow=conn_check.execute("SELECT organization_id FROM patients WHERE patient_id=?",(patient_id.strip().upper(),)).fetchone()
        finally: conn_check.close()
        if not prow or str(prow["organization_id"] or "DEFAULT") != organization_id:
            raise RecordGuardError("The Patient ID is invalid or belongs to another organization.")
        patient_id = patient_id.strip().upper()

    hashed_pw = hash_password(new_password)
    created_at = _now()

    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT user_id FROM users WHERE username = ?",
            (new_username,)
        )
        if cursor.fetchone():
            raise RecordGuardError(
                "Username already exists. Please choose another."
            )
        if email and cursor.execute("SELECT 1 FROM users WHERE lower(email)=lower(?)", (email,)).fetchone():
            raise RecordGuardError("Email is already associated with an account.")

        cursor.execute("""
            INSERT INTO users (
                username, email, password_hash, role, patient_id,
                full_name, active, organization_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (
            new_username,
            email,
            hashed_pw,
            role,
            patient_id.strip().upper() if patient_id else None,
            full_name,
            organization_id,
            created_at
        ))

        new_user_id = cursor.lastrowid
        _write_audit(
            cursor,
            f"Created new {role} user '{new_username}' (by {creator_user['username']})"
        )
        conn.commit()

    except RecordGuardError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise RecordGuardError(
            "Could not create user account."
        ) from exc
    finally:
        conn.close()

    return new_user_id


def reset_user_password(actor, target_user_id, new_password):
    """Owner/Admin-assisted password recovery; never exposes an existing password."""
    actor=_require_user(actor)
    role=_role(actor)
    if role not in {"owner","admin"}:
        raise AuthorizationRecordGuardError("Only Owner or Admin can reset another account's password.")
    new_password=str(new_password or "")
    if len(new_password)<8:
        raise RecordGuardError("Password must be at least 8 characters long.")
    conn=get_connection()
    try:
        cur=conn.cursor(); target=cur.execute("SELECT user_id,username,role,organization_id,active FROM users WHERE user_id=?",(int(target_user_id),)).fetchone()
        if not target or not target["active"]: raise RecordGuardError("User account not found or inactive.")
        if str(target["organization_id"] or "DEFAULT")!=str(actor.get("organization_id") or "DEFAULT"): raise AuthorizationRecordGuardError("Account is outside your organization scope.")
        target_role=str(target["role"] or "").lower()
        if role=="admin" and target_role in {"owner","admin"}: raise RecordGuardError("Admins cannot reset Owner or Admin passwords.")
        if role=="owner" and target_role=="owner" and int(target["user_id"])==int(actor["user_id"]): raise RecordGuardError("Use your account password-change workflow for your own Owner account.")
        cur.execute("UPDATE users SET password_hash=? WHERE user_id=?",(hash_password(new_password),int(target_user_id)))
        _write_audit(cur,"USER_PASSWORD_RESET",user=actor,resource_type="user",resource_id=target_user_id,reason_context=f"Password reset for {target['username']}")
        conn.commit(); return True
    except RecordGuardError: conn.rollback(); raise
    finally: conn.close()


def list_users(owner_user):
    _require_user(owner_user)
    if _role(owner_user) not in {"owner", "admin"}:
        raise AuthorizationRecordGuardError("Only Owner or Admin can view users.")

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute("SELECT user_id, username, email, full_name, role, patient_id, active, organization_id, created_at FROM users WHERE organization_id=? ORDER BY username", (str(owner_user.get("organization_id") or "DEFAULT"),))
        rows = cursor.fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


# ======================================================================
# FULL EHR: ENCOUNTERS / VISITS / DIAGNOSES / PRESCRIPTIONS
# ======================================================================

def _ehr_clean(value):
    return str(value or "").strip()


def create_encounter(user, patient_id, visit_date, visit_type="", chief_complaint="", visit_notes="", diagnoses=""):
    _require_user(user)
    if _role(user) not in {"owner", "admin", "doctor"}:
        raise AuthorizationRecordGuardError("Only Owner, Admin or Doctor can create clinical encounters.")
    patient_id = str(patient_id or "").strip().upper()
    if not patient_id:
        raise RecordGuardError("Patient ID is required.")
    if not visit_date.strip():
        raise RecordGuardError("Visit date is required.")
    if get_patient_by_id(user, patient_id) is None:
        raise RecordGuardError("Patient not found.")
    conn=get_connection()
    try:
        cur=conn.cursor()
        cur.execute("""INSERT INTO encounters(patient_id,visit_date,visit_type,chief_complaint,visit_notes,diagnoses,created_by,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",(patient_id,visit_date.strip(),_ehr_clean(visit_type),_ehr_clean(chief_complaint),_ehr_clean(visit_notes),_ehr_clean(diagnoses),user["username"],_now()))
        eid=cur.lastrowid
        _write_audit(cur,f"Created encounter {eid} for {patient_id} by {user['username']}")
        conn.commit()
        return eid
    except Exception as exc:
        conn.rollback(); raise RecordGuardError("Could not save the clinical encounter.") from exc
    finally: conn.close()


def list_encounters(user, patient_id):
    _require_user(user); patient_id=str(patient_id or "").strip().upper()
    if not patient_id: raise RecordGuardError("Patient ID is required.")
    if not can_access_family_resource(user,patient_id,"appointments"): raise AuthorizationRecordGuardError("You are not authorized to view this patient's records.")
    conn=get_connection()
    try:
        rows=conn.execute("""SELECT encounter_id,patient_id,visit_date,visit_type,chief_complaint,visit_notes,diagnoses,created_by,created_at,is_archived
                            FROM encounters WHERE patient_id=? AND is_archived=0 ORDER BY visit_date DESC,encounter_id DESC""",(patient_id,)).fetchall()
        result=[dict(r) for r in rows]
        for row in result:
            _log_record_access(user, patient_id, row.get("encounter_id"), "Viewed encounter")
        return result
    finally: conn.close()


def add_prescription(user, patient_id, medicine_name, dosage="", frequency="", duration="", instructions="", encounter_id=None):
    _require_user(user)
    if _role(user) not in {"owner","admin","doctor","staff"}: raise AuthorizationRecordGuardError("You are not authorized to add prescriptions.")
    patient_id=str(patient_id or "").strip().upper()
    if not patient_id: raise RecordGuardError("Patient ID is required.")
    medicine_name=_ehr_clean(medicine_name)
    if not medicine_name: raise RecordGuardError("Medicine name is required.")
    if get_patient_by_id(user,patient_id) is None: raise RecordGuardError("Patient not found.")
    if encounter_id is not None:
        try: encounter_id=int(encounter_id)
        except (TypeError,ValueError): raise RecordGuardError("Invalid encounter ID.")
        check=get_connection()
        try: erow=check.execute("SELECT patient_id FROM encounters WHERE encounter_id=?",(encounter_id,)).fetchone()
        finally: check.close()
        if not erow or str(erow["patient_id"]).upper()!=patient_id: raise RecordGuardError("The encounter does not belong to this patient.")
    conn=get_connection()
    try:
        cur=conn.cursor(); cur.execute("""INSERT INTO prescriptions(encounter_id,patient_id,medicine_name,dosage,frequency,duration,instructions,prescribed_by,created_at)
             VALUES(?,?,?,?,?,?,?,?,?)""",(encounter_id,patient_id,medicine_name,_ehr_clean(dosage),_ehr_clean(frequency),_ehr_clean(duration),_ehr_clean(instructions),user["username"] + (" [PENDING VERIFICATION]" if _role(user)=="staff" else ""),_now()))
        pid=cur.lastrowid; _write_audit(cur,f"Created prescription {pid} for {patient_id} by {user['username']}"); conn.commit(); return pid
    except Exception as exc:
        conn.rollback(); raise RecordGuardError("Could not save the prescription.") from exc
    finally: conn.close()


def list_prescriptions(user, patient_id):
    _require_user(user); patient_id=str(patient_id or "").strip().upper()
    if not patient_id: raise RecordGuardError("Patient ID is required.")
    if not can_access_family_resource(user,patient_id,"medication"): raise AuthorizationRecordGuardError("You are not authorized to view this patient's records.")
    conn=get_connection()
    try:
        rows=conn.execute("""SELECT prescription_id,encounter_id,patient_id,medicine_name,dosage,frequency,duration,instructions,prescribed_by,created_at
                             FROM prescriptions WHERE patient_id=? AND is_archived=0 ORDER BY created_at DESC,prescription_id DESC""",(patient_id,)).fetchall()
        result=[dict(r) for r in rows]
        for row in result:
            _log_record_access(user, patient_id, row.get("prescription_id"), "Viewed prescription")
        return result
    finally: conn.close()


def add_attachment(user, patient_id, source_path, encounter_id=None, record_id=None):
    _require_user(user)
    if _role(user) not in {"owner","admin","doctor","staff","patient"}: raise AuthorizationRecordGuardError("You are not authorized to add attachments.")
    patient_id=str(patient_id or "").strip().upper()
    if not patient_id: raise RecordGuardError("Patient ID is required.")
    if get_patient_by_id(user,patient_id) is None: raise RecordGuardError("Patient not found.")
    if not source_path or not os.path.isfile(source_path): raise RecordGuardError("Attachment file was not found.")
    allowed={".pdf",".png",".jpg",".jpeg",".webp",".doc",".docx",".txt"}
    ext=os.path.splitext(source_path)[1].lower()
    if ext not in allowed: raise RecordGuardError("Unsupported attachment type. Use PDF, image, document or text files.")
    if os.path.getsize(source_path) > 20*1024*1024: raise RecordGuardError("Attachment is too large. Maximum size is 20 MB.")
    if encounter_id is not None:
        try: encounter_id=int(encounter_id)
        except (TypeError,ValueError): raise RecordGuardError("Invalid encounter ID.")
        conn_check=get_connection()
        try: erow=conn_check.execute("SELECT patient_id FROM encounters WHERE encounter_id=?",(encounter_id,)).fetchone()
        finally: conn_check.close()
        if not erow or str(erow["patient_id"]).upper()!=patient_id: raise RecordGuardError("The encounter does not belong to this patient.")
    if record_id is not None:
        try: record_id=int(record_id)
        except (TypeError,ValueError): raise RecordGuardError("Invalid record ID.")
        _validate_patient_record_link(patient_id,record_id)
    root=os.path.join(os.path.dirname(os.path.abspath(__file__)),"attachments",patient_id); os.makedirs(root,exist_ok=True)
    base=os.path.basename(source_path); safe="".join(c if c.isalnum() or c in "._- " else "_" for c in base).strip() or "attachment"
    target=os.path.join(root,f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe}"); shutil.copy2(source_path,target)
    rel=os.path.relpath(target,os.path.dirname(os.path.abspath(__file__)))
    conn=get_connection()
    try:
        cur=conn.cursor(); cur.execute("""INSERT INTO attachments(patient_id,encounter_id,record_id,original_name,stored_path,mime_type,uploaded_by,created_at)
             VALUES(?,?,?,?,?,?,?,?)""",(patient_id,encounter_id,record_id,base,rel,mimetypes.guess_type(base)[0] or "application/octet-stream",user["username"],_now()))
        aid=cur.lastrowid; _write_audit(cur,f"Uploaded attachment {aid} for {patient_id} by {user['username']}",record_id); conn.commit(); return aid
    except Exception as exc:
        conn.rollback();
        try: os.remove(target)
        except OSError: pass
        raise RecordGuardError("Could not save the attachment.") from exc
    finally: conn.close()


def list_attachments(user, patient_id):
    _require_user(user); patient_id=str(patient_id or "").strip().upper()
    if not patient_id: raise RecordGuardError("Patient ID is required.")
    if not can_access_family_resource(user,patient_id,"documents"): raise AuthorizationRecordGuardError("You are not authorized to view this patient's records.")
    conn=get_connection()
    try:
        rows=conn.execute("SELECT * FROM attachments WHERE patient_id=? ORDER BY created_at DESC,attachment_id DESC",(patient_id,)).fetchall()
        result=[dict(r) for r in rows]
        for row in result:
            _log_record_access(user, patient_id, row.get("attachment_id"), "Viewed attachment")
        return result
    finally: conn.close()


def archive_ehr_item(user, resource_type, resource_id):
    _require_user(user)
    if not can_archive_records(user): raise AuthorizationRecordGuardError("You are not authorized to archive records.")
    return _lifecycle_ehr(user, resource_type, resource_id, "archive")

def recover_archived_ehr_item(user, resource_type, resource_id):
    _require_user(user)
    if not can_recover_archived_records(user): raise AuthorizationRecordGuardError("You are not authorized to recover archived records.")
    return _lifecycle_ehr(user, resource_type, resource_id, "recover")

def admin_delete_ehr_item(user, resource_type, resource_id, password):
    _require_user(user)
    if not can_admin_delete_records(user): raise AuthorizationRecordGuardError("You are not authorized to perform recoverable deletion.")
    _verify_current_user_password(user,password)
    return _lifecycle_ehr(user, resource_type, resource_id, "delete")

def recover_admin_deleted_ehr_item(user, resource_type, resource_id):
    _require_user(user)
    if not can_recover_admin_deleted_records(user): raise AuthorizationRecordGuardError("Only Owner can recover Admin-deleted records.")
    return _lifecycle_ehr(user, resource_type, resource_id, "owner_recover")

def permanently_delete_ehr_item(user, resource_type, resource_id, password):
    _require_user(user)
    if not can_permanently_delete(user): raise AuthorizationRecordGuardError("Only Owner can permanently destroy records.")
    _verify_current_user_password(user,password)
    return _lifecycle_ehr(user, resource_type, resource_id, "permanent")

def _lifecycle_ehr(user, resource_type, resource_id, action):
    typ=str(resource_type or "").strip().lower(); rid=int(resource_id)
    cfg={"encounter":("encounters","encounter_id"),"prescription":("prescriptions","prescription_id"),"document":("attachments","attachment_id")}
    if typ not in cfg: raise RecordGuardError("Unsupported clinical record type.")
    table,key=cfg[typ]; conn=get_connection()
    # table/key are selected exclusively from the fixed internal whitelist above.
    try:
        cur=conn.cursor(); row=cur.execute(f"SELECT * FROM {table} WHERE {key}=?",(rid,)).fetchone()
        if not row: raise RecordGuardError("Clinical record not found.")
        _ensure_patient_scope(user, row["patient_id"])
        archived=int(row["is_archived"] or 0); deleted=int(row["deleted_by_admin"] or 0) if "deleted_by_admin" in row.keys() else 0
        if action=="archive":
            if archived or deleted: raise RecordGuardError("Only active records can be archived.")
            cur.execute(f"UPDATE {table} SET is_archived=1 WHERE {key}=?",(rid,))
        elif action=="recover":
            if not archived or deleted: raise RecordGuardError("This record is not an archived record available for recovery.")
            cur.execute(f"UPDATE {table} SET is_archived=0 WHERE {key}=?",(rid,))
        elif action=="delete":
            if deleted: raise RecordGuardError("This record is already Admin-deleted.")
            if not archived: raise RecordGuardError("A record must be archived before Admin deletion.")
            cur.execute(f"UPDATE {table} SET deleted_by_admin=1,is_archived=1 WHERE {key}=?",(rid,))
        elif action=="owner_recover":
            if not deleted: raise RecordGuardError("This record is not Admin-deleted.")
            cur.execute(f"UPDATE {table} SET deleted_by_admin=0,is_archived=0 WHERE {key}=?",(rid,))
        elif action=="permanent":
            if not deleted: raise RecordGuardError("Permanent destruction requires an Admin-deleted record.")
            stored=row["stored_path"] if typ=="document" and "stored_path" in row.keys() else None
            cur.execute(f"DELETE FROM {table} WHERE {key}=?",(rid,))
            if stored:
                base=os.path.abspath(os.path.dirname(__file__))
                full=os.path.abspath(os.path.join(base,stored))
                try:
                    if os.path.commonpath([base,full]) == base and os.path.isfile(full): os.remove(full)
                except (OSError,ValueError): pass
        _write_audit(cur,f"{action.replace('_',' ').title()} {typ} #{rid} by {user['username']}",rid); conn.commit(); return True
    except Exception as exc:
        conn.rollback()
        if isinstance(exc,RecordGuardError): raise
        raise RecordGuardError("Could not update the clinical record lifecycle.") from exc
    finally: conn.close()


# ======================================================================
# MEDICINE INTELLIGENCE (HISTORICAL PATTERNING ONLY)
# ======================================================================

def medicine_intelligence(user, patient_id, medicine_name):
    _require_user(user)
    result=search_medicine_with_alerts(patient_id,medicine_name,user=user)
    records=result["records"]
    counts={k:0 for k in ("Effective","Ineffective","Allergy","Adverse reaction","Unknown")}
    for r in records:
        key=r.get("response_type") or "Unknown"
        if key not in counts: key="Unknown"
        counts[key]+=1
    return {"medicine_name":medicine_name.strip(),"patient_id":patient_id.strip().upper(),"total_records":len(records),"counts":counts,"alerts":result["alerts"],
            "disclaimer":"Historical patient-record pattern only. Not a diagnosis, prescription, dose recommendation, or independent medical safety determination."}


# ======================================================================
# PATIENT PERSONAL MEDICATION LIST
# ======================================================================

def add_personal_medication(user, patient_id, medicine_name, dosage="", frequency="", duration="", route="", instructions="", source_document="", verified_by="User"):
    _require_user(user)
    if _role(user) != "patient" or not can_view_patient(user, patient_id):
        raise AuthorizationRecordGuardError("Only the linked patient can add personal medication entries.")
    patient_id = str(patient_id or "").strip().upper()
    medicine_name = str(medicine_name or "").strip()
    if not medicine_name:
        raise RecordGuardError("Medicine name is required.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO personal_medications(patient_id,medicine_name,dosage,frequency,duration,route,instructions,source_document,verified_by,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""", (patient_id,medicine_name,str(dosage or "").strip(),str(frequency or "").strip(),str(duration or "").strip(),str(route or "").strip(),str(instructions or "").strip(),str(source_document or "").strip(),str(verified_by or "User").strip(),_now()))
        pid = cur.lastrowid
        _write_audit(cur, f"Added personal medication {pid} for {patient_id} by {user['username']}")
        conn.commit()
        return pid
    except Exception as exc:
        conn.rollback()
        if isinstance(exc, RecordGuardError): raise
        raise RecordGuardError("Could not save the personal medication entry.") from exc
    finally:
        conn.close()


def list_personal_medications(user, patient_id):
    _require_user(user)
    patient_id = str(patient_id or "").strip().upper()
    if not can_view_patient(user, patient_id):
        raise AuthorizationRecordGuardError("You are not authorized to view this patient's personal medication list.")
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM personal_medications WHERE patient_id=? ORDER BY created_at DESC, personal_medication_id DESC", (patient_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ======================================================================
# BACKUP / RESTORE
# ======================================================================

BACKUP_MAGIC=b"RGCB2\x00"
BACKUP_KDF_ITERATIONS=600000

def _derive_backup_key(passphrase, salt):
    if not passphrase or len(passphrase) < 8:
        raise RecordGuardError("Backup passphrase must be at least 8 characters long.")
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, BACKUP_KDF_ITERATIONS, dklen=32)

def _encrypt_backup_bytes(payload, passphrase):
    if AESGCM is None:
        raise RecordGuardError("Backup encryption requires the 'cryptography' package. Run: python -m pip install -r requirements.txt")
    salt=secrets.token_bytes(16); nonce=secrets.token_bytes(12)
    key=_derive_backup_key(passphrase,salt)
    ciphertext=AESGCM(key).encrypt(nonce,payload,None)
    return BACKUP_MAGIC+salt+nonce+ciphertext

def _decrypt_backup_bytes(blob, passphrase):
    if not blob.startswith(BACKUP_MAGIC):
        # Backward compatibility for RecordGuard v1 plaintext ZIP backups.
        if zipfile.is_zipfile(BytesIO(blob)):
            return blob, True
        raise RecordGuardError("This is not a valid RecordGuard backup.")
    if len(blob) < len(BACKUP_MAGIC)+28+16:
        raise RecordGuardError("The encrypted backup is incomplete.")
    salt=blob[len(BACKUP_MAGIC):len(BACKUP_MAGIC)+16]
    nonce=blob[len(BACKUP_MAGIC)+16:len(BACKUP_MAGIC)+28]
    ciphertext=blob[len(BACKUP_MAGIC)+28:]
    try:
        if AESGCM is None:
            raise RecordGuardError("Backup encryption requires the 'cryptography' package. Run: python -m pip install -r requirements.txt")
        key=_derive_backup_key(passphrase,salt)
        return AESGCM(key).decrypt(nonce,ciphertext,None), False
    except Exception as exc:
        raise RecordGuardError("The backup passphrase is incorrect or the backup is damaged.") from exc

def backup_database(user, destination_path, backup_passphrase):
    """Create an encrypted portable RecordGuard backup containing DB + patient attachments."""
    _require_user(user)
    if not is_owner(user): raise AuthorizationRecordGuardError("Only the Owner can create database backups.")
    _derive_backup_key(backup_passphrase,b"validation-salt")
    destination_path=os.path.abspath(destination_path)
    if not destination_path.lower().endswith(".rgbackup"): destination_path += ".rgbackup"
    os.makedirs(os.path.dirname(destination_path),exist_ok=True)
    base=os.path.dirname(os.path.abspath(__file__)); db_path=os.path.join(base,"recordguard.db")
    tmp_db=None
    try:
        fd,tmp_db=tempfile.mkstemp(suffix=".db"); os.close(fd)
        src=__import__('sqlite3').connect(db_path); dst=__import__('sqlite3').connect(tmp_db)
        try: src.backup(dst)
        finally: src.close(); dst.close()
        zip_buffer=BytesIO()
        with zipfile.ZipFile(zip_buffer,"w",zipfile.ZIP_DEFLATED) as z:
            z.write(tmp_db,"recordguard.db")
            att_root=os.path.join(base,"attachments")
            if os.path.isdir(att_root):
                for root,_,files in os.walk(att_root):
                    for name in files:
                        full=os.path.join(root,name); z.write(full,os.path.relpath(full,base))
            z.writestr("manifest.txt", "RecordGuard encrypted portable backup\nVersion: 2\nContains: SQLite database and attachments\nEncryption: AES-256-GCM\nKDF: PBKDF2-HMAC-SHA256\n")
        encrypted=_encrypt_backup_bytes(zip_buffer.getvalue(),backup_passphrase)
        with open(destination_path,"wb") as out: out.write(encrypted)
    except Exception as exc:
        try:
            if os.path.exists(destination_path): os.remove(destination_path)
        except OSError: pass
        if isinstance(exc,RecordGuardError): raise
        raise RecordGuardError("Could not create the encrypted RecordGuard backup.") from exc
    finally:
        if tmp_db:
            try: os.remove(tmp_db)
            except OSError: pass
    conn=get_connection()
    try:
        cur=conn.cursor(); _write_audit(cur,f"OWNER BACKUP | user={user['username']} | path={destination_path} | encrypted=v2"); cur.execute("INSERT INTO backup_history(backup_path,created_by,created_at,action) VALUES(?,?,?,?)",(destination_path,user['username'],_now(),"backup")); conn.commit()
    finally: conn.close()
    return destination_path

def restore_database(user, source_path, password, backup_passphrase=None):
    """Restore a RecordGuard backup after Owner re-authentication and integrity checks."""
    _require_user(user)
    if not is_owner(user): raise AuthorizationRecordGuardError("Only the Owner can restore the database.")
    _verify_current_user_password(user,password)
    source_path=os.path.abspath(source_path)
    if not os.path.isfile(source_path): raise RecordGuardError("Backup file was not found.")
    if not source_path.lower().endswith(".rgbackup"): raise RecordGuardError("Please select a RecordGuard .rgbackup file.")
    try:
        with open(source_path,"rb") as fh: blob=fh.read()
        decrypted,legacy=_decrypt_backup_bytes(blob,backup_passphrase)
    except RecordGuardError: raise
    except Exception as exc: raise RecordGuardError("Could not read the RecordGuard backup.") from exc
    if legacy:
        # Legacy v1 backups remain restorable for migration; newly-created backups are encrypted v2.
        pass
    base=os.path.dirname(os.path.abspath(__file__)); db_path=os.path.join(base,"recordguard.db")
    with zipfile.ZipFile(BytesIO(decrypted),"r") as z:
        names=set(z.namelist())
        if "recordguard.db" not in names: raise RecordGuardError("This is not a valid RecordGuard backup.")
        for n in names:
            if n.startswith("/") or ".." in os.path.normpath(n).split(os.sep): raise RecordGuardError("Backup contains an unsafe file path.")
        info_list=z.infolist(); total_uncompressed=sum(i.file_size for i in info_list)
        if total_uncompressed > 250*1024*1024: raise RecordGuardError("Backup is too large to restore safely (250 MB limit).")
        for info in info_list:
            if info.file_size > 50*1024*1024: raise RecordGuardError("A backup member exceeds the 50 MB safety limit.")
        fd,tmp_db=tempfile.mkstemp(suffix=".db"); os.close(fd)
        try:
            with z.open("recordguard.db") as src, open(tmp_db,"wb") as dst: shutil.copyfileobj(src,dst)
            test=__import__('sqlite3').connect(tmp_db)
            try:
                ok=test.execute("PRAGMA integrity_check").fetchone()[0]
                if ok!="ok": raise RecordGuardError("Backup failed integrity verification.")
                required={"users","patients","medication_records","medications","audit_log"}
                tables={r[0] for r in test.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if not required.issubset(tables): raise RecordGuardError("Backup schema is incomplete or incompatible with RecordGuard.")
            finally: test.close()
            pre=db_path+".before_restore.bak"; shutil.copy2(db_path,pre)
            att_root=os.path.join(base,"attachments"); temp_extract=tempfile.mkdtemp(prefix="rg_restore_")
            try:
                with z.open("recordguard.db") as src, open(os.path.join(temp_extract,"recordguard.db"),"wb") as dst: shutil.copyfileobj(src,dst)
                extracted_att=os.path.join(temp_extract,"attachments")
                for name in names:
                    if name in {"recordguard.db","manifest.txt"}: continue
                    if not name.startswith("attachments/") or name.endswith("/"): raise RecordGuardError("Backup contains an unsupported archive member.")
                    rel=name[len("attachments/"):]
                    if not rel or os.path.isabs(rel) or ".." in Path(rel).parts: raise RecordGuardError("Backup contains an unsafe attachment path.")
                    target=os.path.join(extracted_att,*Path(rel).parts); os.makedirs(os.path.dirname(target),exist_ok=True)
                    with z.open(name) as src, open(target,"wb") as dst: shutil.copyfileobj(src,dst)
                shutil.copy2(os.path.join(temp_extract,"recordguard.db"),db_path)
                if os.path.isdir(att_root): shutil.rmtree(att_root)
                if os.path.isdir(extracted_att): shutil.copytree(extracted_att,att_root)
            except Exception as exc:
                shutil.copy2(pre,db_path)
                raise RecordGuardError("Could not restore the RecordGuard backup.") from exc
            finally: shutil.rmtree(temp_extract,ignore_errors=True)
        finally:
            try: os.remove(tmp_db)
            except OSError: pass
    return db_path

def get_backup_history(user):
    _require_user(user)
    if not is_owner(user): raise AuthorizationRecordGuardError("Only the Owner can view backup history.")
    conn=get_connection()
    try: return [dict(r) for r in conn.execute("SELECT * FROM backup_history ORDER BY created_at DESC,backup_id DESC").fetchall()]
    finally: conn.close()

# ======================================================================
# CORE34 — Organization / clinic administration
# ======================================================================
def _org_admin_user(user):
    _require_user(user)
    role = _role(user)
    if role not in {"owner", "admin"}:
        raise AuthorizationRecordGuardError("Only an Owner or Admin can manage organization clinics.")
    return str(user.get("organization_id") or "DEFAULT")


def create_clinic(user, name, code, address=None):
    org = _org_admin_user(user)
    name, code = str(name or "").strip(), str(code or "").strip().upper()
    if not name or not code:
        raise RecordGuardError("Clinic name and code are required.")
    if len(code) > 40 or not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]*", code):
        raise RecordGuardError("Clinic code must use letters, numbers, hyphens or underscores.")
    import uuid
    clinic_id = "CLN-" + uuid.uuid4().hex[:12].upper()
    conn = get_connection()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute("INSERT INTO clinics(clinic_id,organization_id,name,code,address,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                     (clinic_id, org, name, code, str(address or "").strip() or None, str(user.get("user_id")), now))
        _write_audit(conn, "CLINIC_CREATED", user=user, category="organization", resource_type="clinic", resource_id=clinic_id, reason_context=code)
        conn.commit()
        return clinic_id
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise RecordGuardError("A clinic with that code already exists in this organization.") from exc
    finally: conn.close()


def list_clinics(user, include_inactive=False):
    org = _org_admin_user(user)
    conn = get_connection()
    try:
        q="SELECT clinic_id,name,code,address,active,created_at FROM clinics WHERE organization_id=?"
        args=[org]
        if not include_inactive: q += " AND active=1"
        q += " ORDER BY name COLLATE NOCASE"
        return [dict(r) for r in conn.execute(q,args).fetchall()]
    finally: conn.close()


def set_clinic_status(user, clinic_id, active):
    org = _org_admin_user(user)
    conn = get_connection()
    try:
        row=conn.execute("SELECT clinic_id FROM clinics WHERE organization_id=? AND clinic_id=?",(org,str(clinic_id))).fetchone()
        if not row: raise RecordGuardError("Clinic not found in this organization.")
        conn.execute("UPDATE clinics SET active=? WHERE organization_id=? AND clinic_id=?",(1 if active else 0,org,str(clinic_id)))
        _write_audit(conn, "CLINIC_ACTIVATED" if active else "CLINIC_DEACTIVATED", user=user, category="organization", resource_type="clinic", resource_id=str(clinic_id))
        conn.commit(); return True
    finally: conn.close()


def assign_user_to_clinic(user, target_user_id, clinic_id, role_scope="member"):
    org = _org_admin_user(user)
    target = str(target_user_id); clinic = str(clinic_id); scope=str(role_scope or "member").strip().lower()
    if scope not in {"member","lead"}: raise RecordGuardError("Clinic role scope must be member or lead.")
    conn=get_connection()
    try:
        if not conn.execute("SELECT 1 FROM users WHERE organization_id=? AND user_id=? AND active=1",(org,target)).fetchone(): raise RecordGuardError("User not found in this organization.")
        if not conn.execute("SELECT 1 FROM clinics WHERE organization_id=? AND clinic_id=? AND active=1",(org,clinic)).fetchone(): raise RecordGuardError("Clinic not found or inactive in this organization.")
        now=datetime.utcnow().isoformat()
        conn.execute("INSERT OR REPLACE INTO user_clinics(organization_id,user_id,clinic_id,role_scope,created_at) VALUES(?,?,?,?,?)",(org,target,clinic,scope,now))
        _write_audit(conn,"CLINIC_USER_ASSIGNED",user=user,category="organization",resource_type="clinic",resource_id=clinic,reason_context=f"user={target};scope={scope}")
        conn.commit(); return True
    finally: conn.close()


def list_user_clinics(user, target_user_id=None):
    org=_org_admin_user(user); target=str(target_user_id or user.get("user_id"))
    conn=get_connection()
    try:
        if not conn.execute("SELECT 1 FROM users WHERE organization_id=? AND user_id=?",(org,target)).fetchone(): raise RecordGuardError("User not found in this organization.")
        rows=conn.execute("SELECT uc.clinic_id,c.name,c.code,c.active,uc.role_scope,uc.created_at FROM user_clinics uc JOIN clinics c ON c.clinic_id=uc.clinic_id WHERE uc.organization_id=? AND uc.user_id=? ORDER BY c.name",(org,target)).fetchall()
        return [dict(r) for r in rows]
    finally: conn.close()


def assign_patient_to_clinic(user, patient_id, clinic_id, primary=False):
    org=_org_admin_user(user); pid=str(patient_id).strip().upper(); clinic=str(clinic_id)
    conn=get_connection()
    try:
        if not conn.execute("SELECT 1 FROM patients WHERE organization_id=? AND patient_id=?",(org,pid)).fetchone(): raise RecordGuardError("Patient not found in this organization.")
        if not conn.execute("SELECT 1 FROM clinics WHERE organization_id=? AND clinic_id=? AND active=1",(org,clinic)).fetchone(): raise RecordGuardError("Clinic not found or inactive in this organization.")
        if primary: conn.execute("UPDATE patient_clinics SET is_primary=0 WHERE organization_id=? AND patient_id=?",(org,pid))
        conn.execute("INSERT OR REPLACE INTO patient_clinics(organization_id,patient_id,clinic_id,is_primary,created_at) VALUES(?,?,?,?,?)",(org,pid,clinic,1 if primary else 0,datetime.utcnow().isoformat()))
        _write_audit(conn,"CLINIC_PATIENT_ASSIGNED",user=user,category="organization",resource_type="clinic",resource_id=clinic,patient_id=pid,reason_context="primary" if primary else None)
        conn.commit(); return True
    finally: conn.close()


def list_patient_clinics(user, patient_id):
    org=_org_admin_user(user); pid=str(patient_id).strip().upper(); conn=get_connection()
    try:
        if not conn.execute("SELECT 1 FROM patients WHERE organization_id=? AND patient_id=?",(org,pid)).fetchone(): raise RecordGuardError("Patient not found in this organization.")
        return [dict(r) for r in conn.execute("SELECT pc.clinic_id,c.name,c.code,c.active,pc.is_primary,pc.created_at FROM patient_clinics pc JOIN clinics c ON c.clinic_id=pc.clinic_id WHERE pc.organization_id=? AND pc.patient_id=? ORDER BY pc.is_primary DESC,c.name",(org,pid)).fetchall()]
    finally: conn.close()
