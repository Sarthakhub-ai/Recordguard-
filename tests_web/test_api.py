import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def api_client(monkeypatch):
    # These API tests are SQLite-isolated even when the release-validation shell
    # has PostgreSQL configured in its environment.
    monkeypatch.setenv('RECORDGUARD_SESSION_BACKEND', 'sqlite')
    monkeypatch.delenv('RECORDGUARD_DATABASE_URL', raising=False)
    import database
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(database, "DB_PATH", str(Path(td) / "test.db"))
        database.initialize_database()
        import backend.api as api
        database.initialize_database()
        from backend.repositories.sqlite import SQLiteSessionRepository
        api.sessions = SQLiteSessionRepository()
        yield TestClient(api.app)


def test_health(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_owner_setup_and_auth_response_never_contains_password_hash(api_client):
    r = api_client.post("/auth/owner/setup", json={"username":"owner1","password":"StrongPass123","full_name":"Owner"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert "password_hash" not in body["user"]
    assert "organization_id" in body["user"]

    me = api_client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert "password_hash" not in me.json()["user"]


def test_second_owner_setup_is_rejected(api_client):
    first = {"username":"owner1","password":"StrongPass123","full_name":"Owner"}
    assert api_client.post("/auth/owner/setup", json=first).status_code == 200
    second = {"username":"owner2","password":"StrongPass123","full_name":"Owner 2"}
    assert api_client.post("/auth/owner/setup", json=second).status_code == 409


def test_web_login_uses_cookie_and_does_not_expose_bearer_token(api_client):
    setup = api_client.post("/auth/owner/setup", json={"username":"webowner","password":"StrongPass123","full_name":"Web Owner"})
    assert setup.status_code == 200
    r = api_client.post("/auth/login", json={"username":"webowner","password":"StrongPass123","client":"web"})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"] is None
    assert any("rg_session=" in value for value in r.headers.get_list("set-cookie"))
    me = api_client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "webowner"
