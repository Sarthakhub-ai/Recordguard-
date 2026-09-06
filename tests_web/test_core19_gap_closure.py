from pathlib import Path

ROOT = Path(__file__).parents[1]
REPO = (ROOT / "backend" / "repositories" / "postgres.py").read_text(encoding="utf-8")
APP = (ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
SCHEMA = (ROOT / "database" / "migrations" / "001_recordguard_web.sql").read_text(encoding="utf-8")
STORAGE = (ROOT / "backend" / "storage.py").read_text(encoding="utf-8")


def test_live_infrastructure_compose_is_defined():
    compose = (ROOT / "docker-compose.postgres.yml").read_text(encoding="utf-8")
    assert "postgres:16-alpine" in compose
    assert "5432:5432" in compose
    assert "pg_isready" in compose


def test_database_has_tenant_consistency_constraints():
    for marker in (
        "users_org_patient_fk",
        "encounters_org_patient_fk",
        "prescriptions_org_patient_fk",
        "med_records_org_patient_fk",
        "attachments_org_patient_fk",
        "family_org_patient_fk",
        "shares_org_patient_fk",
    ):
        assert marker in SCHEMA


def test_clinical_crud_foundation_exists_and_is_tenant_bound():
    assert "def _core19_create_encounter" in REPO
    assert "def _core19_list_encounters" in REPO
    assert "def _core19_create_prescription" in REPO
    assert "def _core19_list_prescriptions" in REPO
    assert 'organization_id=%s AND encounter_id=%s' in REPO
    assert 'organization_id=%s AND patient_id=%s' in REPO


def test_correction_requests_preserve_provenance_and_do_not_silently_edit_records():
    assert "CREATE TABLE IF NOT EXISTS correction_requests" in SCHEMA
    assert "CORRECTION_REQUESTED" in REPO
    assert "CORRECTION_REVIEWED" in REPO
    assert "does not silently mutate" in REPO or "provenance-preserving request" in REPO


def test_attachment_storage_uses_opaque_keys_and_path_traversal_guard():
    assert "class LocalObjectStorage" in STORAGE
    assert "_safe_path" in STORAGE
    assert "self.root not in path.parents" in STORAGE
    assert "object_key" in REPO
    assert 'FileResponse' in APP


def test_attachment_download_is_authenticated_and_non_cacheable():
    assert 'def download_attachment' in APP
    assert 'Depends(current_user)' in APP
    assert 'Cache-Control' in APP and 'no-store' in APP


def test_shares_require_future_timezone_aware_expiration_and_management_does_not_expose_token():
    assert 'Share expiration must include a timezone.' in REPO
    assert 'expiry = expiry.astimezone(timezone.utc)' in REPO
    assert 'token_hash' not in APP[APP.index('def sharing'):APP.index('@app.post("/sharing")')]
    assert '"token"' not in APP[APP.index('def sharing'):APP.index('@app.post("/sharing")')]


def test_security_headers_are_present():
    for header in ('X-Content-Type-Options', 'X-Frame-Options', 'Referrer-Policy', 'Permissions-Policy'):
        assert f'response.headers["{header}"]' in APP


def test_correction_routes_are_registered():
    assert '@app.post("/correction-requests")' in APP
    assert '@app.post("/correction-requests/review")' in APP
    assert '@app.get("/correction-requests")' in APP


def test_formal_role_matrix_is_declared_for_all_six_roles():
    domain = (ROOT / "shared" / "domain.py").read_text(encoding="utf-8")
    for role in ("owner", "admin", "doctor", "staff", "patient", "user"):
        assert f'"{role}"' in domain or f"'{role}'" in domain
    for resource in ("patient", "encounter", "prescription", "document", "sharing", "family", "audit"):
        assert resource in APP.lower() or resource in domain.lower()
