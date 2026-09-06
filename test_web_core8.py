from pathlib import Path

ROOT = Path(__file__).parent
WEB = ROOT / "apps" / "web"
PAGE = WEB / "app" / "page.tsx"
CSS = WEB / "app" / "styles.css"


def test_web_core8_has_authenticated_workspace():
    text = PAGE.read_text(encoding="utf-8")
    for marker in ["/auth/login", "/auth/me", "/auth/logout", "credentials:'include'", "Patients", "Medications", "Sharing", "Settings"]:
        assert marker in text


def test_web_core8_uses_server_authorization_boundary():
    text = PAGE.read_text(encoding="utf-8")
    assert "Authorization" in text
    assert "credentials:'include'" in text
    assert "localStorage" not in text


def test_web_core8_patient_and_medication_flows_are_api_backed():
    text = PAGE.read_text(encoding="utf-8")
    for marker in ["/patients", "/medications", "/patients/${encodeURIComponent(pid)}/medications"]:
        assert marker in text
    assert "Register patient" in text
    assert "Add medication record" in text


def test_web_core8_sharing_does_not_request_or_render_bearer_token():
    text = PAGE.read_text(encoding="utf-8")
    assert "/sharing?patient_id=" in text
    sharing = text[text.index("function Sharing"):text.index("function Audit")]
    assert "access_token" not in sharing


def test_web_core8_role_restricted_audit_navigation():
    text = PAGE.read_text(encoding="utf-8")
    assert "role==='owner'||role==='admin'" in text
    assert "role==='owner'||role==='admin'" in text
    assert "Audit" in text


def test_web_core8_accessible_responsive_baseline():
    text = CSS.read_text(encoding="utf-8")
    assert "max-width: 850px" in text
    assert "input,\nselect,\ntextarea" in text or "input,select,textarea" in text
    assert "button:disabled" in text
