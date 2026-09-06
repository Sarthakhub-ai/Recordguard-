from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parents[1]


def _repository_methods():
    repository_path = ROOT / "backend" / "repositories" / "postgres.py"
    source = repository_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    methods = set()

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "PostgreSQLRepository":
            methods.update(
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )

    methods.update(
        re.findall(
            r"PostgreSQLRepository\.([A-Za-z_]\w*)\s*=",
            source,
        )
    )

    return methods


def test_core35_api_repository_calls_are_bound():
    api = (
        ROOT / "backend" / "api" / "app.py"
    ).read_text(encoding="utf-8")

    calls = set(re.findall(r"data_repository\.([A-Za-z_]\w*)", api))
    missing = sorted(calls - _repository_methods())

    assert not missing, (
        "PostgreSQL repository methods missing from API surface: "
        f"{missing}"
    )


def test_core35_utf8_reads_are_explicit():
    ux = (
        ROOT / "tests_web" / "test_core26_ux.py"
    ).read_text(encoding="utf-8")

    assert 'core_ui.py").read_text(encoding="utf-8")' in ux


def test_core35_clinic_routes_use_postgres_repository_when_enabled():
    api = (
        ROOT / "backend" / "api" / "app.py"
    ).read_text(encoding="utf-8")

    for method in (
        "list_user_clinics",
        "assign_user_to_clinic",
        "list_patient_clinics",
        "assign_patient_to_clinic",
    ):
        assert f"data_repository.{method}" in api


def test_core35_clinic_role_check_uses_normalized_role_value():
    repo = (
        ROOT / "backend" / "repositories" / "postgres.py"
    ).read_text(encoding="utf-8")

    assert 'if _pg_role(actor) not in {"owner", "admin"}:' in repo


def test_core35_repository_contains_clinic_status_and_assignment_methods():
    repo = (
        ROOT / "backend" / "repositories" / "postgres.py"
    ).read_text(encoding="utf-8")

    for method in (
        "create_clinic",
        "list_clinics",
        "set_clinic_status",
        "assign_user_to_clinic",
        "list_user_clinics",
        "assign_patient_to_clinic",
        "list_patient_clinics",
    ):
        assert f"PostgreSQLRepository.{method} =" in repo or f"def {method}(" in repo


def test_core35_clinic_repository_queries_are_organization_scoped():
    repo = (
        ROOT / "backend" / "repositories" / "postgres.py"
    ).read_text(encoding="utf-8")

    assert "WHERE organization_id=%s AND clinic_id=%s" in repo
    assert "organization_id,user_id,clinic_id" in repo
    assert "organization_id,patient_id,clinic_id" in repo
