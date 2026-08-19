from datetime import datetime as dt, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user
from app.services.schedule import (
    generate_round_robin,
    generate_single_elimination,
    generate_double_elimination,
    generate_group_knockout,
    generate_king_of_court,
    SUGGESTIONS,
)

router = APIRouter()


def count_results(cursor, game_id: int) -> tuple:
    """(scored_matches, player_stat_rows) for a game — what a wipe would destroy."""
    cursor.execute(
        "SELECT COUNT(*) AS n FROM game_match WHERE game_id = ? "
        "AND (score_home IS NOT NULL OR score_away IS NOT NULL)",
        (game_id,)
    )
    scored = cursor.fetchone()["n"]
    cursor.execute(
        "SELECT COUNT(*) AS n FROM game_player_stat WHERE game_id = ?", (game_id,)
    )
    return scored, cursor.fetchone()["n"]


def delete_matches(cursor, game_id: int, match_id: int = None) -> None:
    """Delete matches and their player stats.

    Foreign keys are not enforced (PRAGMA foreign_keys = 0), so the declared
    ON DELETE CASCADE does nothing — dependent rows must go explicitly or they
    are orphaned, not removed.
    """
    if match_id is None:
        cursor.execute("DELETE FROM game_player_stat WHERE game_id = ?", (game_id,))
        cursor.execute("DELETE FROM game_match WHERE game_id = ?", (game_id,))
    else:
        cursor.execute("DELETE FROM game_player_stat WHERE match_id = ?", (match_id,))
        cursor.execute("DELETE FROM game_match WHERE id = ? AND game_id = ?", (match_id, game_id))



@router.post("/manage/games/{game_id}/schedule/generate")
async def generate_schedule(
    request: Request,
    game_id: int,
    format: str = Form("round_robin"),
    start_time: str = Form("18:00"),
    duration: int = Form(8),
    break_time: int = Form(0),
    confirm_destructive: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()

    # Get teams
    cursor.execute("SELECT id, team_name FROM game_team WHERE game_id = ? ORDER BY id", (game_id,))
    teams = cursor.fetchall()

    if len(teams) < 2:
        conn.close()
        return JSONResponse({"error": "Need at least 2 teams"}, status_code=400)

    # Get current datetime for calculating match times (don't update game.datetime)
    cursor.execute("SELECT datetime FROM game WHERE id = ?", (game_id,))
    game = cursor.fetchone()
    current_datetime = game["datetime"] if game and game["datetime"] else None

    # Use start_time from form for schedule calculation, but don't save to game.datetime
    if current_datetime:
        # Accepts either separator — the datetime-local input writes "T",
        # scripts and manual edits write a space.
        current_date = str(current_datetime).replace("T", " ").split(" ")[0]
        new_datetime = f"{current_date}T{start_time}:00"
    else:
        new_datetime = f"2025-01-01T{start_time}:00"

    # Update only schedule settings, NOT datetime
    cursor.execute(
        "UPDATE game SET schedule_format = ?, duration_per_game = ?, break_time = ? WHERE id = ?",
        (format, duration, break_time, game_id)
    )

    # Regenerating destroys results. Require explicit confirmation first.
    scored, stats = count_results(cursor, game_id)
    if (scored or stats) and confirm_destructive != "1":
        conn.close()
        msg = (f"Generating would delete {scored} match result(s) and {stats} player "
               f"stat row(s). Nothing was changed.")
        return RedirectResponse(
            f"/manage/games/{game_id}?tab=schedule&error={quote(msg)}", status_code=302)

    delete_matches(cursor, game_id)

    # Generate matches based on format
    if format == "round_robin":
        matches = generate_round_robin(teams)
    elif format == "single_elimination":
        matches = generate_single_elimination(teams)
    elif format == "double_elimination":
        matches = generate_double_elimination(teams)
    elif format == "group_knockout":
        matches = generate_group_knockout(teams)
    elif format == "king_of_court":
        matches = generate_king_of_court(teams)
    elif format == "custom":
        # Custom: create one placeholder match
        matches = [{
            "team_home_id": None,
            "team_away_id": None,
            "round_number": 1,
            "bracket_slot": None,
            "is_tbd": 1
        }]
    else:
        matches = generate_round_robin(teams)

    # Insert matches with scheduled_start calculated
    game_start_dt = dt.strptime(new_datetime, "%Y-%m-%dT%H:%M:%S")
    match_duration = duration + break_time

    for i, m in enumerate(matches):
        match_start_dt = game_start_dt + timedelta(minutes=i * match_duration)
        scheduled_start = match_start_dt.strftime("%H:%M")

        cursor.execute("""
            INSERT INTO game_match (
                game_id, round_number, match_order, team_home_id, team_away_id,
                type, bracket_slot, next_match_id, is_tbd, scheduled_start
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            game_id,
            m.get("round_number", 1),
            i + 1,
            m.get("team_home_id"),
            m.get("team_away_id"),
            format,
            m.get("bracket_slot"),
            m.get("next_match_id"),
            m.get("is_tbd", 0),
            scheduled_start
        ))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)


@router.post("/manage/games/{game_id}/schedule/reorder")
async def reorder_matches(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()
    match_ids = data.get("match_ids", [])

    if not match_ids:
        return JSONResponse({"error": "No match IDs provided"}, status_code=400)

    conn = get_db()
    cursor = conn.cursor()

    # Get game datetime and durations
    cursor.execute("SELECT datetime, duration_per_game, break_time FROM game WHERE id = ?", (game_id,))
    game = cursor.fetchone()
    if game and game["datetime"]:
        raw = game["datetime"].replace("T", " ")
        if len(raw) == 16:
            raw += ":00"
        game_start_dt = dt.strptime(raw, "%Y-%m-%d %H:%M:%S")
        match_duration = int(game["duration_per_game"] or 8) + int(game["break_time"] or 0)

        for order, match_id in enumerate(match_ids):
            match_start_dt = game_start_dt + timedelta(minutes=order * match_duration)
            scheduled_start = match_start_dt.strftime("%H:%M")
            cursor.execute(
                "UPDATE game_match SET match_order = ?, scheduled_start = ? WHERE id = ? AND game_id = ?",
                (order + 1, scheduled_start, match_id, game_id)
            )
    else:
        for order, match_id in enumerate(match_ids):
            cursor.execute(
                "UPDATE game_match SET match_order = ? WHERE id = ? AND game_id = ?",
                (order + 1, match_id, game_id)
            )

    conn.commit()
    conn.close()

    return JSONResponse({"success": True})


@router.post("/manage/games/{game_id}/schedule/clear")
async def clear_schedule(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()

    # Clear matches and reset format
    delete_matches(cursor, game_id)
    cursor.execute(
        "UPDATE game SET schedule_format = 'round_robin', best_of = 1 WHERE id = ?",
        (game_id,)
    )

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)


@router.post("/manage/games/{game_id}/schedule/add")
async def add_match(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()

    # Get max round_number and max match_order
    cursor.execute("SELECT COALESCE(MAX(round_number), 0) as max_round, COALESCE(MAX(match_order), 0) as max_order FROM game_match WHERE game_id = ?", (game_id,))
    result = cursor.fetchone()
    next_round = (result["max_round"] or 0) + 1
    next_order = (result["max_order"] or 0) + 1

    cursor.execute("""
        INSERT INTO game_match (game_id, round_number, match_order, is_tbd, type)
        VALUES (?, ?, ?, 1, 'custom')
    """, (game_id, next_round, next_order))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)


@router.post("/manage/games/{game_id}/schedule/{match_id}")
async def update_match(
    request: Request,
    game_id: int,
    match_id: int,
    score_home: int = Form(0),
    score_away: int = Form(0),
    notes: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()

    winner = None
    if score_home > score_away:
        cursor.execute("SELECT team_home_id FROM game_match WHERE id = ?", (match_id,))
        winner = cursor.fetchone()["team_home_id"]
    elif score_away > score_home:
        cursor.execute("SELECT team_away_id FROM game_match WHERE id = ?", (match_id,))
        winner = cursor.fetchone()["team_away_id"]

    cursor.execute("""
        UPDATE game_match SET score_home = ?, score_away = ?, winner_team_id = ?, notes = ?
        WHERE id = ? AND game_id = ?
    """, (score_home, score_away, winner, notes, match_id, game_id))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)


@router.post("/manage/games/{game_id}/schedule/{match_id}/update-teams")
async def update_match_teams(
    request: Request,
    game_id: int,
    match_id: int,
    team_home_id: str = Form(""),
    team_away_id: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Skip update if pickup is selected (handled in template)
    if team_home_id == "pickup" or team_away_id == "pickup":
        return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    home_id = int(team_home_id) if team_home_id else None
    away_id = int(team_away_id) if team_away_id else None

    cursor.execute("""
        UPDATE game_match SET team_home_id = ?, team_away_id = ?, is_tbd = ?
        WHERE id = ? AND game_id = ?
    """, (home_id, away_id, 0 if home_id and away_id else 1, match_id, game_id))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)


@router.post("/manage/games/{game_id}/schedule/{match_id}/delete")
async def delete_match(request: Request, game_id: int, match_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    delete_matches(cursor, game_id, match_id)
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)
