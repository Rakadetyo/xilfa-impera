import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user, is_superadmin
from app.templating import templates
from app.services.team_balance import compute_player_values


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


def _game_period(cursor, game_id: int) -> str | None:
    cursor.execute("SELECT datetime FROM game WHERE id = ?", (game_id,))
    row = cursor.fetchone()
    if not row:
        return None
    dt_str = str(row["datetime"])[:10]
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d")
    except ValueError:
        return None
    months = ['January','February','March','April','May','June','July','August','September','October','November','December']
    return f"{months[dt.month - 1]} {dt.year}"


def _get_slot_type(cursor, game_id: int, player_id: int) -> str:
    period = _game_period(cursor, game_id)
    if not period:
        return "non-member"
    cursor.execute("SELECT id FROM member WHERE player_id = ? AND member_period = ?", (player_id, period))
    return "member" if cursor.fetchone() else "non-member"


def parse_types(types_str):
    """Parse comma-separated types string into cleaned list."""
    if not types_str:
        return []
    return [t.strip() for t in types_str.split(",") if t.strip()]


router = APIRouter()


@router.get("/manage/games")
async def list_games(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT g.*, a.location_name as arena_name,
               (SELECT COUNT(*) FROM game_attendee WHERE game_id = g.id) as attendee_count
        FROM game g
        LEFT JOIN arena a ON g.arena_id = a.id
        ORDER BY g.datetime ASC
    """)
    all_games = cursor.fetchall()

    # Filter to show 7 games: 3 before + 1 closest + 3 after
    games_list = list(all_games)
    if len(games_list) <= 7:
        games = games_list
    else:
        now = datetime.now()
        closest_idx = 0
        closest_diff = float('inf')
        for i, g in enumerate(games_list):
            game_dt = g["datetime"]
            if game_dt:
                if isinstance(game_dt, str):
                    game_dt = datetime.fromisoformat(game_dt.replace("Z", "+00:00").replace("+00:00", ""))
                diff = abs((game_dt - now).total_seconds())
                if diff < closest_diff:
                    closest_diff = diff
                    closest_idx = i

        start = max(0, closest_idx - 3)
        end = min(len(games_list), closest_idx + 4)
        if end - start < 7:
            if start == 0:
                end = min(len(games_list), 7)
            else:
                start = max(0, end - 7)
        games = games_list[start:end]

    cursor.execute("SELECT id, location_name FROM arena ORDER BY location_name")
    arenas = cursor.fetchall()

    conn.close()
    return templates.TemplateResponse(request, "games/list.html", {
        "user": user,
        "games": games,
        "all_games": [dict(g) for g in games_list],
        "arenas": arenas,
        "active": "games"
    })


@router.get("/manage/games/new")
async def new_game(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, location_name FROM arena ORDER BY location_name")
    arenas = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(request, "games/new.html", {
        "user": user,
        "arenas": arenas,
        "active": "games"
    })


@router.post("/manage/games/new")
async def create_game(
    request: Request,
    datetime: str = Form(...),
    arena_id: int = Form(None),
    price_per_person: float = Form(0),
    price_per_member: float = Form(0),
    duration_per_game: int = Form(8),
    session_duration: int = Form(120),
    max_players: int = Form(25),
    status: str = Form("open"),
    notes: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO game (datetime, arena_id, price_per_person, price_per_member,
                         duration_per_game, session_duration, max_players, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime, arena_id, price_per_person, price_per_member,
          duration_per_game, session_duration, max_players, status, notes))

    game_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}", status_code=302)


@router.get("/manage/games/{game_id}")
async def game_detail(request: Request, game_id: int, tab: str = "overview", error: str = None):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT g.*, a.location_name as arena_name
        FROM game g
        LEFT JOIN arena a ON g.arena_id = a.id
        WHERE g.id = ?
    """, (game_id,))
    game = cursor.fetchone()

    if not game:
        conn.close()
        raise HTTPException(status_code=404, detail="Game not found")

    # Format title
    game_dict = dict(game)
    # Ensure datetime is string (handle potential list type from SQLite quirk)
    if isinstance(game_dict.get("datetime"), list):
        game_dict["datetime"] = game_dict["datetime"][0] if game_dict["datetime"] else ""
    dt_str = str(game_dict["datetime"]).replace("T", " ")
    if len(dt_str) == 16:
        dt_str += ":00"
    if len(dt_str) == 10:
        dt_str += " 00:00:00"
    try:
        date_part = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").strftime("%a, %d %b %Y")
    except ValueError:
        # Never let an odd datetime take down the whole page.
        date_part = dt_str or "No date"
    base_title = date_part + " @ " + (game_dict["arena_name"] or "No arena")
    game_dict["title"] = f"{game_dict['game_name']} — {base_title}" if game_dict.get("game_name") else base_title

    # Get attendees with player info
    cursor.execute("""
        SELECT ga.id, ga.player_id, ga.team_id, ga.is_paid, ga.is_attend, ga.locked, ga.slot_type,
               ga.amount_paid, ga.created_at, ga.updated_at,
               p.name, p.nickname, p.position_1, p.position_2, p.skill_level,
               gt.team_name as team_name_assigned, gt.team_color
        FROM game_attendee ga
        JOIN player p ON ga.player_id = p.id
        LEFT JOIN game_team gt ON ga.team_id = gt.id
        WHERE ga.game_id = ?
        ORDER BY p.name
    """, (game_id,))
    attendees = cursor.fetchall()

    # Auto-populate with current members if no attendees
    if not attendees:
        # Get current month period (e.g., "May 2026")
        now = datetime.now()
        months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
        current_period = f"{months[now.month - 1]} {now.year}"

        # Only insert players not already in game
        cursor.execute("""
            INSERT INTO game_attendee (game_id, player_id, is_paid, is_attend, slot_type)
            SELECT ?, p.id, 1, 1, 'member'
            FROM player p
            JOIN member m ON p.id = m.player_id
            WHERE p.status = 1
            AND m.member_period = ?
            AND p.id NOT IN (SELECT player_id FROM game_attendee WHERE game_id = ?)
        """, (game_id, current_period, game_id))
        conn.commit()

        # Refetch attendees after auto-populate
        cursor.execute("""
            SELECT ga.*, p.name, p.nickname, p.position_1, p.position_2, p.skill_level,
                   gt.team_name as team_name_assigned, gt.team_color
            FROM game_attendee ga
            JOIN player p ON ga.player_id = p.id
            LEFT JOIN game_team gt ON ga.team_id = gt.id
            WHERE ga.game_id = ?
            ORDER BY p.name
        """, (game_id,))
        attendees = cursor.fetchall()

    # Get partners
    cursor.execute("SELECT * FROM game_partner WHERE game_id = ?", (game_id,))
    partners = cursor.fetchall()

    # Get all active partners for dropdown
    cursor.execute("SELECT * FROM partner WHERE is_active = 1 ORDER BY name")
    all_partners = cursor.fetchall()

    # Get assets with optional partner name
    cursor.execute("""
        SELECT ga.*, gp.name as partner_name
        FROM game_asset ga
        LEFT JOIN game_partner gp ON ga.game_partner_id = gp.id
        WHERE ga.game_id = ?
        ORDER BY ga.created_at
    """, (game_id,))
    assets = cursor.fetchall()

    # Get ratings with player name
    cursor.execute("""
        SELECT gr.*, p.name as player_name, p.nickname as player_nickname
        FROM game_rating gr
        JOIN player p ON gr.player_id = p.id
        WHERE gr.game_id = ?
        ORDER BY gr.created_at
    """, (game_id,))
    ratings_raw = cursor.fetchall()

    # Aggregate ratings
    RATING_TAGS = ['team', 'competitiveness', 'atmosphere', 'punctuality',
                   'organization', 'price', 'court', 'sportsmanship', 'supporting_partners']

    ratings_list = [dict(r) for r in ratings_raw]
    total_ratings = len(ratings_list)
    avg_rating = round(sum(r["rating"] for r in ratings_list) / total_ratings, 1) if total_ratings else 0
    rating_dist = {i: sum(1 for r in ratings_list if r["rating"] == i) for i in range(1, 6)}

    great_counts = {t: 0 for t in RATING_TAGS}
    improve_counts = {t: 0 for t in RATING_TAGS}
    for r in ratings_list:
        for t in (r["great_things"] or "").split(","):
            t = t.strip()
            if t in great_counts:
                great_counts[t] += 1
        for t in (r["could_be_improved"] or "").split(","):
            t = t.strip()
            if t in improve_counts:
                improve_counts[t] += 1

    great_tags = sorted([(t, c) for t, c in great_counts.items() if c > 0], key=lambda x: -x[1])
    improve_tags = sorted([(t, c) for t, c in improve_counts.items() if c > 0], key=lambda x: -x[1])

    # Diverging chart data: all tags sorted by total mentions desc
    tag_chart_data = sorted(
        [{"tag": t, "great": great_counts[t], "improve": improve_counts[t]} for t in RATING_TAGS],
        key=lambda x: -(int(x["great"]) + int(x["improve"]))
    )
    tag_chart_max = max((max(d["great"], d["improve"]) for d in tag_chart_data), default=1)

    ratings_summary = {
        "total": total_ratings,
        "avg": avg_rating,
        "dist": rating_dist,
        "great_tags": great_tags,
        "improve_tags": improve_tags,
        "tag_chart_data": tag_chart_data,
        "tag_chart_max": tag_chart_max,
        "response_rate": round(total_ratings / len(attendees) * 100) if attendees else 0,
    }

    # Get finance entries
    cursor.execute("SELECT * FROM game_finance_entry WHERE game_id = ? ORDER BY created_at", (game_id,))
    finance_entries = cursor.fetchall()

    # Compute finance summary
    price_member = game_dict.get("price_per_member") or 0
    price_person = game_dict.get("price_per_person") or 0

    def attendee_price(a):
        return price_member if a["slot_type"] == "member" else price_person

    # Income: sum amount_paid (written on pay toggle)
    income_players = sum((a["amount_paid"] or 0) for a in attendees)
    # Income: if all attendees paid (for reference)
    income_expected = sum(attendee_price(a) for a in attendees)
    # Expense: arena price (from arena master)
    cursor.execute("SELECT price FROM arena WHERE id = ?", (game_dict.get("arena_id"),))
    arena_row = cursor.fetchone()
    expense_arena = (arena_row["price"] or 0) if arena_row else 0
    # Expense: sum of partner fees
    expense_partners = sum((p["fee"] or 0) for p in partners)
    # Additional entries
    extra_income = sum((e["amount"] or 0) for e in finance_entries if e["type"] == "income")
    extra_expense = sum((e["amount"] or 0) for e in finance_entries if e["type"] == "expense")

    finance = {
        "income_players": income_players,
        "income_expected": income_expected,
        "extra_income": extra_income,
        "expense_arena": expense_arena,
        "expense_partners": expense_partners,
        "extra_expense": extra_expense,
        "total_income": income_players + extra_income,
        "total_expense": expense_arena + expense_partners + extra_expense,
    }
    finance["net"] = finance["total_income"] - finance["total_expense"]

    # Get teams
    cursor.execute("SELECT * FROM game_team WHERE game_id = ?", (game_id,))
    teams = cursor.fetchall()

    # Get matches
    cursor.execute("""
        SELECT gm.*,
               th.team_name as home_team, th.team_color as home_color,
               ta.team_name as away_team, ta.team_color as away_color
        FROM game_match gm
        LEFT JOIN game_team th ON gm.team_home_id = th.id
        LEFT JOIN game_team ta ON gm.team_away_id = ta.id
        WHERE gm.game_id = ?
        ORDER BY gm.match_order
    """, (game_id,))
    matches = cursor.fetchall()

    # Per-match player stats keyed by match_id -> team_id -> [player rows]
    cursor.execute("""
        SELECT gps.match_id, gps.team_id, gps.player_id, p.name,
               gps.points, gps.rebounds, gps.assists,
               gps.steals, gps.blocks, gps.turnovers, gps.fouls
        FROM game_player_stat gps
        JOIN player p ON gps.player_id = p.id
        WHERE gps.game_id = ?
        ORDER BY gps.match_id, gps.team_id, gps.points DESC
    """, (game_id,))
    match_player_stats: dict = {}
    for row in cursor.fetchall():
        row = dict(row)
        mid, tid = row["match_id"], row["team_id"]
        match_player_stats.setdefault(mid, {}).setdefault(tid, []).append(row)

    # Aggregated player stats for the whole game
    cursor.execute("""
        SELECT gps.player_id, p.name,
               SUM(gps.points) as points, SUM(gps.rebounds) as rebounds,
               SUM(gps.assists) as assists, SUM(gps.steals) as steals,
               SUM(gps.blocks) as blocks, SUM(gps.turnovers) as turnovers,
               SUM(gps.fouls) as fouls
        FROM game_player_stat gps
        JOIN player p ON gps.player_id = p.id
        WHERE gps.game_id = ?
        GROUP BY gps.player_id, p.name
        ORDER BY points DESC
    """, (game_id,))
    player_stats_totals = [dict(r) for r in cursor.fetchall()]

    # Get all players for adding attendees - current members first
    cursor.execute("""
        SELECT p.*,
               CASE WHEN EXISTS (
                   SELECT 1 FROM member m WHERE m.player_id = p.id
                   AND m.member_start_date <= date('now') AND m.member_end_date >= date('now')
               ) THEN 1 ELSE 0 END as is_current_member
        FROM player p
        WHERE p.status = 1
        ORDER BY is_current_member DESC, p.name
    """)
    all_players = cursor.fetchall()

    # Get arenas for dropdown
    cursor.execute("SELECT id, location_name FROM arena ORDER BY location_name")
    arenas = cursor.fetchall()

    # Get player groups with members (always fetched for teams tab)
    cursor.execute("SELECT * FROM game_player_group WHERE game_id = ? ORDER BY id", (game_id,))
    groups_raw = cursor.fetchall()
    groups = []
    grouped_player_ids = set()
    for g in groups_raw:
        cursor.execute("""
            SELECT gpm.player_id, p.name, p.skill_level, p.position_1, p.position_2
            FROM game_player_group_members gpm
            JOIN player p ON gpm.player_id = p.id
            WHERE gpm.group_id = ?
        """, (g["id"],))
        members = [dict(m) for m in cursor.fetchall()]
        groups.append({"id": g["id"], "name": g["name"], "members": members})
        for m in members:
            grouped_player_ids.add(m["player_id"])

    conn.close()

    # Compute per-player value scores relative to attending pool
    attendees_list = [dict(a) for a in attendees]
    skill_weight = float(game_dict.get("skill_weight") or 0.6)
    player_values = compute_player_values(attendees_list, skill_weight)

    # Compute balance scores if teams exist
    balance = None
    if teams:
        team_value_sums = []
        for team in teams:
            total_value = sum(
                player_values.get(a["id"], 0) for a in attendees_list if a.get("team_id") == team["id"]
            )
            team_value_sums.append(round(total_value, 1))
        if team_value_sums:
            skill_spread = max(team_value_sums) - min(team_value_sums)
            balance_score = max(0, round(100 - skill_spread, 1))
            balance = {
                "skill_spread": round(skill_spread, 1),
                "score": balance_score,
                "group_warning": skill_spread > 10 and bool(groups),
            }

    tabs = ["overview", "general", "players", "teams", "schedule", "scores", "results"]
    if tab not in tabs:
        tab = "overview"

    # Overview tab computed data
    paid_count = sum(1 for a in attendees if dict(a).get("is_paid", 0))
    assigned_count = sum(1 for a in attendees if dict(a).get("team_id", None))
    total_attendees = len(attendees)

    # Analytics: Average skill level
    if total_attendees > 0:
        total_skill = 0
        for a in attendees:
            a_dict = dict(a)
            skill = a_dict.get("skill_level", 0) or 0
            if skill:
                total_skill += skill
        avg_skill = round(total_skill / total_attendees, 1)
    else:
        avg_skill = 0

    if avg_skill <= 1.5:
        avg_skill_label = "Newbie"
    elif avg_skill <= 2.5:
        avg_skill_label = "Beginner"
    elif avg_skill <= 3.75:
        avg_skill_label = "Intermediate"
    elif avg_skill <= 4.49:
        avg_skill_label = "Expert"
    else:
        avg_skill_label = "Pro"

    # Analytics: Position counts
    position_counts = {"PG": 0, "SG": 0, "SF": 0, "PF": 0, "C": 0}
    position_counts_primary = {"PG": 0, "SG": 0, "SF": 0, "PF": 0, "C": 0}
    position_counts_secondary = {"PG": 0, "SG": 0, "SF": 0, "PF": 0, "C": 0}
    for a in attendees:
        a_dict = dict(a)
        pos1 = a_dict.get("position_1")
        pos2 = a_dict.get("position_2")
        if pos1:
            position_counts[pos1] = position_counts.get(pos1, 0) + 1
            position_counts_primary[pos1] = position_counts_primary.get(pos1, 0) + 1
        if pos2:
            position_counts[pos2] = position_counts.get(pos2, 0) + 1
            position_counts_secondary[pos2] = position_counts_secondary.get(pos2, 0) + 1

    # Step completion
    step_general = bool(game_dict.get("arena_id") and game_dict.get("datetime"))
    step_players = total_attendees > 0 and (paid_count / total_attendees) >= 0.5
    step_teams = len(teams) > 0
    step_schedule = len(matches) > 0

    overview_steps = [
        {
            "key": "general",
            "label": "General",
            "done": step_general,
            "sub": "Arena & time set" if step_general else "Missing arena or time",
            "tab": "general",
        },
        {
            "key": "players",
            "label": "Players",
            "done": step_players,
            "sub": f"{paid_count}/{total_attendees} paid" if total_attendees > 0 else "No players yet",
            "tab": "players",
        },
        {
            "key": "teams",
            "label": "Teams",
            "done": step_teams,
            "sub": f"{len(teams)} teams generated" if len(teams) > 0 else "Not generated",
            "tab": "teams",
        },
        {
            "key": "schedule",
            "label": "Schedule",
            "done": step_schedule,
            "sub": f"{len(matches)} matches" if step_schedule else "Not generated",
            "tab": "schedule",
        },
    ]
    overview_progress = round(sum(1 for s in overview_steps if s["done"]) / 4 * 100)

    # Tip-off time for the schedule form. Accepts either separator: rows written
    # by the datetime-local input use "T", scripts and manual edits use a space.
    game_start_time = "18:00"
    if game_dict.get("datetime"):
        _parts = str(game_dict["datetime"]).replace("T", " ").split(" ")
        if len(_parts) >= 2 and _parts[1][:5]:
            game_start_time = _parts[1][:5]

    # End time calculation
    if game_dict.get("datetime") and game_dict.get("session_duration"):
        try:
            dt_str = game_dict["datetime"].replace("T", " ")
            if len(dt_str) == 16:
                dt_str += ":00"
            start_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            end_dt = start_dt + timedelta(minutes=int(game_dict["session_duration"]))
            overview_start_time_fmt = start_dt.strftime("%H:%M")
            overview_end_time_fmt = end_dt.strftime("%H:%M")
        except Exception:
            overview_start_time_fmt = ""
            overview_end_time_fmt = ""
    else:
        overview_start_time_fmt = ""
        overview_end_time_fmt = ""

    # Revenue calculation
    revenue_collected = sum(
        (a["amount_paid"] if a["amount_paid"] else 0) for a in attendees
    )

    return templates.TemplateResponse(request, "games/detail.html", {
        "user": user,
        "game": game_dict,
        "game_datetime": game_dict.get("datetime", ""),
        "game_start_time": game_start_time,
        "attendees": attendees,
        "partners": partners,
        "all_partners": all_partners,
        "teams": teams,
        "matches": matches,
        "all_players": all_players,
        "arenas": arenas,
        "tab": tab,
        "tabs": tabs,
        "groups": groups,
        "grouped_player_ids": grouped_player_ids,
        "balance": balance,
        "player_values": player_values,
        "error": error,
        "overview_steps": overview_steps,
        "overview_progress": overview_progress,
        "overview_start_time_fmt": overview_start_time_fmt,
        "overview_end_time_fmt": overview_end_time_fmt,
        "paid_count": paid_count,
        "total_attendees": total_attendees,
        "revenue_collected": revenue_collected,
        "assigned_count": assigned_count,
        "parse_types": parse_types,
        "skill_labels": {1: "Newbie", 2: "Beginner", 3: "Intermediate", 4: "Expert", 5: "Pro"},
        "avg_skill": avg_skill,
        "avg_skill_label": avg_skill_label,
        "position_counts": position_counts,
        "position_counts_primary": position_counts_primary,
        "position_counts_secondary": position_counts_secondary,
        "assets": assets,
        "ratings": ratings_list,
        "ratings_summary": ratings_summary,
        "finance": finance,
        "finance_entries": finance_entries,
        "is_superadmin": is_superadmin,
        "active": "games",
        "match_player_stats": match_player_stats,
        "player_stats_totals": player_stats_totals,
    })


@router.post("/manage/games/{game_id}/assets/new")
async def add_game_asset(
    request: Request,
    game_id: int,
    type: str = Form("video"),
    url: str = Form(...),
    label: str = Form(""),
    game_partner_id: str = Form(""),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    partner_id = int(game_partner_id) if game_partner_id.strip().isdigit() else None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO game_asset (game_id, game_partner_id, type, url, label) VALUES (?, ?, ?, ?, ?)",
        (game_id, partner_id, type, url.strip(), label.strip() or None),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=results", status_code=302)


@router.post("/manage/games/{game_id}/assets/{asset_id}/delete")
async def delete_game_asset(request: Request, game_id: int, asset_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_asset WHERE id = ? AND game_id = ?", (asset_id, game_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=results", status_code=302)


@router.post("/manage/games/{game_id}/finance/new")
async def add_finance_entry(
    request: Request,
    game_id: int,
    type: str = Form(...),
    label: str = Form(...),
    amount: float = Form(...),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO game_finance_entry (game_id, type, label, amount) VALUES (?, ?, ?, ?)",
        (game_id, type, label.strip(), amount),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=results", status_code=302)


@router.post("/manage/games/{game_id}/finance/{entry_id}/delete")
async def delete_finance_entry(request: Request, game_id: int, entry_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_finance_entry WHERE id = ? AND game_id = ?", (entry_id, game_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=results", status_code=302)


@router.get("/manage/games/{game_id}/edit")
async def edit_game(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM game WHERE id = ?", (game_id,))
    game = cursor.fetchone()

    cursor.execute("SELECT id, location_name FROM arena ORDER BY location_name")
    arenas = cursor.fetchall()

    conn.close()

    return templates.TemplateResponse(request, "games/edit.html", {
        "user": user,
        "game": game,
        "arenas": arenas,
        "active": "games"
    })


@router.post("/manage/games/{game_id}/edit")
async def update_game(
    request: Request,
    game_id: int,
    datetime: str = Form(...),
    arena_id: int = Form(None),
    price_per_person: float = Form(0),
    price_per_member: float = Form(0),
    duration_per_game: int = Form(8),
    session_duration: int = Form(120),
    max_players: int = Form(25),
    status: str = Form("open"),
    notes: str = Form(""),
    is_video: bool = Form(default=False),
    is_photo: bool = Form(default=False),
    is_referee: bool = Form(default=False),
    game_name: str = Form(""),
    add_partner: str = Form(None),
    partner_type: str = Form(None),
    partner_name: str = Form(None),
    partner_contact: str = Form(None),
    partner_fee: float = Form(0)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE game SET datetime = ?, arena_id = ?, price_per_person = ?,
                       price_per_member = ?, duration_per_game = ?,
                       session_duration = ?, max_players = ?, status = ?, notes = ?,
                       is_video = ?, is_photo = ?, is_referee = ?, game_name = ?,
                       updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (datetime, arena_id, price_per_person, price_per_member,
          duration_per_game, session_duration, max_players, status, notes,
          1 if is_video else 0, 1 if is_photo else 0, 1 if is_referee else 0,
          game_name or None, game_id))

    # Handle add partner
    if add_partner and partner_type:
        cursor.execute("""
            INSERT INTO game_partner (game_id, type, name, contact, fee)
            VALUES (?, ?, ?, ?, ?)
        """, (game_id, partner_type, partner_name, partner_contact, partner_fee))
        conn.commit()

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=general", status_code=302)


@router.post("/manage/games/{game_id}/delete")
async def delete_game(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game WHERE id = ?", (game_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/games", status_code=302)


@router.post("/manage/games/{game_id}/invite/generate")
async def generate_invite(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT invite_token FROM game WHERE id = ?", (game_id,))
    row = cursor.fetchone()
    if row and row["invite_token"]:
        conn.close()
        return RedirectResponse(f"/manage/games/{game_id}?tab=overview", status_code=302)

    token = secrets.token_urlsafe(8)
    cursor.execute("UPDATE game SET invite_token = ? WHERE id = ?", (token, game_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=overview", status_code=302)


@router.post("/manage/games/{game_id}/invite/regenerate")
async def regenerate_invite(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    token = secrets.token_urlsafe(8)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE game SET invite_token = ? WHERE id = ?", (token, game_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=overview", status_code=302)
