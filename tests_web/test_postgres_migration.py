from pathlib import Path


def test_postgres_migration_is_idempotent_and_tenant_scoped():
    sql = (Path(__file__).resolve().parents[1] / "database" / "migrations" / "001_recordguard_web.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS organizations" in sql
    assert "CREATE TABLE IF NOT EXISTS patients" in sql
    assert "organization_id uuid NOT NULL REFERENCES organizations" in sql
    assert "CREATE TABLE IF NOT EXISTS audit_events" in sql
    assert "CREATE TABLE IF NOT EXISTS api_sessions" in sql
    assert "IF NOT EXISTS (" in sql and "users_patient_fk" in sql
    # Every tenant-owned clinical table must carry an organization scope.
    for table in ("patients", "encounters", "prescriptions", "medication_records",
                  "attachments", "record_shares", "family_relationships",
                  "family_access_grants", "audit_events"):
        marker = f"CREATE TABLE IF NOT EXISTS {table}"
        start = sql.index(marker)
        end = sql.find("CREATE TABLE IF NOT EXISTS", start + len(marker))
        block = sql[start:] if end == -1 else sql[start:end]
        assert "organization_id" in block, table
