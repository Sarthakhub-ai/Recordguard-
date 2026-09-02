from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_core28_release_gate_artifacts_exist():
    for rel in ("PRODUCTION_READINESS.md", "scripts/release_readiness.py"):
        assert (ROOT / rel).is_file()


def test_ci_runs_live_postgres_web_build_and_dependency_scan():
    ci = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
    assert "RECORDGUARD_SESSION_BACKEND: postgres" in ci
    assert "npm install" in ci
    assert "npm run build" in ci
    assert "pip-audit" in ci


def test_release_gate_is_conservative_about_production_defaults():
    script = (ROOT / "scripts/release_readiness.py").read_text(encoding="utf-8")
    assert 'backend == "postgres"' in script
    assert 'RECORDGUARD_DATABASE_URL' in script
    assert 'RECORDGUARD_WEB_ORIGINS' in script
