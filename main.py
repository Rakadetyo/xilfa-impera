import os
from pathlib import Path
from passlib.hash import bcrypt
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
    cursor.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

# --- Public Routes ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.title, p.body, p.status, p.created_at, u.username,
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
async def get_post(post_id: Request):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.id, p.title, p.body, p.status, p.created_at, p.updated_at, u.username
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

    if not user or not bcrypt.verify(password, user["password_hash"]):
        return RedirectResponse("/masukgan?error=Invalid credentials", status_code=302)

    request.session["user_id"] = user["id"]
    return RedirectResponse("/admin", status_code=302)

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

    password_hash = bcrypt.hash(password)
    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash)
    )
    conn.commit()
    conn.close()

    return RedirectResponse("/masukgan?registered=1", status_code=302)

@app.post("/admin/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)

# --- Admin Routes ---
@app.get("/admin", response_class=HTMLResponse)
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

@app.get("/admin/new", response_class=HTMLResponse)
async def new_post_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)
    return templates.TemplateResponse(request, "post_form.html", {"request": request, "post": None, "user": user})

@app.post("/admin/posts")
async def create_post(request: Request, title: str = Form(...), body: str = Form(...), status: str = Form("draft")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO posts (title, body, author_id, status) VALUES (?, ?, ?, ?)",
        (title, body, user["id"], status)
    )
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return RedirectResponse(f"/admin/posts/{post_id}", status_code=302)

@app.get("/admin/posts/{post_id}", response_class=HTMLResponse)
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

@app.post("/admin/posts/{post_id}")
async def update_post(request: Request, post_id: int, title: str = Form(...), body: str = Form(...), status: str = Form("draft")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE posts SET title = ?, body = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (title, body, status, post_id)
    )
    conn.commit()
    conn.close()

    return RedirectResponse(f"/admin/posts/{post_id}", status_code=302)

@app.post("/admin/posts/{post_id}/images")
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

@app.post("/admin/posts/{post_id}/delete")
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

    return RedirectResponse("/admin", status_code=302)

@app.post("/admin/posts/{post_id}/toggle")
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
