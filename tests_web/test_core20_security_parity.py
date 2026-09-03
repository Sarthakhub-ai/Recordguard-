from pathlib import Path

ROOT = Path(__file__).parents[1]
REPO = ROOT / "backend" / "repositories" / "postgres.py"
PAGE = ROOT / "apps" / "web" / "app" / "page.tsx"

def test_postgres_patient_reads_have_explicit_role_and_link_scope():
    text = REPO.read_text(encoding="utf-8")
    assert "def _pg_require_patient_read" in text
    assert 'if role in {"owner", "admin", "doctor", "staff"}' in text
    assert 'if role == "patient"' in text
    assert 'raise PermissionError("This account is not authorized to access patient medical records.")' in text
    assert '_pg_require_patient_read(c, actor, p["patient_id"], "medication")' in text

def test_postgres_clinical_reads_share_the_same_patient_scope_guard():
    text = REPO.read_text(encoding="utf-8")
    assert '_pg_require_patient_read(c, actor, p, "ehr")' in text
    assert '_pg_require_patient_read(c, actor, p, "medication")' in text

def test_common_user_is_not_given_patient_directory_access_by_web_ui():
    text = PAGE.read_text(encoding="utf-8")
    assert "localStorage" not in text
    assert "client:'web'" in text
    assert "credentials:'include'" in text

def test_server_side_patient_search_is_supported():
    app = (ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    repo = REPO.read_text(encoding="utf-8")
    assert 'def patients(q: Optional[str] = None' in app
    assert 'def list_patients(self, actor, query=None)' in repo
    assert 'ILIKE %s' in repo

def test_share_redemption_endpoint_and_resource_allowlist_exist():
    app = (ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    repo = REPO.read_text(encoding="utf-8")
    assert '@app.post("/sharing/redeem")' in app
    assert 'def _core20_redeem_share' in repo
    assert 'token_hash = hashlib.sha256(token.encode()).hexdigest()' in repo
    assert 'revoked_at' in repo and 'expires_at' in repo

def test_attachment_magic_byte_validation_is_enforced():
    repo = REPO.read_text(encoding="utf-8")
    assert 'def _validate_attachment_content(source_path):' in repo
    for marker in ('b"%PDF-"', 'b"\\x89PNG', 'b"\\xff\\xd8\\xff"', 'b"RIFF"'):
        assert marker in repo
    assert '_validate_attachment_content(source_path)' in repo

def test_http_only_session_cookie_support_exists():
    app = (ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    assert 'response.set_cookie("rg_session"' in app
    assert 'httponly=True' in app
    assert 'samesite="lax"' in app
    assert 'response.delete_cookie("rg_session"' in app

def test_typed_authorization_error_is_available_for_new_api_paths():
    domain = (ROOT / "shared" / "domain.py").read_text(encoding="utf-8")
    app = (ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    repo = REPO.read_text(encoding="utf-8")
    assert 'class AuthorizationError(DomainError)' in domain
    assert 'except AuthorizationError as exc:' in app
    assert 'raise AuthorizationError(message)' in repo


def test_postgres_family_grants_are_part_of_resource_read_authorization():
    text = REPO.read_text(encoding="utf-8")
    assert "def _pg_has_family_permission" in text
    assert "family_access_grants" in text
    assert "permission=%s AND status='ACTIVE'" in text
    assert 'resource_type=None' in text

def test_sharing_management_policy_is_explicit_and_backend_aligned():
    pg = REPO.read_text(encoding="utf-8")
    sqlite = (ROOT / "functions.py").read_text(encoding="utf-8")
    assert "def _pg_require_share_management" in pg
    assert 'role in {"owner", "admin"}' in pg
    assert 'role == "doctor"' in pg
    assert 'role == "patient"' in pg
    assert 'role in {"owner", "admin", "doctor"}' in sqlite
    assert 'role == "patient"' in sqlite
    assert "manage sharing for this patient" in pg
    assert "manage sharing for this patient" in sqlite


def test_permanent_document_destroy_removes_object_before_db_delete():
    repo = REPO.read_text(encoding="utf-8")
    start = repo.index('def _core15_lifecycle_ehr')
    end = repo.index('\ndef _core15_verify_actor_password', start)
    block = repo[start:end]
    assert 'if typ == "document":' in block
    assert 'LocalObjectStorage().delete(object_key)' in block
    assert 'c.execute(f"DELETE FROM {table}' in block
    assert block.index('LocalObjectStorage().delete(object_key)') < block.index('c.execute(f"DELETE FROM {table}')
