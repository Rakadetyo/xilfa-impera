import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "impera.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    from app.db.migrations import run_migrations
    conn = get_db()
    run_migrations(conn)
    conn.close()


def seed_admin():
    from app.db.seed import seed_admin as _seed
    _seed()


if __name__ == "__main__":
    init_db()
    seed_admin()
    print("Database initialized!")
