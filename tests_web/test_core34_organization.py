from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core34_clinic_schema_and_scoped_api_exist():
    db = (ROOT / "database.py").read_text(encoding="utf-8")
    api = (ROOT / "backend/api/app.py").read_text(encoding="utf-8")
    fn = (ROOT / "functions.py").read_text(encoding="utf-8")

    for token in (
        "CREATE TABLE IF NOT EXISTS clinics",
        "CREATE TABLE IF NOT EXISTS user_clinics",
        "CREATE TABLE IF NOT EXISTS patient_clinics",
    ):
        assert token in db

    for token in (
        "/organization/clinics",
        "/organization/users/clinics",
        "/organization/patients/clinics",
    ):
        assert token in api

    for token in (
        "def create_clinic",
        "def assign_user_to_clinic",
        "def assign_patient_to_clinic",
    ):
        assert token in fn


def test_core34_requires_owner_or_admin():
    fn = (ROOT / "functions.py").read_text(encoding="utf-8")

    assert "Only an Owner or Admin can manage organization clinics." in fn


def test_core34_postgres_schema_and_repository_are_tenant_scoped():
    sql = (
        ROOT / "database/migrations/001_recordguard_web.sql"
    ).read_text(encoding="utf-8")
    repo = (
        ROOT / "backend/repositories/postgres.py"
    ).read_text(encoding="utf-8")

    for token in (
        "CREATE TABLE IF NOT EXISTS clinics",
        "CREATE TABLE IF NOT EXISTS user_clinics",
        "CREATE TABLE IF NOT EXISTS patient_clinics",
    ):
        assert token in sql

    assert (
        "WHERE organization_id=%s AND clinic_id=%s"
        in repo
    )


def test_core34_repository_scopes_clinic_assignment_queries():
    repo = (
        ROOT / "backend/repositories/postgres.py"
    ).read_text(encoding="utf-8")

    for token in (
        "User not found in this organization.",
        "Clinic not found or inactive in this organization.",
        "INSERT INTO user_clinics",
        "INSERT INTO patient_clinics",
        "CLINIC_USER_ASSIGNED",
        "CLINIC_PATIENT_ASSIGNED",
    ):
        assert token in repo


def test_core34_clinic_status_change_is_tenant_scoped():
    repo = (
        ROOT / "backend/repositories/postgres.py"
    ).read_text(encoding="utf-8")

    assert "UPDATE clinics SET active=%s" in repo
    assert (
        "WHERE organization_id=%s AND clinic_id=%s"
        in repo
    )
    assert "CLINIC_ACTIVATED" in repo
    assert "CLINIC_DEACTIVATED" in repo
