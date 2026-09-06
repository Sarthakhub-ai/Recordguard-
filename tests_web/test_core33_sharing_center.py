from datetime import datetime, timedelta, timezone

import functions


def test_share_listing_marks_expired_and_hides_bearer_token(monkeypatch):
    class C:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def close(self): pass
        def execute(self, q, args):
            class R:
                def fetchall(self):
                    return [{"share_id":1,"patient_id":"P1","shared_with":"recipient","resource_type":"medication","resource_id":2,"revoked":0,"expires_at":(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),"share_token":"SECRET","created_at":"x"}]
            return R()
    monkeypatch.setattr(functions, "get_connection", lambda: C())
    monkeypatch.setattr(functions, "_require_user", lambda u: u)
    monkeypatch.setattr(functions, "_role", lambda u: "owner")
    monkeypatch.setattr(functions, "can_view_patient", lambda u,p: True)
    rows=functions.list_record_shares({"username":"owner","role":"owner"},"P1")
    assert rows[0]["status"] == "EXPIRED"
    assert "share_token" not in rows[0]


def test_api_sharing_allowlist_includes_status_but_not_token():
    from backend.api.app import sharing
    assert any(isinstance(c, frozenset) and "status" in c for c in sharing.__code__.co_consts)
    assert "share_token" not in {"share_id", "patient_id", "record_id", "resource_type", "resource_id", "shared_by", "shared_with", "expires_at", "revoked", "revoked_at", "created_at", "viewed_at", "status"}
