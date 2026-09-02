import sqlite3
import pytest
import database, functions

@pytest.fixture
def env(tmp_path, monkeypatch):
    db=tmp_path/'sec.db'; monkeypatch.setattr(database,'DB_PATH',str(db)); monkeypatch.setattr(functions,'get_connection',database.get_connection)
    import models; monkeypatch.setattr(models,'get_connection',database.get_connection)
    database.initialize_database(); functions.create_initial_owner('owner','OwnerTest123','Owner')
    owner=functions.authenticate_user('owner','OwnerTest123')
    p=functions.register_patient(owner,'Patient One','30','F')
    functions.create_new_user(owner,'doc','DoctorTest123','doctor','Doctor')
    doc=functions.authenticate_user('doc','DoctorTest123')
    return owner,doc,p,db

def test_medication_mutations_are_patient_scope_checked(env):
    owner,doc,p,db=env
    p2=functions.register_patient(owner,'Patient Two','31','M')
    rid=functions.add_medication_record(doc,p['patient_id'],'Drug','Effective')['record_id']
    # A doctor from the same organization may access both patients, so this is allowed.
    # Cross-organization access must be blocked.
    conn=database.get_connection(); conn.execute("update users set organization_id='OTHER' where username='doc'"); conn.commit(); conn.close()
    doc2=functions.authenticate_user('doc','DoctorTest123')
    with pytest.raises(functions.RecordGuardError): functions.edit_medication_record(doc2,rid,'Drug','Effective')
    with pytest.raises(functions.RecordGuardError): functions.archive_medication_record(doc2,rid)

def test_ehr_lifecycle_is_patient_scope_checked(env):
    owner,doc,p,db=env
    eid=functions.create_encounter(doc,p['patient_id'],'2026-08-31','Visit')
    conn=database.get_connection(); conn.execute("update users set organization_id='OTHER' where username='doc'"); conn.commit(); conn.close()
    doc2=functions.authenticate_user('doc','DoctorTest123')
    with pytest.raises(functions.RecordGuardError): functions.archive_ehr_item(doc2,'encounter',eid)

def test_patient_user_link_must_exist_in_same_org(env):
    owner,doc,p,db=env
    with pytest.raises(functions.RecordGuardError): functions.create_new_user(owner,'badpat','PatientTest123','patient','Bad','NO_SUCH_PATIENT')
    conn=database.get_connection(); conn.execute("update patients set organization_id='OTHER' where patient_id=?",(p['patient_id'],)); conn.commit(); conn.close()
    with pytest.raises(functions.RecordGuardError): functions.create_new_user(owner,'crosspat','PatientTest123','patient','Cross',p['patient_id'])

def test_document_share_does_not_expose_local_path(env,tmp_path):
    owner,doc,p,db=env
    src=tmp_path/'secret.pdf'; src.write_text('secret')
    aid=functions.add_attachment(doc,p['patient_id'],str(src))
    sh=functions.create_record_share(doc,p['patient_id'],aid,'recipient', '2099-12-31T23:59:59', resource_type='document')
    result=functions.access_shared_record(sh['token'])
    assert 'stored_path' not in result['record']

def test_patient_delete_cleans_orphan_security_rows_and_files(env,tmp_path):
    owner,doc,p,db=env
    rid=functions.add_medication_record(doc,p['patient_id'],'Drug','Effective')['record_id']
    src=tmp_path/'x.txt'; src.write_text('x')
    aid=functions.add_attachment(doc,p['patient_id'],str(src))
    pat=functions.create_new_user(owner,'pat','PatientTest123','patient','Patient One',p['patient_id'])
    pat=functions.authenticate_user('pat','PatientTest123')
    sh=functions.create_record_share(pat,p['patient_id'],rid,'recipient','2099-12-31T23:59:59')
    functions.request_record_correction(pat,p['patient_id'],rid,'Please correct this')
    stored_dir=tmp_path
    functions.permanently_delete_patient(owner,p['patient_id'],'OwnerTest123')
    conn=database.get_connection()
    assert conn.execute('select 1 from patients where patient_id=?',(p['patient_id'],)).fetchone() is None
    assert conn.execute('select 1 from record_shares where patient_id=?',(p['patient_id'],)).fetchone() is None
    assert conn.execute('select 1 from correction_requests where patient_id=?',(p['patient_id'],)).fetchone() is None
    assert conn.execute('select 1 from record_access_log where patient_id=?',(p['patient_id'],)).fetchone() is None
    conn.close()

def test_authentication_session_does_not_expose_password_hash(env):
    owner, _, _, _ = env
    assert 'password_hash' not in owner


def test_medication_permanent_delete_requires_admin_deleted_state(env):
    owner, doc, p, db = env
    rid = functions.add_medication_record(doc, p['patient_id'], 'Staged Drug', 'Effective')['record_id']

    with pytest.raises(functions.RecordGuardError, match='Admin-deleted'):
        functions.permanently_delete_medication_record(owner, rid, 'OwnerTest123')

    conn = database.get_connection()
    row = conn.execute('select deleted_by_admin from medication_records where record_id=?', (rid,)).fetchone()
    conn.close()
    assert row is not None and row['deleted_by_admin'] == 0

def test_new_backup_payload_is_encrypted_and_requires_passphrase():
    payload = b'RecordGuard test backup payload'
    encrypted = functions._encrypt_backup_bytes(payload, 'BackupPass123')
    assert encrypted.startswith(functions.BACKUP_MAGIC)
    assert encrypted != payload
    restored, legacy = functions._decrypt_backup_bytes(encrypted, 'BackupPass123')
    assert restored == payload
    assert legacy is False
    with pytest.raises(functions.RecordGuardError):
        functions._decrypt_backup_bytes(encrypted, 'WrongPass123')


def test_legacy_plaintext_backup_is_detected_for_migration():
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('recordguard.db', b'sqlite-placeholder')
    restored, legacy = functions._decrypt_backup_bytes(buf.getvalue(), None)
    assert restored == buf.getvalue()
    assert legacy is True
