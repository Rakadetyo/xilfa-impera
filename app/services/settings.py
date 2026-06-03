from app.database import get_db


def get_setting(page: str, section: str, key: str, default: str = "") -> str:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM site_settings WHERE page = ? AND section = ? AND key = ?",
        (page, section, key),
    )
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default


def get_page_settings(page: str) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT section, key, value FROM site_settings WHERE page = ?",
        (page,),
    )
    rows = cursor.fetchall()
    conn.close()
    settings: dict = {}
    for row in rows:
        if row["section"] not in settings:
            settings[row["section"]] = {}
        settings[row["section"]][row["key"]] = row["value"]
    return settings


def set_setting(page: str, section: str, key: str, value: str) -> None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO site_settings (page, section, key, value) VALUES (?, ?, ?, ?)
           ON CONFLICT(page, section, key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
        (page, section, key, value),
    )
    conn.commit()
    conn.close()
