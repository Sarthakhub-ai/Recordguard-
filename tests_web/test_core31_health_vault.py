from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_health_vault_navigation_and_export_controls_present():
    ui = (ROOT / "apps" / "web" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "Health Vault" in ui
    assert "Emergency Health Card" in ui
    assert "Data portability" in ui
    assert "Download JSON" in ui
    assert "Download CSV" in ui


def test_health_vault_keeps_safety_boundary():
    ui = (ROOT / "apps" / "web" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "not a diagnosis or prescribing tool" in ui
    assert "Verify the source record" in ui
