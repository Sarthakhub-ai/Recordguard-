from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_web_has_patient_timeline_and_safety_passport():
    ui = (ROOT / "apps" / "web" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "Timeline" in ui
    assert "Patient timeline" in ui
    assert "Safety Passport" in ui
    assert "Evidence timeline" in ui


def test_web_medicine_intelligence_is_historical_only():
    ui = (ROOT / "apps" / "web" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "Medicine Intelligence" in ui
    assert "does not diagnose, prescribe" in ui or "not a diagnosis or prescribing tool" in ui
    assert "personalized yes/no safety decision" in ui
    assert "Historical summary" in ui


def test_timeline_uses_server_authorized_patient_endpoints():
    ui = (ROOT / "apps" / "web" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "api(`/patients/${encodeURIComponent(pid)}`" in ui
    assert "/medications`" in ui
    assert "/encounters`" in ui
    assert "/prescriptions`" in ui
    assert "/attachments`" in ui


def test_timeline_css_supports_responsive_evidence_navigation():
    css = (ROOT / "apps" / "web" / "app" / "styles.css").read_text(encoding="utf-8")
    assert ".timeline" in css
    assert ".timeline-item" in css
    assert ".alert-list" in css
    assert "max-width: 520px" in css
