from app.database import get_db


def seed_admin() -> None:
    import bcrypt

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cursor.fetchone():
        password_hash = bcrypt.hashpw(b"impera123", bcrypt.gensalt()).decode()
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("admin", password_hash),
        )
        conn.commit()

    cursor.execute("SELECT COUNT(*) as cnt FROM member WHERE member_period IS NULL OR member_period = ''")
    if cursor.fetchone()["cnt"] > 0:
        cursor.execute("""
            UPDATE member SET member_period =
                CASE CAST(substr(member_start_date, 6, 2) AS INTEGER)
                    WHEN 1 THEN 'January' WHEN 2 THEN 'February' WHEN 3 THEN 'March'
                    WHEN 4 THEN 'April' WHEN 5 THEN 'May' WHEN 6 THEN 'June'
                    WHEN 7 THEN 'July' WHEN 8 THEN 'August' WHEN 9 THEN 'September'
                    WHEN 10 THEN 'October' WHEN 11 THEN 'November' WHEN 12 THEN 'December'
                END || ' ' || substr(member_start_date, 1, 4)
            WHERE (member_period IS NULL OR member_period = '') AND member_start_date IS NOT NULL
        """)
        conn.commit()

    conn.close()
