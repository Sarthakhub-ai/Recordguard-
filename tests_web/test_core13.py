from pathlib import Path
import tempfile
import subprocess
import sys


def test_common_user_is_a_first_class_authenticated_actor():
    from shared.domain import Actor, Role, can_add_records
    actor = Actor.from_mapping({"user_id": 7, "role": "user", "organization_id": "ORG-1"})
    assert actor.role is Role.COMMON_USER
    assert not can_add_records(actor.role)


def test_migration_preflight_reports_schema_without_connecting_to_postgres():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "empty.db"
        import sqlite3
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE patients (patient_id TEXT, organization_id TEXT)")
        conn.commit(); conn.close()
        script = Path(__file__).parents[1] / "scripts" / "migrate_sqlite_to_postgres.py"
        out = subprocess.run([sys.executable, str(script), "--sqlite", str(db), "--report", str(Path(td)/"r.json")], capture_output=True, text=True)
        assert out.returncode != 0
        assert "users" in out.stdout


def test_migration_script_blocks_unvalidated_apply():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "empty.db"
        import sqlite3
        sqlite3.connect(db).close()
        script = Path(__file__).parents[1] / "scripts" / "migrate_sqlite_to_postgres.py"
        out = subprocess.run([sys.executable, str(script), "--sqlite", str(db), "--apply"], capture_output=True, text=True)
        assert out.returncode != 0
        assert "Preflight only" in (out.stdout + out.stderr)

import pytest

@pytest.fixture()
def api_env(monkeypatch):
    import database, functions
    from fastapi.testclient import TestClient
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(database, 'DB_PATH', str(Path(td) / 'web.db'))
        database.initialize_database()
        import backend.api as api
        from backend.repositories.sqlite import SQLiteSessionRepository
        api.sessions = SQLiteSessionRepository()
        client = TestClient(api.app)
        assert client.post('/auth/owner/setup', json={'username':'owner','password':'OwnerPass123','full_name':'Owner'}).status_code == 200
        owner = functions.authenticate_user('owner','OwnerPass123')
        yield client, functions, owner


def _auth(client, username, password):
    r = client.post('/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.text
    return {'Authorization': f"Bearer {r.json()['access_token']}"}


def test_medication_lifecycle_api_preserves_staged_order(api_env):
    client, functions, owner = api_env
    pid = functions.register_patient(owner, 'Lifecycle Patient', '40', 'F')['patient_id']
    functions.add_medication_record(owner, pid, 'Medicine A', 'Effective')
    record_id = functions.get_medication_records_for_patient(pid, False, False, owner)[0]['record_id']
    functions.create_new_user(owner, 'admin', 'AdminPass123', 'admin', 'Admin')
    admin_h = _auth(client, 'admin', 'AdminPass123')
    owner_h = _auth(client, 'owner', 'OwnerPass123')

    assert client.post(f'/medications/{record_id}/admin-delete', headers=admin_h, json={'password':'AdminPass123','confirmation':'DELETE'}).status_code == 400
    assert client.post(f'/medications/{record_id}/archive', headers=admin_h).status_code == 200
    assert client.post(f'/medications/{record_id}/admin-delete', headers=admin_h, json={'password':'AdminPass123','confirmation':'DELETE'}).status_code == 200
    assert client.post(f'/medications/{record_id}/permanent-destroy', headers=admin_h, json={'password':'AdminPass123','confirmation':'DELETE'}).status_code == 403
    assert client.post(f'/medications/{record_id}/owner-recover', headers=owner_h).status_code == 200
    # Recovery returns the record to ACTIVE; archive it again before permanent destruction.
    assert client.post(f'/medications/{record_id}/archive', headers=owner_h).status_code == 200
    assert client.post(f'/medications/{record_id}/admin-delete', headers=owner_h, json={'password':'OwnerPass123','confirmation':'DELETE'}).status_code == 200
    assert client.post(f'/medications/{record_id}/permanent-destroy', headers=owner_h, json={'password':'OwnerPass123','confirmation':'DELETE'}).status_code == 200


def test_audit_api_filters_are_forwarded_and_patient_scoped(api_env):
    client, functions, owner = api_env
    pid = functions.register_patient(owner, 'Audit Patient', '30', 'M')['patient_id']
    headers = _auth(client, 'owner', 'OwnerPass123')
    r = client.get('/audit', headers=headers, params={'patient_id': pid, 'action': 'PATIENT'})
    assert r.status_code == 200, r.text
    assert all(str(item.get('organization_id')) == str(owner.get('organization_id') or 'DEFAULT') for item in r.json()['items'])
