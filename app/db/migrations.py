def run_migrations(conn) -> None:
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
            is_video INTEGER DEFAULT 0,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("PRAGMA table_info(post_images)")
    post_img_cols = [row[1] for row in cursor.fetchall()]
    if "is_video" not in post_img_cols:
        cursor.execute("ALTER TABLE post_images ADD COLUMN is_video INTEGER DEFAULT 0")

    cursor.execute("PRAGMA table_info(posts)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'abstract' in columns:
        cursor.execute("ALTER TABLE posts RENAME COLUMN abstract TO summary")
    elif 'summary' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN summary TEXT DEFAULT ''")
    if 'post_type' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN post_type TEXT DEFAULT 'HIGHLIGHT'")
    if 'cover_image_id' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN cover_image_id INTEGER")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS arena (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_name TEXT NOT NULL,
            address TEXT,
            price REAL DEFAULT 0,
            contact_person TEXT,
            map_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("PRAGMA table_info(arena)")
    arena_columns = {row[1] for row in cursor.fetchall()}
    if 'map_url' not in arena_columns:
        cursor.execute("ALTER TABLE arena ADD COLUMN map_url TEXT")

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

    cursor.execute("PRAGMA table_info(users)")
    user_columns = [row[1] for row in cursor.fetchall()]
    if 'role' not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'admin'")
    if 'invite_token' not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN invite_token TEXT")

    cursor.execute("PRAGMA table_info(member)")
    member_columns = [row[1] for row in cursor.fetchall()]
    if 'membership_price' not in member_columns:
        cursor.execute("ALTER TABLE member ADD COLUMN membership_price REAL DEFAULT 0")
    if 'member_period' not in member_columns:
        cursor.execute("ALTER TABLE member ADD COLUMN member_period TEXT")
    if 'games_played' not in member_columns:
        cursor.execute("ALTER TABLE member ADD COLUMN games_played INTEGER DEFAULT 0")

    cursor.execute("""
        DELETE FROM member
        WHERE length(member_period) = 7 AND substr(member_period, 5, 1) = '-'
          AND EXISTS (
              SELECT 1 FROM member m2
              WHERE m2.player_id = member.player_id
                AND m2.member_period = (
                    CASE CAST(substr(member.member_period, 6, 2) AS INTEGER)
                        WHEN 1 THEN 'January' WHEN 2 THEN 'February' WHEN 3 THEN 'March'
                        WHEN 4 THEN 'April' WHEN 5 THEN 'May' WHEN 6 THEN 'June'
                        WHEN 7 THEN 'July' WHEN 8 THEN 'August' WHEN 9 THEN 'September'
                        WHEN 10 THEN 'October' WHEN 11 THEN 'November' WHEN 12 THEN 'December'
                    END || ' ' || substr(member.member_period, 1, 4)
                )
          )
    """)
    cursor.execute("""
        UPDATE member SET member_period =
            CASE CAST(substr(member_period, 6, 2) AS INTEGER)
                WHEN 1 THEN 'January' WHEN 2 THEN 'February' WHEN 3 THEN 'March'
                WHEN 4 THEN 'April' WHEN 5 THEN 'May' WHEN 6 THEN 'June'
                WHEN 7 THEN 'July' WHEN 8 THEN 'August' WHEN 9 THEN 'September'
                WHEN 10 THEN 'October' WHEN 11 THEN 'November' WHEN 12 THEN 'December'
            END || ' ' || substr(member_period, 1, 4)
        WHERE length(member_period) = 7 AND substr(member_period, 5, 1) = '-'
    """)

    cursor.execute("PRAGMA table_info(player)")
    player_columns = {row[1] for row in cursor.fetchall()}
    if 'status' not in player_columns:
        cursor.execute("ALTER TABLE player ADD COLUMN status INTEGER DEFAULT 1")
    if 'notes' not in player_columns:
        cursor.execute("ALTER TABLE player ADD COLUMN notes TEXT DEFAULT ''")
    if 'join_source' not in player_columns:
        cursor.execute("ALTER TABLE player ADD COLUMN join_source TEXT DEFAULT ''")

    cursor.execute("PRAGMA table_info(game)")
    game_columns = {row[1] for row in cursor.fetchall()}
    for col, defn in [
        ('duration_per_game', 'INTEGER DEFAULT 8'),
        ('session_duration', 'INTEGER DEFAULT 120'),
        ('max_players', 'INTEGER DEFAULT 25'),
        ('status', "TEXT DEFAULT 'open'"),
        ('notes', 'TEXT'),
        ('num_teams', 'INTEGER DEFAULT 3'),
        ('players_per_team', 'INTEGER DEFAULT 5'),
        ('skill_weight', 'REAL DEFAULT 0.6'),
        ('schedule_format', "TEXT DEFAULT 'round_robin'"),
        ('best_of', 'INTEGER DEFAULT 1'),
        ('break_time', 'INTEGER DEFAULT 0'),
        ('invite_token', 'TEXT'),
        ('game_name', 'TEXT'),
        ('schedule_template_id', 'INTEGER'),
        ('schedule_template_name', 'TEXT'),
        ('invite_background', "TEXT DEFAULT 'purple'"),
    ]:
        if col not in game_columns:
            cursor.execute(f"ALTER TABLE game ADD COLUMN {col} {defn}")

    cursor.execute("PRAGMA table_info(game_attendee)")
    attendee_columns = {row[1] for row in cursor.fetchall()}
    for col, defn in [
        ('slot_type', "TEXT DEFAULT 'non-member'"),
        ('is_paid', 'INTEGER DEFAULT 0'),
        ('amount_paid', 'REAL DEFAULT 0'),
        ('is_attend', 'INTEGER DEFAULT 0'),
        ('team_id', 'INTEGER'),
        ('locked', 'INTEGER DEFAULT 0'),
    ]:
        if col not in attendee_columns:
            cursor.execute(f"ALTER TABLE game_attendee ADD COLUMN {col} {defn}")

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

    cursor.execute("PRAGMA table_info(partner)")
    partner_cols = {row[1] for row in cursor.fetchall()}
    if "company" not in partner_cols:
        cursor.execute("ALTER TABLE partner ADD COLUMN company TEXT DEFAULT ''")

    cursor.execute("PRAGMA table_info(game_partner)")
    gp_columns = {row[1] for row in cursor.fetchall()}
    if "types" not in gp_columns:
        cursor.execute("ALTER TABLE game_partner ADD COLUMN types TEXT DEFAULT ''")
        cursor.execute("UPDATE game_partner SET types = type WHERE type IS NOT NULL AND type != ''")
    if "partner_id" not in gp_columns:
        cursor.execute("ALTER TABLE game_partner ADD COLUMN partner_id INTEGER")
    if "is_paid" not in gp_columns:
        cursor.execute("ALTER TABLE game_partner ADD COLUMN is_paid INTEGER DEFAULT 0")

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

    cursor.execute("PRAGMA table_info(game_team)")
    team_columns = {row[1] for row in cursor.fetchall()}
    if 'team_color_name' not in team_columns:
        cursor.execute("ALTER TABLE game_team ADD COLUMN team_color_name TEXT")

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

    cursor.execute("PRAGMA table_info(game_match)")
    match_columns = {row[1] for row in cursor.fetchall()}
    for col, defn in [
        ('bracket_slot', 'TEXT'),
        ('next_match_id', 'INTEGER'),
        ('is_tbd', 'INTEGER DEFAULT 0'),
    ]:
        if match_columns and col not in match_columns:
            cursor.execute(f"ALTER TABLE game_match ADD COLUMN {col} {defn}")


    cursor.execute("PRAGMA table_info(game_player_stat)")
    gps_cols = {row[1] for row in cursor.fetchall()}
    if gps_cols and 'match_id' not in gps_cols:
        cursor.execute("DROP TABLE game_player_stat")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_player_stat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            team_id INTEGER,
            points INTEGER DEFAULT 0,
            rebounds INTEGER DEFAULT 0,
            assists INTEGER DEFAULT 0,
            steals INTEGER DEFAULT 0,
            blocks INTEGER DEFAULT 0,
            turnovers INTEGER DEFAULT 0,
            fouls INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES game(id) ON DELETE CASCADE,
            FOREIGN KEY (match_id) REFERENCES game_match(id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES player(id),
            FOREIGN KEY (team_id) REFERENCES game_team(id),
            UNIQUE(match_id, player_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_asset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            game_partner_id INTEGER,
            type TEXT NOT NULL DEFAULT 'video',
            url TEXT NOT NULL,
            label TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES game(id) ON DELETE CASCADE,
            FOREIGN KEY (game_partner_id) REFERENCES game_partner(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_rating (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            game_attendee_id INTEGER,
            player_id INTEGER NOT NULL,
            is_anonymous INTEGER DEFAULT 0,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            great_things TEXT DEFAULT '',
            could_be_improved TEXT DEFAULT '',
            feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES game(id) ON DELETE CASCADE,
            FOREIGN KEY (game_attendee_id) REFERENCES game_attendee(id) ON DELETE SET NULL,
            FOREIGN KEY (player_id) REFERENCES player(id),
            UNIQUE (game_attendee_id),
            UNIQUE (game_id, player_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_finance_entry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            label TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES game(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedule_template (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            team_count INTEGER NOT NULL,
            duration_per_game INTEGER NOT NULL DEFAULT 8,
            break_time INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedule_template_match (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL,
            match_order INTEGER NOT NULL,
            round_number INTEGER,
            home_ordinal INTEGER,
            away_ordinal INTEGER,
            is_tbd INTEGER DEFAULT 0,
            has_time INTEGER DEFAULT 1,
            FOREIGN KEY (template_id) REFERENCES schedule_template(id) ON DELETE CASCADE
        )
    """)

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
            ('homepage', 'about', 'body', "Impera is a basketball community rooted in BSD-Gading Serpong. We bring together players of all levels who share a love for the game. No politics, no drama — just ball. Whether you're seasoned or just starting, you're welcome on our court."),
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
            defaults,
        )

    conn.commit()
