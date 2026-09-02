import sqlite3
import database


def test_connection_uses_busy_timeout_and_foreign_keys(tmp_path, monkeypatch):
    db = tmp_path / "engineering.db"
    monkeypatch.setattr(database, "DB_PATH", str(db))
    conn = database.get_connection()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 10000
    finally:
        conn.close()


def test_transaction_commits_and_rolls_back(tmp_path, monkeypatch):
    db = tmp_path / "transaction.db"
    monkeypatch.setattr(database, "DB_PATH", str(db))
    conn = database.get_connection()
    conn.execute("CREATE TABLE sample (value TEXT)")
    conn.commit()
    conn.close()

    with database.transaction() as conn:
        conn.execute("INSERT INTO sample(value) VALUES (?)", ("committed",))

    with sqlite3.connect(db) as check:
        assert check.execute("SELECT value FROM sample").fetchone()[0] == "committed"

    try:
        with database.transaction() as conn:
            conn.execute("INSERT INTO sample(value) VALUES (?)", ("rolled-back",))
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    with sqlite3.connect(db) as check:
        values = [r[0] for r in check.execute("SELECT value FROM sample").fetchall()]
        assert values == ["committed"]
