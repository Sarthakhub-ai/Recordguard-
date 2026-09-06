import os
import pytest
import database, functions

@pytest.fixture
def env(tmp_path, monkeypatch):
    db=tmp_path/'complete.db'
    monkeypatch.setattr(database,'DB_PATH',str(db))
    monkeypatch.setattr(functions,'get_connection',database.get_connection)
    database.initialize_database()
    owner=functions.create_initial_owner('owner','OwnerTest123','Owner')
    return functions.authenticate_user('owner','OwnerTest123')

def test_family_relationship_and_explicit_access(env):
    owner=env
    p1=functions.register_patient(owner,'Alice Patient','30','F')
    p2=functions.register_patient(owner,'Bob Patient','32','M')
    uid=functions.create_public_user_account('caregiver','CareTest123','Caregiver')
    user=functions.authenticate_user('caregiver','CareTest123')
    rid=functions.create_family_relationship(owner,p1['patient_id'],p2['patient_id'],'caregiver')
    assert functions.list_family_relationships(owner,p1['patient_id'])[0]['relationship_id']==rid
    gid=functions.grant_family_access(owner,p1['patient_id'],uid,'medication','view')
    assert functions.can_access_family_resource(user,p1['patient_id'],'medication')
    functions.revoke_family_access(owner,gid)
    assert not functions.can_access_family_resource(user,p1['patient_id'],'medication')

def test_medication_lifecycle_status(env):
    owner=env
    p=functions.register_patient(owner,'Status Patient','30','F')
    r=functions.add_medication_record(owner,p['patient_id'],'Medicine S','Effective')
    assert r['medication_uid']=='MED-000001'
    assert functions.get_medication_records_for_patient(p['patient_id'],user=owner)[0]['status']=='ACTIVE'
    functions.set_medication_status(owner,r['record_id'],'COMPLETED')
    assert functions.get_medication_records_for_patient(p['patient_id'],user=owner)[0]['status']=='COMPLETED'
    functions.archive_medication_record(owner,r['record_id'])
    assert functions.get_medication_records_for_patient(p['patient_id'],include_archived=True,user=owner)[0]['status']=='ARCHIVED'

def test_assisted_password_recovery_is_scoped(env):
    owner=env
    functions.create_new_user(owner,'staffx','StaffTest123','staff','Staff X')
    assert functions.reset_user_password(owner,2,'NewPass123')
    assert functions.authenticate_user('staffx','NewPass123')['role']=='staff'
    with pytest.raises(functions.RecordGuardError): functions.authenticate_user('staffx','StaffTest123')
