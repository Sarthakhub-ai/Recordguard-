"""Optional live PostgreSQL integration tests.

Set RECORDGUARD_DATABASE_URL and install psycopg to run these. They skip cleanly
when the live service is unavailable; fake/static tests must never be treated as
proof of live database readiness.
"""
import os
import pytest

DSN = os.getenv("RECORDGUARD_DATABASE_URL")
if DSN:
    psycopg = pytest.importorskip("psycopg")
else:
    psycopg = None

pytestmark = pytest.mark.skipif(not DSN, reason="Set RECORDGUARD_DATABASE_URL for live PostgreSQL integration tests")


def test_live_postgres_connection():
    with psycopg.connect(DSN) as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_live_postgres_transaction_rolls_back():
    with psycopg.connect(DSN) as conn:
        try:
            with conn.transaction():
                conn.execute("CREATE TEMP TABLE rg_tx_test(x integer)")
                conn.execute("INSERT INTO rg_tx_test VALUES (1)")
                raise RuntimeError("intentional rollback")
        except RuntimeError:
            pass
        assert conn.execute("SELECT to_regclass('pg_temp.rg_tx_test')").fetchone()[0] is None
