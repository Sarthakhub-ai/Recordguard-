from pathlib import Path


def test_core15_repository_contains_shared_operations():
    text = (Path(__file__).parents[1] / "backend" / "repositories" / "postgres.py").read_text(encoding="utf-8")
    for name in ("request_patient_link", "review_patient_link_request", "create_family_relationship",
                 "grant_family_access", "create_record_shares_batch", "revoke_record_share",
                 "lifecycle_medication", "lifecycle_ehr", "add_attachment", "list_attachments"):
        assert name in text
    assert "organization_id=%s" in text
    assert "token_hash" in text


def test_audit_schema_is_append_only():
    text = (Path(__file__).parents[1] / "database" / "migrations" / "001_recordguard_web.sql").read_text(encoding="utf-8")
    assert "audit_events is append-only" in text
    assert "BEFORE UPDATE OR DELETE ON audit_events" in text


def test_api_routes_to_repository_for_core15_operations(monkeypatch):
    import importlib
    api = importlib.import_module("backend.api.app")
    from fastapi.testclient import TestClient

    owner = {"user_id":"u1","username":"owner","role":"owner","organization_id":"org1","active":True,"patient_id":None}
    calls=[]
    class Sessions:
        def get_session_user(self, token): return owner if token == "t" else None
    class Repo:
        def list_record_shares(self,*a): calls.append("shares:list"); return []
        def create_record_shares_batch(self,*a): calls.append("shares:create"); return [{"share_id":"s","token":"secret"}]
        def revoke_record_share(self,*a): calls.append("shares:revoke")
        def list_family_relationships(self,*a): calls.append("family:list"); return []
        def create_family_relationship(self,*a): calls.append("family:create"); return "r"
        def list_family_access(self,*a): calls.append("family:access:list"); return []
        def grant_family_access(self,*a): calls.append("family:grant"); return "g"
        def revoke_family_access(self,*a): calls.append("family:revoke")
        def list_patient_link_requests(self,*a): calls.append("links:list"); return []
        def request_patient_link(self,*a): calls.append("links:request"); return "lr"
        def review_patient_link_request(self,*a): calls.append("links:review")
        def list_attachments(self,*a): calls.append("attachments:list"); return []
        def add_attachment(self,*a): calls.append("attachments:add"); return "a"
        def lifecycle_medication(self,*a): calls.append("med:lifecycle"); return True
        def lifecycle_ehr(self,*a): calls.append("ehr:lifecycle"); return True
    monkeypatch.setattr(api,"sessions",Sessions()); monkeypatch.setattr(api,"data_repository",Repo())
    c=TestClient(api.app); h={"Authorization":"Bearer t"}
    assert c.get('/sharing',params={'patient_id':'RG00001'},headers=h).status_code == 200
    assert c.post('/sharing',headers=h,json={'patient_id':'RG00001','record_id':'r1','shared_with':'x','resource_type':'medication'}).status_code == 200
    assert c.post('/sharing/revoke',headers=h,json={'share_id':'s'}).status_code == 200
    assert c.get('/family/relationships',params={'patient_id':'RG00001'},headers=h).status_code == 200
    assert c.post('/family/relationships',headers=h,json={'patient_id':'RG00001','related_patient_id':'RG00002','relationship_type':'sibling'}).status_code == 200
    assert c.get('/family/access',params={'patient_id':'RG00001'},headers=h).status_code == 200
    assert c.post('/family/access',headers=h,json={'patient_id':'RG00001','grantee_user_id':'u2','resource_type':'ehr','permission':'view'}).status_code == 200
    assert c.post('/family/access/revoke',headers=h,json={'grant_id':'g'}).status_code == 200
    assert c.get('/patient-links',headers=h).status_code == 200
    assert c.get('/patients/RG00001/attachments',headers=h).status_code == 200
    assert c.post('/medications/r1/archive',headers=h).status_code == 200
    assert c.post('/ehr/encounter/e1/archive',headers=h).status_code == 200
    assert {'shares:list','shares:create','shares:revoke','family:list','family:create','family:access:list','family:grant','family:revoke','links:list','attachments:list','med:lifecycle','ehr:lifecycle'} <= set(calls)
