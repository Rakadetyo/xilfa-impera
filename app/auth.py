from passlib.hash import bcrypt
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from app.database import get_db

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.verify(plain, hashed)

def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    return user

def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
