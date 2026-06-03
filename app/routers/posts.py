import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user, is_superadmin
from app.templating import templates

router = APIRouter()


@router.get("/manage", response_class=HTMLResponse)
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
    month_names = ["January","February","March","April","May","June","July","August","September","October","November","December"]
    current_period = f"{month_names[now.month - 1]} {now.year}"
    cursor.execute("SELECT COUNT(*) as total FROM member WHERE member_period = ?", (current_period,))
    members_this_month = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM arena")
    total_arenas = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM game WHERE datetime >= date('now', '-30 days')")
    recent_games = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT g.id, g.datetime, g.status, a.location_name,
               (SELECT COUNT(*) FROM game_attendee WHERE game_id = g.id) as attendee_count
        FROM game g LEFT JOIN arena a ON g.arena_id = a.id
        WHERE g.datetime < datetime('now')
        ORDER BY g.datetime DESC LIMIT 1
    """)
    last_game = cursor.fetchone()

    cursor.execute("""
        SELECT g.id, g.datetime, g.status, a.location_name,
               (SELECT COUNT(*) FROM game_attendee WHERE game_id = g.id) as attendee_count
        FROM game g LEFT JOIN arena a ON g.arena_id = a.id
        WHERE g.datetime >= datetime('now')
        ORDER BY g.datetime ASC LIMIT 1
    """)
    upcoming_game = cursor.fetchone()

    conn.close()

    return templates.TemplateResponse(request, "manage/dashboard.html", {
        "request": request,
        "user": user,
        "stats": {
            "total_players": total_players,
            "active_players": active_players,
            "members_this_month": members_this_month,
            "total_arenas": total_arenas,
            "recent_games": recent_games
        },
        "last_game": dict(last_game) if last_game else None,
        "upcoming_game": dict(upcoming_game) if upcoming_game else None,
        "active": "dashboard"
    })

@router.get("/manage/posts", response_class=HTMLResponse)
async def list_posts(request: Request):
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

    return templates.TemplateResponse(request, "manage/admin.html", {
        "request": request,
        "user": user,
        "posts": posts,
        "stats": {"total": total, "drafts": drafts, "published": published},
        "active": "posts"
    })

@router.get("/manage/new", response_class=HTMLResponse)
async def new_post_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)
    return templates.TemplateResponse(request, "manage/post_form.html", {"request": request, "post": None, "user": user})

@router.post("/manage/posts")
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

@router.get("/manage/posts/{post_id}", response_class=HTMLResponse)
async def edit_post_page(request: Request, post_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, body, summary, post_type, status, created_at, updated_at, cover_image_id FROM posts WHERE id = ?", (post_id,))
    post = cursor.fetchone()

    if not post:
        conn.close()
        raise HTTPException(status_code=404, detail="Post not found")

    cursor.execute("SELECT * FROM post_images WHERE post_id = ? ORDER BY display_order", (post_id,))
    images = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(request, "manage/post_form.html", {
        "request": request,
        "post": post,
        "images": images,
        "cover_image_id": post["cover_image_id"],
        "user": user
    })

@router.post("/manage/posts/{post_id}")
async def update_post(request: Request, post_id: int, title: str = Form(...), body: str = Form(...), summary: str = Form(""), post_type: str = Form("HIGHLIGHT"), status: str = Form("draft"), created_date: str = Form(""), created_time: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    # Update post fields
    cursor.execute(
        "UPDATE posts SET title = ?, body = ?, summary = ?, post_type = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (title, body, summary, post_type, status, post_id)
    )

    # Update created_at if provided
    if created_date and created_time:
        cursor.execute(
            "UPDATE posts SET created_at = ? WHERE id = ?",
            (f"{created_date} {created_time}", post_id)
        )

    conn.commit()
    conn.close()

    return RedirectResponse(f"/manage/posts/{post_id}", status_code=302)

@router.post("/manage/posts/{post_id}/images")
async def upload_image(request: Request, post_id: int, image: UploadFile = File(...)):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Check combined media count (images + videos)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM post_images WHERE post_id = ?", (post_id,))
    if cursor.fetchone()["cnt"] >= 8:
        conn.close()
        raise HTTPException(status_code=400, detail="Maximum 8 media items allowed")

    upload_dir = Path("app/static/img/comics")
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(image.filename).suffix.lower()
    valid_images = [".jpg", ".jpeg", ".png", ".webp"]
    valid_videos = [".mp4", ".webm", ".mov"]

    is_video = ext in valid_videos

    if is_video:
        if ext not in valid_videos:
            conn.close()
            raise HTTPException(status_code=400, detail="Invalid video format")
    else:
        if ext not in valid_images:
            conn.close()
            raise HTTPException(status_code=400, detail="Invalid image format")

    filename = f"{uuid.uuid4()}{ext}"
    filepath = upload_dir / filename

    with open(filepath, "wb") as f:
        shutil.copyfileobj(image.file, f)

    cursor.execute("SELECT COALESCE(MAX(display_order), -1) + 1 as next_order FROM post_images WHERE post_id = ?", (post_id,))
    next_order = cursor.fetchone()["next_order"]
    cursor.execute(
        "INSERT INTO post_images (post_id, filename, display_order, is_video) VALUES (?, ?, ?, ?)",
        (post_id, filename, next_order, 1 if is_video else 0)
    )
    conn.commit()
    conn.close()

    return JSONResponse({"filename": filename, "id": cursor.lastrowid, "is_video": is_video})

@router.post("/manage/posts/{post_id}/cover")
async def set_cover_image(request: Request, post_id: int, image_id: int = Form(...)):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = get_db()
    cursor = conn.cursor()

    # Verify image belongs to this post
    cursor.execute("SELECT id FROM post_images WHERE id = ? AND post_id = ?", (image_id, post_id))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Image not found")

    cursor.execute("UPDATE posts SET cover_image_id = ? WHERE id = ?", (image_id, post_id))
    conn.commit()
    conn.close()

    return JSONResponse({"success": True})

@router.post("/manage/posts/{post_id}/delete")
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

@router.post("/manage/posts/{post_id}/toggle")
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
