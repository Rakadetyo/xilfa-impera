import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user
from app.templating import templates

router = APIRouter()


@router.get("/manage/games/{game_id}/scoring", response_class=HTMLResponse)
async def game_scoring_board(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM game WHERE id = ?", (game_id,))
    game = cursor.fetchone()
    if not game:
        conn.close()
        raise HTTPException(status_code=404)

    cursor.execute("""
        SELECT gm.*,
               th.team_name as home_name, th.team_color as home_color,
               ta.team_name as away_name, ta.team_color as away_color
        FROM game_match gm
        LEFT JOIN game_team th ON gm.team_home_id = th.id
        LEFT JOIN game_team ta ON gm.team_away_id = ta.id
        WHERE gm.game_id = ?
        ORDER BY gm.match_order, gm.id
    """, (game_id,))
    matches = [dict(m) for m in cursor.fetchall()]

    team_ids = set()
    for m in matches:
        if m.get("team_home_id"):
            team_ids.add(m["team_home_id"])
        if m.get("team_away_id"):
            team_ids.add(m["team_away_id"])

    team_rosters = {}
    for team_id in team_ids:
        cursor.execute("""
            SELECT p.id as player_id, p.name, p.position_1
            FROM game_attendee ga
            JOIN player p ON ga.player_id = p.id
            WHERE ga.team_id = ? AND ga.game_id = ?
            ORDER BY p.name
        """, (team_id, game_id))
        team_rosters[str(team_id)] = [dict(p) for p in cursor.fetchall()]

    conn.close()

    return templates.TemplateResponse(request, "games/scoring.html", {
        "game": dict(game),
        "matches_json": json.dumps(matches),
        "rosters_json": json.dumps(team_rosters),
    })


@router.post("/manage/games/{game_id}/matches/{match_id}/score")
async def update_match_score(request: Request, game_id: int, match_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    field = body.get("field")
    if field not in ("score_home", "score_away"):
        return JSONResponse({"error": "invalid field"}, status_code=400)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM game_match WHERE id = ? AND game_id = ?", (match_id, game_id))
    match = cursor.fetchone()
    if not match:
        conn.close()
        return JSONResponse({"error": "not found"}, status_code=404)

    if "delta" in body:
        new_value = max(0, (match[field] or 0) + int(body["delta"]))
    elif "value" in body:
        new_value = max(0, int(body["value"]))
    else:
        conn.close()
        return JSONResponse({"error": "missing delta or value"}, status_code=400)

    cursor.execute(f"UPDATE game_match SET {field} = ? WHERE id = ?", (new_value, match_id))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True, "value": new_value})


@router.get("/manage/games/{game_id}/matches/{match_id}/team-stats")
async def get_match_team_stats(request: Request, game_id: int, match_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT team_home_id, team_away_id FROM game_match WHERE id = ? AND game_id = ?", (match_id, game_id))
    match = cursor.fetchone()
    if not match:
        conn.close()
        return JSONResponse({"error": "not found"}, status_code=404)
    blank = {"points":0,"rebounds":0,"assists":0,"steals":0,"blocks":0,"turnovers":0,"fouls":0}
    def team_totals(team_id):
        if not team_id:
            return blank.copy()
        cursor.execute("""
            SELECT SUM(points),SUM(rebounds),SUM(assists),SUM(steals),SUM(blocks),SUM(turnovers),SUM(fouls)
            FROM game_player_stat WHERE match_id = ? AND team_id = ?
        """, (match_id, team_id))
        r = cursor.fetchone()
        if r and r[0] is not None:
            return {"points":r[0]or 0,"rebounds":r[1]or 0,"assists":r[2]or 0,"steals":r[3]or 0,"blocks":r[4]or 0,"turnovers":r[5]or 0,"fouls":r[6]or 0}
        return blank.copy()
    result = {"home": team_totals(match["team_home_id"]), "away": team_totals(match["team_away_id"])}
    conn.close()
    return JSONResponse(result)


@router.get("/manage/games/{game_id}/matches/{match_id}/player-stat/{player_id}")
async def get_player_stat(request: Request, game_id: int, match_id: int, player_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT points, rebounds, assists, steals, blocks, turnovers, fouls
        FROM game_player_stat WHERE match_id = ? AND player_id = ?
    """, (match_id, player_id))
    row = cursor.fetchone()
    conn.close()
    blank = {"points":0,"rebounds":0,"assists":0,"steals":0,"blocks":0,"turnovers":0,"fouls":0}
    return JSONResponse({"stats": dict(row) if row else blank})


@router.post("/manage/games/{game_id}/matches/{match_id}/player-stat")
async def update_player_stat(request: Request, game_id: int, match_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    player_id = body.get("player_id")
    team_id = body.get("team_id")
    stat = body.get("stat")
    delta = int(body.get("delta", 0))

    VALID_STATS = {"points", "rebounds", "assists", "steals", "blocks", "turnovers", "fouls"}
    if stat not in VALID_STATS or not player_id:
        return JSONResponse({"error": "invalid params"}, status_code=400)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM game_match WHERE id = ? AND game_id = ?", (match_id, game_id))
    match = cursor.fetchone()
    if not match:
        conn.close()
        return JSONResponse({"error": "not found"}, status_code=404)

    cursor.execute("""
        INSERT INTO game_player_stat (game_id, match_id, player_id, team_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(match_id, player_id) DO NOTHING
    """, (game_id, match_id, player_id, team_id))

    cursor.execute(f"""
        UPDATE game_player_stat
        SET {stat} = MAX(0, {stat} + ?), updated_at = CURRENT_TIMESTAMP
        WHERE match_id = ? AND player_id = ?
    """, (delta, match_id, player_id))

    cursor.execute(f"SELECT {stat} FROM game_player_stat WHERE match_id = ? AND player_id = ?",
                   (match_id, player_id))
    row = cursor.fetchone()
    new_stat = row[0] if row else 0

    response: dict = {"ok": True, "value": new_stat}

    if stat == "points":
        match_dict = dict(match)
        if team_id == match_dict.get("team_home_id"):
            score_field = "score_home"
        elif team_id == match_dict.get("team_away_id"):
            score_field = "score_away"
        else:
            score_field = None
        if score_field:
            new_score = max(0, (match_dict.get(score_field) or 0) + delta)
            cursor.execute(f"UPDATE game_match SET {score_field} = ? WHERE id = ?", (new_score, match_id))
            response["team_score"] = new_score
            response["score_field"] = score_field

    conn.commit()
    conn.close()
    return JSONResponse(response)
