"""Saved schedule formats.

A template is an ordered list of fixtures expressed as team *ordinals* plus the
session cadence. Ordinal N resolves to the Nth team of the target game, ordered
by game_team.id — so the same template produces the same fixture structure for
any game with a matching team count, while each game keeps its own rosters,
team names and colours.

A NULL ordinal is "Pickup / Free" — a deliberate state, not a missing team.

Templates are a stamp, not a live link: applying one copies rows into
game_match, so editing or deleting a template never changes a game that
already used it.

Foreign keys are not enforced (PRAGMA foreign_keys = 0), so dependent rows are
always deleted explicitly.
"""


def team_ids_in_order(cursor, game_id: int) -> list:
    """The game's teams by id — the order ordinals are resolved against."""
    cursor.execute("SELECT id FROM game_team WHERE game_id = ? ORDER BY id", (game_id,))
    return [r["id"] for r in cursor.fetchall()]


def list_templates(cursor, team_count: int = None) -> list:
    """All templates, newest first, annotated for the format dropdown."""
    cursor.execute("""
        SELECT st.*, u.username AS created_by_name,
               (SELECT COUNT(*) FROM schedule_template_match m
                WHERE m.template_id = st.id) AS match_count
        FROM schedule_template st
        LEFT JOIN users u ON st.created_by = u.id
        ORDER BY st.name
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    for r in rows:
        r["usable"] = team_count is None or r["team_count"] == team_count
        r["reason"] = (
            "" if r["usable"]
            else f"needs {r['team_count']} teams, you have {team_count}"
        )
    return rows


def find_by_name(cursor, name: str):
    cursor.execute("SELECT * FROM schedule_template WHERE name = ?", (name.strip(),))
    return cursor.fetchone()


def can_modify(template, user) -> bool:
    """Creator or superadmin, matching the app's ownership model."""
    if not user or not template:
        return False
    u = dict(user)
    return u.get("role") == "superadmin" or template["created_by"] == u["id"]


def delete_template(cursor, template_id: int) -> None:
    """ON DELETE CASCADE is decorative here — remove match rows by hand."""
    cursor.execute("DELETE FROM schedule_template_match WHERE template_id = ?", (template_id,))
    cursor.execute("DELETE FROM schedule_template WHERE id = ?", (template_id,))


def save_template(cursor, game_id: int, name: str, user_id: int, match_ids: list) -> int:
    """Snapshot a game's schedule as a named template.

    `match_ids` is the on-screen row order, so what gets saved is what the user
    is looking at rather than what was last persisted.
    """
    name = name.strip()
    team_ids = team_ids_in_order(cursor, game_id)
    ordinal_of = {tid: i + 1 for i, tid in enumerate(team_ids)}

    cursor.execute(
        "SELECT duration_per_game, break_time FROM game WHERE id = ?", (game_id,))
    game = cursor.fetchone()

    existing = find_by_name(cursor, name)
    if existing:
        template_id = existing["id"]
        cursor.execute(
            "DELETE FROM schedule_template_match WHERE template_id = ?", (template_id,))
        cursor.execute(
            """UPDATE schedule_template SET team_count = ?, duration_per_game = ?,
               break_time = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (len(team_ids), game["duration_per_game"] or 8, game["break_time"] or 0, template_id))
    else:
        cursor.execute(
            """INSERT INTO schedule_template
               (name, team_count, duration_per_game, break_time, created_by)
               VALUES (?, ?, ?, ?, ?)""",
            (name, len(team_ids), game["duration_per_game"] or 8,
             game["break_time"] or 0, user_id))
        template_id = cursor.lastrowid

    for order, match_id in enumerate(match_ids, start=1):
        cursor.execute(
            """SELECT team_home_id, team_away_id, round_number, is_tbd, scheduled_start
               FROM game_match WHERE id = ? AND game_id = ?""", (match_id, game_id))
        m = cursor.fetchone()
        if not m:
            continue
        cursor.execute(
            """INSERT INTO schedule_template_match
               (template_id, match_order, round_number, home_ordinal, away_ordinal,
                is_tbd, has_time)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (template_id, order, m["round_number"],
             ordinal_of.get(m["team_home_id"]), ordinal_of.get(m["team_away_id"]),
             m["is_tbd"] or 0, 1 if m["scheduled_start"] else 0))

    return template_id


def apply_template(cursor, game_id: int, template, start_time: str) -> int:
    """Write a template's fixtures into game_match. Caller clears existing rows.

    Rows that had a time get the next sequential slot; rows that did not stay
    untimed and do not advance the clock, so a trailing pickup slot survives the
    round trip.
    """
    from datetime import datetime as dt, timedelta

    team_ids = team_ids_in_order(cursor, game_id)
    duration = template["duration_per_game"] or 8
    brk = template["break_time"] or 0
    slot = duration + brk

    try:
        base = dt.strptime(start_time, "%H:%M")
    except (ValueError, TypeError):
        base = dt.strptime("18:00", "%H:%M")

    def team_for(ordinal):
        if ordinal is None or ordinal < 1 or ordinal > len(team_ids):
            return None
        return team_ids[ordinal - 1]

    cursor.execute(
        """SELECT * FROM schedule_template_match
           WHERE template_id = ? ORDER BY match_order""", (template["id"],))
    rows = cursor.fetchall()

    timed_seen = 0
    for i, r in enumerate(rows):
        if r["has_time"]:
            scheduled = (base + timedelta(minutes=timed_seen * slot)).strftime("%H:%M")
            timed_seen += 1
        else:
            scheduled = None
        cursor.execute(
            """INSERT INTO game_match
               (game_id, round_number, match_order, team_home_id, team_away_id,
                type, is_tbd, scheduled_start)
               VALUES (?, ?, ?, ?, ?, 'custom', ?, ?)""",
            (game_id, r["round_number"], i + 1,
             team_for(r["home_ordinal"]), team_for(r["away_ordinal"]),
             r["is_tbd"] or 0, scheduled))

    cursor.execute(
        """UPDATE game SET schedule_format = 'custom', duration_per_game = ?,
           break_time = ?, schedule_template_id = ?, schedule_template_name = ?
           WHERE id = ?""",
        (duration, brk, template["id"], template["name"], game_id))

    return len(rows)
