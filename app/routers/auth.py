import bcrypt
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_db
from app.templating import templates

router = APIRouter()


@router.get("/setup/{token}", response_class=HTMLResponse)
async def setup_password_page(request: Request, token: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE invite_token = ?", (token,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return templates.TemplateResponse(request, "setup_password.html", {
            "request": request, "error": "Invalid or expired invite link.", "token": token, "invalid": True
        })
    return templates.TemplateResponse(request, "setup_password.html", {
        "request": request, "token": token, "username": row["username"], "error": None, "invalid": False
    })

@router.post("/setup/{token}", response_class=HTMLResponse)
async def setup_password(request: Request, token: str, password: str = Form(...), confirm_password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE invite_token = ?", (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return templates.TemplateResponse(request, "setup_password.html", {
            "request": request, "error": "Invalid or expired invite link.", "token": token, "invalid": True
        })

    username = row["username"]

    if password != confirm_password:
        return templates.TemplateResponse(request, "setup_password.html", {
            "request": request, "token": token, "username": username, "error": "Passwords don't match.", "invalid": False
        })

    if len(password) < 6:
        return templates.TemplateResponse(request, "setup_password.html", {
            "request": request, "token": token, "username": username, "error": "Password must be at least 6 characters.", "invalid": False
        })

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password_hash = ?, invite_token = NULL WHERE id = ?", (password_hash, row["id"]))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/masukgan?success=Password+set.+You+can+now+log+in.&username={row['username']}", status_code=302)

@router.get("/masukgan", response_class=HTMLResponse)
async def login_page(request: Request):
    error = request.query_params.get("error")
    success = request.query_params.get("success")
    prefill_username = request.query_params.get("username", "")
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": error, "success": success, "prefill_username": prefill_username})

@router.post("/masukgan")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return RedirectResponse("/masukgan?error=Invalid credentials", status_code=302)

    request.session["user_id"] = user["id"]
    return RedirectResponse("/manage", status_code=302)

@router.get("/joinbang", response_class=HTMLResponse)
async def register_page(request: Request):
    error = request.query_params.get("error")
    return templates.TemplateResponse(request, "register.html", {"request": request, "error": error})

@router.post("/joinbang")
async def register(request: Request, username: str = Form(...), password: str = Form(...)):
    if len(password) < 6:
        return RedirectResponse("/joinbang?error=Password must be at least 6 characters", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return RedirectResponse("/joinbang?error=Username already taken", status_code=302)

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash)
    )
    conn.commit()
    conn.close()

    return RedirectResponse("/masukgan?registered=1", status_code=302)

@router.post("/manage/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
