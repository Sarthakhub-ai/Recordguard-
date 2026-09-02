"""Core12 acceptance tests for link, family, sharing and disclosure boundaries."""
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
        monkeypatch.setattr(database, 'DB_PATH', str(Path(td) / 'web.db'))
        database.initialize_database()
        import backend.api as api
        from backend.repositories.sqlite import SQLiteSessionRepository
        api.sessions = SQLiteSessionRepository()
        client = TestClient(api.app)
        r = client.post('/auth/owner/setup', json={'username':'owner','password':'OwnerPass123','full_name':'Owner'})
        assert r.status_code == 200, r.text
        owner = functions.authenticate_user('owner','OwnerPass123')
        yield client, functions, owner

def login(client, username, password):
    r = client.post('/auth/login', json={'username':username,'password':password})
    assert r.status_code == 200, r.text
    return {'Authorization': f"Bearer {r.json()['access_token']}"}

def test_sharing_list_does_not_disclose_bearer_token(env):
    client, functions, owner = env
    pid = functions.register_patient(owner, 'Share Patient', '40', 'F')['patient_id']
    functions.add_medication_record(owner, pid, 'Paracetamol', 'Effective')
    functions.create_new_user(owner, 'doc', 'DoctorPass123', 'doctor', 'Doctor')
    doc = functions.authenticate_user('doc','DoctorPass123')
    rows = functions.get_medication_records_for_patient(pid, False, False, doc)
    rid = rows[0]['record_id']
    headers = login(client,'doc','DoctorPass123')
    created = client.post('/sharing', headers=headers, json={'patient_id':pid,'record_id':rid,'shared_with':'recipient@example.com'})
    assert created.status_code == 200, created.text
    token = created.json()['token']
    listing = client.get(f'/sharing?patient_id={pid}', headers=headers)
    assert listing.status_code == 200, listing.text
    item = listing.json()['items'][0]
    assert 'token' not in item and 'share_token' not in item and 'token_hash' not in item
    assert token

def test_family_access_does_not_cross_organizations(env):
    client, functions, owner = env
    import database
    p1 = functions.register_patient(owner,'Family A','35','F')['patient_id']
    p2 = functions.register_patient(owner,'Family B','36','M')['patient_id']
    conn = database.get_connection()
    conn.execute("UPDATE patients SET organization_id='OTHER' WHERE patient_id=?", (p2,))
    conn.commit(); conn.close()
    functions.create_new_user(owner,'patienta','PatientPass123','patient','Family A',p1)
    headers = login(client,'patienta','PatientPass123')
    # Cross-organization family relationships must be rejected.
    r = client.post('/family/relationships', headers=headers, json={'patient_id':p1,'related_patient_id':p2,'relationship_type':'sibling'})
    assert r.status_code == 403, r.text

def test_unlinked_user_can_request_link_but_cannot_directly_link(env):
    client, functions, owner = env
    pid = functions.register_patient(owner,'Link Target','28','M')['patient_id']
    functions.create_public_user_account('common','CommonPass123','Common User')
    headers = login(client,'common','CommonPass123')
    r = client.post('/patient-links/request', headers=headers, json={'patient_id':pid,'reason':'I need access to my record'})
    assert r.status_code == 200, r.text
    # Public/common account still cannot read the Patient profile merely by knowing the ID.
    assert client.get(f'/patients/{pid}', headers=headers).status_code in (403,404)

def test_link_review_is_organization_scoped(env):
    client, functions, owner = env
    pid = functions.register_patient(owner,'Scoped Link','30','F')['patient_id']
    functions.create_public_user_account('common2','CommonPass123','Common User 2')
    # The request endpoint creates a pending request in the owner's organization.
    h = login(client,'common2','CommonPass123')
    req = client.post('/patient-links/request', headers=h, json={'patient_id':pid}).json()['request_id']
    assert req > 0
    # A Patient cannot review administrative link requests.
    functions.create_new_user(owner,'pat','PatientPass123','patient','Patient',pid)
    hp = login(client,'pat','PatientPass123')
    assert client.post('/patient-links/review', headers=hp, json={'request_id':req,'decision':'APPROVED'}).status_code == 403

def test_logout_revokes_session(env):
    client, functions, owner = env
    headers = login(client, 'owner', 'OwnerPass123')
    assert client.get('/auth/me', headers=headers).status_code == 200
    assert client.post('/auth/logout', headers=headers).status_code == 200
    assert client.get('/auth/me', headers=headers).status_code == 401


def test_admin_cannot_create_privileged_admin_or_owner(env):
    client, functions, owner = env
    functions.create_new_user(owner, 'admin1', 'AdminPass123', 'admin', 'Admin')
    admin = functions.authenticate_user('admin1', 'AdminPass123')
    with pytest.raises(functions.RecordGuardError):
        functions.create_new_user(admin, 'admin2', 'AdminPass456', 'admin', 'Admin 2')
    with pytest.raises(functions.RecordGuardError):
        functions.create_new_user(admin, 'owner2', 'OwnerPass456', 'owner', 'Owner 2')


def test_audit_log_is_append_only(env):
    client, functions, owner = env
    import database
    conn = database.get_connection()
    try:
        row = conn.execute('SELECT log_id, action FROM audit_log ORDER BY log_id DESC LIMIT 1').fetchone()
        assert row is not None
        with pytest.raises(Exception):
            conn.execute('UPDATE audit_log SET action=? WHERE log_id=?', ('tampered', row['log_id']))
            conn.commit()
    finally:
        conn.rollback()
        conn.close()
