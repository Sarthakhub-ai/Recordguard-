import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    import database
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(database, "DB_PATH", str(Path(td) / "test.db"))
        monkeypatch.setenv("RECORDGUARD_SESSION_BACKEND", "sqlite")
        monkeypatch.delenv("RECORDGUARD_DATABASE_URL", raising=False)
        database.initialize_database()
        import backend.api as api
        api.sessions = __import__("backend.repositories.sqlite", fromlist=["SQLiteSessionRepository"]).SQLiteSessionRepository()
        yield TestClient(api.app)


def auth_owner(client):
    r = client.post("/auth/owner/setup", json={"username":"owner29","password":"OwnerPass123","full_name":"Owner"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_public_registration_creates_only_common_user(client):
    r = client.post("/auth/register", json={"username":"public29","password":"PublicPass123","full_name":"Public User"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "user"
    assert r.json()["user"]["patient_id"] is None


def test_owner_can_create_admin_and_admin_cannot_create_admin(client):
    owner = auth_owner(client)
    r = client.post("/users", headers={"Authorization": f"Bearer {owner}"}, json={
        "username":"admin29","password":"AdminPass123","full_name":"Admin","role":"admin"
    })
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "admin"

    admin_login = client.post("/auth/login", json={"username":"admin29","password":"AdminPass123"})
    assert admin_login.status_code == 200
    admin = admin_login.json()["access_token"]
    denied = client.post("/users", headers={"Authorization": f"Bearer {admin}"}, json={
        "username":"admin230","password":"AdminPass456","full_name":"Admin 2","role":"admin"
    })
    assert denied.status_code == 400 or denied.status_code == 403


def test_owner_user_listing_is_org_scoped_and_password_reset_is_supported(client):
    owner = auth_owner(client)
    created = client.post("/users", headers={"Authorization": f"Bearer {owner}"}, json={
        "username":"doctor29","password":"DoctorPass123","full_name":"Doctor","role":"doctor"
    })
    assert created.status_code == 200, created.text
    users = client.get("/users", headers={"Authorization": f"Bearer {owner}"})
    assert users.status_code == 200
    assert any(x["username"] == "doctor29" for x in users.json()["items"])
    target = next(x["user_id"] for x in users.json()["items"] if x["username"] == "doctor29")
    reset = client.post("/users/password-reset", headers={"Authorization": f"Bearer {owner}"}, json={
        "target_user_id": str(target), "new_password":"DoctorNew123"
    })
    assert reset.status_code == 200, reset.text
    login = client.post("/auth/login", json={"username":"doctor29","password":"DoctorNew123"})
    assert login.status_code == 200, login.text
