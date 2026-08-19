"""Test harness: every test gets a throwaway SQLite DB, never impera.db."""
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def db_path(monkeypatch):
    """Point app.database at a fresh temp DB with the real schema applied."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    path = Path(path)

    import app.database as database
    monkeypatch.setattr(database, "DB_PATH", path)

    from app.db.migrations import run_migrations
    conn = sqlite3.connect(path)
    try:
        run_migrations(conn)
    finally:
        conn.close()

    yield path
    path.unlink(missing_ok=True)


@pytest.fixture()
def conn(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture()
def client(db_path, monkeypatch):
    """TestClient with an authenticated session, no password typed anywhere."""
    from starlette.testclient import TestClient
    from app.main import app
    import app.deps as deps

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES ('tester', 'x', 'admin')"
    )
    conn.commit()
    user = conn.execute("SELECT id, username, role FROM users WHERE username='tester'").fetchone()
    conn.close()

    # Bypass the session cookie entirely — auth is not what these tests cover.
    # Routers do `from app.deps import get_current_user`, so each module holds
    # its own reference; patch every one that imported it.
    import sys
    monkeypatch.setattr(deps, "get_current_user", lambda request: user)
    for name, mod in list(sys.modules.items()):
        if name.startswith("app.routers") and hasattr(mod, "get_current_user"):
            monkeypatch.setattr(mod, "get_current_user", lambda request: user)

    return TestClient(app)
