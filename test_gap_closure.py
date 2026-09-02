import os, shutil, sqlite3
import pytest
import database, functions, models

@pytest.fixture
def qa_env(tmp_path, monkeypatch):
    # Start from the shipped schema/data, but isolate all mutations.
    db = tmp_path / 'qa.db'
    monkeypatch.setattr(database, 'DB_PATH', str(db))
    database.initialize_database()
    monkeypatch.setattr(functions, 'get_connection', database.get_connection)
    monkeypatch.setattr(models, 'get_connection', database.get_connection)
    # Ensure shipped DB has an owner for deterministic tests.
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    if not conn.execute("select 1 from users where role='owner' limit 1").fetchone():
        conn.execute("insert into users(username,password_hash,role,full_name,active,permanent_delete_authorized,created_at,organization_id) values(?,?,?,?,?,?,?,?)",
                     ('owner', database.hash_password('OwnerTest123'), 'owner', 'QA Owner', 1, 0, '2026-08-31T00:00:00', 'DEFAULT'))
    conn.commit(); conn.close()
    owner = functions.authenticate_user('owner', 'OwnerTest123')
    return owner

def test_patient_scan_attachment_permission_and_personal_medication(qa_env, tmp_path):
    owner=qa_env
    patient=functions.register_patient(owner,'Scan Patient','30','M')
    puid=functions.create_new_user(owner,'scanpatient','PatientTest123','patient','Scan Patient',patient['patient_id'])
    user=functions.authenticate_user('scanpatient','PatientTest123')
    src=tmp_path/'rx.txt'; src.write_text('Amoxicillin 500 mg BD for 5 days')
    pid=functions.add_personal_medication(user,patient['patient_id'],'Amoxicillin','500 mg','BD','5 days',source_document=src.name)
    aid=functions.add_attachment(user,patient['patient_id'],str(src))
    assert pid and aid

def test_staff_prescription_is_pending(qa_env):
    owner=qa_env
    patient=functions.register_patient(owner,'Staff Patient','35','F')
    functions.create_new_user(owner,'staffqa','StaffTest123','staff','QA Staff')
    staff=functions.authenticate_user('staffqa','StaffTest123')
    rid=functions.add_prescription(staff,patient['patient_id'],'Medicine X','10 mg','OD','7 days')
    rx=functions.list_prescriptions(staff,patient['patient_id'])
    assert rx[0]['prescription_id']==rid
    assert '[PENDING VERIFICATION]' in rx[0]['prescribed_by']

def test_secure_share_expiry_revoke_and_access(qa_env):
    owner=qa_env
    patient=functions.register_patient(owner,'Share Patient','40','M')
    functions.create_new_user(owner,'docqa','DoctorTest123','doctor','QA Doctor')
    doc=functions.authenticate_user('docqa','DoctorTest123')
    rid=functions.add_medication_record(doc,patient['patient_id'],'Medicine Y','Effective')['record_id']
    functions.create_new_user(owner,'patqa','PatientTest123','patient','QA Patient',patient['patient_id'])
    pat=functions.authenticate_user('patqa','PatientTest123')
    sh=functions.create_record_share(pat,patient['patient_id'],rid,'qa-recipient','2099-12-31T23:59:59')
    assert functions.access_shared_record(sh['token'])['record']['record_id']==rid
    functions.revoke_record_share(pat,sh['share_id'])
    with pytest.raises(functions.RecordGuardError, match='revoked'):
        functions.access_shared_record(sh['token'])

def test_correction_review_workflow_and_admin_directory(qa_env):
    owner=qa_env
    patient=functions.register_patient(owner,'Correction Patient','41','F')
    functions.create_new_user(owner,'doccorr','DoctorTest123','doctor','QA Doctor')
    doc=functions.authenticate_user('doccorr','DoctorTest123')
    rid=functions.add_medication_record(doc,patient['patient_id'],'Medicine Z','Unknown')['record_id']
    functions.create_new_user(owner,'patcorr','PatientTest123','patient','QA Patient',patient['patient_id'])
    pat=functions.authenticate_user('patcorr','PatientTest123')
    req=functions.request_record_correction(pat,patient['patient_id'],rid,'The response is incorrect')
    assert functions.get_correction_requests(owner)[0]['status']=='Pending'
    functions.review_correction_request(owner,req,'Approved','Verified against source record')
    assert functions.get_correction_requests(owner)[0]['status']=='Approved'
    functions.create_new_user(owner,'adminqa','AdminTest123','admin','QA Admin')
    admin=functions.authenticate_user('adminqa','AdminTest123')
    assert any(x['username']=='adminqa' for x in functions.list_users(admin))

def test_organization_scope_blocks_cross_org_patient(qa_env):
    owner=qa_env
    p1=functions.register_patient(owner,'Org Patient','25','M')
    functions.create_new_user(owner,'otheradmin','AdminTest123','admin','Other Admin')
    conn=database.get_connection(); conn.execute("update users set organization_id='OTHER' where username='otheradmin'"); conn.commit(); conn.close()
    other=functions.authenticate_user('otheradmin','AdminTest123')
    assert not functions.can_view_patient(other,p1['patient_id'])

def test_ehr_lifecycle_for_encounter_prescription_and_document(qa_env, tmp_path):
    owner=qa_env
    patient=functions.register_patient(owner,'Lifecycle Patient','50','M')
    functions.create_new_user(owner,'doclife','DoctorTest123','doctor','QA Doctor')
    doc=functions.authenticate_user('doclife','DoctorTest123')
    eid=functions.create_encounter(doc,patient['patient_id'],'2026-08-31','Review')
    rxid=functions.add_prescription(doc,patient['patient_id'],'Medicine L','20 mg','OD','5 days',encounter_id=eid)
    src=tmp_path/'report.txt'; src.write_text('report')
    aid=functions.add_attachment(doc,patient['patient_id'],str(src),encounter_id=eid)
    for typ,rid in [('encounter',eid),('prescription',rxid),('document',aid)]:
        functions.archive_ehr_item(doc,typ,rid)
    functions.create_new_user(owner,'adminlife','AdminTest123','admin','QA Admin')
    admin=functions.authenticate_user('adminlife','AdminTest123')
    for typ,rid in [('encounter',eid),('prescription',rxid),('document',aid)]:
        functions.recover_archived_ehr_item(admin,typ,rid)
        functions.archive_ehr_item(admin,typ,rid)
        functions.admin_delete_ehr_item(admin,typ,rid,'AdminTest123')
    for typ,rid in [('encounter',eid),('prescription',rxid),('document',aid)]:
        functions.recover_admin_deleted_ehr_item(owner,typ,rid)
        functions.archive_ehr_item(owner,typ,rid)
        functions.admin_delete_ehr_item(admin,typ,rid,'AdminTest123')
        functions.permanently_delete_ehr_item(owner,typ,rid,'OwnerTest123')
