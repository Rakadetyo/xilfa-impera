from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user
from app.templating import templates
from app.routers.games.crud import _game_period, _get_slot_type

router = APIRouter()


@router.post("/manage/games/{game_id}/players/add")
async def add_player_to_game(
    request: Request,
    game_id: int,
    name: str = Form(...),
    nickname: str = Form(""),
    position_1: str = Form(""),
    position_2: str = Form(""),
    skill_level: int = Form(3),
    contact_no: str = Form(""),
    instagram: str = Form(""),
    reclub: str = Form(""),
    status: int = Form(1)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    if skill_level < 1 or skill_level > 5:
        skill_level = 3
    if status not in (-1, 0, 1):
        status = 1

    conn = get_db()
    cursor = conn.cursor()

    # Create player
    cursor.execute("""
        INSERT INTO player (name, nickname, position_1, position_2, skill_level, contact_no, instagram, reclub, join_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, date('now'), ?)
    """, (name, nickname, position_1, position_2, skill_level, contact_no, instagram, reclub, status))

    player_id = cursor.lastrowid

    # Add to game as attendee
    cursor.execute("""
        INSERT INTO game_attendee (game_id, player_id, is_paid, is_attend)
        VALUES (?, ?, 0, 1)
    """, (game_id, player_id))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=players", status_code=302)


@router.post("/manage/games/{game_id}/attendees")
async def add_attendee(request: Request, game_id: int, player_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()

    # Check if already attending
    cursor.execute("SELECT id FROM game_attendee WHERE game_id = ? AND player_id = ?", (game_id, player_id))
    if cursor.fetchone():
        conn.close()
        return JSONResponse({"error": "Player already added"}, status_code=400)

    slot_type = _get_slot_type(cursor, game_id, player_id)
    cursor.execute("INSERT INTO game_attendee (game_id, player_id, is_attend, slot_type) VALUES (?, ?, 1, ?)", (game_id, player_id, slot_type))
    conn.commit()
    conn.close()

    return JSONResponse({"success": True})


@router.post("/manage/games/{game_id}/attendees/bulk")
async def add_attendees_bulk(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    form = await request.form()
    player_ids = form.getlist("player_ids")

    conn = get_db()
    cursor = conn.cursor()

    for player_id in player_ids:
        pid = int(player_id)
        cursor.execute("SELECT id FROM game_attendee WHERE game_id = ? AND player_id = ?", (game_id, pid))
        if not cursor.fetchone():
            slot_type = _get_slot_type(cursor, game_id, pid)
            cursor.execute("INSERT INTO game_attendee (game_id, player_id, is_attend, slot_type) VALUES (?, ?, 1, ?)", (game_id, pid, slot_type))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=players", status_code=302)


@router.post("/manage/games/{game_id}/attendees/{attendee_id}/edit")
async def edit_attendee(
    request: Request,
    game_id: int,
    attendee_id: int,
    name: str = Form(...),
    nickname: str = Form(""),
    position_1: str = Form(""),
    position_2: str = Form(""),
    skill_level: int = Form(3)
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    # Update player info
    cursor.execute("""
        UPDATE player SET name = ?, nickname = ?, position_1 = ?, position_2 = ?, skill_level = ?
        WHERE id = (SELECT player_id FROM game_attendee WHERE id = ? AND game_id = ?)
    """, (name, nickname, position_1, position_2, skill_level, attendee_id, game_id))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=players", status_code=302)


@router.post("/manage/games/{game_id}/attendees/{attendee_id}/delete")
async def remove_attendee(request: Request, game_id: int, attendee_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_attendee WHERE id = ? AND game_id = ?", (attendee_id, game_id))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=players", status_code=302)


@router.post("/manage/games/{game_id}/attendees/{attendee_id}/pay")
async def toggle_payment(request: Request, game_id: int, attendee_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ga.is_paid, ga.slot_type, g.price_per_member, g.price_per_person
        FROM game_attendee ga
        JOIN game g ON ga.game_id = g.id
        WHERE ga.id = ?
    """, (attendee_id,))
    row = cursor.fetchone()
    if row:
        new_is_paid = 0 if row["is_paid"] else 1
        if new_is_paid == 1:
            amount_paid = (row["price_per_member"] or 0) if row["slot_type"] == "member" else (row["price_per_person"] or 0)
        else:
            amount_paid = 0
        cursor.execute(
            "UPDATE game_attendee SET is_paid = ?, amount_paid = ? WHERE id = ?",
            (new_is_paid, amount_paid, attendee_id)
        )
        conn.commit()
    conn.close()

    return JSONResponse({"is_paid": new_is_paid})


@router.post("/manage/games/{game_id}/attendees/{attendee_id}/attend")
async def toggle_attendance(request: Request, game_id: int, attendee_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT is_attend FROM game_attendee WHERE id = ?", (attendee_id,))
    row = cursor.fetchone()
    if row:
        new_is_attend = 0 if row["is_attend"] else 1
        cursor.execute("UPDATE game_attendee SET is_attend = ? WHERE id = ?", (new_is_attend, attendee_id))
        conn.commit()
    conn.close()

    return JSONResponse({"is_attend": new_is_attend})


@router.post("/manage/games/{game_id}/attendees/{attendee_id}/assign-team")
async def assign_team(request: Request, game_id: int, attendee_id: int, team_id: str = Form("")):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    # If team_id is empty, remove team assignment (set to NULL)
    if team_id:
        cursor.execute("UPDATE game_attendee SET team_id = ? WHERE id = ? AND game_id = ?",
                      (int(team_id), attendee_id, game_id))
    else:
        cursor.execute("UPDATE game_attendee SET team_id = NULL WHERE id = ? AND game_id = ?",
                      (attendee_id, game_id))
    conn.commit()
    conn.close()

    if "application/json" in request.headers.get("Accept", "") or request.headers.get("X-Requested-With") == "fetch":
        return JSONResponse({"ok": True})
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)


@router.post("/manage/games/{game_id}/attendees/bulk-assign-team")
async def bulk_assign_team(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()
    assignments = data.get("assignments", [])

    conn = get_db()
    cursor = conn.cursor()

    for a in assignments:
        attendee_id = a.get("attendeeId")
        team_id = a.get("teamId")
        if team_id is None:
            cursor.execute("UPDATE game_attendee SET team_id = NULL WHERE id = ? AND game_id = ?",
                          (attendee_id, game_id))
        else:
            cursor.execute("UPDATE game_attendee SET team_id = ? WHERE id = ? AND game_id = ?",
                          (team_id, attendee_id, game_id))

    conn.commit()
    conn.close()

    return JSONResponse({"ok": True})


@router.post("/manage/games/{game_id}/attendees/{attendee_id}/toggle-lock")
async def toggle_attendee_lock(request: Request, game_id: int, attendee_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE game_attendee SET locked = NOT locked WHERE id = ? AND game_id = ?", (attendee_id, game_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)
