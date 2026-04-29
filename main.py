import os
from pathlib import Path
import bcrypt
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import shutil
import uuid

load_dotenv()

app = FastAPI(title="Impera")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
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

# --- Public Routes ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")

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
    filter_member = request.query_params.get("member", "")
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
        SELECT p.id, p.name, p.nickname, p.position_1, p.position_2, p.skill_level, p.contact_no, p.instagram, p.reclub, p.join_date, p.created_at,
               (SELECT MAX(g.datetime) FROM game_attendee ga JOIN game g ON ga.game_id = g.id WHERE ga.player_id = p.id) as last_played,
               CASE WHEN EXISTS (
                   SELECT 1 FROM member m
                   WHERE m.player_id = p.id
                   AND m.member_start_date <= date('now')
                   AND (m.member_end_date IS NULL OR m.member_end_date >= date('now'))
               ) THEN 1 ELSE 0 END as is_member
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

    if filter_member != "":
        has_member = 1 if filter_member == "1" else 0
        if has_member:
            query += " AND EXISTS (SELECT 1 FROM member m WHERE m.player_id = p.id AND m.member_start_date <= date('now') AND (m.member_end_date IS NULL OR m.member_end_date >= date('now')))"
        else:
            query += " AND NOT EXISTS (SELECT 1 FROM member m WHERE m.player_id = p.id AND m.member_start_date <= date('now') AND (m.member_end_date IS NULL OR m.member_end_date >= date('now')))"

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
    if filter_member != "":
        # For count, check member table
        count_query = """
            SELECT COUNT(*) as cnt FROM player p
            WHERE EXISTS (
                SELECT 1 FROM member m
                WHERE m.player_id = p.id
                AND m.member_start_date <= date('now')
                AND (m.member_end_date IS NULL OR m.member_end_date >= date('now'))
            ) = ?
        """
        count_params = [1 if filter_member == "1" else 0]
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
            "member": filter_member,
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
    is_member: bool = Form(False),
    contact_no: str = Form(""),
    instagram: str = Form(""),
    reclub: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    if skill_level < 1 or skill_level > 5:
        skill_level = 3

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO player (name, nickname, position_1, position_2, skill_level, is_member, contact_no, instagram, reclub, join_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'))
    """, (name, nickname, position_1, position_2, skill_level, 1 if is_member else 0, contact_no, instagram, reclub))
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
    is_member: bool = Form(False),
    contact_no: str = Form(""),
    instagram: str = Form(""),
    reclub: str = Form(""),
    join_date: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    if skill_level < 1 or skill_level > 5:
        skill_level = 3

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE player SET name = ?, nickname = ?, position_1 = ?, position_2 = ?, skill_level = ?, is_member = ?, contact_no = ?, instagram = ?, reclub = ?, join_date = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (name, nickname, position_1, position_2, skill_level, 1 if is_member else 0, contact_no, instagram, reclub, join_date or None, player_id))
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/players?success=Player updated", status_code=302)

@app.post("/manage/players/{player_id}/delete")
async def delete_player(request: Request, player_id: int):
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

    return RedirectResponse("/manage/players?success=Player deleted", status_code=302)

# --- Admin Routes ---
@app.get("/manage", response_class=HTMLResponse)
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

    # Calculate first and last day of selected month
    first_day = datetime.date(filter_year, filter_month, 1)
    if filter_month == 12:
        last_day = datetime.date(filter_year, 12, 31)
    else:
        last_day = datetime.date(filter_year, filter_month + 1, 1) - datetime.timedelta(days=1)

    conn = get_db()
    cursor = conn.cursor()

    # Get members active in selected month with n_members and last_member_date
    cursor.execute("""
        SELECT m.id, m.player_id, m.member_start_date, m.member_end_date, m.is_paid, m.membership_price,
               p.name,
               (SELECT COUNT(*) FROM member m2 WHERE m2.player_id = m.player_id AND m2.member_start_date <= m.member_start_date) as n_members,
               (SELECT m2.member_end_date FROM member m2 WHERE m2.player_id = m.player_id AND m2.member_start_date < m.member_start_date ORDER BY m2.member_start_date DESC LIMIT 1) as last_member_date
        FROM member m
        JOIN player p ON m.player_id = p.id
        WHERE (m.member_start_date <= ?)
          AND (m.member_end_date IS NULL OR m.member_end_date >= ?)
        ORDER BY p.name ASC
        LIMIT 15
    """, (last_day.isoformat(), first_day.isoformat()))

    members = cursor.fetchall()

    # Get all players for the dropdown
    cursor.execute("SELECT id, name FROM player ORDER BY name")
    players = cursor.fetchall()

    # Analytics
    # 1. Total active members this month + total unique all time
    cursor.execute("""
        SELECT COUNT(DISTINCT player_id) as cnt FROM member
        WHERE member_start_date <= ? AND (member_end_date IS NULL OR member_end_date >= ?)
    """, (last_day.isoformat(), first_day.isoformat()))
    active_this_month = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(DISTINCT player_id) as cnt FROM member")
    total_unique = cursor.fetchone()["cnt"]

    # 2. Paid vs Unpaid + Total Income this month
    cursor.execute("""
        SELECT COUNT(*) as cnt, SUM(CASE WHEN is_paid = 1 THEN 1 ELSE 0 END) as paid_cnt,
               SUM(CASE WHEN is_paid = 1 THEN COALESCE(membership_price, 0) ELSE 0 END) as total_income
        FROM member
        WHERE member_start_date <= ? AND (member_end_date IS NULL OR member_end_date >= ?)
    """, (last_day.isoformat(), first_day.isoformat()))
    paid_stats = cursor.fetchone()
    paid_count = paid_stats["paid_cnt"] or 0
    unpaid_count = (paid_stats["cnt"] or 0) - paid_count
    total_income = paid_stats["total_income"] or 0

    # 3. New members this month
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM member
        WHERE member_start_date >= ? AND member_start_date <= ?
    """, (first_day.isoformat(), last_day.isoformat()))
    new_this_month = cursor.fetchone()["cnt"]

    # Retention Rate (members who were also active in previous month)
    prev_month = filter_month - 1
    prev_year = filter_year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    prev_first = datetime.date(prev_year, prev_month, 1)
    if prev_month == 12:
        prev_last = datetime.date(prev_year, 12, 31)
    else:
        prev_last = datetime.date(prev_year, prev_month + 1, 1) - datetime.timedelta(days=1)

    cursor.execute("""
        SELECT COUNT(DISTINCT player_id) as cnt FROM member
        WHERE member_start_date <= ? AND (member_end_date IS NULL OR member_end_date >= ?)
    """, (prev_last.isoformat(), prev_first.isoformat()))
    prev_active = cursor.fetchone()["cnt"]

    if prev_active > 0:
        retention_rate = round((active_this_month / prev_active) * 100, 1)
    else:
        retention_rate = 0

    # Avg member per month (all time)
    cursor.execute("""
        SELECT member_start_date FROM member ORDER BY member_start_date
    """)
    all_members = cursor.fetchall()
    if all_members:
        # Get min and max months
        min_date = all_members[0]["member_start_date"][:7]  # YYYY-MM
        max_date = all_members[-1]["member_start_date"][:7]
        min_parts = min_date.split("-")
        max_parts = max_date.split("-")
        months_span = (int(max_parts[0]) - int(min_parts[0])) * 12 + (int(max_parts[1]) - int(min_parts[1])) + 1
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

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE member SET is_paid = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (is_paid, member_id))
    conn.commit()
    conn.close()

    return JSONResponse({"success": True})

@app.post("/manage/members")
async def create_member(request: Request, player_id: int = Form(...), member_start_date: str = Form(...), member_end_date: str = Form(None), membership_price: float = Form(None), is_paid: bool = Form(False), month: int = Form(1), year: int = Form(2024)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO member (player_id, member_start_date, member_end_date, membership_price, is_paid) VALUES (?, ?, ?, ?, ?)",
        (player_id, member_start_date, member_end_date if member_end_date else None, membership_price if membership_price is not None else 0, 1 if is_paid else 0)
    )
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/members?month={month}&year={year}", status_code=302)

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
    cursor.execute("SELECT id, name FROM player ORDER BY name")
    all_players = [{"id": p["id"], "name": p["name"]} for p in cursor.fetchall()]

    conn.close()

    return JSONResponse({
        "preview": preview,
        "start_date": start_date,
        "end_date": end_date,
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

    if not members_data or not start_date or not end_date:
        return JSONResponse({"error": "Missing data"}, status_code=400)

    conn = get_db()
    cursor = conn.cursor()

    imported = 0
    for member in members_data:
        if not member.get("found"):
            continue

        player_id = member.get("player_id")
        price = member.get("price")

        # Check if member already exists for this period
        cursor.execute("""
            SELECT id FROM member
            WHERE player_id = ? AND member_start_date = ? AND member_end_date = ?
        """, (player_id, start_date, end_date))
        existing = cursor.fetchone()

        if existing:
            # Update existing
            cursor.execute("""
                UPDATE member SET membership_price = ?, is_paid = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (price, existing["id"]))
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO member (player_id, member_start_date, member_end_date, membership_price, is_paid)
                VALUES (?, ?, ?, ?, 0)
            """, (player_id, start_date, end_date, price))
        imported += 1

    conn.commit()
    conn.close()

    return JSONResponse({"imported": imported})

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

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE member SET player_id = ?, member_start_date = ?, member_end_date = ?, membership_price = ?, is_paid = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (player_id, member_start_date, member_end_date if member_end_date else None, membership_price if membership_price is not None else 0, 1 if is_paid else 0, member_id)
    )
    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/members?month={month}&year={year}", status_code=302)

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
