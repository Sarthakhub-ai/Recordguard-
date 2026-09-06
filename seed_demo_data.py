"""
RecordGuard demo-data seeder.

Creates synthetic data only. It NEVER creates or changes the Owner account.
The existing Owner signs in during setup and authorizes the seed operation.

Dataset:
- 5 Admins
- 10 Staff
- 5 Doctors
- 100 synthetic Patients (20 registered by each Admin)
- 50 patient/individual login accounts linked to the first 50 patients
- 1 clearly-marked demo encounter + prescription per patient

Run after the normal RecordGuard first-run Owner setup:
    python seed_demo_data.py

The generated demo credentials are written to DEMO_CREDENTIALS.txt.
Do not use these demo accounts for production data.
"""

from datetime import date, timedelta
from pathlib import Path
import getpass
import secrets
import string
import sqlite3

from database import get_connection, initialize_database, hash_password
from functions import authenticate_user, RecordGuardError
from models import generate_patient_id

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_PATH = BASE_DIR / "DEMO_CREDENTIALS.txt"

ADMIN_COUNT = 5
PATIENTS_PER_ADMIN = 20
STAFF_COUNT = 10
DOCTOR_COUNT = 5
PATIENT_USER_COUNT = 50

FIRST_NAMES = [
    "Aarav", "Aditi", "Arjun", "Ananya", "Dev", "Diya", "Kabir", "Kavya",
    "Rohan", "Riya", "Vihaan", "Meera", "Advik", "Ishita", "Kunal", "Nisha",
    "Rahul", "Sneha", "Varun", "Tanya", "Manav", "Pooja", "Yash", "Neha",
    "Vivek", "Simran", "Aman", "Priya", "Rajat", "Sanya", "Nikhil", "Ira",
    "Aditya", "Maya", "Sahil", "Rhea", "Ankit", "Shreya", "Mohit", "Tanvi",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Kapoor", "Malhotra", "Mehta", "Bansal", "Joshi",
    "Saxena", "Arora", "Khanna", "Sethi", "Agarwal", "Singh", "Chopra", "Rana",
    "Mishra", "Nair", "Iyer", "Das", "Patel", "Shah", "Jain", "Sinha",
]

BLOOD_GROUPS = ["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-"]


def _now():
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _password(length=14):
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.islower() for c in value) and any(c.isupper() for c in value) and any(c.isdigit() for c in value):
            return value


def _name(index):
    return f"{FIRST_NAMES[index % len(FIRST_NAMES)]} {LAST_NAMES[(index * 7) % len(LAST_NAMES)]}"


def _dob_for_age(age):
    return date.today().replace(year=date.today().year - age) - timedelta(days=(age * 17) % 300)


def _preflight(conn):
    if conn.execute("SELECT 1 FROM users WHERE role='owner' LIMIT 1").fetchone() is None:
        raise RecordGuardError("Create the Owner account in RecordGuard before running the demo-data setup.")
    existing = conn.execute(
        "SELECT username FROM users WHERE username LIKE 'demo_%' LIMIT 1"
    ).fetchone()
    if existing:
        raise RecordGuardError(
            "Demo data already appears to be installed. No changes were made."
        )


def main():
    print("RecordGuard synthetic demo-data setup")
    print("=====================================")
    print("This will add synthetic users, patients and clearly-marked demo clinical data.")
    print("It will NOT create or replace the Owner account.\n")

    initialize_database()
    owner_username = input("Owner username: ").strip()
    owner_password = getpass.getpass("Owner password: ")
    owner = authenticate_user(owner_username, owner_password)
    if owner.get("role") != "owner":
        raise RecordGuardError("The supplied account is not the Owner.")

    conn = get_connection()
    try:
        _preflight(conn)
    finally:
        conn.close()

    print("\nPreparing 5 admins, 10 staff, 5 doctors and 100 patients...")

    # Generate IDs before the single seed transaction. Gaps are harmless and
    # preferable to weakening the existing patient-ID sequence implementation.
    patient_ids = [generate_patient_id() for _ in range(ADMIN_COUNT * PATIENTS_PER_ADMIN)]

    accounts = []
    for i in range(ADMIN_COUNT):
        accounts.append((f"demo_admin{i+1:02d}", "admin", f"Demo Admin {i+1}"))
    for i in range(STAFF_COUNT):
        accounts.append((f"demo_staff{i+1:02d}", "staff", f"Demo Staff {i+1}"))
    for i in range(DOCTOR_COUNT):
        accounts.append((f"demo_doctor{i+1:02d}", "doctor", f"Demo Doctor {i+1}"))

    passwords = {username: _password() for username, _, _ in accounts}
    for i in range(PATIENT_USER_COUNT):
        username = f"demo_patient{i+1:02d}"
        accounts.append((username, "patient", f"Demo Patient User {i+1}"))
        passwords[username] = _password()

    conn = get_connection()
    try:
        cur = conn.cursor()
        org = str(owner.get("organization_id") or "DEFAULT")
        created = _now()

        # A local marker makes future automation able to detect that this seed
        # has already run without relying on a hidden application state.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS demo_seed_runs (
                seed_name TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL
            )
        """)
        if cur.execute("SELECT 1 FROM demo_seed_runs WHERE seed_name='RecordGuardDemo100-v1'").fetchone():
            raise RecordGuardError("This demo dataset has already been installed.")

        # Users first, except patient accounts which are linked after patients exist.
        for username, role, full_name in accounts:
            if role == "patient":
                continue
            cur.execute("""
                INSERT INTO users
                    (username, password_hash, role, patient_id, full_name, active,
                     permanent_delete_authorized, organization_id, created_at)
                VALUES (?, ?, ?, NULL, ?, 1, 0, ?, ?)
            """, (username, hash_password(passwords[username]), role, full_name, org, created))
            cur.execute(
                "INSERT INTO audit_log(action, record_id, timestamp) VALUES(?,?,?)",
                (f"Created demo {role} user '{username}'", None, created),
            )

        # 100 patients: exactly 20 registered by each demo Admin.
        patient_rows = []
        for idx, patient_id in enumerate(patient_ids):
            admin_idx = idx // PATIENTS_PER_ADMIN
            admin_username = f"demo_admin{admin_idx+1:02d}"
            age = 18 + (idx * 7) % 63
            sex = ["Male", "Female"][idx % 2]
            dob = _dob_for_age(age).isoformat()
            name = _name(idx)
            phone = f"90000{idx:05d}"
            address = f"Demo Address {idx+1}, RecordGuard Test City"
            blood = BLOOD_GROUPS[idx % len(BLOOD_GROUPS)]
            cur.execute("""
                INSERT INTO patients
                    (patient_id, name, age, sex, date_of_birth, permanent_address,
                     current_address, phone_number, blood_group, registered_by,
                     organization_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, name, age, sex, dob, address, address, phone, blood,
                  admin_username, org, created))
            cur.execute(
                "INSERT INTO audit_log(action, record_id, timestamp) VALUES(?,?,?)",
                (f"Registered demo patient {patient_id} by {admin_username}", None, created),
            )
            patient_rows.append((patient_id, name, admin_username))

        # 50 individual/patient accounts linked to the first 50 synthetic patients.
        patient_accounts = [(u, role, name) for u, role, name in accounts if role == "patient"]
        for i, (username, _, full_name) in enumerate(patient_accounts):
            patient_id = patient_ids[i]
            cur.execute("""
                INSERT INTO users
                    (username, password_hash, role, patient_id, full_name, active,
                     permanent_delete_authorized, organization_id, created_at)
                VALUES (?, ?, 'patient', ?, ?, 1, 0, ?, ?)
            """, (username, hash_password(passwords[username]), patient_id, full_name, org, created))
            cur.execute(
                "INSERT INTO audit_log(action, record_id, timestamp) VALUES(?,?,?)",
                (f"Created demo patient user '{username}' linked to {patient_id}", None, created),
            )

        # Give every patient a safe, obviously synthetic clinical timeline.
        demo_visit = date.today().isoformat()
        for idx, (patient_id, name, admin_username) in enumerate(patient_rows):
            visit_type = "Demo follow-up"
            notes = "DEMO DATA ONLY — synthetic record created for RecordGuard testing."
            diagnoses = "Demo test entry — not a clinical diagnosis."
            cur.execute("""
                INSERT INTO encounters
                    (patient_id, visit_date, visit_type, chief_complaint, visit_notes,
                     diagnoses, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, demo_visit, visit_type, "Demo test visit", notes, diagnoses,
                  admin_username, created))
            encounter_id = cur.lastrowid
            cur.execute(
                "INSERT INTO audit_log(action, record_id, timestamp) VALUES(?,?,?)",
                (f"Created demo encounter {encounter_id} for {patient_id} by {admin_username}", encounter_id, created),
            )
            medicine = ["Demo Tablet A", "Demo Tablet B", "Demo Capsule C"][idx % 3]
            cur.execute("""
                INSERT INTO prescriptions
                    (encounter_id, patient_id, medicine_name, dosage, frequency,
                     duration, instructions, prescribed_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (encounter_id, patient_id, medicine, "Demo dose", "Demo frequency",
                  "Demo duration", "DEMO DATA ONLY — do not use as medical advice.",
                  admin_username, created))
            prescription_id = cur.lastrowid
            cur.execute(
                "INSERT INTO audit_log(action, record_id, timestamp) VALUES(?,?,?)",
                (f"Created demo prescription {prescription_id} for {patient_id} by {admin_username}", prescription_id, created),
            )

        cur.execute(
            "INSERT INTO demo_seed_runs(seed_name, created_at, created_by) VALUES(?,?,?)",
            ("RecordGuardDemo100-v1", created, owner_username),
        )
        cur.execute(
            "INSERT INTO audit_log(action, record_id, timestamp) VALUES(?,?,?)",
            (f"Installed synthetic demo dataset: 100 patients, 5 admins, 10 staff, 5 doctors, 50 patient users by {owner_username}", None, created),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    lines = [
        "RecordGuard synthetic demo credentials",
        "======================================",
        "WARNING: These accounts are for local testing only.",
        "Delete/deactivate them before using RecordGuard for real data.",
        "",
        "Owner: existing Owner account was NOT changed.",
        "",
    ]
    for username, role, full_name in accounts:
        lines.append(f"{role:7} | {username:18} | {passwords[username]} | {full_name}")
    lines.append("")
    lines.append("Patient assignment: demo_admin01..05 each registered exactly 20 patients.")
    lines.append("Patient users: demo_patient01..50 are linked to the first 50 demo patients.")
    lines.append("All clinical entries are explicitly synthetic demo data and not medical advice.")
    CREDENTIALS_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\nSUCCESS")
    print("-------")
    print("100 synthetic patients created: 20 per Admin.")
    print("5 Admins, 10 Staff, 5 Doctors and 50 linked patient users created.")
    print("1 synthetic encounter + prescription created for each patient.")
    print(f"Credentials saved to: {CREDENTIALS_PATH}")
    print("The Owner account was left unchanged.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled. No partial seed is committed by the final transaction.")
        raise SystemExit(1)
    except (RecordGuardError, sqlite3.Error, ValueError) as exc:
        print(f"\nSetup failed: {exc}")
        raise SystemExit(1)
