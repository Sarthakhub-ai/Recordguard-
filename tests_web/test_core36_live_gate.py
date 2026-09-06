"""Core36: live PostgreSQL gate is explicit and never silently treated as passed."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_core36_validation_script_requires_live_postgres_configuration():
    text = (ROOT / "scripts" / "final_validation.py").read_text(encoding="utf-8")
    assert "postgres_live_configuration" in text
    assert "BLOCKED" in text
    assert "RECORDGUARD_DATABASE_URL" in text


def test_core36_live_postgres_tests_are_environment_gated():
    text = (ROOT / "tests_web" / "test_live_postgres.py").read_text(encoding="utf-8")
    assert "RECORDGUARD_DATABASE_URL" in text
    assert "pytest.skip" in text or "skip" in text


def test_core36_no_default_postgres_secret_is_committed():
    env_example = (ROOT / ".env.validation.example").read_text(encoding="utf-8")
    assert "replace-with" in env_example
    assert "POSTGRES_PASSWORD=" in env_example
