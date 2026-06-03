from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from app.database import get_db


def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user


def is_superadmin(user) -> bool:
    return user and dict(user).get("role") == "superadmin"


def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_superadmin(request: Request):
    user = get_current_user(request)
    if not user or not is_superadmin(user):
        raise HTTPException(status_code=403, detail="Forbidden")
    return user
