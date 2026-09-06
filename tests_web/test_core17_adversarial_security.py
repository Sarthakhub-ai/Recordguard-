from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).parents[1]
REPO = ROOT / "backend" / "repositories" / "postgres.py"
DOMAIN = ROOT / "shared" / "domain.py"
SCHEMA = ROOT / "database" / "migrations" / "001_recordguard_web.sql"


def test_postgres_medication_links_are_tenant_and_patient_bound():
    text = REPO.read_text(encoding="utf-8")
    assert 'SELECT patient_id,organization_id FROM prescriptions WHERE prescription_id=%s' in text
    assert 'SELECT patient_id,organization_id FROM encounters WHERE encounter_id=%s' in text
    assert 'The prescription does not belong to this organization and patient.' in text
    assert 'The encounter does not belong to this organization and patient.' in text
    assert 'The prescription and encounter do not match.' in text


def test_postgres_audit_ids_are_uuid_validated_and_resource_filter_is_exact():
    text = REPO.read_text(encoding="utf-8")
    assert 'def _pg_uuid(value, label):' in text
    assert 'resource_uuid = _pg_uuid(resource_id, "resource_id")' in text
    assert 'AND {col}=%s' in text
    assert 'CAST({col} AS text) ILIKE' not in text


def test_link_approval_creates_canonical_patient_user_link():
    text = REPO.read_text(encoding="utf-8")
    assert 'INSERT INTO patient_user_links' in text
    assert "ON CONFLICT(organization_id,user_id,patient_id) DO UPDATE SET status='ACTIVE'" in text


def test_family_duplicate_handling_does_not_swallow_unrelated_database_errors():
    text = REPO.read_text(encoding="utf-8")
    assert 'except UniqueViolation as exc:' in text
    assert 'except Exception as exc:' not in text


def test_lifecycle_role_matrix_matches_shared_policy_for_archiving():
    repo = REPO.read_text(encoding="utf-8")
    domain = DOMAIN.read_text(encoding="utf-8")
    assert 'can_archive_records(role)' in domain
    assert 'Role.STAFF' in domain
    assert 'doctor' in repo and 'staff' in repo
    assert '_pg_require_role(actor, {"owner", "admin", "doctor", "staff"}' in repo
    lifecycle = repo[repo.index("def _core15_lifecycle_medication"):repo.index("def _core15_lifecycle_ehr") + 1200]
    assert '_pg_require_role(actor, {"owner", "admin", "doctor"}' not in lifecycle


def test_destructive_lifecycle_requires_staged_transition_and_password():
    repo = REPO.read_text(encoding="utf-8")
    domain = DOMAIN.read_text(encoding="utf-8")
    assert 'admin_delete' in repo and 'ARCHIVED' in repo and 'ADMIN_DELETED' in repo
    assert 'permanent_destroy' in repo and 'ADMIN_DELETED' in repo
    assert 'if not password or not self._verify_actor_password(actor, password)' in repo
    assert 'A record must be archived before Admin deletion.' in domain
    assert 'Permanent destruction requires an Admin-deleted record.' in domain


def test_cross_tenant_queries_are_explicitly_scoped():
    text = REPO.read_text(encoding="utf-8")
    required = [
        'WHERE organization_id=%s AND public_patient_id=%s',
        'WHERE organization_id=%s AND request_id=%s',
        'WHERE organization_id=%s AND grant_id=%s',
        'WHERE organization_id=%s AND share_id=%s',
        'WHERE organization_id=%s AND record_id=%s',
    ]
    for marker in required:
        assert marker in text


def test_schema_supports_canonical_links_and_tenant_unique_usernames():
    text = SCHEMA.read_text(encoding="utf-8")
    assert 'UNIQUE (organization_id, username)' in text
    assert 'CREATE TABLE IF NOT EXISTS patient_user_links' in text
    assert 'UNIQUE (organization_id, user_id, patient_id)' in text


def test_login_detects_ambiguous_active_credentials_instead_of_picking_an_account():
    text = REPO.read_text(encoding="utf-8")
    assert 'Multiple active accounts match these credentials.' in text
    assert 'len(matches) > 1' in text
    assert 'ORDER BY created_at ASC' in text


def test_uuid_helper_accepts_uuid_strings_and_rejects_public_ids():
    import importlib
    repo = importlib.import_module("backend.repositories.postgres")
    value = "123e4567-e89b-12d3-a456-426614174000"
    assert repo._pg_uuid(value, "x") == UUID(value)
    try:
        repo._pg_uuid("MED-000001", "resource_id")
    except ValueError as exc:
        assert "resource_id must be a PostgreSQL UUID" in str(exc)
    else:
        raise AssertionError("Public IDs must not be accepted as PostgreSQL audit UUIDs")
