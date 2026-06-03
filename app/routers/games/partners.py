from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user

router = APIRouter()


@router.post("/manage/games/{game_id}/partners/{game_partner_id}/pay")
async def toggle_partner_payment(request: Request, game_id: int, game_partner_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE game_partner SET is_paid = 1 - is_paid WHERE id = ? AND game_id = ?",
        (game_partner_id, game_id)
    )
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=general", status_code=302)


@router.post("/manage/games/{game_id}/partners/{game_partner_id}/delete")
async def delete_game_partner(request: Request, game_id: int, game_partner_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_partner WHERE id = ? AND game_id = ?", (game_partner_id, game_id))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=general", status_code=302)


@router.post("/manage/games/{game_id}/partners/new")
async def add_partner(
    request: Request,
    game_id: int,
    partner_id: str = Form(""),
    partner_name: str = Form(""),
    types: str = Form(""),
    contact: str = Form(""),
    fee: float = Form(0),
    notes: str = Form(""),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    resolved_partner_id = int(partner_id) if partner_id.strip().isdigit() else None
    resolved_name = partner_name.strip()

    if resolved_partner_id and not resolved_name:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name, contact FROM partner WHERE id = ?", (resolved_partner_id,))
        master = cursor.fetchone()
        conn.close()
        if master:
            resolved_name = master["name"]
            if not contact:
                contact = master["contact"]

    conn = get_db()
    cursor = conn.cursor()
    # Use type (singular) for the required column
    partner_type = types if types else "partner"
    cursor.execute("""
        INSERT INTO game_partner (game_id, partner_id, name, type, types, contact, fee, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (game_id, resolved_partner_id, resolved_name, partner_type, types, contact, fee, notes))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=general", status_code=302)
