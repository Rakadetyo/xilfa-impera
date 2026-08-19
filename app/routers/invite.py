from collections import defaultdict
from datetime import datetime as dt, timedelta

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.services.invite_theme import get_style
from app.templating import templates


def _platform_from_url(url: str) -> str:
    _map = {
        "drive.google.com": "Google Drive",
        "docs.google.com": "Google Docs",
        "photos.google.com": "Google Photos",
        "youtube.com": "YouTube",
        "youtu.be": "YouTube",
        "instagram.com": "Instagram",
        "tiktok.com": "TikTok",
        "vimeo.com": "Vimeo",
        "dropbox.com": "Dropbox",
        "icloud.com": "iCloud",
        "fb.com": "Facebook",
        "facebook.com": "Facebook",
    }
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().lstrip("www.")
        for domain, name in _map.items():
            if host == domain or host.endswith("." + domain):
                return name
        return host or url
    except Exception:
        return url


router = APIRouter()


@router.get("/invite/{token}")
async def invite_landing(request: Request, token: str):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT g.*, a.location_name as arena_name, a.address as arena_address, a.map_url as arena_map_url
        FROM game g
        LEFT JOIN arena a ON g.arena_id = a.id
        WHERE g.invite_token = ?
    """, (token,))
    game = cursor.fetchone()
    invite_style = get_style(dict(game).get("invite_background") if game else None)

    if not game:
        conn.close()
        raise HTTPException(status_code=404, detail="Invitation not found")

    cursor.execute("""
        SELECT ga.id as attendee_id, p.id as player_id, p.name
        FROM game_attendee ga
        JOIN player p ON ga.player_id = p.id
        WHERE ga.game_id = ?
        ORDER BY p.name
    """, (game["id"],))
    attendees = cursor.fetchall()

    # Get partners
    cursor.execute("""
        SELECT gp.*, p.name as partner_name, p.contact as partner_contact
        FROM game_partner gp
        LEFT JOIN partner p ON gp.partner_id = p.id
        WHERE gp.game_id = ?
        ORDER BY gp.type
    """, (game["id"],))
    partners = cursor.fetchall()
    conn.close()

    game_dict = dict(game)
    start_fmt, end_fmt, date_fmt = "", "", ""
    try:
        raw = game_dict["datetime"].replace("T", " ")
        if len(raw) == 16:
            raw += ":00"
        start_dt = dt.strptime(raw, "%Y-%m-%d %H:%M:%S")
        end_dt = start_dt + timedelta(minutes=int(game_dict.get("session_duration") or 120))
        start_fmt = start_dt.strftime("%H:%M")
        end_fmt = end_dt.strftime("%H:%M")
        date_fmt = start_dt.strftime("%A, %d %B %Y")
    except Exception:
        pass

    # Build og:image URL
    base_url = str(request.base_url).rstrip("/")
    og_image = f"{base_url}/assets/short deck impera-04.jpg"

    return templates.TemplateResponse(request, "invite/landing.html", {
        "invite_style": invite_style,
        "token": token,
        "game": game_dict,
        "attendees": attendees,
        "start_fmt": start_fmt,
        "end_fmt": end_fmt,
        "date_fmt": date_fmt,
        "partners": [dict(p) for p in partners],
        "arena_map_url": game_dict.get("arena_map_url"),
        "og_image": og_image,
    })


@router.post("/invite/{token}/identify")
async def invite_identify(request: Request, token: str, attendee_id: int = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM game WHERE invite_token = ?", (token,))
    game = cursor.fetchone()
    conn.close()

    if not game:
        raise HTTPException(status_code=404)

    return RedirectResponse(f"/invite/{token}/{attendee_id}", status_code=302)


@router.get("/invite/{token}/{attendee_id}")
async def invite_player(request: Request, token: str, attendee_id: int):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT g.*, a.location_name as arena_name, a.address as arena_address, a.map_url as arena_map_url
        FROM game g
        LEFT JOIN arena a ON g.arena_id = a.id
        WHERE g.invite_token = ?
    """, (token,))
    game = cursor.fetchone()
    invite_style = get_style(dict(game).get("invite_background") if game else None)
    if not game:
        conn.close()
        raise HTTPException(status_code=404)

    cursor.execute("""
        SELECT ga.*, p.name, p.nickname, p.position_1, p.position_2, p.join_date,
               (SELECT COUNT(*) FROM game_attendee WHERE player_id = p.id AND is_attend = 1) as games_played
        FROM game_attendee ga
        JOIN player p ON ga.player_id = p.id
        WHERE ga.id = ? AND ga.game_id = ?
    """, (attendee_id, game["id"]))
    attendee = cursor.fetchone()
    if not attendee:
        conn.close()
        raise HTTPException(status_code=404)

    team = None
    teammates = []
    if attendee["team_id"]:
        cursor.execute("SELECT * FROM game_team WHERE id = ?", (attendee["team_id"],))
        team = cursor.fetchone()

        cursor.execute("""
            SELECT ga.id as attendee_id, p.name, p.position_1, p.position_2
            FROM game_attendee ga
            JOIN player p ON ga.player_id = p.id
            WHERE ga.team_id = ? AND ga.game_id = ?
            ORDER BY p.name
        """, (attendee["team_id"], game["id"]))
        teammates = cursor.fetchall()

    # Get partners
    cursor.execute("""
        SELECT gp.*, p.name as partner_name, p.contact as partner_contact
        FROM game_partner gp
        LEFT JOIN partner p ON gp.partner_id = p.id
        WHERE gp.game_id = ?
        ORDER BY gp.type
    """, (game["id"],))
    partners = cursor.fetchall()

    # Build game_dict before closing connection
    game_dict = dict(game)

    # Check if player is a member by querying member table with current month period
    current_month = dt.now().strftime("%B %Y")  # e.g., "May 2026"

    cursor.execute("""
        SELECT is_paid FROM member
        WHERE player_id = ? AND member_period = ? AND is_paid = 1
    """, (attendee["player_id"], current_month))
    member_record = cursor.fetchone()

    is_member = member_record is not None
    is_member_slot = True if attendee["slot_type"] == "member" else False
    price = game_dict.get("price_per_member") if (is_member or is_member_slot) else game_dict.get("price_per_person")

    # Member label logic
    member_label = None
    if is_member:
        cursor.execute("""
            SELECT member_start_date FROM member
            WHERE player_id = ?
            ORDER BY member_start_date ASC
        """, (attendee["player_id"],))
        all_memberships = cursor.fetchall()
        cursor.execute("""
            SELECT member_start_date, member_end_date FROM member
            WHERE player_id = ? AND member_start_date <= date('now') AND member_end_date >= date('now')
            ORDER BY member_start_date ASC LIMIT 1
        """, (attendee["player_id"],))
        current_membership = cursor.fetchone()

        if current_membership:
            current_start = current_membership["member_start_date"]
            # Check if there's a gap before current membership
            cursor.execute("""
                SELECT member_end_date FROM member
                WHERE player_id = ? AND member_end_date < ?
                ORDER BY member_end_date DESC LIMIT 1
            """, (attendee["player_id"], current_start))
            prev = cursor.fetchone()
            if prev:
                # Gap exists — rejoined
                try:
                    rejoined_dt = dt.strptime(current_start, "%Y-%m-%d")
                    member_label = f"Rejoined {rejoined_dt.strftime('%b %Y')}"
                except Exception:
                    member_label = "Rejoined"
            else:
                # No gap — member since first record
                first_start = all_memberships[0]["member_start_date"] if all_memberships else current_start
                try:
                    since_dt = dt.strptime(first_start, "%Y-%m-%d")
                    member_label = f"Member Since {since_dt.strftime('%b %Y')}"
                except Exception:
                    member_label = "Member Since"
    else:
        join_date = dict(attendee).get("join_date")
        if join_date:
            try:
                join_dt = dt.strptime(join_date, "%Y-%m-%d")
                member_label = f"Playing Since {join_dt.strftime('%b %Y')}"
            except Exception:
                member_label = "Playing Since"

    # Attendance streak — count consecutive attended games up to and including this game
    cursor.execute("""
        SELECT COALESCE(ga.is_attend, 0) as attended
        FROM game g
        LEFT JOIN game_attendee ga ON g.id = ga.game_id AND ga.player_id = ?
        WHERE g.datetime <= (SELECT datetime FROM game WHERE id = ?)
        AND g.datetime IS NOT NULL
        ORDER BY g.datetime DESC
    """, (dict(attendee)["player_id"], game["id"]))
    streak = 0
    for row in cursor.fetchall():
        if row["attended"] == 1:
            streak += 1
        else:
            break

    conn.close()

    start_fmt, end_fmt, date_fmt = "", "", ""
    game_ended = False
    start_dt = None
    try:
        raw = game_dict["datetime"].replace("T", " ")
        if len(raw) == 16:
            raw += ":00"
        start_dt = dt.strptime(raw, "%Y-%m-%d %H:%M:%S")
        session_minutes = int(game_dict.get("session_duration") or 120)
        end_dt = start_dt + timedelta(minutes=session_minutes)
        halfway_dt = start_dt + timedelta(minutes=session_minutes / 2)
        start_fmt = start_dt.strftime("%H:%M")
        end_fmt = end_dt.strftime("%H:%M")
        date_fmt = start_dt.strftime("%A, %d %B %Y")
        game_ended = dt.now() > halfway_dt
    except Exception:
        pass

    if start_dt and dt.now().date() > start_dt.date() and not request.query_params.get("back"):
        return RedirectResponse(f"/invite/{token}/{attendee_id}/post-game", status_code=302)

    # Check if player already submitted a rating
    conn2 = get_db()
    c2 = conn2.cursor()
    c2.execute(
        "SELECT id FROM game_rating WHERE game_id = ? AND player_id = ?",
        (game_dict["id"], dict(attendee)["player_id"])
    )
    already_rated = c2.fetchone() is not None
    conn2.close()

    return templates.TemplateResponse(request, "invite/player.html", {
        "invite_style": invite_style,
        "token": token,
        "game": game_dict,
        "attendee": dict(attendee),
        "team": dict(team) if team else None,
        "teammates": [dict(t) for t in teammates],
        "start_fmt": start_fmt,
        "end_fmt": end_fmt,
        "date_fmt": date_fmt,
        "price": price or 0,
        "partners": [dict(p) for p in partners],
        "arena_map_url": game_dict.get("arena_map_url"),
        "is_member": is_member,
        "member_label": member_label,
        "streak": streak,
        "game_ended": game_ended,
        "already_rated": already_rated,
    })


@router.get("/invite/{token}/{attendee_id}/post-game")
async def post_game_page(request: Request, token: str, attendee_id: int):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM game WHERE invite_token = ?", (token,))
    game = cursor.fetchone()
    invite_style = get_style(dict(game).get("invite_background") if game else None)
    if not game:
        conn.close()
        raise HTTPException(status_code=404)

    cursor.execute("""
        SELECT ga.*, p.name, p.nickname
        FROM game_attendee ga
        JOIN player p ON ga.player_id = p.id
        WHERE ga.id = ? AND ga.game_id = ?
    """, (attendee_id, game["id"]))
    attendee = cursor.fetchone()
    if not attendee:
        conn.close()
        raise HTTPException(status_code=404)

    cursor.execute("""
        SELECT ga.*, gp.name as partner_name
        FROM game_asset ga
        LEFT JOIN game_partner gp ON ga.game_partner_id = gp.id
        WHERE ga.game_id = ?
        ORDER BY ga.created_at
    """, (game["id"],))
    assets = cursor.fetchall()

    cursor.execute(
        "SELECT id FROM game_rating WHERE game_id = ? AND player_id = ?",
        (game["id"], dict(attendee)["player_id"])
    )
    already_rated = cursor.fetchone() is not None

    # Team standings
    cursor.execute("SELECT * FROM game_team WHERE game_id = ? ORDER BY id", (game["id"],))
    teams_raw = {t["id"]: dict(t) for t in cursor.fetchall()}

    cursor.execute("""
        SELECT * FROM game_match
        WHERE game_id = ? AND score_home IS NOT NULL AND score_away IS NOT NULL
    """, (game["id"],))
    scored_matches = cursor.fetchall()

    team_rosters = {}
    for team_id in teams_raw:
        cursor.execute("""
            SELECT p.name, p.position_1, p.position_2
            FROM game_attendee ga
            JOIN player p ON ga.player_id = p.id
            WHERE ga.team_id = ? AND ga.game_id = ?
            ORDER BY p.name
        """, (team_id, game["id"]))
        team_rosters[team_id] = [dict(p) for p in cursor.fetchall()]

    conn.close()

    stats = defaultdict(lambda: {"wins": 0, "losses": 0, "draws": 0, "score_for": 0, "score_against": 0})
    for m in scored_matches:
        h, a, sh, sa = m["team_home_id"], m["team_away_id"], m["score_home"], m["score_away"]
        stats[h]["score_for"] += sh
        stats[h]["score_against"] += sa
        stats[a]["score_for"] += sa
        stats[a]["score_against"] += sh
        if sh > sa:
            stats[h]["wins"] += 1
            stats[a]["losses"] += 1
        elif sa > sh:
            stats[a]["wins"] += 1
            stats[h]["losses"] += 1
        else:
            stats[h]["draws"] += 1
            stats[a]["draws"] += 1

    standings = []
    for team_id, team in teams_raw.items():
        s = stats[team_id]
        standings.append({
            **team,
            "wins": s["wins"],
            "losses": s["losses"],
            "draws": s["draws"],
            "score_for": s["score_for"],
            "score_against": s["score_against"],
            "score_diff": s["score_for"] - s["score_against"],
            "played": s["wins"] + s["losses"] + s["draws"],
        })
    standings.sort(key=lambda x: (-x["wins"], -x["score_diff"], -x["score_for"]))
    for i, t in enumerate(standings):
        t["rank"] = i + 1

    RATING_TAGS = ['team', 'competitiveness', 'atmosphere', 'punctuality',
                   'organization', 'price', 'court', 'sportsmanship', 'supporting_partners']

    return templates.TemplateResponse(request, "invite/post_game.html", {
        "invite_style": invite_style,
        "token": token,
        "game": dict(game),
        "attendee": dict(attendee),
        "assets": [{**dict(a), "platform": _platform_from_url(a["url"])} for a in assets],
        "already_rated": already_rated,
        "rating_tags": RATING_TAGS,
        "standings": standings,
        "team_rosters": team_rosters,
        "has_scores": len(scored_matches) > 0,
    })


@router.post("/invite/{token}/{attendee_id}/post-game")
async def post_game_submit(
    request: Request,
    token: str,
    attendee_id: int,
    rating: int = Form(...),
    great_things: list[str] = Form(default=[]),
    could_be_improved: list[str] = Form(default=[]),
    feedback: str = Form(""),
    is_anonymous: int = Form(0),
):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM game WHERE invite_token = ?", (token,))
    game = cursor.fetchone()
    if not game:
        conn.close()
        raise HTTPException(status_code=404)

    cursor.execute("SELECT player_id FROM game_attendee WHERE id = ? AND game_id = ?", (attendee_id, game["id"]))
    attendee = cursor.fetchone()
    if not attendee:
        conn.close()
        raise HTTPException(status_code=404)

    player_id = attendee["player_id"]
    game_id = game["id"]

    # Guard: one rating per player per game
    cursor.execute("SELECT id FROM game_rating WHERE game_id = ? AND player_id = ?", (game_id, player_id))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO game_rating (game_id, game_attendee_id, player_id, is_anonymous, rating, great_things, could_be_improved, feedback)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            game_id, attendee_id, player_id, is_anonymous,
            max(1, min(5, rating)),
            ",".join(great_things),
            ",".join(could_be_improved),
            feedback.strip() or None,
        ))
        conn.commit()

    conn.close()
    return RedirectResponse(f"/invite/{token}/{attendee_id}/post-game", status_code=302)


@router.post("/invite/{token}/{attendee_id}/post-game/reset-rating")
async def reset_rating(request: Request, token: str, attendee_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM game WHERE invite_token = ?", (token,))
    game = cursor.fetchone()
    if game:
        cursor.execute("SELECT player_id FROM game_attendee WHERE id = ? AND game_id = ?", (attendee_id, game["id"]))
        attendee = cursor.fetchone()
        if attendee:
            cursor.execute("DELETE FROM game_rating WHERE game_id = ? AND player_id = ?", (game["id"], attendee["player_id"]))
            conn.commit()
    conn.close()
    return RedirectResponse(f"/invite/{token}/{attendee_id}/post-game", status_code=302)


@router.get("/invite/{token}/{attendee_id}/teams")
async def invite_teams(request: Request, token: str, attendee_id: int):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, invite_background FROM game WHERE invite_token = ?", (token,))
    game = cursor.fetchone()
    invite_style = get_style(dict(game).get("invite_background") if game else None)
    if not game:
        conn.close()
        raise HTTPException(status_code=404)

    # Get all teams with players
    cursor.execute("""
        SELECT gt.id as team_id, gt.team_name, gt.team_color,
               ga.id as attendee_id, p.name, p.position_1, p.position_2
        FROM game_team gt
        LEFT JOIN game_attendee ga ON ga.team_id = gt.id AND ga.game_id = gt.game_id
        LEFT JOIN player p ON ga.player_id = p.id
        WHERE gt.game_id = ?
        ORDER BY gt.id, p.name
    """, (game["id"],))

    rows = cursor.fetchall()

    # Group by team
    teams = {}
    for row in rows:
        tid = row["team_id"]
        if tid not in teams:
            teams[tid] = {
                "team_id": tid,
                "team_name": row["team_name"],
                "team_color": row["team_color"],
                "players": []
            }
        if row["name"]:
            teams[tid]["players"].append({
                "attendee_id": row["attendee_id"],
                "name": row["name"],
                "position_1": row["position_1"],
                "position_2": row["position_2"]
            })

    conn.close()

    return templates.TemplateResponse(request, "invite/teams.html", {
        "invite_style": invite_style,
        "token": token,
        "attendee_id": attendee_id,
        "teams": list(teams.values()),
    })


@router.get("/invite/{token}/{attendee_id}/schedule")
async def invite_schedule(request: Request, token: str, attendee_id: int):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT g.*, a.location_name as arena_name
        FROM game g LEFT JOIN arena a ON g.arena_id = a.id
        WHERE g.invite_token = ?
    """, (token,))
    game = cursor.fetchone()
    invite_style = get_style(dict(game).get("invite_background") if game else None)
    if not game:
        conn.close()
        raise HTTPException(status_code=404)

    cursor.execute("""
        SELECT ga.team_id FROM game_attendee ga
        WHERE ga.id = ? AND ga.game_id = ?
    """, (attendee_id, game["id"]))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404)
    player_team_id = row["team_id"]

    cursor.execute("""
        SELECT gm.*,
               th.team_name as home_name, th.team_color as home_color,
               ta.team_name as away_name, ta.team_color as away_color
        FROM game_match gm
        LEFT JOIN game_team th ON gm.team_home_id = th.id
        LEFT JOIN game_team ta ON gm.team_away_id = ta.id
        WHERE gm.game_id = ?
        ORDER BY gm.match_order
    """, (game["id"],))
    all_matches = [dict(m) for m in cursor.fetchall()]

    cursor.execute("SELECT * FROM game_team WHERE game_id = ? ORDER BY id", (game["id"],))
    teams_raw = cursor.fetchall()
    team_rosters = {}
    for t in teams_raw:
        cursor.execute("""
            SELECT p.name, p.position_1, ga.id as attendee_id
            FROM game_attendee ga
            JOIN player p ON ga.player_id = p.id
            WHERE ga.team_id = ? AND ga.game_id = ?
            ORDER BY p.name
        """, (t["id"], game["id"]))
        team_rosters[t["id"]] = {
            "id": t["id"],
            "name": t["team_name"],
            "color": t["team_color"] or "#6B7280",
            "players": [dict(p) for p in cursor.fetchall()]
        }

    # Standings
    cursor.execute("""
        SELECT * FROM game_match
        WHERE game_id = ? AND score_home IS NOT NULL AND score_away IS NOT NULL
    """, (game["id"],))
    scored_matches = cursor.fetchall()

    stats = defaultdict(lambda: {"wins": 0, "losses": 0, "draws": 0, "score_for": 0, "score_against": 0})
    for m in scored_matches:
        h, a, sh, sa = m["team_home_id"], m["team_away_id"], m["score_home"], m["score_away"]
        stats[h]["score_for"] += sh
        stats[h]["score_against"] += sa
        stats[a]["score_for"] += sa
        stats[a]["score_against"] += sh
        if sh > sa:
            stats[h]["wins"] += 1
            stats[a]["losses"] += 1
        elif sa > sh:
            stats[a]["wins"] += 1
            stats[h]["losses"] += 1
        else:
            stats[h]["draws"] += 1
            stats[a]["draws"] += 1

    standings = []
    for t in teams_raw:
        t_dict = dict(t)
        s = stats[t_dict["id"]]
        standings.append({
            **t_dict,
            "wins": s["wins"],
            "losses": s["losses"],
            "draws": s["draws"],
            "score_for": s["score_for"],
            "score_against": s["score_against"],
            "score_diff": s["score_for"] - s["score_against"],
            "played": s["wins"] + s["losses"] + s["draws"],
        })
    standings.sort(key=lambda x: (-x["wins"], -x["score_diff"], -x["score_for"]))
    for i, t in enumerate(standings):
        t["rank"] = i + 1
    has_scores = len(scored_matches) > 0

    # Format game time
    game_dict = dict(game)
    start_fmt, end_fmt, date_fmt, session_duration, match_duration = "", "", "", 120, 8
    break_time = 0
    start_dt = None
    try:
        raw = game_dict["datetime"].replace("T", " ")
        if len(raw) == 16:
            raw += ":00"
        start_dt = dt.strptime(raw, "%Y-%m-%d %H:%M:%S")
        session_duration = int(game_dict.get("session_duration") or 120)
        break_time = int(game_dict.get("break_time") or 0)
        match_duration = int(game_dict.get("duration_per_game") or 8) + break_time
        end_dt = start_dt + timedelta(minutes=session_duration)
        start_fmt = start_dt.strftime("%H:%M")
        end_fmt = end_dt.strftime("%H:%M")
        date_fmt = start_dt.strftime("%A, %d %B %Y")
    except Exception:
        pass

    # Calculate each match's start and end time
    game_duration = int(game_dict.get("duration_per_game") or 8)
    for i, match in enumerate(all_matches):
        if match.get("match_order") and start_dt:
            match_start = start_dt + timedelta(minutes=(match["match_order"] - 1) * match_duration)
            match_end = match_start + timedelta(minutes=game_duration)
            match["match_start"] = match_start.strftime("%H:%M")
            match["match_end"] = match_end.strftime("%H:%M")

    conn.close()

    return templates.TemplateResponse(request, "invite/schedule.html", {
        "invite_style": invite_style,
        "token": token,
        "attendee_id": attendee_id,
        "game": game_dict,
        "all_matches": all_matches,
        "player_team_id": player_team_id,
        "team_rosters": team_rosters,
        "standings": standings,
        "has_scores": has_scores,
        "start_fmt": start_fmt,
        "end_fmt": end_fmt,
        "date_fmt": date_fmt,
        "duration": session_duration,
        "match_duration": match_duration,
        "break_time": break_time,
    })
