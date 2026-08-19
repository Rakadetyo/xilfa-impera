"""Saved schedule format templates.

A template stores fixtures as team *ordinals* plus the session cadence, so the
same format replays onto any game with a matching team count while each game
keeps its own rosters. NULL ordinal means "Pickup / Free".
"""
import pytest

from tests.helpers import make_game

GEN = {"start_time": "19:00", "duration": 8, "break_time": 0}


def build_schedule(conn, game_id, rows):
    """rows: list of (home_ordinal, away_ordinal, has_time). 1-based ordinals."""
    cur = conn.cursor()
    teams = [r["id"] for r in conn.execute(
        "SELECT id FROM game_team WHERE game_id = ? ORDER BY id", (game_id,))]
    for i, (h, a, has_time) in enumerate(rows, start=1):
        cur.execute(
            """INSERT INTO game_match (game_id, round_number, match_order,
               team_home_id, team_away_id, scheduled_start)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (game_id, i, i,
             teams[h - 1] if h else None,
             teams[a - 1] if a else None,
             "19:00" if has_time else None))
    conn.commit()
    return [r["id"] for r in conn.execute(
        "SELECT id FROM game_match WHERE game_id = ? ORDER BY match_order", (game_id,))]


def save(client, conn, game_id, name, match_ids=None):
    if match_ids is None:
        match_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM game_match WHERE game_id = ? ORDER BY match_order", (game_id,))]
    return client.post(f"/manage/games/{game_id}/schedule/save-template",
                       data={"name": name, "match_order": ",".join(map(str, match_ids))},
                       follow_redirects=False)


def fixtures(conn, game_id):
    """(home_ordinal, away_ordinal, has_time) as replayed onto the game."""
    teams = [r["id"] for r in conn.execute(
        "SELECT id FROM game_team WHERE game_id = ? ORDER BY id", (game_id,))]
    idx = {t: i + 1 for i, t in enumerate(teams)}
    return [(idx.get(m["team_home_id"]), idx.get(m["team_away_id"]),
             bool(m["scheduled_start"]))
            for m in conn.execute(
                "SELECT * FROM game_match WHERE game_id = ? ORDER BY match_order", (game_id,))]


class TestRoundTrip:

    def test_same_fixtures_replay_onto_a_different_game(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        rows = [(1, 2, True), (3, 4, True), (1, 3, True), (2, 4, True)]
        build_schedule(conn, src, rows)
        save(client, conn, src, "4-team standard")

        dst, _, _ = make_game(conn, num_teams=4, num_players=20)
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='4-team standard'").fetchone()["id"]
        client.post(f"/manage/games/{dst}/schedule/generate",
                    data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)

        assert fixtures(conn, dst) == rows

    def test_rosters_and_team_names_are_untouched(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True), (3, 4, True)])
        save(client, conn, src, "f1")

        dst, _, dst_teams = make_game(conn, num_teams=4, num_players=20)
        conn.execute("UPDATE game_team SET team_name = 'Ballers' WHERE id = ?", (dst_teams[0],))
        conn.commit()
        before = [r["team_id"] for r in conn.execute(
            "SELECT team_id FROM game_attendee WHERE game_id = ? ORDER BY id", (dst,))]

        tid = conn.execute("SELECT id FROM schedule_template WHERE name='f1'").fetchone()["id"]
        client.post(f"/manage/games/{dst}/schedule/generate",
                    data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)

        after = [r["team_id"] for r in conn.execute(
            "SELECT team_id FROM game_attendee WHERE game_id = ? ORDER BY id", (dst,))]
        assert after == before, "players must not move"
        assert conn.execute("SELECT team_name FROM game_team WHERE id = ?",
                            (dst_teams[0],)).fetchone()["team_name"] == "Ballers"

    def test_pickup_free_rows_survive(self, client, conn):
        """NULL ordinals are a chosen state, not a missing team."""
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(None, None, True), (1, 2, True), (None, None, False)])
        save(client, conn, src, "with pickup")

        dst, _, _ = make_game(conn, num_teams=4, num_players=20)
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='with pickup'").fetchone()["id"]
        client.post(f"/manage/games/{dst}/schedule/generate",
                    data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)

        assert fixtures(conn, dst) == [(None, None, True), (1, 2, True), (None, None, False)]

    def test_untimed_rows_do_not_shift_later_times(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True), (None, None, False), (3, 4, True)])
        save(client, conn, src, "gap")

        dst, _, _ = make_game(conn, num_teams=4, num_players=20)
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='gap'").fetchone()["id"]
        client.post(f"/manage/games/{dst}/schedule/generate",
                    data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)

        times = [m["scheduled_start"] for m in conn.execute(
            "SELECT scheduled_start FROM game_match WHERE game_id = ? ORDER BY match_order", (dst,))]
        assert times == ["19:00", None, "19:08"], "the untimed row must not consume a slot"

    def test_cadence_travels_and_start_time_does_not(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        conn.execute("UPDATE game SET duration_per_game = 12, break_time = 3 WHERE id = ?", (src,))
        conn.commit()
        build_schedule(conn, src, [(1, 2, True), (3, 4, True)])
        save(client, conn, src, "long games")

        dst, _, _ = make_game(conn, num_teams=4, num_players=20)
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='long games'").fetchone()["id"]
        client.post(f"/manage/games/{dst}/schedule/generate",
                    data={**GEN, "start_time": "20:30", "format": f"template:{tid}"},
                    follow_redirects=False)

        g = conn.execute("SELECT duration_per_game, break_time FROM game WHERE id = ?", (dst,)).fetchone()
        assert (g["duration_per_game"], g["break_time"]) == (12, 3), "cadence comes from the template"
        times = [m["scheduled_start"] for m in conn.execute(
            "SELECT scheduled_start FROM game_match WHERE game_id = ? ORDER BY match_order", (dst,))]
        assert times == ["20:30", "20:45"], "start time comes from the form, 12+3 apart"

    def test_saved_order_is_the_order_submitted(self, client, conn):
        """Save captures the on-screen order, not what was last persisted."""
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        ids = build_schedule(conn, src, [(1, 2, True), (3, 4, True), (1, 3, True)])
        save(client, conn, src, "reordered", match_ids=[ids[2], ids[0], ids[1]])

        dst, _, _ = make_game(conn, num_teams=4, num_players=20)
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='reordered'").fetchone()["id"]
        client.post(f"/manage/games/{dst}/schedule/generate",
                    data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)

        assert fixtures(conn, dst) == [(1, 3, True), (1, 2, True), (3, 4, True)]


class TestTeamCountBinding:

    def test_mismatched_team_count_is_refused(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True)])
        save(client, conn, src, "four only")

        dst, _, _ = make_game(conn, num_teams=3, num_players=15)
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='four only'").fetchone()["id"]
        r = client.post(f"/manage/games/{dst}/schedule/generate",
                        data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)

        assert "error=" in r.headers["location"]
        assert conn.execute("SELECT COUNT(*) c FROM game_match WHERE game_id = ?",
                            (dst,)).fetchone()["c"] == 0

    def test_dropdown_marks_mismatches_unusable(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True)])
        save(client, conn, src, "four only")

        dst, _, _ = make_game(conn, num_teams=3, num_players=15)
        body = client.get(f"/manage/games/{dst}?tab=schedule").text
        assert "needs 4 teams, you have 3" in body
        assert "disabled" in body

    def test_ordinals_resolve_by_id_with_gaps(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 4, True)])
        save(client, conn, src, "first vs last")

        dst, _, dst_teams = make_game(conn, num_teams=4, num_players=20)
        conn.execute("UPDATE game_team SET id = 9001 WHERE id = ?", (dst_teams[-1],))
        conn.execute("UPDATE game_attendee SET team_id = 9001 WHERE team_id = ?", (dst_teams[-1],))
        conn.commit()

        tid = conn.execute("SELECT id FROM schedule_template WHERE name='first vs last'").fetchone()["id"]
        client.post(f"/manage/games/{dst}/schedule/generate",
                    data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)

        m = conn.execute("SELECT * FROM game_match WHERE game_id = ?", (dst,)).fetchone()
        assert m["team_home_id"] == dst_teams[0]
        assert m["team_away_id"] == 9001, "ordinal 4 is the highest id, not the 4th created"


class TestOwnershipAndLifecycle:

    def test_same_owner_overwrites_rather_than_duplicating(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True), (3, 4, True)])
        save(client, conn, src, "my format")

        conn.execute("DELETE FROM game_match WHERE game_id = ?", (src,))
        conn.commit()
        build_schedule(conn, src, [(1, 3, True)])
        save(client, conn, src, "my format")

        rows = conn.execute("SELECT * FROM schedule_template WHERE name='my format'").fetchall()
        assert len(rows) == 1, "no duplicate template"
        assert conn.execute(
            "SELECT COUNT(*) c FROM schedule_template_match WHERE template_id = ?",
            (rows[0]["id"],)).fetchone()["c"] == 1, "old match rows replaced"

    def test_cannot_overwrite_someone_elses_format(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True)])
        save(client, conn, src, "theirs")
        conn.execute("UPDATE schedule_template SET created_by = 999 WHERE name='theirs'")
        conn.commit()

        r = save(client, conn, src, "theirs")
        assert "error=" in r.headers["location"]
        assert conn.execute(
            "SELECT COUNT(*) c FROM schedule_template_match st "
            "JOIN schedule_template t ON st.template_id = t.id WHERE t.name='theirs'"
        ).fetchone()["c"] == 1

    def test_deleting_a_format_leaves_past_games_intact(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True), (3, 4, True)])
        save(client, conn, src, "doomed")
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='doomed'").fetchone()["id"]

        dst, _, _ = make_game(conn, num_teams=4, num_players=20)
        client.post(f"/manage/games/{dst}/schedule/generate",
                    data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)
        before = fixtures(conn, dst)

        client.post(f"/manage/schedule-templates/{tid}/delete",
                    data={"game_id": dst}, follow_redirects=False)

        assert fixtures(conn, dst) == before, "copy-on-use: the schedule stands alone"
        assert client.get(f"/manage/games/{dst}?tab=schedule").status_code == 200
        assert conn.execute(
            "SELECT schedule_template_name FROM game WHERE id = ?", (dst,)
        ).fetchone()["schedule_template_name"] == "doomed", "name kept for history"

    def test_delete_removes_match_rows_no_orphans(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True), (3, 4, True)])
        save(client, conn, src, "gone")
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='gone'").fetchone()["id"]

        client.post(f"/manage/schedule-templates/{tid}/delete",
                    data={"game_id": src}, follow_redirects=False)

        assert conn.execute(
            "SELECT COUNT(*) c FROM schedule_template_match WHERE template_id = ?",
            (tid,)).fetchone()["c"] == 0

    def test_non_owner_cannot_delete(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True)])
        save(client, conn, src, "protected")
        conn.execute("UPDATE schedule_template SET created_by = 999 WHERE name='protected'")
        conn.commit()
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='protected'").fetchone()["id"]

        client.post(f"/manage/schedule-templates/{tid}/delete",
                    data={"game_id": src}, follow_redirects=False)

        assert conn.execute("SELECT COUNT(*) c FROM schedule_template WHERE id = ?",
                            (tid,)).fetchone()["c"] == 1

    def test_applying_records_provenance(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True)])
        save(client, conn, src, "tracked")
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='tracked'").fetchone()["id"]

        dst, _, _ = make_game(conn, num_teams=4, num_players=20)
        client.post(f"/manage/games/{dst}/schedule/generate",
                    data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)

        g = conn.execute("SELECT * FROM game WHERE id = ?", (dst,)).fetchone()
        assert g["schedule_format"] == "custom", "the enum keeps its closed set of values"
        assert g["schedule_template_id"] == tid
        assert g["schedule_template_name"] == "tracked"

    def test_builtin_format_clears_provenance(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True)])
        save(client, conn, src, "temp")
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='temp'").fetchone()["id"]

        client.post(f"/manage/games/{src}/schedule/generate",
                    data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)
        client.post(f"/manage/games/{src}/schedule/generate",
                    data={**GEN, "format": "round_robin"}, follow_redirects=False)

        g = conn.execute("SELECT * FROM game WHERE id = ?", (src,)).fetchone()
        assert g["schedule_format"] == "round_robin"
        assert g["schedule_template_id"] is None


class TestGuardsStillApply:

    def test_applying_over_results_needs_confirmation(self, client, conn):
        from tests.test_schedule import add_results
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True)])
        save(client, conn, src, "safe")
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='safe'").fetchone()["id"]

        dst, _, _ = make_game(conn, num_teams=4, num_players=20)
        add_results(conn, dst)

        r = client.post(f"/manage/games/{dst}/schedule/generate",
                        data={**GEN, "format": f"template:{tid}"}, follow_redirects=False)

        assert "error=" in r.headers["location"]
        assert conn.execute("SELECT COUNT(*) c FROM game_player_stat WHERE game_id = ?",
                            (dst,)).fetchone()["c"] == 6

    def test_saving_with_no_schedule_is_refused(self, client, conn):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        r = save(client, conn, src, "empty")
        assert "error=" in r.headers["location"]
        assert conn.execute("SELECT COUNT(*) c FROM schedule_template").fetchone()["c"] == 0

    @pytest.mark.parametrize("name", ["", "   "])
    def test_blank_name_is_refused(self, client, conn, name):
        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True)])
        r = save(client, conn, src, name)
        assert "error=" in r.headers["location"]
        assert conn.execute("SELECT COUNT(*) c FROM schedule_template").fetchone()["c"] == 0


class TestSuperadminOverride:
    """The fixture user is a plain admin, so the superadmin path needs its own test."""

    def test_superadmin_can_delete_someone_elses_format(self, client, conn, db_path):
        import sqlite3
        import app.deps as deps
        import sys

        src, _, _ = make_game(conn, num_teams=4, num_players=20)
        build_schedule(conn, src, [(1, 2, True)])
        save(client, conn, src, "not mine")
        conn.execute("UPDATE schedule_template SET created_by = 999 WHERE name='not mine'")
        conn.commit()
        tid = conn.execute("SELECT id FROM schedule_template WHERE name='not mine'").fetchone()["id"]

        boss = {"id": 2, "username": "boss", "role": "superadmin"}
        for name, mod in list(sys.modules.items()):
            if name.startswith("app.routers") and hasattr(mod, "get_current_user"):
                mod.get_current_user = lambda request: boss
        deps.get_current_user = lambda request: boss

        client.post(f"/manage/schedule-templates/{tid}/delete",
                    data={"game_id": src}, follow_redirects=False)

        assert conn.execute("SELECT COUNT(*) c FROM schedule_template WHERE id = ?",
                            (tid,)).fetchone()["c"] == 0
