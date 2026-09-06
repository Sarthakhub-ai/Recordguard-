
"""
database.py
-----------
RecordGuard database and security system.

Roles:
- owner
- admin
- doctor
- staff
- patient

Record lifecycle:
    ACTIVE
       |
       v
    ARCHIVED
       |
       v
    ADMIN DELETED  ---> recoverable by Owner
       |
       v
    OWNER PERMANENTLY DELETED ---> unrecoverable

Security:
- Only Owner can permanently delete records/patients.
- Admin deletion requires the Admin's own password.
- Owner deletion requires the Owner's own password.
- Permanent deletion leaves an audit entry.

Patient information:
- Name
- Age
- Sex
- Date of Birth
- Permanent Address
- Current Address
- Phone Number
- Blood Group
"""

import sqlite3
import os
import hashlib
import secrets
from datetime import datetime


# ======================================================================
# DATABASE CONFIGURATION
# ======================================================================

DB_FILENAME = "recordguard.db"

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    DB_FILENAME
)


# ======================================================================
# DATABASE CONNECTION
# ======================================================================

def get_connection():
    """
    Opens a SQLite connection.

    Foreign-key enforcement is enabled for every connection.
    sqlite3.Row allows access such as row["username"].
    """

    # A short-lived connection per operation keeps the desktop SQLite
    # architecture simple while a busy timeout prevents transient
    # "database is locked" failures when UI/background work overlaps.
    conn = sqlite3.connect(DB_PATH, timeout=15.0)

    conn.execute("PRAGMA busy_timeout = 15000;")
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.row_factory = sqlite3.Row

    return conn


# ======================================================================
# TRANSACTION HELPER
# ======================================================================

from contextlib import contextmanager


@contextmanager
def transaction():
    """Yield a SQLite connection and atomically commit or roll back.

    Use this helper for new multi-statement database operations. Existing
    callers may continue using get_connection() directly; the helper keeps
    new code from duplicating transaction/cleanup boilerplate.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ======================================================================
# PASSWORD SECURITY
# ======================================================================

def hash_password(password):
    """
    Securely hashes a password using PBKDF2-HMAC-SHA256.
    """

    if not password:
        raise ValueError("Password cannot be empty.")

    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        600000
    ).hex()

    return f"{salt}${password_hash}"


def verify_password(password, stored_hash):
    """Verify PBKDF2-HMAC-SHA256 hashes, including legacy 100k hashes."""
    try:
        salt, original_hash = stored_hash.split("$", 1)
        for iterations in (600000, 100000):
            password_hash = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
            ).hex()
            if secrets.compare_digest(password_hash, original_hash):
                return True
        return False
    except Exception:
        return False


def initialize_database():

    conn = get_connection()

    cursor = conn.cursor()

    try:

        # ==============================================================
        # PATIENTS
        # ==============================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                patient_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                sex TEXT NOT NULL,

                date_of_birth TEXT,
                permanent_address TEXT,
                current_address TEXT,
                phone_number TEXT,
                blood_group TEXT,
                registered_by TEXT,

                created_at TEXT NOT NULL
            );
        """)

        # ==============================================================
        # UPGRADE EXISTING PATIENT TABLE
        # ==============================================================

        cursor.execute("""
            PRAGMA table_info(patients)
        """)

        patient_columns = {
            row["name"]
            for row in cursor.fetchall()
        }

        if "date_of_birth" not in patient_columns:

            cursor.execute("""
                ALTER TABLE patients
                ADD COLUMN date_of_birth TEXT
            """)

        if "permanent_address" not in patient_columns:

            cursor.execute("""
                ALTER TABLE patients
                ADD COLUMN permanent_address TEXT
            """)

        if "current_address" not in patient_columns:

            cursor.execute("""
                ALTER TABLE patients
                ADD COLUMN current_address TEXT
            """)

        if "phone_number" not in patient_columns:

            cursor.execute("""
                ALTER TABLE patients
                ADD COLUMN phone_number TEXT
            """)

        if "blood_group" not in patient_columns:

            cursor.execute("""
                ALTER TABLE patients
                ADD COLUMN blood_group TEXT
            """)

        if "registered_by" not in patient_columns:

            cursor.execute("""
                ALTER TABLE patients
                ADD COLUMN registered_by TEXT
            """)

        # ==============================================================
        # MEDICATIONS
        # ==============================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medications (
                medication_id INTEGER PRIMARY KEY AUTOINCREMENT,
                medicine_name TEXT NOT NULL UNIQUE
            );
        """)

        # ==============================================================
        # MEDICATION RECORDS
        # ==============================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medication_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                medication_uid TEXT,
                patient_id TEXT NOT NULL,
                medication_id INTEGER NOT NULL,
                response_type TEXT NOT NULL,
                reaction TEXT,
                severity TEXT,
                reason TEXT,
                notes TEXT,
                record_date TEXT NOT NULL,

                is_archived INTEGER NOT NULL DEFAULT 0,
                archived_at TEXT,
                archived_by TEXT,

                deleted_by_admin INTEGER NOT NULL DEFAULT 0,
                admin_deleted_at TEXT,
                admin_deleted_by TEXT,
                prescription_id INTEGER,
                encounter_id INTEGER,
                status TEXT NOT NULL DEFAULT 'ACTIVE',

                FOREIGN KEY (patient_id)
                    REFERENCES patients(patient_id)
                    ON DELETE CASCADE,

                FOREIGN KEY (medication_id)
                    REFERENCES medications(medication_id)
                    ON DELETE RESTRICT
            );
        """)

        # ==============================================================
        # UPGRADE EXISTING MEDICATION RECORD TABLE
        # ==============================================================

        cursor.execute("""
            PRAGMA table_info(medication_records)
        """)

        record_columns = {
            row["name"]
            for row in cursor.fetchall()
        }

        for column, definition in [
            ("medication_uid", "TEXT"),
            ("prescription_id", "INTEGER"),
            ("encounter_id", "INTEGER"),
            ("status", "TEXT NOT NULL DEFAULT 'ACTIVE'"),
        ]:
            if column not in record_columns:
                cursor.execute(f"ALTER TABLE medication_records ADD COLUMN {column} {definition}")

        if "is_archived" not in record_columns:

            cursor.execute("""
                ALTER TABLE medication_records
                ADD COLUMN is_archived
                INTEGER NOT NULL DEFAULT 0
            """)

        if "archived_at" not in record_columns:

            cursor.execute("""
                ALTER TABLE medication_records
                ADD COLUMN archived_at TEXT
            """)

        if "archived_by" not in record_columns:

            cursor.execute("""
                ALTER TABLE medication_records
                ADD COLUMN archived_by TEXT
            """)

        if "deleted_by_admin" not in record_columns:

            cursor.execute("""
                ALTER TABLE medication_records
                ADD COLUMN deleted_by_admin
                INTEGER NOT NULL DEFAULT 0
            """)

        if "admin_deleted_at" not in record_columns:

            cursor.execute("""
                ALTER TABLE medication_records
                ADD COLUMN admin_deleted_at TEXT
            """)

        if "admin_deleted_by" not in record_columns:

            cursor.execute("""
                ALTER TABLE medication_records
                ADD COLUMN admin_deleted_by TEXT
            """)

        # ==============================================================
        # AUDIT LOG
        # ==============================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE,
                timestamp TEXT NOT NULL,
                actor_id TEXT NOT NULL DEFAULT 'SYSTEM',
                actor_role TEXT NOT NULL DEFAULT 'system',
                organization_id TEXT NOT NULL DEFAULT 'DEFAULT',
                action TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'SYSTEM',
                resource_type TEXT,
                resource_id TEXT,
                record_id INTEGER,
                patient_id TEXT,
                result TEXT NOT NULL DEFAULT 'SUCCESS',
                reason_context TEXT,
                source TEXT NOT NULL DEFAULT 'application',
                correlation_id TEXT
            );
        """)

        # ==============================================================

        # ==============================================================
        # CORE8 AUDIT MIGRATION
        # ==============================================================
        cursor.execute("PRAGMA table_info(audit_log)")
        audit_columns = {row["name"] for row in cursor.fetchall()}
        legacy_audit_schema = "event_id" not in audit_columns
        for column, definition in [
            ("event_id", "TEXT"), ("actor_id", "TEXT NOT NULL DEFAULT 'SYSTEM'"),
            ("actor_role", "TEXT NOT NULL DEFAULT 'system'"),
            ("organization_id", "TEXT NOT NULL DEFAULT 'DEFAULT'"),
            ("category", "TEXT NOT NULL DEFAULT 'SYSTEM'"),
            ("resource_type", "TEXT"), ("resource_id", "TEXT"),
            ("patient_id", "TEXT"), ("result", "TEXT NOT NULL DEFAULT 'SUCCESS'"),
            ("reason_context", "TEXT"), ("source", "TEXT NOT NULL DEFAULT 'application'"),
            ("correlation_id", "TEXT"),
        ]:
            if column not in audit_columns:
                cursor.execute(f"ALTER TABLE audit_log ADD COLUMN {column} {definition}")
        cursor.execute("UPDATE audit_log SET event_id='EVT-' || printf('%06d', log_id) WHERE event_id IS NULL")
        # Normalize legacy Core7 free-form actions only during the one-time schema migration.
        if legacy_audit_schema:
            cursor.execute("""UPDATE audit_log SET action = CASE
            WHEN upper(action) LIKE '%LOGIN%' AND upper(action) LIKE '%FAIL%' THEN 'LOGIN_FAILED'
            WHEN upper(action) LIKE '%LOGIN%' THEN 'LOGIN_SUCCESS'
            WHEN upper(action) LIKE '%REGISTERED PATIENT%' THEN 'PATIENT_REGISTERED'
            WHEN upper(action) LIKE '%PATIENT%LINK%' THEN 'PATIENT_LINKED'
            WHEN upper(action) LIKE '%ARCHIV%' THEN 'RECORD_ARCHIVED'
            WHEN upper(action) LIKE '%RECOVER%' THEN 'RECORD_RECOVERED'
            WHEN upper(action) LIKE '%PERMANENT%' OR upper(action) LIKE '%UNRECOVERABLE%' THEN 'RECORD_PERMANENTLY_DESTROYED'
            WHEN upper(action) LIKE '%DELETE%' THEN 'RECORD_ADMIN_DELETED'
            WHEN upper(action) LIKE '%MEDICATION%' AND upper(action) LIKE '%ADD%' THEN 'MEDICATION_CREATED'
            WHEN upper(action) LIKE '%SHARE%' AND upper(action) LIKE '%REVOK%' THEN 'SHARE_REVOKED'
            WHEN upper(action) LIKE '%SHARE%' THEN 'SHARE_CREATED'
            WHEN upper(action) LIKE '%USER%' OR upper(action) LIKE '%ACCOUNT%' THEN 'USER_CREATED'
            ELSE 'SYSTEM_EVENT' END,
            category = CASE
            WHEN upper(action) LIKE 'LOGIN_%' THEN 'AUTHENTICATION'
            WHEN upper(action) LIKE 'PATIENT_%' THEN 'PATIENT'
            WHEN upper(action) LIKE 'MEDICATION_%' THEN 'MEDICATION'
            WHEN upper(action) LIKE 'SHARE_%' THEN 'SHARING'
            WHEN upper(action) LIKE 'USER_%' THEN 'USER_MANAGEMENT'
            WHEN upper(action) LIKE 'RECORD_%' THEN 'CLINICAL_RECORD'
            ELSE category END""")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_event_id ON audit_log(event_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_patient ON audit_log(patient_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_log(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_correlation ON audit_log(correlation_id)")
        cursor.execute("""CREATE TRIGGER IF NOT EXISTS audit_log_no_update
            BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'Audit log is append-only'); END;""")
        cursor.execute("""CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
            BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'Audit log is append-only'); END;""")

        # SECURITY / PATIENT TRANSPARENCY TABLES
        # ==============================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS record_access_log (
                access_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                record_id INTEGER,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                action TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS record_shares (
                share_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                record_id INTEGER,
                shared_by TEXT NOT NULL,
                shared_with TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS correction_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                record_id INTEGER NOT NULL,
                requested_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL
            );
        """)

        # FULL EHR / CLINICAL ENCOUNTER TABLES
        # ==============================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS encounters (
                encounter_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                visit_date TEXT NOT NULL,
                visit_type TEXT,
                chief_complaint TEXT,
                visit_notes TEXT,
                diagnoses TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_archived INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prescriptions (
                prescription_id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER,
                patient_id TEXT NOT NULL,
                medicine_name TEXT NOT NULL,
                dosage TEXT,
                frequency TEXT,
                duration TEXT,
                instructions TEXT,
                prescribed_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_archived INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(encounter_id) REFERENCES encounters(encounter_id) ON DELETE SET NULL,
                FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                attachment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                encounter_id INTEGER,
                record_id INTEGER,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                mime_type TEXT,
                uploaded_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
                FOREIGN KEY(encounter_id) REFERENCES encounters(encounter_id) ON DELETE SET NULL,
                FOREIGN KEY(record_id) REFERENCES medication_records(record_id) ON DELETE SET NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backup_history (
                backup_id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_path TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL
            );
        """)

        # ==============================================================
        # PATIENT PERSONAL MEDICATIONS
        # ==============================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personal_medications (
                personal_medication_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                medicine_name TEXT NOT NULL,
                dosage TEXT,
                frequency TEXT,
                duration TEXT,
                route TEXT,
                instructions TEXT,
                source_document TEXT,
                verified_by TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
            );
        """)

        # ==============================================================
        # CORE8 IDENTITY LINKING + FAMILY FOUNDATION
        # ==============================================================
        cursor.execute("""CREATE TABLE IF NOT EXISTS patient_link_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            patient_id TEXT NOT NULL,
            requested_by INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            reason_context TEXT,
            reviewed_by INTEGER,
            reviewed_at TEXT,
            review_notes TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, patient_id, status),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
        );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS family_relationships (
            relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            related_patient_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(patient_id, related_patient_id, relationship_type),
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
            FOREIGN KEY(related_patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
        );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS family_access_grants (
            grant_id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            grantee_user_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            permission TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            granted_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            UNIQUE(patient_id, grantee_user_id, resource_type, permission),
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
            FOREIGN KEY(grantee_user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );""")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_link_requests_status ON patient_link_requests(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_relationships_patient ON family_relationships(patient_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_access_patient ON family_access_grants(patient_id)")

        # ==============================================================
        # USERS
        # ==============================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                patient_id TEXT,
                full_name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,

                -- Legacy column retained for existing databases.
                -- It is no longer used; permanent deletion is Owner-only.
                permanent_delete_authorized
                    INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL,

                FOREIGN KEY (patient_id)
                    REFERENCES patients(patient_id)
                    ON DELETE SET NULL
            );
        """)

        # ==============================================================
        # UPGRADE EXISTING USERS TABLE
        # ==============================================================

        cursor.execute("""
            PRAGMA table_info(users)
        """)

        user_columns = {
            row["name"]
            for row in cursor.fetchall()
        }

        if "permanent_delete_authorized" not in user_columns:

            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN permanent_delete_authorized
                INTEGER NOT NULL DEFAULT 0
            """)

        if "email" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")

   # ==============================================================
        # Forward-compatible security/sharing columns for existing databases.
        for table, column, definition in [
            ("users", "organization_id", "TEXT NOT NULL DEFAULT 'DEFAULT'"),
            ("patients", "organization_id", "TEXT NOT NULL DEFAULT 'DEFAULT'"),
            ("record_shares", "share_token", "TEXT"),
            ("record_shares", "resource_type", "TEXT NOT NULL DEFAULT 'medication'"),
            ("record_shares", "resource_id", "INTEGER"),
            ("record_shares", "viewed_at", "TEXT"),
            ("record_shares", "revoked_at", "TEXT"),
            ("correction_requests", "reviewed_by", "TEXT"),
            ("correction_requests", "reviewed_at", "TEXT"),
            ("correction_requests", "review_notes", "TEXT"),
            ("encounters", "deleted_by_admin", "INTEGER NOT NULL DEFAULT 0"),
            ("prescriptions", "deleted_by_admin", "INTEGER NOT NULL DEFAULT 0"),
            ("attachments", "is_archived", "INTEGER NOT NULL DEFAULT 0"),
            ("attachments", "deleted_by_admin", "INTEGER NOT NULL DEFAULT 0"),
        ]:
            cursor.execute(f"PRAGMA table_info({table})")
            cols={r["name"] for r in cursor.fetchall()}
            if column not in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        cursor.execute("UPDATE users SET organization_id='DEFAULT' WHERE organization_id IS NULL OR TRIM(organization_id)=''")
        cursor.execute("UPDATE patients SET organization_id='DEFAULT' WHERE organization_id IS NULL OR TRIM(organization_id)=''")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_record_shares_token ON record_shares(share_token) WHERE share_token IS NOT NULL")

        # =============================================================
        # WEB-MIGRATION TENANCY HARDENING
        # =============================================================
        # Child clinical/share/family tables now carry an explicit organization
        # scope. Existing desktop inserts omit the column, so compatibility
        # triggers derive it from the referenced patient/user. The Web API will
        # additionally enforce the same scope before every protected operation.
        scoped_tables = [
            ("medication_records", "patient_id"),
            ("record_access_log", "patient_id"),
            ("record_shares", "patient_id"),
            ("correction_requests", "patient_id"),
            ("encounters", "patient_id"),
            ("prescriptions", "patient_id"),
            ("attachments", "patient_id"),
            ("personal_medications", "patient_id"),
            ("family_relationships", "patient_id"),
            ("family_access_grants", "patient_id"),
            ("patient_link_requests", "patient_id"),
        ]
        for table, patient_column in scoped_tables:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = {r["name"] for r in cursor.fetchall()}
            if "organization_id" not in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN organization_id TEXT NOT NULL DEFAULT 'DEFAULT'")
            # Backfill all existing rows from the owning patient.
            cursor.execute(
                f"UPDATE {table} SET organization_id=(SELECT organization_id FROM patients p WHERE p.patient_id={table}.{patient_column}) "
                f"WHERE {patient_column} IS NOT NULL AND EXISTS (SELECT 1 FROM patients p WHERE p.patient_id={table}.{patient_column})"
            )
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_organization ON {table}(organization_id)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_org_patient ON {table}(organization_id, {patient_column})")

        # Backup rows are owned by the actor rather than a patient.
        cursor.execute("PRAGMA table_info(backup_history)")
        backup_cols = {r["name"] for r in cursor.fetchall()}
        if "organization_id" not in backup_cols:
            cursor.execute("ALTER TABLE backup_history ADD COLUMN organization_id TEXT NOT NULL DEFAULT 'DEFAULT'")
        cursor.execute("""UPDATE backup_history SET organization_id=(
            SELECT organization_id FROM users u WHERE u.username=backup_history.created_by
        ) WHERE EXISTS (SELECT 1 FROM users u WHERE u.username=backup_history.created_by)""")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_backup_history_org ON backup_history(organization_id)")

        # Organization administration: clinics/departments and explicit user assignments.
        cursor.execute("""CREATE TABLE IF NOT EXISTS clinics (
            clinic_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL DEFAULT 'DEFAULT',
            name TEXT NOT NULL, code TEXT NOT NULL, address TEXT, active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT, created_at TEXT NOT NULL,
            UNIQUE (organization_id, code)
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS user_clinics (
            organization_id TEXT NOT NULL DEFAULT 'DEFAULT', user_id TEXT NOT NULL, clinic_id TEXT NOT NULL,
            role_scope TEXT NOT NULL DEFAULT 'member', created_at TEXT NOT NULL,
            PRIMARY KEY (organization_id, user_id, clinic_id),
            FOREIGN KEY (clinic_id) REFERENCES clinics(clinic_id) ON DELETE CASCADE
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS patient_clinics (
            organization_id TEXT NOT NULL DEFAULT 'DEFAULT', patient_id TEXT NOT NULL, clinic_id TEXT NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            PRIMARY KEY (organization_id, patient_id, clinic_id),
            FOREIGN KEY (clinic_id) REFERENCES clinics(clinic_id) ON DELETE CASCADE
        )""")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_clinics_org ON clinics(organization_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_clinics_org_user ON user_clinics(organization_id,user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_patient_clinics_org_patient ON patient_clinics(organization_id,patient_id)")

        # Shared/session state for API deployments. Tokens are stored only as
        # SHA-256 digests, never in plaintext. This table is also useful for a
        # single-instance prototype and can be mapped to PostgreSQL unchanged.
        cursor.execute("""CREATE TABLE IF NOT EXISTS api_sessions (
            session_id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            organization_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )""")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_sessions_token ON api_sessions(token_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_sessions_user ON api_sessions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_sessions_expires ON api_sessions(expires_at)")

        cursor.execute("""CREATE TABLE IF NOT EXISTS api_login_attempts (
            key TEXT PRIMARY KEY,
            failures INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            updated_at TEXT NOT NULL
        )""")

        # Compatibility triggers keep the desktop implementation's existing
        # INSERT statements tenant-safe while the codebase is being migrated
        # to repositories.
        for table, patient_column in scoped_tables:
            trigger = f"trg_{table}_set_org"
            cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            cursor.execute(f"""CREATE TRIGGER {trigger}
                AFTER INSERT ON {table}
                WHEN NEW.{patient_column} IS NOT NULL
                BEGIN
                    UPDATE {table}
                    SET organization_id=COALESCE((SELECT organization_id FROM patients WHERE patient_id=NEW.{patient_column}), 'DEFAULT')
                    WHERE rowid=NEW.rowid;
                END;""")

        # ==============================================================


        # First-run Owner creation is handled by the GUI so the app can
        # launch cleanly even when started by double-clicking the launcher.
        # No default password is ever created here.

        # DATABASE INDEXES
        # ==============================================================

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_medication_records_patient
            ON medication_records(patient_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_medication_records_archived
            ON medication_records(is_archived)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_medication_records_admin_deleted
            ON medication_records(deleted_by_admin)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_medication_records_date
            ON medication_records(record_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_audit_log_record
            ON audit_log(record_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_audit_log_timestamp
            ON audit_log(timestamp)
        """)

        # Backfill stable MED identifiers for Core7 records.
        cursor.execute("UPDATE medication_records SET medication_uid='MED-' || printf('%06d', record_id) WHERE medication_uid IS NULL OR TRIM(medication_uid)=''")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_medication_records_uid ON medication_records(medication_uid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_medication_records_prescription ON medication_records(prescription_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_medication_records_encounter ON medication_records(encounter_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_medication_records_status ON medication_records(status)")
        cursor.execute("UPDATE medication_records SET status='ARCHIVED' WHERE is_archived=1 AND (status IS NULL OR status='ACTIVE')")

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ======================================================================
# AUDIT LOG
# ======================================================================

def log_action(action, record_id=None):
    """
    Adds an entry to the audit log.

    Audit entries are intentionally kept separate from the medication
    record itself so that an audit entry can remain even after the
    medication record is permanently destroyed.
    """

    conn = get_connection()

    try:

        cursor = conn.cursor()

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
                datetime.now().isoformat(
                    timespec="seconds"
                )
            )
        )

        conn.commit()

    finally:

        conn.close()