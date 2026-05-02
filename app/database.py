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

    # === GAME EXPANSION MIGRATIONS ===
    # game: add new columns
    cursor.execute("PRAGMA table_info(game)")
    game_columns = {row[1] for row in cursor.fetchall()}
    if 'duration_per_game' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN duration_per_game INTEGER DEFAULT 8")
    if 'session_duration' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN session_duration INTEGER DEFAULT 120")
    if 'max_players' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN max_players INTEGER DEFAULT 25")
    if 'status' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN status TEXT DEFAULT 'open'")
    if 'notes' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN notes TEXT")
    if 'num_teams' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN num_teams INTEGER DEFAULT 3")
    if 'players_per_team' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN players_per_team INTEGER DEFAULT 5")
    if 'skill_weight' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN skill_weight REAL DEFAULT 0.6")
    if 'schedule_format' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN schedule_format TEXT DEFAULT 'round_robin'")
    if 'best_of' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN best_of INTEGER DEFAULT 1")
    if 'break_time' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN break_time INTEGER DEFAULT 0")
    if 'invite_token' not in game_columns:
        cursor.execute("ALTER TABLE game ADD COLUMN invite_token TEXT")

    # game_attendee: add new columns
    cursor.execute("PRAGMA table_info(game_attendee)")
    attendee_columns = {row[1] for row in cursor.fetchall()}
    if 'slot_type' not in attendee_columns:
        cursor.execute("ALTER TABLE game_attendee ADD COLUMN slot_type TEXT DEFAULT 'regular'")
    if 'is_paid' not in attendee_columns:
        cursor.execute("ALTER TABLE game_attendee ADD COLUMN is_paid INTEGER DEFAULT 0")
    if 'amount_paid' not in attendee_columns:
        cursor.execute("ALTER TABLE game_attendee ADD COLUMN amount_paid REAL DEFAULT 0")
    if 'is_attend' not in attendee_columns:
        cursor.execute("ALTER TABLE game_attendee ADD COLUMN is_attend INTEGER DEFAULT 0")
    if 'team_id' not in attendee_columns:
        cursor.execute("ALTER TABLE game_attendee ADD COLUMN team_id INTEGER")
    if 'locked' not in attendee_columns:
        cursor.execute("ALTER TABLE game_attendee ADD COLUMN locked INTEGER DEFAULT 0")

    # game_match: add new columns
    cursor.execute("PRAGMA table_info(game_match)")
    match_columns = {row[1] for row in cursor.fetchall()}
    if 'bracket_slot' not in match_columns:
        cursor.execute("ALTER TABLE game_match ADD COLUMN bracket_slot TEXT")
    if 'next_match_id' not in match_columns:
        cursor.execute("ALTER TABLE game_match ADD COLUMN next_match_id INTEGER")
    if 'is_tbd' not in match_columns:
        cursor.execute("ALTER TABLE game_match ADD COLUMN is_tbd INTEGER DEFAULT 0")

    # game_player_group: groups of players that always stay on the same team
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_player_group (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES game(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_player_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            UNIQUE(group_id, player_id),
            FOREIGN KEY (group_id) REFERENCES game_player_group(id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES player(id)
        )
    """)

    # game_partner: referee/videographer/photographer/sponsor tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_partner (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            name TEXT,
            contact TEXT,
            fee REAL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES game(id) ON DELETE CASCADE
        )
    """)

    # Master partner registry
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS partner (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            types TEXT DEFAULT '',
            contact TEXT,
            social_media TEXT,
            default_fee REAL DEFAULT 0,
            internal_rating INTEGER DEFAULT 0,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add company column to partner if not exists
    cursor.execute("PRAGMA table_info(partner)")
    partner_cols = {row[1] for row in cursor.fetchall()}
    if "company" not in partner_cols:
        cursor.execute("ALTER TABLE partner ADD COLUMN company TEXT DEFAULT ''")

    # Migrate game_partner with new columns
    cursor.execute("PRAGMA table_info(game_partner)")
    gp_columns = {row[1] for row in cursor.fetchall()}

    if "types" not in gp_columns:
        cursor.execute("ALTER TABLE game_partner ADD COLUMN types TEXT DEFAULT ''")
        cursor.execute("UPDATE game_partner SET types = type WHERE type IS NOT NULL AND type != ''")

    if "partner_id" not in gp_columns:
        cursor.execute("ALTER TABLE game_partner ADD COLUMN partner_id INTEGER")

    if "is_paid" not in gp_columns:
        cursor.execute("ALTER TABLE game_partner ADD COLUMN is_paid INTEGER DEFAULT 0")

    # game_team: teams within a game
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_team (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            team_color TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES game(id) ON DELETE CASCADE
        )
    """)

    # Add team_color_name column to game_team
    cursor.execute("PRAGMA table_info(game_team)")
    team_columns = {row[1] for row in cursor.fetchall()}
    if 'team_color_name' not in team_columns:
        cursor.execute("ALTER TABLE game_team ADD COLUMN team_color_name TEXT")

    # game_match: scheduled matches within a game
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_match (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            round_number INTEGER,
            match_order INTEGER,
            team_home_id INTEGER,
            team_away_id INTEGER,
            court_label TEXT,
            scheduled_start TEXT,
            type TEXT DEFAULT 'round_robin',
            score_home INTEGER,
            score_away INTEGER,
            winner_team_id INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES game(id) ON DELETE CASCADE,
            FOREIGN KEY (team_home_id) REFERENCES game_team(id),
            FOREIGN KEY (team_away_id) REFERENCES game_team(id),
            FOREIGN KEY (winner_team_id) REFERENCES game_team(id)
        )
    """)

    # site_settings: key-value config for pages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS site_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page TEXT NOT NULL,
            section TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(page, section, key)
        )
    """)

    # Insert default homepage settings if not exists
    cursor.execute("SELECT COUNT(*) FROM site_settings WHERE page = 'homepage'")
    if cursor.fetchone()[0] == 0:
        defaults = [
            ('homepage', 'hero', 'youtube_video_id', 'rBW1uZnZhbo'),
            ('homepage', 'hero', 'headline', 'IMPERA'),
            ('homepage', 'hero', 'tagline', 'BSD — Gading Serpong'),
            ('homepage', 'hero', 'subtitle', 'Basketball community. Every Saturday at 18:00. Show up, compete, grow.'),
            ('homepage', 'hero', 'cta_primary_text', 'Play With Us'),
            ('homepage', 'hero', 'cta_primary_link', '#schedule'),
            ('homepage', 'hero', 'cta_secondary_text', 'Learn More'),
            ('homepage', 'hero', 'cta_secondary_link', '#about'),
            ('homepage', 'hero', 'logo', '/assets/impera-logo-only-white.png'),
            ('homepage', 'about', 'title', 'Built for Those Who Play.'),
            ('homepage', 'about', 'body', 'Impera is a basketball community rooted in BSD-Gading Serpong. We bring together players of all levels who share a love for the game. No politics, no drama — just ball. Whether you\'re seasoned or just starting, you\'re welcome on our court.'),
            ('homepage', 'about', 'stat_1_label', 'Members'),
            ('homepage', 'about', 'stat_1_value', '90+'),
            ('homepage', 'about', 'stat_2_label', 'Sessions'),
            ('homepage', 'about', 'stat_2_value', '100+'),
            ('homepage', 'about', 'stat_3_label', 'Home Court'),
            ('homepage', 'about', 'stat_3_value', 'Jetz'),
            ('homepage', 'about', 'stat_4_label', 'Every Week'),
            ('homepage', 'about', 'stat_4_value', 'SAT'),
            ('homepage', 'schedule', 'day', 'Saturday'),
            ('homepage', 'schedule', 'time', '18:00'),
            ('homepage', 'schedule', 'location', 'BSD — Gading Serpong Area'),
            ('homepage', 'social', 'instagram', 'https://www.instagram.com/imperabasketball/'),
            ('homepage', 'social', 'whatsapp', ''),
            ('homepage', 'social', 'reclub', 'https://reclub.co/clubs/@impera'),
        ]
        cursor.executemany(
            "INSERT INTO site_settings (page, section, key, value) VALUES (?, ?, ?, ?)",
            defaults
        )

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

    # Migration: populate member_period from member_start_date
    cursor.execute("SELECT COUNT(*) as cnt FROM member WHERE member_period IS NULL OR member_period = ''")
    if cursor.fetchone()["cnt"] > 0:
        cursor.execute("""
            UPDATE member SET member_period =
                CASE CAST(substr(member_start_date, 6, 2) AS INTEGER)
                    WHEN 1 THEN 'January'
                    WHEN 2 THEN 'February'
                    WHEN 3 THEN 'March'
                    WHEN 4 THEN 'April'
                    WHEN 5 THEN 'May'
                    WHEN 6 THEN 'June'
                    WHEN 7 THEN 'July'
                    WHEN 8 THEN 'August'
                    WHEN 9 THEN 'September'
                    WHEN 10 THEN 'October'
                    WHEN 11 THEN 'November'
                    WHEN 12 THEN 'December'
                END || ' ' || substr(member_start_date, 1, 4)
            WHERE (member_period IS NULL OR member_period = '') AND member_start_date IS NOT NULL
        """)
        conn.commit()

    conn.close()

if __name__ == "__main__":
    init_db()
    seed_admin()
    print("Database initialized!")
