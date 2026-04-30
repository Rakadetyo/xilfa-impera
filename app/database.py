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
            summary TEXT DEFAULT '',
            post_type TEXT DEFAULT 'HIGHLIGHT',
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

    # Add summary column if not exists (renamed from abstract)
    cursor.execute("PRAGMA table_info(posts)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'abstract' in columns:
        cursor.execute("ALTER TABLE posts RENAME COLUMN abstract TO summary")
    elif 'summary' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN summary TEXT DEFAULT ''")

    # Add post_type column if not exists
    if 'post_type' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN post_type TEXT DEFAULT 'HIGHLIGHT'")

    # New tables for arena/game/player/member system

    # arena: venues for games
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS arena (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_name TEXT NOT NULL,
            address TEXT,
            price REAL DEFAULT 0,
            contact_person TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # game: each session
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datetime TIMESTAMP NOT NULL,
            arena_id INTEGER,
            is_video INTEGER DEFAULT 0,
            is_photo INTEGER DEFAULT 0,
            is_referee INTEGER DEFAULT 0,
            price_per_person REAL DEFAULT 0,
            price_per_member REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (arena_id) REFERENCES arena(id)
        )
    """)

    # player: member profiles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            nickname TEXT,
            position_1 TEXT,
            position_2 TEXT,
            skill_level INTEGER CHECK(skill_level BETWEEN 1 AND 5) DEFAULT 3,
            is_member INTEGER DEFAULT 0,
            contact_no TEXT,
            instagram TEXT,
            reclub TEXT,
            join_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # member: membership status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            member_period TEXT NOT NULL,
            member_start_date DATE,
            member_end_date DATE,
            is_paid INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES player(id),
            UNIQUE(player_id, member_period)
        )
    """)

    # game_attendee: who played which game
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_attendee (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            team_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES game(id),
            FOREIGN KEY (player_id) REFERENCES player(id)
        )
    """)

    # changelog: audit log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Add role column to users if not exists
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [row[1] for row in cursor.fetchall()]
    if 'role' not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'admin'")

    # Add membership_price to member if not exists
    cursor.execute("PRAGMA table_info(member)")
    member_columns = [row[1] for row in cursor.fetchall()]
    if 'membership_price' not in member_columns:
        cursor.execute("ALTER TABLE member ADD COLUMN membership_price REAL DEFAULT 0")

    # Add member_period column if not exists
    if 'member_period' not in member_columns:
        cursor.execute("ALTER TABLE member ADD COLUMN member_period TEXT")

    # Add status column to player if not exists
    cursor.execute("PRAGMA table_info(player)")
    player_columns = {row[1] for row in cursor.fetchall()}
    if 'status' not in player_columns:
        cursor.execute("ALTER TABLE player ADD COLUMN status INTEGER DEFAULT 1")

    conn.commit()
    conn.close()

def seed_admin():
    import bcrypt

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cursor.fetchone():
        password_hash = bcrypt.hashpw(b"impera123", bcrypt.gensalt()).decode()
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
