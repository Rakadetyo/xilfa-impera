import random
from urllib.parse import quote

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user
from app.services.team_balance import compute_player_values, generate_balanced_teams

router = APIRouter()

TEAM_COLORS = ["#000000", "#9CA3AF", "#9B59B6", "#3498DB", "#E74C3C", "#2ECC71", "#F1C40F", "#E91E63", "#F39C12"]
COLOR_NAMES = {
    "#000000": "Black", "#9CA3AF": "Gray / White", "#9B59B6": "Purple", "#3498DB": "Blue",
    "#E74C3C": "Red", "#2ECC71": "Green", "#F1C40F": "Yellow", "#E91E63": "Pink", "#F39C12": "Orange",
}


def _next_team_defaults(cursor, game_id):
    """Pick a name and an unused colour for a team appended to an existing game."""
    cursor.execute("SELECT team_name, team_color FROM game_team WHERE game_id = ?", (game_id,))
    rows = cursor.fetchall()
    used_colors = {r["team_color"] for r in rows}
    used_names = {r["team_name"] for r in rows}

    n = len(rows) + 1
    while f"Team {n}" in used_names:
        n += 1

    color = next((c for c in TEAM_COLORS if c not in used_colors), TEAM_COLORS[len(rows) % len(TEAM_COLORS)])
    return f"Team {n}", color, COLOR_NAMES.get(color, "")


@router.post("/manage/games/{game_id}/teams")
async def create_team(
    request: Request,
    game_id: int,
    team_name: str = Form(""),
    team_color: str = Form(""),
    team_color_name: str = Form("")
):
    """Append one team. Never touches existing teams or attendee assignments."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()

    auto_name, auto_color, auto_color_name = _next_team_defaults(cursor, game_id)
    team_name = team_name.strip() or auto_name
    if not team_color:
        team_color, team_color_name = auto_color, auto_color_name

    cursor.execute("INSERT INTO game_team (game_id, team_name, team_color, team_color_name) VALUES (?, ?, ?, ?)",
                  (game_id, team_name, team_color, team_color_name))

    # Keep game.num_teams in step so the config box reflects reality.
    cursor.execute("SELECT COUNT(*) AS n FROM game_team WHERE game_id = ?", (game_id,))
    cursor.execute("UPDATE game SET num_teams = ? WHERE id = ?", (cursor.fetchone()["n"], game_id))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)


@router.post("/manage/games/{game_id}/teams/{team_id}/edit")
async def edit_team(
    request: Request,
    game_id: int,
    team_id: int,
    team_name: str = Form(...),
    team_color: str = Form(""),
    team_color_name: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE game_team SET team_name = ?, team_color = ?, team_color_name = ? WHERE id = ? AND game_id = ?",
                  (team_name, team_color, team_color_name, team_id, game_id))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)


@router.post("/manage/games/{game_id}/teams/{team_id}/delete")
async def delete_team(request: Request, game_id: int, team_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    # Clear team_id from attendees first
    cursor.execute("UPDATE game_attendee SET team_id = NULL WHERE team_id = ?", (team_id,))
    cursor.execute("DELETE FROM game_team WHERE id = ? AND game_id = ?", (team_id, game_id))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)


@router.post("/manage/games/{game_id}/teams/skill-weight")
async def update_skill_weight(
    request: Request,
    game_id: int,
    skill_weight_pct: int = Form(60),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    skill_weight = max(0.0, min(1.0, skill_weight_pct / 100))

    conn = get_db()
    cursor = conn.cursor()

    # Save skill_weight only
    cursor.execute("UPDATE game SET skill_weight = ? WHERE id = ?", (skill_weight, game_id))
    conn.commit()
    conn.close()

    # Redirect back to teams tab without regenerating
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)


@router.post("/manage/games/{game_id}/teams/generate")
async def generate_teams_route(
    request: Request,
    game_id: int,
    num_teams: int = Form(3),
    players_per_team: int = Form(5),
    skill_weight_pct: int = Form(60),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    skill_weight = max(0.0, min(1.0, skill_weight_pct / 100))

    conn = get_db()
    cursor = conn.cursor()

    # Persist config
    cursor.execute(
        "UPDATE game SET num_teams = ?, players_per_team = ?, skill_weight = ? WHERE id = ?",
        (num_teams, players_per_team, skill_weight, game_id)
    )

    # Locked attendees keep their team. Only wipe what is not locked.
    cursor.execute(
        "SELECT id, team_id FROM game_attendee WHERE game_id = ? AND locked = 1 AND team_id IS NOT NULL",
        (game_id,)
    )
    locked = {r["id"]: r["team_id"] for r in cursor.fetchall()}
    locked_team_ids = []
    for tid in locked.values():
        if tid not in locked_team_ids:
            locked_team_ids.append(tid)

    if locked:
        cursor.execute(
            "UPDATE game_attendee SET team_id = NULL WHERE game_id = ? AND id NOT IN (%s)"
            % ",".join("?" * len(locked)), (game_id, *locked.keys()))
        cursor.execute(
            "DELETE FROM game_team WHERE game_id = ? AND id NOT IN (%s)"
            % ",".join("?" * len(locked_team_ids)), (game_id, *locked_team_ids))
    else:
        cursor.execute("UPDATE game_attendee SET team_id = NULL WHERE game_id = ?", (game_id,))
        cursor.execute("DELETE FROM game_team WHERE game_id = ?", (game_id,))

    # Fetch attending players
    cursor.execute("""
        SELECT ga.id, ga.player_id, p.name, p.skill_level, p.position_1, p.position_2
        FROM game_attendee ga
        JOIN player p ON ga.player_id = p.id
        WHERE ga.game_id = ?
        ORDER BY p.name
    """, (game_id,))
    attendees = [dict(a) for a in cursor.fetchall()]

    # Fetch groups with member attendee ids
    cursor.execute("SELECT * FROM game_player_group WHERE game_id = ?", (game_id,))
    groups_raw = cursor.fetchall()
    groups = []
    for g in groups_raw:
        cursor.execute("""
            SELECT ga.id as attendee_id
            FROM game_player_group_members gpm
            JOIN game_attendee ga ON gpm.player_id = ga.player_id AND ga.game_id = ?
            WHERE gpm.group_id = ?
        """, (game_id, g["id"]))
        groups.append({
            "id": g["id"],
            "name": g["name"],
            "member_attendee_ids": [r["attendee_id"] for r in cursor.fetchall()]
        })

    value_scores = compute_player_values(attendees, skill_weight)

    if not locked:
        # No locks: original behaviour — build every team from scratch.
        team_assignments = generate_balanced_teams(attendees, groups, num_teams, players_per_team, value_scores)
        team_ids = []
        for i in range(num_teams):
            cursor.execute(
                "INSERT INTO game_team (game_id, team_name, team_color, team_color_name) VALUES (?, ?, ?, ?)",
                (game_id, f"Team {i+1}", TEAM_COLORS[i % len(TEAM_COLORS)],
                 COLOR_NAMES.get(TEAM_COLORS[i % len(TEAM_COLORS)], ""))
            )
            team_ids.append(cursor.lastrowid)

        for team_idx, attendee_ids in enumerate(team_assignments):
            for aid in attendee_ids:
                cursor.execute(
                    "UPDATE game_attendee SET team_id = ? WHERE id = ? AND game_id = ?",
                    (team_ids[team_idx], aid, game_id)
                )

        conn.commit()
        conn.close()
        return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)

    # Locks present: preserved teams stay, remaining players fill the rest.
    notice = None
    if len(locked_team_ids) > num_teams:
        notice = (f"{len(locked_team_ids)} teams hold locked players, so team count stayed at "
                  f"{len(locked_team_ids)}. Unlock players first to go below that.")
        num_teams = len(locked_team_ids)
        cursor.execute("UPDATE game SET num_teams = ? WHERE id = ?", (num_teams, game_id))

    team_ids = list(locked_team_ids)
    for _ in range(num_teams - len(team_ids)):
        name, color, color_name = _next_team_defaults(cursor, game_id)
        cursor.execute(
            "INSERT INTO game_team (game_id, team_name, team_color, team_color_name) VALUES (?, ?, ?, ?)",
            (game_id, name, color, color_name)
        )
        team_ids.append(cursor.lastrowid)

    # Seed per-team load from the locked players already sitting there.
    counts = {tid: 0 for tid in team_ids}
    totals = {tid: 0.0 for tid in team_ids}
    for aid, tid in locked.items():
        counts[tid] = counts.get(tid, 0) + 1
        totals[tid] = totals.get(tid, 0.0) + value_scores.get(aid, 0)

    free = [a for a in attendees if a["id"] not in locked]
    free.sort(key=lambda a: -value_scores.get(a["id"], 0))

    for a in free:
        open_teams = [t for t in team_ids if counts[t] < players_per_team]
        if not open_teams:
            break
        target = min(open_teams, key=lambda t: (counts[t], totals[t]))
        cursor.execute(
            "UPDATE game_attendee SET team_id = ? WHERE id = ? AND game_id = ?",
            (target, a["id"], game_id)
        )
        counts[target] += 1
        totals[target] += value_scores.get(a["id"], 0)

    conn.commit()
    conn.close()

    url = f"/manage/games/{game_id}?tab=teams"
    if notice:
        url += f"&error={quote(notice)}"
    return RedirectResponse(url + "#teams", status_code=302)


@router.post("/manage/games/{game_id}/teams/randomize")
async def randomize_teams(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    # Get all teams for this game
    cursor.execute("SELECT id FROM game_team WHERE game_id = ?", (game_id,))
    teams = [row[0] for row in cursor.fetchall()]
    if not teams:
        conn.close()
        return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)
    # Get locked attendees (keep their current team) - only those with a team assigned
    cursor.execute("SELECT id, team_id FROM game_attendee WHERE game_id = ? AND locked = 1 AND team_id IS NOT NULL", (game_id,))
    locked_attendees = {row[0]: row[1] for row in cursor.fetchall()}
    # Count locked players per team
    locked_per_team = {}
    for team_id in locked_attendees.values():
        locked_per_team[team_id] = locked_per_team.get(team_id, 0) + 1
    # Get unlocked attendees - only those with a team assigned (skip unassigned)
    cursor.execute("SELECT id FROM game_attendee WHERE game_id = ? AND (locked != 1 OR locked IS NULL) AND team_id IS NOT NULL", (game_id,))
    unlocked = [row[0] for row in cursor.fetchall()]
    if not unlocked:
        conn.close()
        return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)
    # Shuffle unlocked players
    random.shuffle(unlocked)
    # Calculate target per team (total players / num teams)
    total_players = len(locked_attendees) + len(unlocked)
    target_per_team = total_players // len(teams)
    remainder = total_players % len(teams)
    # Track current count per team
    current_per_team = dict(locked_per_team)
    for t in teams:
        if t not in current_per_team:
            current_per_team[t] = 0
    # Assign unlocked players evenly
    for attendee_id in unlocked:
        # Find team with fewest players
        team_counts = [(t, current_per_team.get(t, 0)) for t in teams]
        team_counts.sort(key=lambda x: x[1])
        # First fill teams that need more to reach target
        min_count = team_counts[0][1]
        candidates = [t for t, c in team_counts if c == min_count]
        team_id = random.choice(candidates)
        cursor.execute("UPDATE game_attendee SET team_id = ? WHERE id = ?", (team_id, attendee_id))
        current_per_team[team_id] = current_per_team.get(team_id, 0) + 1
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)


@router.post("/manage/games/{game_id}/teams/clear")
async def clear_teams(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE game_attendee SET team_id = NULL WHERE game_id = ?", (game_id,))
    cursor.execute("DELETE FROM game_team WHERE game_id = ?", (game_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)
