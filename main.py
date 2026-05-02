import os
from pathlib import Path
import bcrypt
import logging
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import shutil
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Impera")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
templates = Jinja2Templates(directory="app/templates")

from app.database import init_db, seed_admin, get_db

@app.on_event("startup")
async def startup():
    init_db()
    seed_admin()

# --- Helpers ---
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

def get_setting(page: str, section: str, key: str, default: str = ""):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM site_settings WHERE page = ? AND section = ? AND key = ?",
        (page, section, key)
    )
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def get_page_settings(page: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT section, key, value FROM site_settings WHERE page = ?",
        (page,)
    )
    rows = cursor.fetchall()
    conn.close()
    settings = {}
    for row in rows:
        if row["section"] not in settings:
            settings[row["section"]] = {}
        settings[row["section"]][row["key"]] = row["value"]
    return settings

def set_setting(page: str, section: str, key: str, value: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO site_settings (page, section, key, value) VALUES (?, ?, ?, ?)
           ON CONFLICT(page, section, key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
        (page, section, key, value)
    )
    conn.commit()
    conn.close()

# --- Public Routes ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    settings = get_page_settings("homepage")
    return templates.TemplateResponse(request, "index.html", {"request": request, "settings": settings})

@app.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.title, p.body, p.status, p.post_type, p.created_at, u.username,
               (SELECT filename FROM post_images WHERE post_id = p.id ORDER BY display_order LIMIT 1) as cover_image
        FROM posts p
        JOIN users u ON p.author_id = u.id
        WHERE p.status = 'published'
        ORDER BY p.created_at DESC
    """)
    posts = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(request, "blog.html", {"request": request, "posts": posts})

@app.get("/api/blog/{post_id}")
async def get_post(post_id: int):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.id, p.title, p.body, p.summary, p.post_type, p.status, p.created_at, p.updated_at, u.username
        FROM posts p
        JOIN users u ON p.author_id = u.id
        WHERE p.id = ?
    """, (post_id,))
    post = cursor.fetchone()

    if not post:
        conn.close()
        raise HTTPException(status_code=404, detail="Post not found")

    cursor.execute("""
        SELECT id, filename FROM post_images
        WHERE post_id = ?
        ORDER BY display_order
    """, (post_id,))
    images = cursor.fetchall()
    conn.close()

    return JSONResponse({
        "id": post["id"],
        "title": post["title"],
        "body": post["body"],
        "summary": post["summary"],
        "post_type": post["post_type"],
        "status": post["status"],
        "author": post["username"],
        "created_at": post["created_at"],
        "updated_at": post["updated_at"],
        "images": [{"id": img["id"], "filename": img["filename"]} for img in images]
    })

# --- Auth Routes ---
@app.get("/masukgan", response_class=HTMLResponse)
async def login_page(request: Request):
    error = request.query_params.get("error")
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": error})

@app.post("/masukgan")
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

# --- Register Routes ---
@app.get("/joinbang", response_class=HTMLResponse)
async def register_page(request: Request):
    error = request.query_params.get("error")
    return templates.TemplateResponse(request, "register.html", {"request": request, "error": error})

@app.post("/joinbang")
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

@app.post("/manage/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)

# --- User Management Routes ---
@app.get("/manage/users", response_class=HTMLResponse)
async def list_users(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(request, "users.html", {
        "request": request,
        "user": user,
        "users": users
    })

@app.post("/manage/users")
async def create_user(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("admin")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    # Only superadmin can create superadmin
    if role == "superadmin" and not is_superadmin(user):
        return RedirectResponse("/manage/users?error=Only superadmin can create superadmin users", status_code=302)

    if len(password) < 6:
        return RedirectResponse("/manage/users?error=Password must be at least 6 characters", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return RedirectResponse("/manage/users?error=Username already taken", status_code=302)

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    cursor.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, password_hash, role)
    )
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/users?success=User created", status_code=302)

@app.post("/manage/users/{user_id}/delete")
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

# --- Player Management Routes ---
@app.get("/manage/players", response_class=HTMLResponse)
async def list_players(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    # Get query params
    search = request.query_params.get("search", "").strip()
    filter_pos = request.query_params.get("position", "")
    filter_skill = request.query_params.get("skill", "")
    filter_status = request.query_params.get("status", "")
    sort_by = request.query_params.get("sort", "name")
    sort_order = request.query_params.get("order", "asc")
    page = int(request.query_params.get("page", 1))
    per_page = int(request.query_params.get("per_page", 10))
    if per_page == 100:
        per_page = 1000000  # "All"

    # Validate sort
    allowed_sorts = {"name", "nickname", "skill_level", "join_date", "last_played"}
    if sort_by not in allowed_sorts:
        sort_by = "name"
    if sort_order not in {"asc", "desc"}:
        sort_order = "asc"

    conn = get_db()
    cursor = conn.cursor()

    # Build dynamic query
    query = """
        SELECT p.id, p.name, p.nickname, p.position_1, p.position_2, p.skill_level, p.contact_no, p.instagram, p.reclub, p.join_date, p.created_at, p.status,
               (SELECT MAX(g.datetime) FROM game_attendee ga JOIN game g ON ga.game_id = g.id WHERE ga.player_id = p.id) as last_played
        FROM player p
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND (p.name LIKE ? OR p.nickname LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    if filter_pos:
        query += " AND (p.position_1 = ? OR p.position_2 = ?)"
        params.extend([filter_pos, filter_pos])

    if filter_skill:
        query += " AND p.skill_level = ?"
        params.append(int(filter_skill))

    if filter_status:
        query += " AND p.status = ?"
        params.append(int(filter_status))

    # Handle last_played sort (needs subquery)
    if sort_by == "last_played":
        query += f" ORDER BY last_played {sort_order}"
    else:
        query += f" ORDER BY p.{sort_by} {sort_order}"

    # Get total count - build separate count query
    count_query = "SELECT COUNT(*) as cnt FROM player p WHERE 1=1"
    count_params = []
    if search:
        count_query += " AND (p.name LIKE ? OR p.nickname LIKE ?)"
        count_params.extend([f"%{search}%", f"%{search}%"])
    if filter_pos:
        count_query += " AND (p.position_1 = ? OR p.position_2 = ?)"
        count_params.extend([filter_pos, filter_pos])
    if filter_skill:
        count_query += " AND p.skill_level = ?"
        count_params.append(int(filter_skill))

    cursor.execute(count_query, count_params)
    total_count = cursor.fetchone()["cnt"]

    # Add limit/offset
    offset = (page - 1) * per_page
    query += f" LIMIT {per_page} OFFSET {offset}"

    cursor.execute(query, params)
    players = cursor.fetchall()

    # Stats
    cursor.execute("SELECT COUNT(*) as total FROM player")
    total_players = cursor.fetchone()["total"]

    cursor.execute("SELECT AVG(skill_level) as avg_skill FROM player")
    avg_skill = cursor.fetchone()["avg_skill"] or 0

    # Position counts (both position_1 and position_2)
    cursor.execute("""
        SELECT position_1 as pos FROM player WHERE position_1 != ''
    """)
    pos1_rows = cursor.fetchall()
    cursor.execute("""
        SELECT position_2 as pos FROM player WHERE position_2 != ''
    """)
    pos2_rows = cursor.fetchall()

    position_dict = {}
    for row in pos1_rows:
        pos = row["pos"]
        position_dict[pos] = position_dict.get(pos, 0) + 1
    for row in pos2_rows:
        pos = row["pos"]
        position_dict[pos] = position_dict.get(pos, 0) + 1

    position_dict_1 = {}
    for row in pos1_rows:
        pos = row["pos"]
        position_dict_1[pos] = position_dict_1.get(pos, 0) + 1

    position_dict_2 = {}
    for row in pos2_rows:
        pos = row["pos"]
        position_dict_2[pos] = position_dict_2.get(pos, 0) + 1

    # Skill level distribution
    cursor.execute("""
        SELECT skill_level, COUNT(*) as cnt FROM player GROUP BY skill_level
    """)
    skill_counts = cursor.fetchall()

    conn.close()

    return templates.TemplateResponse(request, "players.html", {
        "request": request,
        "user": user,
        "players": players,
        "filters": {
            "search": search,
            "position": filter_pos,
            "skill": filter_skill,
            "status": filter_status,
            "sort": sort_by,
            "order": sort_order
        },
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total_count,
            "total_pages": (total_count + per_page - 1) // per_page
        },
        "stats": {
            "total": total_players,
            "avg_skill": round(avg_skill, 1),
            "positions": position_dict,
            "positions_1": position_dict_1,
            "positions_2": position_dict_2,
            "skill_dist": {row["skill_level"]: row["cnt"] for row in skill_counts}
        }
    })

@app.post("/manage/players")
async def create_player(
    request: Request,
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

    conn.commit()
    conn.close()

    return RedirectResponse("/manage/players?success=Player added", status_code=302)

@app.post("/manage/players/{player_id}")
async def update_player(
    request: Request,
    player_id: int,
    name: str = Form(...),
    nickname: str = Form(""),
    position_1: str = Form(""),
    position_2: str = Form(""),
    skill_level: int = Form(3),
    contact_no: str = Form(""),
    instagram: str = Form(""),
    reclub: str = Form(""),
    join_date: str = Form(""),
    status: int = Form(1),
    page: int = Form(1),
    sort: str = Form("name"),
    order: str = Form("asc"),
    search: str = Form(""),
    position: str = Form(""),
    skill: str = Form("")
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

    cursor.execute("""
        UPDATE player SET name = ?, nickname = ?, position_1 = ?, position_2 = ?, skill_level = ?, contact_no = ?, instagram = ?, reclub = ?, join_date = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (name, nickname, position_1, position_2, skill_level, contact_no, instagram, reclub, join_date or None, status, player_id))
    conn.commit()
    conn.close()

    redirect_url = f"/manage/players?success=Player updated&page={page}&sort={sort}&order={order}"
    if search:
        redirect_url += f"&search={search}"
    if position:
        redirect_url += f"&position={position}"
    if skill:
        redirect_url += f"&skill={skill}"

    return RedirectResponse(redirect_url, status_code=302)

@app.post("/manage/players/{player_id}/delete")
async def delete_player(request: Request, player_id: int, page: int = Form(1), sort: str = Form("name"), order: str = Form("asc"), search: str = Form(""), position: str = Form(""), skill: str = Form(""), member: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    if not is_superadmin(user):
        return RedirectResponse("/manage/players?error=Only superadmin can delete players", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM player WHERE id = ?", (player_id,))
    conn.commit()
    conn.close()

    # Build redirect URL with current filters
    redirect_url = f"/manage/players?success=Player deleted&page={page}&sort={sort}&order={order}"
    if search:
        redirect_url += f"&search={search}"
    if position:
        redirect_url += f"&position={position}"
    if skill:
        redirect_url += f"&skill={skill}"
    if member:
        redirect_url += f"&member={member}"

    return RedirectResponse(redirect_url, status_code=302)

# --- Admin Routes ---
@app.get("/manage", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    # Get stats
    cursor.execute("SELECT COUNT(*) as total FROM player")
    total_players = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM player WHERE status = 1")
    active_players = cursor.fetchone()["total"]

    import datetime
    now = datetime.datetime.now()
    current_period = f"{now.year}-{now.month:02d}"
    cursor.execute("SELECT COUNT(*) as total FROM member WHERE member_period = ?", (current_period,))
    members_this_month = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM arena")
    total_arenas = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM game WHERE datetime >= date('now', '-30 days')")
    recent_games = cursor.fetchone()["total"]

    conn.close()

    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "user": user,
        "stats": {
            "total_players": total_players,
            "active_players": active_players,
            "members_this_month": members_this_month,
            "total_arenas": total_arenas,
            "recent_games": recent_games
        }
    })

@app.get("/manage/posts", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.title, p.status, p.created_at, u.username,
               (SELECT COUNT(*) FROM post_images WHERE post_id = p.id) as image_count
        FROM posts p
        JOIN users u ON p.author_id = u.id
        ORDER BY p.created_at DESC
    """)
    posts = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) as total FROM posts")
    total = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) as total FROM posts WHERE status = 'draft'")
    drafts = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) as total FROM posts WHERE status = 'published'")
    published = cursor.fetchone()["total"]
    conn.close()

    return templates.TemplateResponse(request, "admin.html", {
        "request": request,
        "user": user,
        "posts": posts,
        "stats": {"total": total, "drafts": drafts, "published": published}
    })

@app.get("/manage/new", response_class=HTMLResponse)
async def new_post_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)
    return templates.TemplateResponse(request, "post_form.html", {"request": request, "post": None, "user": user})

@app.post("/manage/posts")
async def create_post(request: Request, title: str = Form(...), body: str = Form(...), summary: str = Form(""), post_type: str = Form("HIGHLIGHT"), status: str = Form("draft")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO posts (title, body, summary, post_type, author_id, status) VALUES (?, ?, ?, ?, ?, ?)",
        (title, body, summary, post_type, user["id"], status)
    )
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/posts/{post_id}", status_code=302)

@app.get("/manage/posts/{post_id}", response_class=HTMLResponse)
async def edit_post_page(request: Request, post_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
    post = cursor.fetchone()

    if not post:
        conn.close()
        raise HTTPException(status_code=404, detail="Post not found")

    cursor.execute("SELECT * FROM post_images WHERE post_id = ? ORDER BY display_order", (post_id,))
    images = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(request, "post_form.html", {
        "request": request,
        "post": post,
        "images": images,
        "user": user
    })

@app.post("/manage/posts/{post_id}")
async def update_post(request: Request, post_id: int, title: str = Form(...), body: str = Form(...), summary: str = Form(""), post_type: str = Form("HIGHLIGHT"), status: str = Form("draft")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE posts SET title = ?, body = ?, summary = ?, post_type = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (title, body, summary, post_type, status, post_id)
    )
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/posts/{post_id}", status_code=302)

@app.post("/manage/posts/{post_id}/images")
async def upload_image(request: Request, post_id: int, image: UploadFile = File(...)):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    upload_dir = Path("app/static/img/comics")
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(image.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Invalid image format")

    filename = f"{uuid.uuid4()}{ext}"
    filepath = upload_dir / filename

    with open(filepath, "wb") as f:
        shutil.copyfileobj(image.file, f)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(display_order), -1) + 1 as next_order FROM post_images WHERE post_id = ?", (post_id,))
    next_order = cursor.fetchone()["next_order"]
    cursor.execute(
        "INSERT INTO post_images (post_id, filename, display_order) VALUES (?, ?, ?)",
        (post_id, filename, next_order)
    )
    conn.commit()
    conn.close()

    return JSONResponse({"filename": filename, "id": cursor.lastrowid})

@app.post("/manage/posts/{post_id}/delete")
async def delete_post(request: Request, post_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT filename FROM post_images WHERE post_id = ?", (post_id,))
    images = cursor.fetchall()

    for img in images:
        filepath = Path(f"app/static/img/comics/{img['filename']}")
        if filepath.exists():
            filepath.unlink()

    cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/manage", status_code=302)

# --- Members ---
@app.get("/manage/members", response_class=HTMLResponse)
async def members_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    import datetime
    now = datetime.datetime.now()
    filter_month = request.query_params.get("month", now.month)
    filter_year = request.query_params.get("year", now.year)

    try:
        filter_month = int(filter_month)
        filter_year = int(filter_year)
    except (ValueError, TypeError):
        filter_month = now.month
        filter_year = now.year

    conn = get_db()
    cursor = conn.cursor()

    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    member_period = f"{months[filter_month - 1]} {filter_year}"

    # Get members for selected period
    cursor.execute("""
        SELECT m.id, m.player_id, m.member_start_date, m.member_end_date, m.is_paid, m.membership_price, m.member_period,
               p.name, p.nickname,
               (SELECT COUNT(*) FROM member m2 WHERE m2.player_id = m.player_id) as n_members,
               (SELECT m2.member_period FROM member m2 WHERE m2.player_id = m.player_id AND m2.member_period < m.member_period ORDER BY m2.member_period DESC LIMIT 1) as last_member_period
        FROM member m
        JOIN player p ON m.player_id = p.id
        WHERE m.member_period = ?
        ORDER BY p.name ASC
    """, (member_period,))

    members = cursor.fetchall()

    # Get all players for the dropdown
    cursor.execute("SELECT id, name, nickname FROM player ORDER BY name")
    players = cursor.fetchall()

    # Analytics
    # 1. Total members this period + total unique all time
    cursor.execute("SELECT COUNT(*) as cnt FROM member WHERE member_period = ?", (member_period,))
    active_this_month = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(DISTINCT player_id) as cnt FROM member")
    total_unique = cursor.fetchone()["cnt"]

    # 2. Paid vs Unpaid + Total Income this period
    cursor.execute("""
        SELECT COUNT(*) as cnt, SUM(CASE WHEN is_paid = 1 THEN 1 ELSE 0 END) as paid_cnt,
               SUM(CASE WHEN is_paid = 1 THEN COALESCE(membership_price, 0) ELSE 0 END) as total_income
        FROM member
        WHERE member_period = ?
    """, (member_period,))
    paid_stats = cursor.fetchone()
    paid_count = paid_stats["paid_cnt"] or 0
    unpaid_count = (paid_stats["cnt"] or 0) - paid_count
    total_income = paid_stats["total_income"] or 0

    # 3. New members this period (count of members with this period)
    new_this_month = active_this_month

    # Retention Rate (members who were also active in previous period)
    prev_month = filter_month - 1
    prev_year = filter_year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    prev_period = f"{months[prev_month - 1]} {prev_year}"

    cursor.execute("SELECT COUNT(*) as cnt FROM member WHERE member_period = ?", (prev_period,))
    prev_active = cursor.fetchone()["cnt"]

    if prev_active > 0:
        retention_rate = round((active_this_month / prev_active) * 100, 1)
    else:
        retention_rate = 0

    # Avg member per month (all time)
    cursor.execute("""
        SELECT DISTINCT member_period FROM member WHERE member_period IS NOT NULL ORDER BY member_period
    """)
    all_periods = cursor.fetchall()
    if all_periods:
        def parse_period(p):
            # Handle "Month Year" format
            months_map = {'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
                         'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12}
            if '-' in p:
                parts = p.split('-')
                return int(parts[0]), int(parts[1])
            else:
                parts = p.split()
                return int(parts[1]), months_map.get(parts[0], 1)

        min_period = all_periods[0]["member_period"]
        max_period = all_periods[-1]["member_period"]
        min_year, min_month = parse_period(min_period)
        max_year, max_month = parse_period(max_period)
        months_span = (max_year - min_year) * 12 + (max_month - min_month) + 1
        if months_span > 0:
            avg_per_month = round(total_unique / months_span, 1)
        else:
            avg_per_month = total_unique
    else:
        avg_per_month = 0

    stats = {
        "active_this_month": active_this_month,
        "total_unique": total_unique,
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "total_income": total_income,
        "new_this_month": new_this_month,
        "retention_rate": retention_rate,
        "avg_per_month": avg_per_month
    }

    conn.close()

    # Pad to 15 rows if empty
    while len(members) < 15:
        members.append(None)

    # Generate month/year options
    months = [(i, datetime.date(2000, i, 1).strftime("%B")) for i in range(1, 13)]
    years = [now.year - i for i in range(5)] + [now.year + 1]

    return templates.TemplateResponse(request, "members.html", {
        "request": request,
        "user": user,
        "members": members,
        "players": players,
        "stats": stats,
        "filter_month": filter_month,
        "filter_year": filter_year,
        "months": months,
        "years": years
    })

@app.post("/manage/members/{member_id}/toggle-paid")
async def toggle_member_paid(request: Request, member_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()
    is_paid = data.get("is_paid", 0)

    username = user["username"]
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE member SET is_paid = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (is_paid, member_id))
        logger.info(f"[MEMBER] TOGGLE_PAID: member_id={member_id}, is_paid={is_paid}, by={username}")
        conn.commit()
        conn.close()
        return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"[MEMBER] TOGGLE_PAID ERROR: member_id={member_id}, by={username}, error={str(e)}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/manage/members")
async def create_member(request: Request, player_id: int = Form(...), member_start_date: str = Form(...), member_end_date: str = Form(None), membership_price: float = Form(None), is_paid: bool = Form(False), month: int = Form(1), year: int = Form(2024)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    # Generate member_period in "Month Year" format
    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    member_period = f"{months[month - 1]} {year}"

    conn = get_db()
    cursor = conn.cursor()

    # Check if member exists for this period
    cursor.execute("SELECT id FROM member WHERE player_id = ? AND member_period = ?", (player_id, member_period))
    existing = cursor.fetchone()

    username = user["username"]
    try:
        if existing:
            cursor.execute(
                """UPDATE member SET member_start_date = ?, member_end_date = ?, membership_price = ?, is_paid = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE player_id = ? AND member_period = ?""",
                (member_start_date, member_end_date if member_end_date else None, membership_price if membership_price is not None else 0, 1 if is_paid else 0, player_id, member_period)
            )
            logger.info(f"[MEMBER] UPDATE: player_id={player_id}, period={member_period}, start={member_start_date}, end={member_end_date}, price={membership_price}, paid={is_paid}, by={username}")
        else:
            # Check member limit (max 25 per period)
            cursor.execute("SELECT COUNT(*) as total FROM member WHERE member_period = ?", (member_period,))
            member_count = cursor.fetchone()["total"]

            if member_count >= 25:
                conn.close()
                return RedirectResponse(f"/manage/members?error=Member limit reached for {member_period} (max 25)&month={month}&year={year}", status_code=302)

            cursor.execute(
                """INSERT INTO member (player_id, member_period, member_start_date, member_end_date, membership_price, is_paid)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (player_id, member_period, member_start_date, member_end_date if member_end_date else None, membership_price if membership_price is not None else 0, 1 if is_paid else 0)
            )
            logger.info(f"[MEMBER] CREATE: player_id={player_id}, period={member_period}, start={member_start_date}, end={member_end_date}, price={membership_price}, paid={is_paid}, by={username}")
        conn.commit()
        conn.close()
        return RedirectResponse(f"/manage/members?month={month}&year={year}", status_code=302)
    except Exception as e:
        logger.error(f"[MEMBER] CREATE/UPDATE ERROR: player_id={player_id}, period={member_period}, by={username}, error={str(e)}")
        conn.close()
        return RedirectResponse(f"/manage/members?error=Operation failed: {str(e)}&month={month}&year={year}", status_code=302)

# --- WhatsApp Import ---
@app.post("/api/import-whatsapp-members")
async def import_whatsapp_members(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()
    chat_text = data.get("chat_text", "")
    filter_month = data.get("month")
    filter_year = data.get("year")

    import re
    from datetime import datetime
    import calendar

    # Find the member list section
    lines = chat_text.split('\n')
    members = []

    # Pattern: number. name price or number. name  price
    member_pattern = re.compile(r'^\d+[.)\s]+(.+?)\s+(\d+)\s*$')

    for line in lines:
        line = line.strip()
        # Remove emoji/特殊characters at start
        line = re.sub(r'^[​-‏ - ]', '', line)
        match = member_pattern.match(line)
        if match:
            name = match.group(1).strip()
            # Remove any trailing punctuation
            name = re.sub(r'[^\w\s]', '', name).strip()
            price_thousands = int(match.group(2))
            price = price_thousands * 1000
            members.append((name, price))

    if not members:
        return JSONResponse({"error": "No members found in chat text. Make sure the format is: 1. Name 250"}, status_code=400)

    conn = get_db()
    cursor = conn.cursor()

    # Get first and last Saturday of the month
    last_day = calendar.monthrange(filter_year, filter_month)[1]

    first_saturday = None
    for day in range(1, 8):
        if datetime(filter_year, filter_month, day).weekday() == 5:
            first_saturday = day
            break

    last_saturday = None
    for day in range(last_day, last_day - 7, -1):
        if datetime(filter_year, filter_month, day).weekday() == 5:
            last_saturday = day
            break

    start_date = f"{filter_year}-{filter_month:02d}-{first_saturday:02d}"
    end_date = f"{filter_year}-{filter_month:02d}-{last_saturday:02d}"
    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    member_period = f"{months[filter_month - 1]} {filter_year}"

    # Build preview list
    preview = []
    for name, price in members:
        # Find player by name (case insensitive)
        cursor.execute("SELECT id, name, nickname FROM player WHERE LOWER(name) = LOWER(?)", (name,))
        player = cursor.fetchone()

        if not player:
            # Try nickname
            cursor.execute("SELECT id, name, nickname FROM player WHERE LOWER(nickname) = LOWER(?)", (name,))
            player = cursor.fetchone()

        if player:
            # Check if member already exists for this period
            cursor.execute("""
                SELECT id FROM member
                WHERE player_id = ? AND member_start_date = ? AND member_end_date = ?
            """, (player["id"], start_date, end_date))
            existing = cursor.fetchone()

            preview.append({
                "name": name,
                "found": True,
                "player_id": player["id"],
                "price": price,
                "existing": existing is not None,
                "display_name": player["name"]
            })
        else:
            preview.append({
                "name": name,
                "found": False,
                "player_id": None,
                "price": price,
                "existing": False,
                "display_name": name
            })

    # Get all players for dropdown
    cursor.execute("SELECT id, name, nickname FROM player ORDER BY name")
    all_players = [{"id": p["id"], "name": p["name"], "nickname": p.get("nickname")} for p in cursor.fetchall()]

    conn.close()

    return JSONResponse({
        "preview": preview,
        "start_date": start_date,
        "end_date": end_date,
        "member_period": member_period,
        "all_players": all_players
    })

@app.post("/api/import-whatsapp-members/confirm")
async def import_whatsapp_members_confirm(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()
    members_data = data.get("members", [])
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    member_period = data.get("member_period")

    if not members_data or not start_date or not end_date:
        return JSONResponse({"error": "Missing data"}, status_code=400)

    # Derive member_period from start_date if not provided (format: "Month Year")
    if not member_period and start_date:
        parts = start_date.split("-")
        if len(parts) >= 2:
            months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
            try:
                month_idx = int(parts[1]) - 1
                member_period = f"{months[month_idx]} {parts[0]}"
            except:
                member_period = ""

    if not member_period:
        return JSONResponse({"error": "Missing data"}, status_code=400)

    username = user["username"]
    try:
        conn = get_db()
        cursor = conn.cursor()

        imported = 0
        for member in members_data:
            if not member.get("found"):
                continue

            player_id = member.get("player_id")
            if not player_id:
                continue

            price = member.get("price")

            # Check if exists, then update or insert
            cursor.execute("SELECT id FROM member WHERE player_id = ? AND member_period = ?", (player_id, member_period))
            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE member SET membership_price = ?, is_paid = 0, member_start_date = ?, member_end_date = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE player_id = ? AND member_period = ?
                """, (price, start_date, end_date, player_id, member_period))
                logger.info(f"[MEMBER] WHATSAPP UPDATE: player_id={player_id}, period={member_period}, price={price}, by={username}")
            else:
                cursor.execute("""
                    INSERT INTO member (player_id, member_period, member_start_date, member_end_date, membership_price, is_paid)
                    VALUES (?, ?, ?, ?, ?, 0)
                """, (player_id, member_period, start_date, end_date, price))
                logger.info(f"[MEMBER] WHATSAPP CREATE: player_id={player_id}, period={member_period}, price={price}, by={username}")
            imported += 1

        conn.commit()
        conn.close()
        return JSONResponse({"imported": imported})
    except Exception as e:
        logger.error(f"[MEMBER] WHATSAPP IMPORT ERROR: period={member_period}, by={username}, error={str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

# --- Generate WhatsApp Chat ---
@app.get("/api/generate-whatsapp-chat")
async def generate_whatsapp_chat(request: Request, month: int, year: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    import calendar
    from datetime import datetime

    # Get first and last Saturday
    last_day = calendar.monthrange(year, month)[1]

    first_saturday = None
    for day in range(1, 8):
        if datetime(year, month, day).weekday() == 5:
            first_saturday = day
            break

    last_saturday = None
    for day in range(last_day, last_day - 7, -1):
        if datetime(year, month, day).weekday() == 5:
            last_saturday = day
            break

    start_date = f"{year}-{month:02d}-{first_saturday:02d}"
    end_date = f"{year}-{month:02d}-{last_saturday:02d}"

    month_names = ["", "JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"]
    month_name = month_names[month]

    conn = get_db()
    cursor = conn.cursor()

    # Get members active in this month
    first_of_month = f"{year}-{month:02d}-01"
    last_of_month = f"{year}-{month:02d}-{last_day}"

    cursor.execute("""
        SELECT m.id, m.player_id, m.membership_price, m.is_paid, p.name
        FROM member m
        JOIN player p ON m.player_id = p.id
        WHERE m.member_start_date <= ? AND (m.member_end_date IS NULL OR m.member_end_date >= ?)
        ORDER BY p.name ASC
    """, (last_of_month, first_of_month))

    members = cursor.fetchall()
    conn.close()

    # Build simple list: name price
    lines = []
    for i, m in enumerate(members, 1):
        name = m["name"]
        price_k = int(m["membership_price"] // 1000)
        is_paid = m["is_paid"]
        if is_paid:
            lines.append(f"{i}. {name} 💸")
        else:
            lines.append(f"{i}. {name} {price_k}")

    return JSONResponse({
        "chat_text": "\n".join(lines)
    })

# --- Arena ---
@app.get("/api/resolve-google-maps")
async def resolve_google_maps(url: str):
    import urllib.request
    from urllib.parse import urlparse, parse_qs, unquote
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            final_url = response.geturl()

            parsed = urlparse(final_url)
            path = parsed.path
            query = parse_qs(parsed.query)

            location_name = ""
            address = ""

            # Check for place URL format: /place/Name/@...
            if '/place/' in path:
                match = path.split('/place/')
                if len(match) > 1:
                    name_part = match[1].split('/')[0]
                    location_name = unquote(name_part).replace('+', ' ')
            # Check for search URL format (short URL redirect)
            elif '/search' in path and 'q' in query:
                location_name = unquote(query['q'][0])

            # Try to get address from various query params
            if 'daddr' in query:
                address = unquote(query['daddr'][0])
            elif 'q' in query and location_name != unquote(query['q'][0]):
                # If q is different from location_name, it might be the address
                q_val = unquote(query['q'][0])
                if ',' in q_val:  # Address typically has comma
                    address = q_val

            return JSONResponse({
                "location_name": location_name.strip(),
                "address": address.strip(),
                "url": final_url
            })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
@app.get("/manage/arena", response_class=HTMLResponse)
async def arena_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM arena ORDER BY location_name")
    arenas = cursor.fetchall()

    # Stats
    cursor.execute("SELECT COUNT(*) as cnt FROM arena")
    total_arenas = cursor.fetchone()["cnt"]
    cursor.execute("SELECT SUM(price) as total FROM arena")
    total_price = cursor.fetchone()["total"] or 0
    cursor.execute("SELECT COUNT(DISTINCT arena_id) as cnt FROM game WHERE arena_id IS NOT NULL")
    arenas_played = cursor.fetchone()["cnt"]
    cursor.execute("""
        SELECT a.id, a.location_name, COUNT(g.id) as game_count
        FROM arena a
        LEFT JOIN game g ON a.id = g.arena_id
        GROUP BY a.id
        ORDER BY game_count DESC
    """)
    arena_rows = cursor.fetchall()
    arena_game_counts = {row["id"]: row["game_count"] for row in arena_rows}

    conn.close()

    return templates.TemplateResponse(request, "arena.html", {
        "request": request,
        "user": user,
        "arenas": arenas,
        "stats": {
            "total": total_arenas,
            "total_price": total_price,
            "arenas_played": arenas_played
        },
        "arena_game_counts": arena_game_counts,
        "arena_game_list": arena_rows
    })

# --- Page Settings ---
@app.get("/manage/page_settings/homepage", response_class=HTMLResponse)
async def page_settings(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    settings = get_page_settings("homepage")
    return templates.TemplateResponse(request, "page_settings.html", {
        "request": request,
        "user": user,
        "settings": settings
    })

@app.post("/manage/page_settings/homepage")
async def save_page_settings(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    form = await request.form()
    username = user["username"]

    try:
        for key, value in form.items():
            if key.startswith("hero_"):
                section = "hero"
                setting_key = key[5:]
            elif key.startswith("about_"):
                section = "about"
                setting_key = key[6:]
            elif key.startswith("schedule_"):
                section = "schedule"
                setting_key = key[9:]
            elif key.startswith("social_"):
                section = "social"
                setting_key = key[7:]
            else:
                continue

            set_setting("homepage", section, setting_key, value)

        logger.info(f"[PAGE_SETTINGS] Saved homepage settings by {username}")
        return RedirectResponse("/manage/page_settings/homepage?success=Settings saved", status_code=302)
    except Exception as e:
        logger.error(f"[PAGE_SETTINGS] Error saving settings by {username}: {str(e)}")
        return RedirectResponse(f"/manage/page_settings/homepage?error={str(e)}", status_code=302)

@app.get("/preview", response_class=HTMLResponse)
async def preview_homepage(request: Request):
    """Preview homepage with settings from query params (before saving)"""
    from urllib.parse import parse_qs

    qs = parse_qs(request.url.query)
    settings = {
        "hero": {},
        "about": {},
        "schedule": {},
        "social": {}
    }

    for key, values in qs.items():
        value = values[0] if values else ""
        if key.startswith("hero_"):
            settings["hero"][key[5:]] = value
        elif key.startswith("about_"):
            settings["about"][key[6:]] = value
        elif key.startswith("schedule_"):
            settings["schedule"][key[9:]] = value
        elif key.startswith("social_"):
            settings["social"][key[7:]] = value

    # Use defaults for empty values
    defaults = {
        "hero": {"youtube_video_id": "rBW1uZnZhbo", "headline": "IMPERA", "tagline": "BSD — Gading Serpong", "subtitle": "", "cta_primary_text": "Play With Us", "cta_primary_link": "#schedule", "cta_secondary_text": "Learn More", "cta_secondary_link": "#about", "logo": "/assets/impera-logo-only-white.png"},
        "about": {"title": "Built for Those Who Play.", "body": "", "stat_1_label": "Members", "stat_1_value": "90+", "stat_2_label": "Sessions", "stat_2_value": "100+", "stat_3_label": "Home Court", "stat_3_value": "Jetz", "stat_4_label": "Every Week", "stat_4_value": "SAT"},
        "schedule": {"day": "Saturday", "time": "18:00", "location": "BSD — Gading Serpong Area"},
        "social": {"instagram": "", "whatsapp": "", "reclub": ""}
    }

    for section in settings:
        for key in defaults[section]:
            if not settings[section].get(key):
                settings[section][key] = defaults[section][key]

    return templates.TemplateResponse(request, "index.html", {"request": request, "settings": settings})

@app.post("/manage/arena")
async def create_arena(request: Request, location_name: str = Form(...), address: str = Form(""), price: float = Form(0), contact_person: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO arena (location_name, address, price, contact_person) VALUES (?, ?, ?, ?)",
        (location_name, address, price, contact_person)
    )
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/arena", status_code=302)

@app.post("/manage/arena/{arena_id}")
async def update_arena(request: Request, arena_id: int, location_name: str = Form(...), address: str = Form(""), price: float = Form(0), contact_person: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE arena SET location_name = ?, address = ?, price = ?, contact_person = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (location_name, address, price, contact_person, arena_id)
    )
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/arena", status_code=302)

@app.post("/manage/arena/{arena_id}/delete")
async def delete_arena(request: Request, arena_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM arena WHERE id = ?", (arena_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/arena", status_code=302)

@app.post("/manage/members/{member_id}")
async def update_member(request: Request, member_id: int, player_id: int = Form(...), member_start_date: str = Form(...), member_end_date: str = Form(None), membership_price: float = Form(None), is_paid: bool = Form(False), month: int = Form(1), year: int = Form(2024)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    member_period = f"{year}-{month:02d}"
    username = user["username"]

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE member SET player_id = ?, member_period = ?, member_start_date = ?, member_end_date = ?, membership_price = ?, is_paid = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (player_id, member_period, member_start_date, member_end_date if member_end_date else None, membership_price if membership_price is not None else 0, 1 if is_paid else 0, member_id)
        )
        logger.info(f"[MEMBER] UPDATE: member_id={member_id}, player_id={player_id}, period={member_period}, start={member_start_date}, end={member_end_date}, price={membership_price}, paid={is_paid}, by={username}")
        conn.commit()
        conn.close()
        return RedirectResponse(f"/manage/members?month={month}&year={year}", status_code=302)
    except Exception as e:
        logger.error(f"[MEMBER] UPDATE ERROR: member_id={member_id}, by={username}, error={str(e)}")
        return RedirectResponse(f"/manage/members?error=Update failed: {str(e)}&month={month}&year={year}", status_code=302)

@app.post("/manage/members/{member_id}/delete")
async def delete_member(request: Request, member_id: int, month: int = Form(1), year: int = Form(2024)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    if not is_superadmin(user):
        return RedirectResponse(f"/manage/members?error=Only superadmin can delete members&month={month}&year={year}", status_code=302)

    username = user["username"]
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM member WHERE id = ?", (member_id,))
        logger.info(f"[MEMBER] DELETE: member_id={member_id}, by={username}")
        conn.commit()
        conn.close()
        return RedirectResponse(f"/manage/members?success=Member deleted&month={month}&year={year}", status_code=302)
    except Exception as e:
        logger.error(f"[MEMBER] DELETE ERROR: member_id={member_id}, by={username}, error={str(e)}")
        return RedirectResponse(f"/manage/members?error=Delete failed: {str(e)}&month={month}&year={year}", status_code=302)

@app.post("/manage/posts/{post_id}/toggle")
async def toggle_status(request: Request, post_id: int):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM posts WHERE id = ?", (post_id,))
    post = cursor.fetchone()

    if post:
        new_status = "draft" if post["status"] == "published" else "published"
        cursor.execute("UPDATE posts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, post_id))
        conn.commit()
    conn.close()

    return JSONResponse({"status": new_status})


# ============================================
# TEAM GENERATION ALGORITHM
# ============================================

def compute_player_values(attendees, skill_weight=0.6):
    """
    Returns {attendee_id: value_score (0-100)} relative to attending pool.
    skill_weight 0.0-1.0; remainder = position scarcity weight.
    """
    if not attendees:
        return {}
    position_weight = 1.0 - skill_weight
    skills = [a.get("skill_level") or 3 for a in attendees]
    min_s, max_s = min(skills), max(skills)
    skill_range = (max_s - min_s) or 1
    pos_counts = {}
    for a in attendees:
        pos = a.get("position_1") or "?"
        pos_counts[pos] = pos_counts.get(pos, 0) + 1
    total = len(attendees)
    result = {}
    for a in attendees:
        skill_pct = ((a.get("skill_level") or 3) - min_s) / skill_range
        pos = a.get("position_1") or "?"
        # "?" players counted in pool (hurts real position scarcity) but get 0 scarcity themselves
        pos_scarcity = (1.0 - (pos_counts[pos] / total)) if pos != "?" else 0.0
        result[a["id"]] = round((skill_pct * skill_weight + pos_scarcity * position_weight) * 100, 1)
    return result


def generate_balanced_teams(attendees, groups, num_teams, players_per_team, value_scores=None):
    """
    attendees: list of dicts with keys id, player_id, skill_level, position_1
    groups: list of dicts with keys id, name, member_attendee_ids (list of attendee ids)
    value_scores: {attendee_id: score} from compute_player_values — used to sort solos
    Returns: list of lists — team_assignments[team_idx] = [attendee_id, ...]
    """
    attendee_by_id = {a["id"]: a for a in attendees}
    attendee_skill = {a["id"]: (a.get("skill_level") or 3) for a in attendees}

    # Build set of attendee ids already in a group
    grouped_ids = set()
    for g in groups:
        for aid in g["member_attendee_ids"]:
            if aid in attendee_by_id:
                grouped_ids.add(aid)

    solo_attendees = [a for a in attendees if a["id"] not in grouped_ids]
    if value_scores:
        solo_attendees.sort(key=lambda a: -value_scores.get(a["id"], 0))
    else:
        solo_attendees.sort(key=lambda a: -(a.get("skill_level") or 3))

    # Assign groups to teams: strongest group assigned first, to team with lowest skill sum
    groups_sorted = sorted(
        groups,
        key=lambda g: sum(attendee_skill.get(aid, 3) for aid in g["member_attendee_ids"]),
        reverse=True
    )

    team_assignments = [[] for _ in range(num_teams)]
    team_group_counts = [0] * num_teams
    team_skill_sums = [0.0] * num_teams

    for group in groups_sorted:
        min_count = min(team_group_counts)
        eligible = [i for i, c in enumerate(team_group_counts) if c == min_count]
        target = min(eligible, key=lambda i: team_skill_sums[i])
        for aid in group["member_attendee_ids"]:
            if aid in attendee_by_id and len(team_assignments[target]) < players_per_team:
                team_assignments[target].append(aid)
                team_skill_sums[target] += attendee_skill.get(aid, 3)
        team_group_counts[target] += 1

    # Identify group vs no-group teams
    has_group = [team_group_counts[i] > 0 for i in range(num_teams)]
    no_group_teams = [i for i in range(num_teams) if not has_group[i]]
    # Highest skill group picks last-est within group teams
    group_teams = sorted(
        [i for i in range(num_teams) if has_group[i]],
        key=lambda i: team_skill_sums[i],
        reverse=True
    )

    solo_idx = 0
    round_num = 0
    max_rounds = (len(solo_attendees) + 1) * (num_teams + 1)

    while solo_idx < len(solo_attendees) and round_num < max_rounds:
        no_group_round = list(no_group_teams) if round_num % 2 == 0 else list(reversed(no_group_teams))
        round_order = no_group_round + group_teams
        picks_this_round = 0

        for team_idx in round_order:
            if solo_idx >= len(solo_attendees):
                break
            if len(team_assignments[team_idx]) >= players_per_team:
                continue

            # Group team skips until all open no-group teams have caught up
            if has_group[team_idx]:
                no_group_open = [i for i in no_group_teams if len(team_assignments[i]) < players_per_team]
                if no_group_open:
                    my_count = len(team_assignments[team_idx])
                    if min(len(team_assignments[i]) for i in no_group_open) < my_count:
                        continue

            team_assignments[team_idx].append(solo_attendees[solo_idx]["id"])
            team_skill_sums[team_idx] += attendee_skill.get(solo_attendees[solo_idx]["id"], 3)
            solo_idx += 1
            picks_this_round += 1

        if picks_this_round == 0:
            # Stuck: force-assign to any open team
            for team_idx in range(num_teams):
                if solo_idx >= len(solo_attendees):
                    break
                if len(team_assignments[team_idx]) < players_per_team:
                    team_assignments[team_idx].append(solo_attendees[solo_idx]["id"])
                    solo_idx += 1
            if picks_this_round == 0:
                break

        round_num += 1

    return team_assignments


# ============================================
# GAME MANAGEMENT ROUTES
# ============================================

@app.get("/manage/games")
async def list_games(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT g.*, a.location_name as arena_name,
               (SELECT COUNT(*) FROM game_attendee WHERE game_id = g.id) as attendee_count
        FROM game g
        LEFT JOIN arena a ON g.arena_id = a.id
        ORDER BY g.datetime ASC
    """)
    games = cursor.fetchall()

    cursor.execute("SELECT id, location_name FROM arena ORDER BY location_name")
    arenas = cursor.fetchall()

    conn.close()
    return templates.TemplateResponse(request, "games/list.html", {
        "user": user,
        "games": games,
        "arenas": arenas
    })


@app.get("/manage/games/new")
async def new_game(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, location_name FROM arena ORDER BY location_name")
    arenas = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(request, "games/new.html", {
        "user": user,
        "arenas": arenas
    })


@app.post("/manage/games/new")
async def create_game(
    request: Request,
    datetime: str = Form(...),
    arena_id: int = Form(None),
    price_per_person: float = Form(0),
    price_per_member: float = Form(0),
    duration_per_game: int = Form(8),
    session_duration: int = Form(120),
    max_players: int = Form(25),
    status: str = Form("open"),
    notes: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO game (datetime, arena_id, price_per_person, price_per_member,
                         duration_per_game, session_duration, max_players, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime, arena_id, price_per_person, price_per_member,
          duration_per_game, session_duration, max_players, status, notes))

    game_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}", status_code=302)


@app.get("/manage/games/{game_id}")
async def game_detail(request: Request, game_id: int, tab: str = "general", error: str = None):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT g.*, a.location_name as arena_name
        FROM game g
        LEFT JOIN arena a ON g.arena_id = a.id
        WHERE g.id = ?
    """, (game_id,))
    game = cursor.fetchone()

    if not game:
        conn.close()
        raise HTTPException(status_code=404, detail="Game not found")

    # Format title
    from datetime import datetime
    game_dict = dict(game)
    dt_str = game_dict["datetime"].replace("T", " ")
    if len(dt_str) == 16:
        dt_str += ":00"
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    game_dict["title"] = dt.strftime("%a, %d %b %Y") + " @ " + (game_dict["arena_name"] or "No arena")

    # Get attendees with player info
    cursor.execute("""
        SELECT ga.*, p.name, p.nickname, p.position_1, p.position_2, p.skill_level,
               gt.team_name as team_name_assigned, gt.team_color
        FROM game_attendee ga
        JOIN player p ON ga.player_id = p.id
        LEFT JOIN game_team gt ON ga.team_id = gt.id
        WHERE ga.game_id = ?
        ORDER BY p.name
    """, (game_id,))
    attendees = cursor.fetchall()

    # Auto-populate with current members if no attendees
    if not attendees:
        # Get current month period (e.g., "May 2026")
        from datetime import datetime
        now = datetime.now()
        months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
        current_period = f"{months[now.month - 1]} {now.year}"

        # Only insert players not already in game
        cursor.execute("""
            INSERT INTO game_attendee (game_id, player_id, is_paid, is_attend)
            SELECT ?, p.id, 0, 0
            FROM player p
            JOIN member m ON p.id = m.player_id
            WHERE p.status = 1
            AND m.member_period = ?
            AND p.id NOT IN (SELECT player_id FROM game_attendee WHERE game_id = ?)
        """, (game_id, current_period, game_id))
        conn.commit()

        # Refetch attendees after auto-populate
        cursor.execute("""
            SELECT ga.*, p.name, p.nickname, p.position_1, p.position_2, p.skill_level,
                   gt.team_name as team_name_assigned, gt.team_color
            FROM game_attendee ga
            JOIN player p ON ga.player_id = p.id
            LEFT JOIN game_team gt ON ga.team_id = gt.id
            WHERE ga.game_id = ?
            ORDER BY p.name
        """, (game_id,))
        attendees = cursor.fetchall()

    # Get partners
    cursor.execute("SELECT * FROM game_partner WHERE game_id = ?", (game_id,))
    partners = cursor.fetchall()

    # Get teams
    cursor.execute("SELECT * FROM game_team WHERE game_id = ?", (game_id,))
    teams = cursor.fetchall()

    # Get matches
    cursor.execute("""
        SELECT gm.*,
               th.team_name as home_team, th.team_color as home_color,
               ta.team_name as away_team, ta.team_color as away_color
        FROM game_match gm
        LEFT JOIN game_team th ON gm.team_home_id = th.id
        LEFT JOIN game_team ta ON gm.team_away_id = ta.id
        WHERE gm.game_id = ?
        ORDER BY gm.round_number, gm.match_order
    """, (game_id,))
    matches = cursor.fetchall()

    # Get all players for adding attendees - current members first
    cursor.execute("""
        SELECT p.*,
               CASE WHEN m.id IS NOT NULL AND m.member_start_date <= date('now') AND m.member_end_date >= date('now') THEN 1 ELSE 0 END as is_current_member
        FROM player p
        LEFT JOIN member m ON p.id = m.player_id
        WHERE p.status = 1
        ORDER BY is_current_member DESC, p.name
    """)
    all_players = cursor.fetchall()

    # Get arenas for dropdown
    cursor.execute("SELECT id, location_name FROM arena ORDER BY location_name")
    arenas = cursor.fetchall()

    # Get player groups with members (always fetched for teams tab)
    cursor.execute("SELECT * FROM game_player_group WHERE game_id = ? ORDER BY id", (game_id,))
    groups_raw = cursor.fetchall()
    groups = []
    grouped_player_ids = set()
    for g in groups_raw:
        cursor.execute("""
            SELECT gpm.player_id, p.name, p.skill_level, p.position_1, p.position_2
            FROM game_player_group_members gpm
            JOIN player p ON gpm.player_id = p.id
            WHERE gpm.group_id = ?
        """, (g["id"],))
        members = [dict(m) for m in cursor.fetchall()]
        groups.append({"id": g["id"], "name": g["name"], "members": members})
        for m in members:
            grouped_player_ids.add(m["player_id"])

    conn.close()

    # Compute per-player value scores relative to attending pool
    attendees_list = [dict(a) for a in attendees]
    skill_weight = float(game_dict.get("skill_weight") or 0.6)
    player_values = compute_player_values(attendees_list, skill_weight)

    # Compute balance scores if teams exist
    balance = None
    if teams:
        team_value_sums = []
        for team in teams:
            total_value = sum(
                player_values.get(a["id"], 0) for a in attendees_list if a.get("team_id") == team["id"]
            )
            team_value_sums.append(round(total_value, 1))
        if team_value_sums:
            skill_spread = max(team_value_sums) - min(team_value_sums)
            balance_score = max(0, round(100 - skill_spread, 1))
            balance = {
                "skill_spread": round(skill_spread, 1),
                "score": balance_score,
                "group_warning": skill_spread > 10 and bool(groups),
            }

    tabs = ["overview", "general", "players", "teams", "schedule", "results"]
    if tab not in tabs:
        tab = "overview"

    return templates.TemplateResponse(request, "games/detail.html", {
        "user": user,
        "game": game_dict,
        "game_datetime": game_dict.get("datetime", ""),
        "attendees": attendees,
        "partners": partners,
        "teams": teams,
        "matches": matches,
        "all_players": all_players,
        "arenas": arenas,
        "tab": tab,
        "tabs": tabs,
        "groups": groups,
        "grouped_player_ids": grouped_player_ids,
        "balance": balance,
        "player_values": player_values,
        "error": error,
    })


@app.get("/manage/games/{game_id}/edit")
async def edit_game(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM game WHERE id = ?", (game_id,))
    game = cursor.fetchone()

    cursor.execute("SELECT id, location_name FROM arena ORDER BY location_name")
    arenas = cursor.fetchall()

    conn.close()

    return templates.TemplateResponse(request, "games/edit.html", {
        "user": user,
        "game": game,
        "arenas": arenas
    })


@app.post("/manage/games/{game_id}/edit")
async def update_game(
    request: Request,
    game_id: int,
    datetime: str = Form(...),
    arena_id: int = Form(None),
    price_per_person: float = Form(0),
    price_per_member: float = Form(0),
    duration_per_game: int = Form(8),
    session_duration: int = Form(120),
    max_players: int = Form(25),
    status: str = Form("open"),
    notes: str = Form(""),
    is_video: bool = Form(False),
    is_photo: bool = Form(False),
    is_referee: bool = Form(False),
    add_partner: str = Form(None),
    partner_type: str = Form(None),
    partner_name: str = Form(None),
    partner_contact: str = Form(None),
    partner_fee: float = Form(0)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE game SET datetime = ?, arena_id = ?, price_per_person = ?,
                       price_per_member = ?, duration_per_game = ?,
                       session_duration = ?, max_players = ?, status = ?, notes = ?,
                       is_video = ?, is_photo = ?, is_referee = ?,
                       updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (datetime, arena_id, price_per_person, price_per_member,
          duration_per_game, session_duration, max_players, status, notes,
          1 if is_video else 0, 1 if is_photo else 0, 1 if is_referee else 0, game_id))

    # Handle add partner
    if add_partner and partner_type:
        cursor.execute("""
            INSERT INTO game_partner (game_id, type, name, contact, fee)
            VALUES (?, ?, ?, ?, ?)
        """, (game_id, partner_type, partner_name, partner_contact, partner_fee))
        conn.commit()

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}", status_code=302)


# --- Partners CRUD ---
@app.post("/manage/games/{game_id}/partners")
async def add_partner(
    request: Request,
    game_id: int,
    type: str = Form(...),
    name: str = Form(""),
    contact: str = Form(""),
    fee: float = Form(0),
    notes: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO game_partner (game_id, type, name, contact, fee, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (game_id, type, name, contact, fee, notes))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=partners", status_code=302)


@app.post("/manage/games/{game_id}/partners/{partner_id}/delete")
async def delete_partner(request: Request, game_id: int, partner_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_partner WHERE id = ? AND game_id = ?", (partner_id, game_id))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=partners", status_code=302)


# --- Attendees CRUD ---
@app.post("/manage/games/{game_id}/attendees")
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

    cursor.execute("INSERT INTO game_attendee (game_id, player_id) VALUES (?, ?)", (game_id, player_id))
    conn.commit()
    conn.close()

    return JSONResponse({"success": True})


@app.post("/manage/games/{game_id}/attendees/bulk")
async def add_attendees_bulk(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    form = await request.form()
    player_ids = form.getlist("player_ids")

    conn = get_db()
    cursor = conn.cursor()

    for player_id in player_ids:
        cursor.execute("SELECT id FROM game_attendee WHERE game_id = ? AND player_id = ?", (game_id, int(player_id)))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO game_attendee (game_id, player_id) VALUES (?, ?)", (game_id, int(player_id)))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=players", status_code=302)


@app.post("/manage/games/{game_id}/attendees/{attendee_id}/delete")
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


@app.post("/manage/games/{game_id}/attendees/{attendee_id}/pay")
async def toggle_payment(request: Request, game_id: int, attendee_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT is_paid FROM game_attendee WHERE id = ?", (attendee_id,))
    row = cursor.fetchone()
    if row:
        new_is_paid = 0 if row["is_paid"] else 1
        cursor.execute("UPDATE game_attendee SET is_paid = ? WHERE id = ?", (new_is_paid, attendee_id))
        conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=players", status_code=302)


@app.post("/manage/games/{game_id}/attendees/{attendee_id}/attend")
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

    return RedirectResponse(f"/manage/games/{game_id}?tab=players", status_code=302)


# --- Teams CRUD ---
@app.post("/manage/games/{game_id}/teams")
async def create_team(
    request: Request,
    game_id: int,
    team_name: str = Form(...),
    team_color: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO game_team (game_id, team_name, team_color) VALUES (?, ?, ?)",
                  (game_id, team_name, team_color))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=teams", status_code=302)


@app.post("/manage/games/{game_id}/teams/{team_id}/delete")
async def delete_team(request: Request, game_id: int, team_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    # Clear team_id from attendees first
    cursor.execute("UPDATE game_attendee SET team_id = NULL WHERE team_id = ?", (team_id,))
    cursor.execute("DELETE FROM game_team WHERE id = ? AND game_id = ?", (team_id, game_id))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=teams", status_code=302)


@app.post("/manage/games/{game_id}/attendees/{attendee_id}/assign-team")
async def assign_team(request: Request, game_id: int, attendee_id: int, team_id: int = Form(...)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE game_attendee SET team_id = ? WHERE id = ? AND game_id = ?",
                  (team_id, attendee_id, game_id))
    conn.commit()
    conn.close()

    if "application/json" in request.headers.get("Accept", "") or request.headers.get("X-Requested-With") == "fetch":
        return JSONResponse({"ok": True})
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams", status_code=302)


# --- Player Groups ---
@app.post("/manage/games/{game_id}/groups")
async def create_group(request: Request, game_id: int, name: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO game_player_group (game_id, name) VALUES (?, ?)", (game_id, name))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams", status_code=302)


@app.post("/manage/games/{game_id}/groups/{group_id}/delete")
async def delete_group(request: Request, game_id: int, group_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_player_group WHERE id = ? AND game_id = ?", (group_id, game_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams", status_code=302)


@app.post("/manage/games/{game_id}/groups/{group_id}/members")
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
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams", status_code=302)


@app.post("/manage/games/{game_id}/groups/{group_id}/members/{player_id}/delete")
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
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams", status_code=302)


# --- Team Generation ---
@app.post("/manage/games/{game_id}/teams/skill-weight")
async def update_skill_weight(
    request: Request,
    game_id: int,
    skill_weight_pct: int = Form(60),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    skill_weight = max(0.0, min(1.0, skill_weight_pct / 100))

    conn = get_db()
    cursor = conn.cursor()

    # Save skill_weight only
    cursor.execute("UPDATE game SET skill_weight = ? WHERE id = ?", (skill_weight, game_id))
    conn.commit()
    conn.close()

    # Redirect back to teams tab without regenerating
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams", status_code=302)


@app.post("/manage/games/{game_id}/teams/generate")
async def generate_teams_route(
    request: Request,
    game_id: int,
    num_teams: int = Form(3),
    players_per_team: int = Form(5),
    skill_weight_pct: int = Form(60),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    skill_weight = max(0.0, min(1.0, skill_weight_pct / 100))

    conn = get_db()
    cursor = conn.cursor()

    # Persist config
    cursor.execute(
        "UPDATE game SET num_teams = ?, players_per_team = ?, skill_weight = ? WHERE id = ?",
        (num_teams, players_per_team, skill_weight, game_id)
    )

    # Clear existing
    cursor.execute("UPDATE game_attendee SET team_id = NULL WHERE game_id = ?", (game_id,))
    cursor.execute("DELETE FROM game_team WHERE game_id = ?", (game_id,))

    # Fetch attending players
    cursor.execute("""
        SELECT ga.id, ga.player_id, p.name, p.skill_level, p.position_1, p.position_2
        FROM game_attendee ga
        JOIN player p ON ga.player_id = p.id
        WHERE ga.game_id = ?
        ORDER BY p.name
    """, (game_id,))
    attendees = [dict(a) for a in cursor.fetchall()]

    # Fetch groups with member attendee ids
    cursor.execute("SELECT * FROM game_player_group WHERE game_id = ?", (game_id,))
    groups_raw = cursor.fetchall()
    groups = []
    for g in groups_raw:
        cursor.execute("""
            SELECT ga.id as attendee_id
            FROM game_player_group_members gpm
            JOIN game_attendee ga ON gpm.player_id = ga.player_id AND ga.game_id = ?
            WHERE gpm.group_id = ?
        """, (game_id, g["id"]))
        groups.append({
            "id": g["id"],
            "name": g["name"],
            "member_attendee_ids": [r["attendee_id"] for r in cursor.fetchall()]
        })

    # Compute value scores then run algo
    value_scores = compute_player_values(attendees, skill_weight)
    team_assignments = generate_balanced_teams(attendees, groups, num_teams, players_per_team, value_scores)

    # Create teams
    _TEAM_NAMES = ["Team A", "Team B", "Team C", "Team D", "Team E", "Team F", "Team G", "Team H"]
    _TEAM_COLORS = ["#E74C3C", "#3498DB", "#2ECC71", "#F39C12", "#9B59B6", "#1ABC9C", "#E67E22", "#E91E63"]
    team_ids = []
    for i in range(num_teams):
        cursor.execute(
            "INSERT INTO game_team (game_id, team_name, team_color) VALUES (?, ?, ?)",
            (game_id, _TEAM_NAMES[i % len(_TEAM_NAMES)], _TEAM_COLORS[i % len(_TEAM_COLORS)])
        )
        team_ids.append(cursor.lastrowid)

    # Assign attendees to teams
    for team_idx, attendee_ids in enumerate(team_assignments):
        team_id = team_ids[team_idx]
        for aid in attendee_ids:
            cursor.execute(
                "UPDATE game_attendee SET team_id = ? WHERE id = ? AND game_id = ?",
                (team_id, aid, game_id)
            )

    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams", status_code=302)


@app.post("/manage/games/{game_id}/teams/clear")
async def clear_teams(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE game_attendee SET team_id = NULL WHERE game_id = ?", (game_id,))
    cursor.execute("DELETE FROM game_team WHERE game_id = ?", (game_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/manage/games/{game_id}?tab=teams", status_code=302)


# --- Schedule Generators ---
def generate_round_robin(teams: list) -> list:
    """Circle method round robin - even split, no back-to-back."""
    matches = []
    team_ids = [t["id"] for t in teams]
    n = len(team_ids)

    if n < 2:
        return []

    # For odd number of teams, add a "bye"
    if n % 2 == 1:
        team_ids.append(None)  # None = bye

    n = len(team_ids)
    rounds = n - 1  # Each team plays n-1 matches
    matches_per_round = n // 2

    # Circle method: keep first team fixed, rotate others
    for round_num in range(1, rounds + 1):
        for i in range(matches_per_round):
            home_idx = i
            away_idx = n - 1 - i

            home = team_ids[home_idx]
            away = team_ids[away_idx]

            # Skip if either is a bye
            if home is None or away is None:
                continue

            matches.append({
                "team_home_id": home,
                "team_away_id": away,
                "round_number": round_num,
                "bracket_slot": None,
                "next_match_id": None,
                "is_tbd": 0
            })

        # Rotate: move last element to second position
        team_ids = [team_ids[0]] + [team_ids[-1]] + team_ids[1:-1]

    return matches


def generate_single_elimination(teams: list) -> list:
    """Single elimination bracket. Handles byes for non-power-of-2."""
    import math
    matches = []
    team_ids = [t["id"] for t in teams]
    n = len(team_ids)
    num_rounds = math.ceil(math.log2(n))
    bracket_size = 2 ** num_rounds

    # Calculate byes
    byes = bracket_size - n
    seeds = team_ids.copy()

    # Build first round matches
    round_matches = []
    match_id = 1
    slot = 1

    # Pair teams, giving byes to top seeds
    if byes > 0:
        # Top seeds get byes, face each other in first round
        bye_teams = seeds[:byes]
        playing_teams = seeds[byes:]

        # Create matches for teams that must play
        for i in range(0, len(playing_teams), 2):
            if i + 1 < len(playing_teams):
                round_matches.append({
                    "team_home_id": playing_teams[i],
                    "team_away_id": playing_teams[i + 1],
                    "round_number": 1,
                    "bracket_slot": f"W-{slot}",
                    "is_tbd": 0
                })
                slot += 1
            else:
                # Odd team gets bye
                pass
    else:
        for i in range(0, len(team_ids), 2):
            if i + 1 < len(team_ids):
                round_matches.append({
                    "team_home_id": team_ids[i],
                    "team_away_id": team_ids[i + 1],
                    "round_number": 1,
                    "bracket_slot": f"W-{slot}",
                    "is_tbd": 0
                })
                slot += 1

    # Add placeholder matches for byes (advance automatically)
    # Simplified: just create TBD matches for next rounds
    for r in range(2, num_rounds + 1):
        matches_in_round = bracket_size // (2 ** r)
        for m in range(matches_in_round):
            matches.append({
                "team_home_id": None,
                "team_away_id": None,
                "round_number": r,
                "bracket_slot": f"W-{m + 1}",
                "is_tbd": 1
            })

    # Add first round actual matches
    for m in round_matches:
        matches.append(m)

    return matches


def generate_double_elimination(teams: list) -> list:
    """Double elimination - winners and losers brackets."""
    # Simplified: same as single elim for now, extend later
    return generate_single_elimination(teams)


def generate_group_knockout(teams: list) -> list:
    """Group stage then knockout. Creates TBD placeholders for knockout."""
    matches = []
    n = len(teams)

    # Determine groups (2-4 teams per group)
    if n <= 4:
        num_groups = 1
        teams_per_group = n
    elif n <= 6:
        num_groups = 2
        teams_per_group = 3
    else:
        num_groups = 2
        teams_per_group = n // 2

    team_ids = [t["id"] for t in teams]

    # Group matches (round robin within each group)
    for g in range(num_groups):
        start = g * teams_per_group
        end = min(start + teams_per_group, len(team_ids))
        group_teams = team_ids[start:end]

        for i in range(len(group_teams)):
            for j in range(i + 1, len(group_teams)):
                matches.append({
                    "team_home_id": group_teams[i],
                    "team_away_id": group_teams[j],
                    "round_number": 1,
                    "bracket_slot": f"G{g + 1}",
                    "is_tbd": 0
                })

    # Knockout placeholders
    knockout_slots = max(2, num_groups * 2)
    for k in range(knockout_slots // 2):
        matches.append({
            "team_home_id": None,
            "team_away_id": None,
            "round_number": 2,
            "bracket_slot": f"KF{k + 1}",
            "is_tbd": 1
        })

    return matches


def generate_king_of_court(teams: list) -> list:
    """Sequential queue - winner stays, loser goes to queue end."""
    matches = []
    team_ids = [t["id"] for t in teams]

    # Queue mode: just create sequential matches
    # Each match is: current winner vs next in queue
    for i in range(len(team_ids) * 2):  # Double rotation
        home = team_ids[i % len(team_ids)]
        away = team_ids[(i + 1) % len(team_ids)]
        matches.append({
            "team_home_id": home,
            "team_away_id": away,
            "round_number": 1,
            "bracket_slot": None,
            "is_tbd": 0
        })

    return matches


SUGGESTIONS = {
    2: "single_elimination",
    3: "round_robin",
    4: "round_robin",
    5: "king_of_court",
    6: "group_knockout",
    7: "group_knockout",
    8: "single_elimination",
}


# --- Schedule / Matches ---
@app.post("/manage/games/{game_id}/schedule/generate")
async def generate_schedule(
    request: Request,
    game_id: int,
    format: str = Form("round_robin"),
    best_of: int = Form(1)
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()

    # Get teams
    cursor.execute("SELECT id, team_name FROM game_team WHERE game_id = ?", (game_id,))
    teams = cursor.fetchall()

    if len(teams) < 2:
        conn.close()
        return JSONResponse({"error": "Need at least 2 teams"}, status_code=400)

    # Update game schedule_format and best_of
    cursor.execute(
        "UPDATE game SET schedule_format = ?, best_of = ? WHERE id = ?",
        (format, best_of, game_id)
    )

    # Clear existing matches
    cursor.execute("DELETE FROM game_match WHERE game_id = ?", (game_id,))

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
    else:
        matches = generate_round_robin(teams)

    # Insert matches
    for i, m in enumerate(matches):
        cursor.execute("""
            INSERT INTO game_match (
                game_id, round_number, match_order, team_home_id, team_away_id,
                type, bracket_slot, next_match_id, is_tbd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            game_id,
            m.get("round_number", 1),
            i + 1,
            m.get("team_home_id"),
            m.get("team_away_id"),
            format,
            m.get("bracket_slot"),
            m.get("next_match_id"),
            m.get("is_tbd", 0)
        ))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)


@app.post("/manage/games/{game_id}/schedule/reorder")
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

    for order, match_id in enumerate(match_ids):
        cursor.execute(
            "UPDATE game_match SET match_order = ? WHERE id = ? AND game_id = ?",
            (order + 1, match_id, game_id)
        )

    conn.commit()
    conn.close()

    return JSONResponse({"success": True})


@app.post("/manage/games/{game_id}/schedule/clear")
async def clear_schedule(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()

    # Clear matches and reset format
    cursor.execute("DELETE FROM game_match WHERE game_id = ?", (game_id,))
    cursor.execute(
        "UPDATE game SET schedule_format = 'round_robin', best_of = 1 WHERE id = ?",
        (game_id,)
    )

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)


@app.post("/manage/games/{game_id}/schedule/{match_id}")
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


@app.post("/manage/games/{game_id}/schedule/{match_id}/update-teams")
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


@app.post("/manage/games/{game_id}/schedule/add")
async def add_match(request: Request, game_id: int, _dummy: str = Form("")):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()

    # Get next match order
    cursor.execute("SELECT COALESCE(MAX(match_order), 0) + 1 as next_order FROM game_match WHERE game_id = ?", (game_id,))
    next_order = cursor.fetchone()["next_order"]

    cursor.execute("""
        INSERT INTO game_match (game_id, match_order, is_tbd, type)
        VALUES (?, ?, 1, 'custom')
    """, (game_id, next_order))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)


@app.post("/manage/games/{game_id}/schedule/{match_id}/delete")
async def delete_match(request: Request, game_id: int, match_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_match WHERE id = ? AND game_id = ?", (match_id, game_id))
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/games/{game_id}?tab=schedule", status_code=302)


# --- Delete Game ---
@app.post("/manage/games/{game_id}/delete")
async def delete_game(request: Request, game_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game WHERE id = ?", (game_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/games", status_code=302)
