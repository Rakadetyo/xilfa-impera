"""Regression tests for P1 (destructive schedule ops) and P2 (team ordering).

P1: generate_schedule ran `DELETE FROM game_match` with no guard. Because
    PRAGMA foreign_keys = 0, the declared ON DELETE CASCADE does nothing, so
    game_player_stat rows were left orphaned rather than removed — pointing at
    a match id that no longer existed.

P2: no game_team query had an ORDER BY. Everything relied on SQLite's implicit
    rowid order, which is unspecified.
"""
from tests.helpers import make_game


def add_results(conn, game_id, matches=3, stats_per_match=2):
    """Give the game a schedule with scores and player stats."""
    cur = conn.cursor()
    teams = [r["id"] for r in conn.execute(
        "SELECT id FROM game_team WHERE game_id = ? ORDER BY id", (game_id,))]
    players = [r["player_id"] for r in conn.execute(
        "SELECT player_id FROM game_attendee WHERE game_id = ? LIMIT ?", (game_id, stats_per_match))]
    match_ids = []
    for i in range(matches):
        cur.execute("""INSERT INTO game_match (game_id, round_number, match_order,
                       team_home_id, team_away_id, score_home, score_away, scheduled_start)
                       VALUES (?, ?, ?, ?, ?, 21, 18, '19:00')""",
                    (game_id, i + 1, i + 1, teams[0], teams[1]))
        mid = cur.lastrowid
        match_ids.append(mid)
        for pid in players:
            cur.execute("""INSERT INTO game_player_stat (game_id, match_id, player_id, points)
                           VALUES (?, ?, ?, 10)""", (game_id, mid, pid))
    conn.commit()
    return match_ids


def orphan_count(conn):
    return conn.execute("""SELECT COUNT(*) c FROM game_player_stat gps
                           LEFT JOIN game_match gm ON gps.match_id = gm.id
                           WHERE gm.id IS NULL""").fetchone()["c"]


GEN = {"num_teams": 4, "players_per_team": 5, "format": "round_robin",
       "start_time": "19:00", "duration": 8, "break_time": 0}


class TestGenerateGuard:

    def test_refuses_to_wipe_results_without_confirmation(self, client, conn):
        game_id, _, _ = make_game(conn)
        add_results(conn, game_id)

        r = client.post(f"/manage/games/{game_id}/schedule/generate",
                        data=GEN, follow_redirects=False)

        assert r.status_code == 302
        assert "error=" in r.headers["location"]
        remaining = conn.execute("SELECT COUNT(*) c FROM game_match WHERE game_id = ?",
                                 (game_id,)).fetchone()["c"]
        assert remaining == 3, "matches must survive an unconfirmed generate"
        assert conn.execute("SELECT COUNT(*) c FROM game_player_stat WHERE game_id = ?",
                            (game_id,)).fetchone()["c"] == 6

    def test_proceeds_when_confirmed_and_leaves_no_orphans(self, client, conn):
        game_id, _, _ = make_game(conn)
        add_results(conn, game_id)

        client.post(f"/manage/games/{game_id}/schedule/generate",
                    data={**GEN, "confirm_destructive": "1"}, follow_redirects=False)

        assert orphan_count(conn) == 0, "stats must be deleted, not orphaned"
        assert conn.execute("SELECT COUNT(*) c FROM game_player_stat WHERE game_id = ?",
                            (game_id,)).fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM game_match WHERE game_id = ?",
                            (game_id,)).fetchone()["c"] == 6  # 4 teams round robin

    def test_no_prompt_needed_when_nothing_to_lose(self, client, conn):
        """The normal case: an unscored schedule regenerates with no friction."""
        game_id, _, _ = make_game(conn)

        r = client.post(f"/manage/games/{game_id}/schedule/generate",
                        data=GEN, follow_redirects=False)

        assert "error=" not in r.headers["location"]
        assert conn.execute("SELECT COUNT(*) c FROM game_match WHERE game_id = ?",
                            (game_id,)).fetchone()["c"] == 6

    def test_scores_without_stats_still_guarded(self, client, conn):
        game_id, _, _ = make_game(conn)
        add_results(conn, game_id, matches=2, stats_per_match=0)

        r = client.post(f"/manage/games/{game_id}/schedule/generate",
                        data=GEN, follow_redirects=False)

        assert "error=" in r.headers["location"]
        assert conn.execute("SELECT COUNT(*) c FROM game_match WHERE game_id = ?",
                            (game_id,)).fetchone()["c"] == 2


class TestOtherDestructivePaths:
    """Clear and single-match delete are explicit, so they need no prompt —
    but they must still not orphan stats."""

    def test_clear_removes_stats_too(self, client, conn):
        game_id, _, _ = make_game(conn)
        add_results(conn, game_id)

        client.post(f"/manage/games/{game_id}/schedule/clear", follow_redirects=False)

        assert orphan_count(conn) == 0
        assert conn.execute("SELECT COUNT(*) c FROM game_player_stat WHERE game_id = ?",
                            (game_id,)).fetchone()["c"] == 0

    def test_deleting_one_match_removes_only_its_stats(self, client, conn):
        game_id, _, _ = make_game(conn)
        match_ids = add_results(conn, game_id)

        client.post(f"/manage/games/{game_id}/schedule/{match_ids[0]}/delete",
                    follow_redirects=False)

        assert orphan_count(conn) == 0
        assert conn.execute("SELECT COUNT(*) c FROM game_player_stat WHERE game_id = ?",
                            (game_id,)).fetchone()["c"] == 4, "other matches keep their stats"


class TestTeamOrdering:

    def test_generate_uses_id_order_not_insertion_luck(self, conn, client):
        """Ordinal resolution depends on this, so it must be explicit."""
        game_id, _, team_ids = make_game(conn)
        # Force a non-contiguous id range, the shape delete-and-recreate produces.
        conn.execute("UPDATE game_team SET id = 9001 WHERE id = ?", (team_ids[-1],))
        conn.commit()

        client.post(f"/manage/games/{game_id}/schedule/generate",
                    data=GEN, follow_redirects=False)

        ordered = [r["id"] for r in conn.execute(
            "SELECT id FROM game_team WHERE game_id = ? ORDER BY id", (game_id,))]
        assert ordered == sorted(ordered)
        assert ordered[-1] == 9001

        used = set()
        for m in conn.execute(
                "SELECT team_home_id, team_away_id FROM game_match WHERE game_id = ?", (game_id,)):
            used.update([m["team_home_id"], m["team_away_id"]])
        assert used == set(ordered), "every team must appear in a round robin"


class TestBatchedTeamEdits:
    """Team pickers stage in the browser and commit on Save Order, so changing a
    dropdown no longer reloads the page on every selection."""

    def _schedule(self, conn, game_id):
        cur = conn.cursor()
        teams = [r["id"] for r in conn.execute(
            "SELECT id FROM game_team WHERE game_id = ? ORDER BY id", (game_id,))]
        for i in range(3):
            cur.execute("""INSERT INTO game_match (game_id, round_number, match_order,
                           team_home_id, team_away_id, scheduled_start)
                           VALUES (?, ?, ?, ?, ?, '19:00')""",
                        (game_id, i + 1, i + 1, teams[0], teams[1]))
        conn.commit()
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM game_match WHERE game_id = ? ORDER BY match_order", (game_id,))]
        return ids, teams

    def test_save_order_commits_team_changes(self, client, conn):
        game_id, _, _ = make_game(conn)
        ids, teams = self._schedule(conn, game_id)

        client.post(f"/manage/games/{game_id}/schedule/reorder", json={
            "match_ids": ids,
            "teams": [{"match_id": ids[0], "home": teams[2], "away": teams[3]}],
        })

        m = conn.execute("SELECT * FROM game_match WHERE id = ?", (ids[0],)).fetchone()
        assert (m["team_home_id"], m["team_away_id"]) == (teams[2], teams[3])

    def test_pickup_free_saves_as_null(self, client, conn):
        game_id, _, _ = make_game(conn)
        ids, _ = self._schedule(conn, game_id)

        client.post(f"/manage/games/{game_id}/schedule/reorder", json={
            "match_ids": ids,
            "teams": [{"match_id": ids[0], "home": None, "away": None}],
        })

        m = conn.execute("SELECT * FROM game_match WHERE id = ?", (ids[0],)).fetchone()
        assert m["team_home_id"] is None and m["team_away_id"] is None
        assert m["is_tbd"] == 1, "a pickup row is not a fully assigned match"

    def test_order_and_teams_commit_together(self, client, conn):
        game_id, _, _ = make_game(conn)
        ids, teams = self._schedule(conn, game_id)

        client.post(f"/manage/games/{game_id}/schedule/reorder", json={
            "match_ids": [ids[2], ids[0], ids[1]],
            "teams": [{"match_id": ids[2], "home": teams[3], "away": teams[0]}],
        })

        rows = list(conn.execute(
            "SELECT id, match_order, team_home_id FROM game_match WHERE game_id = ? ORDER BY match_order",
            (game_id,)))
        assert [r["id"] for r in rows] == [ids[2], ids[0], ids[1]]
        assert rows[0]["team_home_id"] == teams[3]

    def test_reorder_without_teams_still_works(self, client, conn):
        """Older payloads with no teams key must keep working."""
        game_id, _, _ = make_game(conn)
        ids, _ = self._schedule(conn, game_id)

        r = client.post(f"/manage/games/{game_id}/schedule/reorder",
                        json={"match_ids": [ids[1], ids[0], ids[2]]})

        assert r.status_code == 200
        assert [x["id"] for x in conn.execute(
            "SELECT id FROM game_match WHERE game_id = ? ORDER BY match_order", (game_id,))] \
            == [ids[1], ids[0], ids[2]]
