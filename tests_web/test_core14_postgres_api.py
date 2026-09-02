from types import SimpleNamespace


def test_postgres_repository_uses_explicit_tenant_predicates():
    from pathlib import Path
    source = Path(__file__).parents[1] / "backend" / "repositories" / "postgres.py"
    text = source.read_text(encoding="utf-8")
    assert "WHERE organization_id=%s" in text
    assert "WHERE mr.organization_id=%s" in text
    assert "WHERE organization_id=%s AND public_patient_id=%s" in text


def test_postgres_repository_uses_password_hash_verification():
    from pathlib import Path
    source = Path(__file__).parents[1] / "backend" / "repositories" / "postgres.py"
    text = source.read_text(encoding="utf-8")
    assert "verify_password(password, user[\"password_hash\"])" in text
    assert "password_hash" in text


def test_api_postgres_mode_uses_repository_for_patient_and_medication(monkeypatch):
    import importlib
    api = importlib.import_module("backend.api.app")
    from fastapi.testclient import TestClient

    owner = {"user_id": "u1", "username": "owner", "role": "owner", "organization_id": "org1", "active": True}
    patient = {"patient_id": "p1", "public_patient_id": "RG00001", "organization_id": "org1", "name": "Test", "age": 30, "sex": "F"}
    medication = {"record_id": "r1", "public_medication_id": "MED-000001", "organization_id": "org1", "patient_id": "p1", "medicine_name": "Medicine A"}

    class FakeSessions:
        def get_session_user(self, token):
            return owner if token == "token" else None
        def revoke_session(self, token):
            pass
        def create_session(self, *args):
            return "token"

    class FakeRepo:
        def get_patient(self, actor, pid):
            return patient if actor.organization_id == "org1" and pid == "RG00001" else None
        def list_patients(self, actor, query=None):
            return [patient] if actor.organization_id == "org1" else []
        def list_medications(self, actor, pid, include_archived=False):
            return [medication] if actor.organization_id == "org1" and pid == "RG00001" else []
        def create_patient(self, actor, *args):
            return patient
        def create_medication(self, actor, *args):
            return medication
        def list_audit_events(self, org, filters=None):
            return [{"organization_id": org, "action": "TEST"}]

    monkeypatch.setattr(api, "sessions", FakeSessions())
    monkeypatch.setattr(api, "data_repository", FakeRepo())
    client = TestClient(api.app)
    headers = {"Authorization": "Bearer token"}

    assert client.get("/patients", headers=headers).json()["items"] == [patient]
    assert client.get("/patients/RG00001", headers=headers).json() == patient
    assert client.get("/patients/RG00001/medications", headers=headers).json()["items"] == [medication]
    assert client.post("/patients", headers=headers, json={"name":"Test","age":30,"sex":"F"}).status_code == 200
    assert client.post("/medications", headers=headers, json={"patient_id":"RG00001","medicine_name":"Medicine A","response_type":"Effective"}).status_code == 200
    assert client.get("/audit", headers=headers).status_code == 200
