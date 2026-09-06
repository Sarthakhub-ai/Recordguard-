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
    assert text.count('_pg_require_patient_read(c, actor, p, "ehr")') >= 1
    assert text.count('_pg_require_patient_read(c, actor, p, "medication")') >= 1

def test_common_user_is_not_given_patient_directory_access_by_web_ui():
    text = PAGE.read_text(encoding="utf-8")
    assert "localStorage" not in text
    assert "client:'web'" in text
    assert "credentials:'include'" in text

def test_server_side_patient_search_is_supported():
    app = (ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    repo = REPO.read_text(encoding="utf-8")
    assert 'def patients(' in app and 'q: Optional[str] = None' in app
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
    assert 'response.set_cookie(' in app and '"rg_session"' in app
    assert 'httponly=True' in app
    assert 'samesite="lax"' in app
    assert 'delete_cookie(' in app and 'rg_session' in app

def test_typed_authorization_error_is_available_for_new_api_paths():
    domain = (ROOT / "shared" / "domain.py").read_text(encoding="utf-8")
    app = (ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    repo = REPO.read_text(encoding="utf-8")
    assert 'class AuthorizationError(DomainError)' in domain
    assert 'except AuthorizationError as exc:' in app
    assert 'raise AuthorizationError(message)' in repo
