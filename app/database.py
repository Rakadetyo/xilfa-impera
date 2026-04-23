import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "impera.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            abstract TEXT DEFAULT '',
            author_id INTEGER NOT NULL,
            status TEXT CHECK(status IN ('draft', 'published')) DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (author_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            display_order INTEGER DEFAULT 0,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    """)

    # Add abstract column if not exists
    cursor.execute("PRAGMA table_info(posts)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'abstract' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN abstract TEXT DEFAULT ''")

    conn.commit()
    conn.close()

def seed_admin():
    from passlib.hash import bcrypt

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cursor.fetchone():
        password_hash = bcrypt.hash("impera123")
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("admin", password_hash)
        )
        conn.commit()

    conn.close()

if __name__ == "__main__":
    init_db()
    seed_admin()
    print("Database initialized!")
