import secrets
import bcrypt
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user, is_superadmin
from app.templating import templates

router = APIRouter()


@router.get("/manage/users", response_class=HTMLResponse)
async def list_users(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, created_at, invite_token FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(request, "users.html", {
        "request": request,
        "user": user,
        "users": users,
        "active": "users",
        "new_invite_token": request.query_params.get("new_invite"),
        "new_invite_username": request.query_params.get("new_username"),
    })

@router.post("/manage/users")
async def create_user(request: Request, username: str = Form(...), role: str = Form("admin")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    if role == "superadmin" and not is_superadmin(user):
        return RedirectResponse("/manage/users?error=Only superadmin can create superadmin users", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return RedirectResponse("/manage/users?error=Username already taken", status_code=302)

    placeholder_hash = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode()
    invite_token = secrets.token_urlsafe(32)
    cursor.execute(
        "INSERT INTO users (username, password_hash, role, invite_token) VALUES (?, ?, ?, ?)",
        (username, placeholder_hash, role, invite_token)
    )
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/users?new_invite={invite_token}&new_username={username}", status_code=302)

@router.post("/manage/users/{user_id}/invite")
async def generate_user_invite(request: Request, user_id: int):
    user = get_current_user(request)
    if not user or not is_superadmin(user):
        return RedirectResponse("/manage/users?error=Unauthorized", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        return RedirectResponse("/manage/users?error=User not found", status_code=302)

    token = secrets.token_urlsafe(32)
    cursor.execute("UPDATE users SET invite_token = ? WHERE id = ?", (token, user_id))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/users?new_invite={token}&new_username={target['username']}", status_code=302)

@router.post("/manage/users/{user_id}/delete")
async def delete_user(request: Request, user_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    # Only superadmin can delete
    if not is_superadmin(user):
        return RedirectResponse("/manage/users?error=Only superadmin can delete users", status_code=302)

    # Cannot delete self
    if user["id"] == user_id:
        return RedirectResponse("/manage/users?error=Cannot delete yourself", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/users?success=User deleted", status_code=302)
