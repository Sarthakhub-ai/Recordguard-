from pathlib import Path

ROOT = Path(__file__).parents[1]
APP = (ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
WEB = (ROOT / "apps" / "web" / "app" / "page.tsx").read_text(encoding="utf-8")

def test_clinical_list_routes_support_lifecycle_visibility():
    assert "def medications(patient_id: str, include_archived: bool = False" in APP
    assert "def list_encounters(patient_id: str, include_archived: bool = False" in APP
    assert "def list_prescriptions(patient_id: str, include_archived: bool = False" in APP
    assert "data_repository.list_medications(_actor(user), patient_id, include_archived)" in APP
    assert "data_repository.list_encounters, _actor(user), patient_id, include_archived" in APP
    assert "data_repository.list_prescriptions, _actor(user), patient_id, include_archived" in APP

def test_web_exposes_encounters_and_prescriptions_with_role_controls():
    assert "'Clinical'" in WEB
    assert "/patients/${encodeURIComponent(pid)}/encounters?include_archived=${includeArchived}" in WEB
    assert "/patients/${encodeURIComponent(pid)}/prescriptions?include_archived=${includeArchived}" in WEB
    assert "api('/encounters'" in WEB
    assert "api('/prescriptions'" in WEB
    assert "Admin delete" in WEB and "Owner recover" in WEB and "permanent-destroy" in WEB

def test_web_destructive_actions_require_password_and_delete_confirmation():
    assert "Enter your current password to continue:" in WEB
    assert "Type DELETE to confirm this destructive action:" in WEB
    assert "JSON.stringify({password,confirmation:'DELETE'})" in WEB

def test_web_does_not_persist_bearer_token():
    assert "localStorage" not in WEB
    assert "credentials:'include'" in WEB
