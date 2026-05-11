from fastapi import Request
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


def is_superadmin(user):
    return user and dict(user).get("role") == "superadmin"
