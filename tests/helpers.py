"""Shared builders for test fixtures."""


def make_game(conn, num_teams=4, players_per_team=5, num_players=20):
    """Game with `num_players` attendees split evenly across `num_teams` teams."""
    cur = conn.cursor()
    cur.execute("INSERT INTO arena (location_name) VALUES ('Test Arena')")
    arena_id = cur.lastrowid
    cur.execute(
        """INSERT INTO game (datetime, arena_id, game_name, num_teams, players_per_team, skill_weight)
           VALUES ('2026-08-22 19:00:00', ?, 'Test Game', ?, ?, 0.6)""",
        (arena_id, num_teams, players_per_team),
    )
    game_id = cur.lastrowid

    positions = ["PG", "SG", "SF", "PF", "C"]
    attendee_ids = []
    for i in range(num_players):
        cur.execute(
            "INSERT INTO player (name, skill_level, position_1, status) VALUES (?, ?, ?, 1)",
            (f"Player {i + 1}", (i % 5) + 1, positions[i % 5]),
        )
        pid = cur.lastrowid
        cur.execute(
            """INSERT INTO game_attendee (game_id, player_id, slot_type, is_paid, is_attend, locked)
               VALUES (?, ?, 'member', 1, 1, 0)""",
            (game_id, pid),
        )
        attendee_ids.append(cur.lastrowid)

    team_ids = []
    for i in range(num_teams):
        cur.execute(
            "INSERT INTO game_team (game_id, team_name, team_color) VALUES (?, ?, ?)",
            (game_id, f"Team {i + 1}", "#000000"),
        )
        team_ids.append(cur.lastrowid)

    per_team = num_players // num_teams if num_teams else 0
    for idx, aid in enumerate(attendee_ids):
        if per_team and idx // per_team < num_teams:
            cur.execute("UPDATE game_attendee SET team_id = ? WHERE id = ?",
                        (team_ids[idx // per_team], aid))
    conn.commit()
    return game_id, attendee_ids, team_ids


def lock_all(conn, game_id):
    conn.execute("UPDATE game_attendee SET locked = 1 WHERE game_id = ?", (game_id,))
    conn.commit()


def assignments(conn, game_id):
    """{attendee_id: team_id} for the game."""
    return {r["id"]: r["team_id"] for r in
            conn.execute("SELECT id, team_id FROM game_attendee WHERE game_id = ?", (game_id,))}
