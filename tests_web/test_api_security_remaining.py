"""Acceptance tests for the remaining Web Foundation security gates."""
import sqlite3
from pathlib import Path
import tempfile
import pytest
from fastapi.testclient import TestClient

@pytest.fixture()
def env(monkeypatch):
    # Force the API acceptance fixture onto isolated SQLite even during PostgreSQL validation.
    monkeypatch.setenv('RECORDGUARD_SESSION_BACKEND', 'sqlite')
    monkeypatch.delenv('RECORDGUARD_DATABASE_URL', raising=False)
    import database, functions
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(database, 'DB_PATH', str(Path(td)/'web.db'))
        database.initialize_database()
        import backend.api as api
        from backend.repositories.sqlite import SQLiteSessionRepository
        api.sessions=SQLiteSessionRepository()
        client=TestClient(api.app)
        owner_r=client.post('/auth/owner/setup',json={'username':'owner','password':'OwnerPass123','full_name':'Owner'})
        assert owner_r.status_code==200, owner_r.text
        owner=functions.authenticate_user('owner','OwnerPass123')
        yield client, functions, owner

def login(client, username, password):
    r=client.post('/auth/login',json={'username':username,'password':password}); assert r.status_code==200, r.text
    return {'Authorization':f"Bearer {r.json()['access_token']}"}

def test_patient_directory_is_restricted_to_linked_patient(env):
    client, functions, owner=env
    pid=functions.register_patient(owner,'Only Me','30','M')['patient_id']
    functions.create_new_user(owner,'pat','PatientPass123','patient','Only Me',pid)
    headers=login(client,'pat','PatientPass123')
    r=client.get('/patients',headers=headers)
    assert r.status_code==200 and [x['patient_id'] for x in r.json()['items']]==[pid]
    assert client.get('/patients/NOT-THIS-PATIENT',headers=headers).status_code in (403,404)

def test_patient_cannot_register_patient(env):
    client, functions, owner=env
    pid=functions.register_patient(owner,'Patient','30','M')['patient_id']
    functions.create_new_user(owner,'pat2','PatientPass123','patient','Patient',pid)
    headers=login(client,'pat2','PatientPass123')
    r=client.post('/patients',headers=headers,json={'name':'Nope','age':20,'sex':'F'})
    assert r.status_code==403

def test_cross_org_user_cannot_read_patient(env):
    client, functions, owner=env
    pid=functions.register_patient(owner,'Tenant A','40','F')['patient_id']
    functions.create_new_user(owner,'other','OtherPass123','admin','Other')
    conn=__import__('database').get_connection(); conn.execute("UPDATE users SET organization_id='OTHER' WHERE username='other'"); conn.commit(); conn.close()
    headers=login(client,'other','OtherPass123')
    r=client.get(f'/patients/{pid}',headers=headers)
    assert r.status_code==403

def test_attachment_endpoints_preserve_patient_scope(env,tmp_path):
    client, functions, owner=env
    pid=functions.register_patient(owner,'Attachment Patient','45','M')['patient_id']
    p=tmp_path/'note.txt'; p.write_text('synthetic demo document')
    functions.create_new_user(owner,'doc','DoctorPass123','doctor','Doctor')
    headers=login(client,'doc','DoctorPass123')
    with p.open('rb') as fh:
        r=client.post(f'/patients/{pid}/attachments',headers=headers,files={'file':('note.txt',fh,'text/plain')})
    assert r.status_code==200, r.text
    listing=client.get(f'/patients/{pid}/attachments',headers=headers)
    assert listing.status_code==200 and listing.json()['items']
    assert 'stored_path' not in listing.json()['items'][0]
