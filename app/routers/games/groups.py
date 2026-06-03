from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user

router = APIRouter()


@router.post("/manage/games/{game_id}/groups")
async def create_group(request: Request, game_id: int, name: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO game_player_group (game_id, name) VALUES (?, ?)", (game_id, name))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)


@router.post("/manage/games/{game_id}/groups/{group_id}/delete")
async def delete_group(request: Request, game_id: int, group_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_player_group WHERE id = ? AND game_id = ?", (group_id, game_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)


@router.post("/manage/games/{game_id}/groups/{group_id}/members")
async def add_group_member(request: Request, game_id: int, group_id: int, player_id: int = Form(...)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()

    # Get game's players_per_team setting
    cursor.execute("SELECT players_per_team FROM game WHERE id = ?", (game_id,))
    game = cursor.fetchone()
    players_per_team = game["players_per_team"] if game else 5

    # Verify group belongs to this game
    cursor.execute("SELECT id FROM game_player_group WHERE id = ? AND game_id = ?", (group_id, game_id))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404)

    # Check current group size
    cursor.execute("SELECT COUNT(*) as cnt FROM game_player_group_members WHERE group_id = ?", (group_id,))
    current_count = cursor.fetchone()["cnt"]

    if current_count >= players_per_team:
        conn.close()
        return RedirectResponse(f"/manage/games/{game_id}?tab=teams&error=Group cannot exceed {players_per_team} players", status_code=302)

    cursor.execute(
        "INSERT OR IGNORE INTO game_player_group_members (group_id, player_id) VALUES (?, ?)",
        (group_id, player_id)
    )
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)


@router.post("/manage/games/{game_id}/groups/{group_id}/members/{player_id}/delete")
async def remove_group_member(request: Request, game_id: int, group_id: int, player_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM game_player_group_members WHERE group_id = ? AND player_id = ?",
        (group_id, player_id)
    )
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams#teams", status_code=302)
