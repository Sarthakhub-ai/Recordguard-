from pathlib import Path


def test_destructive_api_requires_delete_confirmation():
    text = (Path(__file__).parents[1] / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    assert text.count('payload.confirmation != "DELETE"') >= 4
    assert 'Current password is required.' in text


def test_postgres_rejects_legacy_integer_uuid_links():
    text = (Path(__file__).parents[1] / "backend" / "repositories" / "postgres.py").read_text(encoding="utf-8")
    assert 'must be a PostgreSQL UUID when using the PostgreSQL API' in text
    assert 'UUID(str(value))' in text


def test_postgres_attachment_upload_is_not_prechecked_by_sqlite():
    text = (Path(__file__).parents[1] / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    route = text[text.index('def upload_attachment'):text.index('@app.get("/openapi-contract")')]
    assert 'if data_repository is None:' in route
    assert '_handle(functions.get_patient_by_id' in route
    assert 'else:\n        _handle(data_repository.get_patient' in route


def test_attachment_request_is_size_limited_before_repository_storage():
    text = (Path(__file__).parents[1] / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    assert 'max_size = 20 * 1024 * 1024' in text
    assert 'status_code=413' in text
    assert 'total > max_size' in text


def test_postgres_core15_operations_are_tenant_scoped():
    text = (Path(__file__).parents[1] / "backend" / "repositories" / "postgres.py").read_text(encoding="utf-8")
    for marker in (
        'WHERE organization_id=%s AND request_id=%s',
        'WHERE organization_id=%s AND grant_id=%s',
        'WHERE organization_id=%s AND share_id=%s',
        'WHERE organization_id=%s AND record_id=%s',
    ):
        assert marker in text
