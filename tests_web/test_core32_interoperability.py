from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_interoperability_contract_and_route_present():
    api = (ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    assert '/interoperability/capabilities' in api
    assert '/interoperability/fhir/patients/{patient_id}' in api
    assert 'patient_to_bundle' in api

def test_interoperability_ui_has_trust_boundary():
    ui = (ROOT / "apps" / "web" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert 'Interoperability' in ui
    assert 'FHIR-inspired prototype' in ui
    assert 'Download interoperability JSON' in ui
    assert 'does not infer diagnoses or prescribe treatment' in ui
