"""Regression tests for the team-add bug.

Reported: "kalo udah generate 4 tim, terus mau tambah 1 tim lagi, dia generate
ulang semua, kondisi udah di lock semua tim" — with 4 teams generated and every
player locked, adding a 5th team wiped every assignment.
"""
from tests.helpers import make_game, lock_all, assignments


class TestAddTeam:
    """POST /teams appends a team without disturbing anything else."""

    def test_add_team_keeps_all_assignments(self, client, conn):
        game_id, _, _ = make_game(conn)
        lock_all(conn, game_id)
        before = assignments(conn, game_id)

        r = client.post(f"/manage/games/{game_id}/teams", data={}, follow_redirects=False)

        assert r.status_code == 302
        assert assignments(conn, game_id) == before, "player assignments must not change"

    def test_add_team_creates_exactly_one_team(self, client, conn):
        game_id, _, _ = make_game(conn)
        lock_all(conn, game_id)

        client.post(f"/manage/games/{game_id}/teams", data={}, follow_redirects=False)

        teams = conn.execute(
            "SELECT team_name FROM game_team WHERE game_id = ? ORDER BY id", (game_id,)
        ).fetchall()
        assert len(teams) == 5
        assert teams[-1]["team_name"] == "Team 5"

    def test_new_team_starts_empty(self, client, conn):
        game_id, _, _ = make_game(conn)
        lock_all(conn, game_id)

        client.post(f"/manage/games/{game_id}/teams", data={}, follow_redirects=False)

        new_team = conn.execute(
            "SELECT id FROM game_team WHERE game_id = ? ORDER BY id DESC LIMIT 1", (game_id,)
        ).fetchone()["id"]
        n = conn.execute(
            "SELECT COUNT(*) c FROM game_attendee WHERE team_id = ?", (new_team,)
        ).fetchone()["c"]
        assert n == 0

    def test_add_team_syncs_num_teams(self, client, conn):
        game_id, _, _ = make_game(conn)

        client.post(f"/manage/games/{game_id}/teams", data={}, follow_redirects=False)

        num = conn.execute("SELECT num_teams FROM game WHERE id = ?", (game_id,)).fetchone()["num_teams"]
        assert num == 5

    def test_add_team_picks_unused_colour(self, client, conn):
        game_id, _, _ = make_game(conn)

        client.post(f"/manage/games/{game_id}/teams", data={}, follow_redirects=False)

        colors = [r["team_color"] for r in conn.execute(
            "SELECT team_color FROM game_team WHERE game_id = ? ORDER BY id", (game_id,))]
        assert colors[-1] != "#000000", "new team should not reuse the seeded colour"

    def test_explicit_name_is_respected(self, client, conn):
        game_id, _, _ = make_game(conn)

        client.post(f"/manage/games/{game_id}/teams",
                    data={"team_name": "Ballers", "team_color": "#E74C3C"},
                    follow_redirects=False)

        last = conn.execute(
            "SELECT team_name, team_color FROM game_team WHERE game_id = ? ORDER BY id DESC LIMIT 1",
            (game_id,)).fetchone()
        assert last["team_name"] == "Ballers"
        assert last["team_color"] == "#E74C3C"


class TestGenerateRespectsLocks:
    """POST /teams/generate must not throw away locked players."""

    def test_locked_players_keep_their_team(self, client, conn):
        game_id, _, _ = make_game(conn)
        lock_all(conn, game_id)
        before = assignments(conn, game_id)

        client.post(f"/manage/games/{game_id}/teams/generate",
                    data={"num_teams": 5, "players_per_team": 5, "skill_weight_pct": 60},
                    follow_redirects=False)

        assert assignments(conn, game_id) == before

    def test_nobody_left_unassigned_when_all_locked(self, client, conn):
        """Guards the end state. The pre-fix symptom was reshuffling, not blanking:
        all 20 locked players were moved onto freshly created teams."""
        game_id, _, _ = make_game(conn)
        lock_all(conn, game_id)

        client.post(f"/manage/games/{game_id}/teams/generate",
                    data={"num_teams": 5, "players_per_team": 5, "skill_weight_pct": 60},
                    follow_redirects=False)

        orphans = conn.execute(
            "SELECT COUNT(*) c FROM game_attendee WHERE game_id = ? AND team_id IS NULL", (game_id,)
        ).fetchone()["c"]
        assert orphans == 0

    def test_unlocked_players_are_redistributed(self, client, conn):
        """Locked players stay put; unlocked ones may move to the new team."""
        game_id, attendee_ids, team_ids = make_game(conn)
        # Lock only the first three teams' players (15 of 20).
        conn.execute(
            "UPDATE game_attendee SET locked = 1 WHERE game_id = ? AND team_id IN (?, ?, ?)",
            (game_id, *team_ids[:3]))
        conn.commit()
        locked_before = {r["id"]: r["team_id"] for r in conn.execute(
            "SELECT id, team_id FROM game_attendee WHERE game_id = ? AND locked = 1", (game_id,))}

        client.post(f"/manage/games/{game_id}/teams/generate",
                    data={"num_teams": 5, "players_per_team": 4, "skill_weight_pct": 60},
                    follow_redirects=False)

        after = assignments(conn, game_id)
        for aid, tid in locked_before.items():
            assert after[aid] == tid, f"locked attendee {aid} moved"
        assert conn.execute("SELECT COUNT(*) c FROM game_team WHERE game_id = ?",
                            (game_id,)).fetchone()["c"] == 5

    def test_unlocked_game_still_regenerates_from_scratch(self, client, conn):
        """With no locks the original behaviour is preserved."""
        game_id, _, old_team_ids = make_game(conn)

        client.post(f"/manage/games/{game_id}/teams/generate",
                    data={"num_teams": 5, "players_per_team": 5, "skill_weight_pct": 60},
                    follow_redirects=False)

        new_team_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM game_team WHERE game_id = ?", (game_id,))]
        assert len(new_team_ids) == 5
        assert not set(new_team_ids) & set(old_team_ids), "teams should be rebuilt"
        orphans = conn.execute(
            "SELECT COUNT(*) c FROM game_attendee WHERE game_id = ? AND team_id IS NULL", (game_id,)
        ).fetchone()["c"]
        assert orphans == 0

    def test_cannot_shrink_below_locked_team_count(self, client, conn):
        """Asking for fewer teams than hold locked players is clamped, not destructive."""
        game_id, _, _ = make_game(conn)
        lock_all(conn, game_id)
        before = assignments(conn, game_id)

        client.post(f"/manage/games/{game_id}/teams/generate",
                    data={"num_teams": 2, "players_per_team": 5, "skill_weight_pct": 60},
                    follow_redirects=False)

        assert assignments(conn, game_id) == before
        assert conn.execute("SELECT COUNT(*) c FROM game_team WHERE game_id = ?",
                            (game_id,)).fetchone()["c"] == 4


class TestMigrations:
    """The schema must apply cleanly to an empty database."""

    def test_fresh_db_runs_all_migrations(self, db_path):
        import sqlite3
        from app.db.migrations import run_migrations
        conn = sqlite3.connect(":memory:")
        try:
            run_migrations(conn)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        assert "game_match" in tables


class TestGameStartTime:
    """The schedule tab must render whatever separator game.datetime uses.

    A row written as "2026-08-22 19:00:00" (space) used to 500 the whole game
    detail page: the template did game_datetime.split('T')[1], which raised
    "list object has no element 1". Rows written by the datetime-local input
    use "T"; scripts and manual edits do not.
    """

    import pytest

    @pytest.mark.parametrize("stored,expected", [
        ("2026-08-22T19:00", "19:00"),
        ("2026-08-22T19:00:00", "19:00"),
        ("2026-08-22 19:00:00", "19:00"),
        ("2026-08-22 07:30:00", "07:30"),
        ("2026-08-22", "18:00"),
        ("", "18:00"),
    ])
    def test_schedule_tab_renders_for_any_datetime_format(self, client, conn, stored, expected):
        game_id, _, _ = make_game(conn)
        conn.execute("UPDATE game SET datetime = ? WHERE id = ?", (stored, game_id))
        conn.commit()

        r = client.get(f"/manage/games/{game_id}?tab=schedule")

        assert r.status_code == 200, f"{stored!r} broke the page"
        assert f'name="start_time" value="{expected}"' in r.text
