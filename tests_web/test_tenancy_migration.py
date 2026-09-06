import sqlite3


def test_child_tables_have_org_scope_and_backfill(monkeypatch, tmp_path):
    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "tenant.db"))
    database.initialize_database()
    conn = database.get_connection()
    try:
        # Create two organizations through existing Core8 users/patients.
        pw = database.hash_password("StrongPass123")
        conn.execute("INSERT INTO users(username,password_hash,role,full_name,active,organization_id,created_at) VALUES(?,?,?,?,1,?,?)", ("a", pw, "owner", "A", "ORG-A", "2026-09-01T00:00:00"))
        conn.execute("INSERT INTO users(username,password_hash,role,full_name,active,organization_id,created_at) VALUES(?,?,?,?,1,?,?)", ("b", pw, "owner", "B", "ORG-B", "2026-09-01T00:00:00"))
        conn.execute("INSERT INTO patients(patient_id,name,age,sex,registered_by,organization_id,created_at) VALUES(?,?,?,?,?,?,?)", ("RGA00001", "Patient A", 20, "X", "a", "ORG-A", "2026-09-01T00:00:00"))
        conn.execute("INSERT INTO medications(medicine_name) VALUES(?)", ("TestMed",))
        conn.execute("INSERT INTO medication_records(patient_id,medication_id,response_type,record_date) VALUES(?,?,?,?)", ("RGA00001", 1, "OK", "2026-09-01T00:00:00"))
        conn.commit()
    finally:
        conn.close()
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT organization_id FROM medication_records WHERE patient_id='RGA00001'").fetchone()
        assert row["organization_id"] == "ORG-A"
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(medication_records)").fetchall()}
        assert "organization_id" in cols
    finally:
        conn.close()
