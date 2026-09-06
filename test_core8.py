import sqlite3
import pytest
import database, functions

@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / 'core8.db'
    monkeypatch.setattr(database, 'DB_PATH', str(db))
    monkeypatch.setattr(functions, 'get_connection', database.get_connection)
    database.initialize_database()
    owner = functions.create_initial_owner('owner8', 'OwnerTest123', 'Core8 Owner')
    return owner

def test_public_signup_creates_only_user(env):
    user_id = functions.create_public_user_account('common8', 'Common123', 'Common User')
    user = functions.authenticate_user('common8', 'Common123')
    assert user['user_id'] == user_id
    assert user['role'] == 'user'
    assert user['patient_id'] is None
    conn = database.get_connection()
    try:
        assert conn.execute('SELECT COUNT(*) FROM patients').fetchone()[0] == 0
    finally:
        conn.close()

def test_patient_link_requires_review_and_can_unlink(env):
    owner = env
    patient = functions.register_patient(owner, 'Link Patient', '30', 'F')
    functions.create_public_user_account('linkuser', 'LinkTest123', 'Link User')
    user = functions.authenticate_user('linkuser', 'LinkTest123')
    with pytest.raises(functions.RecordGuardError):
        functions.get_patient_by_id(user, patient['patient_id'])
    request_id = functions.request_patient_link(user, patient['patient_id'], 'Verified identity')
    functions.review_patient_link_request(owner, request_id, 'APPROVED', 'Checked authorization')
    linked = functions.authenticate_user('linkuser', 'LinkTest123')
    assert linked['role'] == 'patient'
    assert linked['patient_id'] == patient['patient_id']
    assert functions.get_patient_by_id(linked, patient['patient_id'])['patient_id'] == patient['patient_id']
    functions.unlink_patient_account(linked, 'LinkTest123')
    unlinked = functions.authenticate_user('linkuser', 'LinkTest123')
    assert unlinked['role'] == 'user'
    assert unlinked['patient_id'] is None

def test_patient_id_alone_never_grants_access(env):
    owner = env
    patient = functions.register_patient(owner, 'Private', '31', 'M')
    functions.create_public_user_account('plain', 'PlainTest123', 'Plain User')
    plain = functions.authenticate_user('plain', 'PlainTest123')
    assert not functions.can_view_patient(plain, patient['patient_id'])

def test_medication_identity_and_optional_links(env):
    owner = env
    patient = functions.register_patient(owner, 'Med Patient', '32', 'M')
    enc = functions.create_encounter(owner, patient['patient_id'], '2026-08-31', 'Review')
    rx = functions.add_prescription(owner, patient['patient_id'], 'Medicine A', '10 mg', 'OD', '5 days', encounter_id=enc)
    med = functions.add_medication_record(owner, patient['patient_id'], 'Medicine A', 'Effective', prescription_id=rx, encounter_id=enc)
    assert med['medication_uid'] == 'MED-000001'
    records = functions.get_medication_records_for_patient(patient['patient_id'], user=owner)
    assert records[0]['medication_uid'] == 'MED-000001'
    assert records[0]['prescription_id'] == rx
    assert records[0]['encounter_id'] == enc

def test_audit_is_structured_correlated_and_append_only(env):
    owner = env
    patient = functions.register_patient(owner, 'Audit Patient', '33', 'F')
    functions.create_public_user_account('audituser', 'AuditTest123', 'Audit User')
    user = functions.authenticate_user('audituser', 'AuditTest123')
    req = functions.request_patient_link(user, patient['patient_id'], 'Audit test')
    functions.review_patient_link_request(owner, req, 'APPROVED', 'Approved')
    events = functions.get_audit_log(owner)
    assert all(e['event_id'] and e['actor_id'] and e['actor_role'] and e['category'] and e['action'] for e in events)
    link_events = [e for e in events if e['correlation_id'] == f'COR-LINK-{req}']
    assert len(link_events) >= 1
    conn = database.get_connection()
    try:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE audit_log SET reason_context='tampered' WHERE log_id=1")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM audit_log WHERE log_id=1")
    finally:
        conn.close()

def test_role_escalation_still_blocked(env):
    owner = env
    functions.create_new_user(owner, 'admin8', 'AdminTest123', 'admin', 'Admin')
    admin = functions.authenticate_user('admin8', 'AdminTest123')
    with pytest.raises(functions.RecordGuardError):
        functions.create_new_user(admin, 'owner8b', 'OwnerTest123', 'owner', 'Fake Owner')
    with pytest.raises(functions.RecordGuardError):
        functions.create_new_user(admin, 'admin8b', 'AdminTest123', 'admin', 'Fake Admin')
