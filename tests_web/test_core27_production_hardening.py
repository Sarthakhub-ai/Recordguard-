from pathlib import Path

ROOT = Path(__file__).parents[1]
APP = ROOT / "backend" / "api" / "app.py"
FUNCTIONS = ROOT / "functions.py"


def test_legacy_sqlite_authorization_errors_are_typed():
    app = APP.read_text(encoding="utf-8")
    functions = FUNCTIONS.read_text(encoding="utf-8")
    assert "class AuthorizationRecordGuardError(RecordGuardError)" in functions
    assert "except functions.AuthorizationRecordGuardError as exc:" in app
    assert 'lowered = message.lower()' not in app
    assert 'any(x in lowered' not in app


def test_request_correlation_id_is_generated_server_side():
    app = APP.read_text(encoding="utf-8")
    assert 'request.state.request_id = request_id' in app
    assert 'response.headers["X-Request-ID"] = request_id' in app
    assert 'request_id = str(uuid.uuid4())' in app


def test_cookie_authenticated_mutations_have_origin_guard():
    app = APP.read_text(encoding="utf-8")
    assert 'async def cookie_csrf_guard' in app
    assert 'request.cookies.get("rg_session")' in app
    assert 'Cross-site request blocked.' in app
    assert 'request.method in {"POST", "PUT", "PATCH", "DELETE"}' in app


def test_security_headers_include_core_browser_hardening():
    app = APP.read_text(encoding="utf-8")
    for header in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"):
        assert f'response.headers["{header}"]' in app
    assert 'Strict-Transport-Security' in app


def test_runtime_security_headers_and_request_id():
    from fastapi.testclient import TestClient
    from backend.api.app import app
    with TestClient(app) as client:
        response = client.get('/health')
    assert response.status_code == 200
    assert response.headers.get('X-Request-ID')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Referrer-Policy'] == 'no-referrer'


def test_cookie_session_rejects_disallowed_cross_site_mutation():
    from fastapi.testclient import TestClient
    from backend.api.app import app
    with TestClient(app) as client:
        client.cookies.set('rg_session', 'synthetic-session')
        response = client.post('/auth/logout', headers={'Origin': 'https://evil.example'})
    assert response.status_code == 403
    assert response.json()['detail'] == 'Cross-site request blocked.'
