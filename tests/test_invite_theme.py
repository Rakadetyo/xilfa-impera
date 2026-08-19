"""Background styles for the public invitation flow.

A game picks a style; every page a player sees renders on it. The dark look is
baked into Tailwind utilities in those templates, so a light style has to
retarget them as well as swap the background.
"""
import pytest

from app.services.invite_theme import DEFAULT_STYLE, STYLES, get_style, style_choices
from tests.helpers import make_game

INVITE_PAGES = ["", "/teams", "/schedule", "/post-game"]


def game_with_invite(conn, style=None):
    game_id, attendee_ids, _ = make_game(conn, num_teams=2, num_players=10)
    cur = conn.cursor()
    cur.execute("UPDATE game SET invite_token = 'tok123', datetime = '2026-08-22T19:00' WHERE id = ?",
                (game_id,))
    if style is not None:
        cur.execute("UPDATE game SET invite_background = ? WHERE id = ?", (style, game_id))
    conn.commit()
    return game_id, attendee_ids[0]


class TestStyleResolution:

    def test_default_is_purple(self):
        assert DEFAULT_STYLE == "purple"
        assert get_style(None)["name"] == STYLES["purple"]["name"]

    @pytest.mark.parametrize("bad", [None, "", "   ", "nonsense", "PURPLE!"])
    def test_unknown_styles_fall_back_rather_than_crash(self, bad):
        assert get_style(bad) is STYLES[DEFAULT_STYLE]

    def test_every_style_defines_what_a_template_needs(self):
        for key, st in style_choices():
            for field in ("name", "description", "logo", "background", "color",
                          "option_bg", "option_color", "overrides"):
                assert field in st, f"{key} is missing {field}"

    def test_light_style_retargets_the_dark_utilities(self):
        """A background swap alone would leave white text on a white ground."""
        overrides = STYLES["light"]["overrides"]
        for utility in (".text-white", ".bg-white\\/10", ".border-white\\/20",
                        ".text-gray-400", ".text-gray-500"):
            assert utility in overrides, f"light style does not retarget {utility}"

    def test_purple_needs_no_overrides(self):
        """The templates are authored for the dark look."""
        assert STYLES["purple"]["overrides"].strip() == ""

    def test_styles_use_distinct_logos(self):
        """A white logo is invisible on a white ground."""
        logos = {st["logo"] for _, st in style_choices()}
        assert len(logos) == len(STYLES)


class TestFlowIsThemedConsistently:

    @pytest.mark.parametrize("style,marker", [("purple", "#0f0a1a"), ("light", "#FFFFFF 0%")])
    def test_every_invite_page_uses_the_games_style(self, client, conn, style, marker):
        _, attendee_id = game_with_invite(conn, style)

        for suffix in INVITE_PAGES:
            url = "/invite/tok123" if suffix == "" else f"/invite/tok123/{attendee_id}{suffix}"
            r = client.get(url)
            assert r.status_code == 200, f"{suffix or '/landing'} returned {r.status_code}"
            assert marker in r.text, f"{suffix or '/landing'} is not using the {style} style"

    def test_player_page_is_themed(self, client, conn):
        """Covered separately because it is the only page reached without a suffix."""
        _, attendee_id = game_with_invite(conn, "light")
        r = client.get(f"/invite/tok123/{attendee_id}")
        assert r.status_code == 200
        assert "#FFFFFF 0%" in r.text

    def test_teams_page_reads_the_column(self, client, conn):
        """Regression: this handler selected only game.id, so it always fell back
        to the default while the rest of the flow honoured the choice."""
        _, attendee_id = game_with_invite(conn, "light")
        r = client.get(f"/invite/tok123/{attendee_id}/teams")
        assert "#FFFFFF 0%" in r.text

    def test_a_game_with_no_style_set_renders_the_default(self, client, conn):
        _, attendee_id = game_with_invite(conn, None)
        conn.execute("UPDATE game SET invite_background = NULL WHERE invite_token = 'tok123'")
        conn.commit()
        r = client.get("/invite/tok123")
        assert r.status_code == 200
        assert "#0f0a1a" in r.text


class TestPicker:

    def test_selecting_a_style_persists_it(self, client, conn):
        game_id, _ = game_with_invite(conn)

        client.post(f"/manage/games/{game_id}/invite/background",
                    data={"invite_background": "light"}, follow_redirects=False)

        assert conn.execute("SELECT invite_background FROM game WHERE id = ?",
                            (game_id,)).fetchone()["invite_background"] == "light"

    def test_an_unknown_style_is_rejected_not_stored(self, client, conn):
        game_id, _ = game_with_invite(conn, "light")

        client.post(f"/manage/games/{game_id}/invite/background",
                    data={"invite_background": "../../etc/passwd"}, follow_redirects=False)

        assert conn.execute("SELECT invite_background FROM game WHERE id = ?",
                            (game_id,)).fetchone()["invite_background"] == DEFAULT_STYLE


class TestSettingsScreen:

    def test_lists_every_style_with_usage(self, client, conn):
        import html as html_mod
        game_with_invite(conn, "light")
        r = client.get("/manage/page_settings/invitation")
        assert r.status_code == 200
        page = html_mod.unescape(r.text)   # names contain "&", which Jinja escapes
        for key, st in style_choices():
            assert st["name"] in page
            assert f"preview/{key}" in page, "each style needs a preview frame"

    def test_preview_renders_the_real_template(self, client, conn):
        """The preview must be the actual invite page, not a mockup that can drift."""
        r = client.get("/manage/page_settings/invitation/preview/light")
        assert r.status_code == 200
        assert "#FFFFFF 0%" in r.text
        assert "You're Invited" in r.text or "YOU'RE INVITED" in r.text.upper()

    def test_preview_of_an_unknown_style_falls_back(self, client, conn):
        r = client.get("/manage/page_settings/invitation/preview/nope")
        assert r.status_code == 200
        assert "#0f0a1a" in r.text


class TestPreviewIsInert:
    """The preview renders the real page, so its controls have to be disabled.

    Regression: the sample token is "preview", so submitting the name form from
    inside the preview posted to /invite/preview/identify, 404'd, and replaced
    the frame with a JSON error page.
    """

    def test_the_real_page_keeps_a_working_form(self, client, conn):
        _, _ = game_with_invite(conn)
        body = client.get("/invite/tok123").text
        assert "disabled" not in body.split("Who are you?")[1][:600]

    def test_preview_disables_the_name_form(self, client):
        body = client.get("/manage/page_settings/invitation/preview/purple").text
        form = body.split("Who are you?")[1][:800]
        assert form.count("disabled") >= 2, "select and button must both be disabled"
        assert 'onsubmit="return false"' in body

    def test_preview_cannot_reach_the_identify_route(self, client, conn):
        """Even if the markup regressed, the fake token has nowhere to go."""
        r = client.post("/invite/preview/identify", data={"attendee_id": 1},
                        follow_redirects=False)
        assert r.status_code == 404

    def test_settings_page_sandboxes_the_frames(self, client):
        body = client.get("/manage/page_settings/invitation").text
        assert body.count('sandbox="allow-scripts allow-same-origin"') >= 2
        assert "allow-forms" not in body, "forms must not be permitted in a preview"
