
"""
models.py
---------
Simple data-shaping helpers for RecordGuard.

RecordGuard uses plain functions and dictionaries instead of a heavy ORM
so that the application remains beginner-readable.
"""

from database import get_connection


# ======================================================================
# PATIENT ID
# ======================================================================

PATIENT_ID_PREFIX = "RG"
PATIENT_ID_DIGITS = 5  # RG00001, RG00002, ...

def generate_patient_id():
    """
    Generates the next sequential patient ID safely using an atomic
    database sequence and exclusive locking to prevent race conditions.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # 1. Create a dedicated sequence table if it doesn't exist yet
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patient_sequence (
                id INTEGER PRIMARY KEY,
                last_value INTEGER NOT NULL
            )
        """)

        # 2. If the sequence is empty, seed it with the current max ID
        # so we don't overwrite existing patients.
        cursor.execute("SELECT COUNT(*) as count FROM patient_sequence")
        if cursor.fetchone()["count"] == 0:
            cursor.execute("SELECT patient_id FROM patients")
            max_val = 0
            for row in cursor.fetchall():
                pid = str(row["patient_id"] or "").upper()
                if pid.startswith(PATIENT_ID_PREFIX) and pid[len(PATIENT_ID_PREFIX):].isdigit():
                    max_val = max(max_val, int(pid[len(PATIENT_ID_PREFIX):]))

            cursor.execute("INSERT INTO patient_sequence (id, last_value) VALUES (1, ?)", (max_val,))
            conn.commit()

        # 3. Lock the database, atomically increment, and fetch the new ID
        cursor.execute("BEGIN EXCLUSIVE TRANSACTION")

        cursor.execute("UPDATE patient_sequence SET last_value = last_value + 1 WHERE id = 1")
        cursor.execute("SELECT last_value FROM patient_sequence WHERE id = 1")
        next_number = cursor.fetchone()["last_value"]

        conn.commit()

        return f"{PATIENT_ID_PREFIX}{next_number:0{PATIENT_ID_DIGITS}d}"

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ======================================================================
# PATIENT DATA
# ======================================================================

def patient_row_to_dict(row):
    """
    Converts a sqlite3.Row containing patient information
    into a normal Python dictionary.

    The additional patient fields are optional so this function
    remains compatible with older records.
    """

    if row is None:

        return None

    keys = row.keys()

    return {
        "patient_id": row["patient_id"],
        "name": row["name"],
        "age": row["age"],
        "sex": row["sex"],

        "date_of_birth": (
            row["date_of_birth"]
            if "date_of_birth" in keys
            else None
        ),

        "permanent_address": (
            row["permanent_address"]
            if "permanent_address" in keys
            else None
        ),

        "current_address": (
            row["current_address"]
            if "current_address" in keys
            else None
        ),

        "phone_number": (
            row["phone_number"]
            if "phone_number" in keys
            else None
        ),

        "blood_group": (
            row["blood_group"]
            if "blood_group" in keys
            else None
        ),

        "registered_by": (
            row["registered_by"]
            if "registered_by" in keys
            else None
        ),

        "organization_id": (
            row["organization_id"]
            if "organization_id" in keys
            else "DEFAULT"
        ),

        "created_at": row["created_at"],
    }


# ======================================================================
# MEDICATION
# ======================================================================

def get_or_create_medication(
    medicine_name: str
):
    """
    Looks up a medicine using a case-insensitive match.

    If the medicine does not exist, it is created.

    Returns:
        int: medication_id
    """

    clean_name = (
        medicine_name or ""
    ).strip()

    if not clean_name:

        raise ValueError(
            "Medicine name cannot be empty."
        )

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT medication_id
            FROM medications
            WHERE medicine_name = ?
            COLLATE NOCASE
            """,
            (clean_name,)
        )

        row = cursor.fetchone()

        if row is not None:

            return row["medication_id"]

        cursor.execute(
            """
            INSERT INTO medications
                (medicine_name)
            VALUES (?)
            """,
            (clean_name,)
        )

        conn.commit()

        return cursor.lastrowid

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ======================================================================
# MEDICATION RECORD
# ======================================================================

def medication_record_row_to_dict(row):
    """
    Converts a joined medication_records + medications database row
    into a normal Python dictionary.

    Supports both the original fields and the archive/admin-delete
    fields used by the current RecordGuard system.
    """

    if row is None:

        return None

    keys = row.keys()

    return {
        "record_id": row["record_id"],
        "medication_uid": row["medication_uid"] if "medication_uid" in keys else f"MED-{int(row['record_id']):06d}",
        "patient_id": row["patient_id"],
        "medicine_name": row["medicine_name"],
        "response_type": row["response_type"],
        "reaction": row["reaction"],
        "severity": row["severity"],
        "reason": row["reason"],
        "notes": row["notes"],
        "record_date": row["record_date"],
        "status": row["status"] if "status" in keys else ("ARCHIVED" if row["is_archived"] else "ACTIVE"),

        "is_archived": (
            row["is_archived"]
            if "is_archived" in keys
            else 0
        ),

        "archived_at": (
            row["archived_at"]
            if "archived_at" in keys
            else None
        ),

        "archived_by": (
            row["archived_by"]
            if "archived_by" in keys
            else None
        ),

        "deleted_by_admin": (
            row["deleted_by_admin"]
            if "deleted_by_admin" in keys
            else 0
        ),

        "admin_deleted_at": (
            row["admin_deleted_at"]
            if "admin_deleted_at" in keys
            else None
        ),

        "admin_deleted_by": (
            row["admin_deleted_by"]
            if "admin_deleted_by" in keys
            else None
        ),
        "prescription_id": row["prescription_id"] if "prescription_id" in keys else None,
        "encounter_id": row["encounter_id"] if "encounter_id" in keys else None,
    }