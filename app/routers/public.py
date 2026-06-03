from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from app.database import get_db
from app.templating import templates
from app.services.settings import get_page_settings

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    settings = get_page_settings("homepage")
    return templates.TemplateResponse(request, "index.html", {"request": request, "settings": settings})

@router.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.title, p.body, p.status, p.post_type, p.created_at, u.username,
               COALESCE(
                   (SELECT filename FROM post_images WHERE id = p.cover_image_id),
                   (SELECT filename FROM post_images WHERE post_id = p.id AND is_video = 0 ORDER BY display_order LIMIT 1)
               ) as cover_image
        FROM posts p
        JOIN users u ON p.author_id = u.id
        WHERE p.status = 'published'
        ORDER BY p.created_at DESC
    """)
    posts = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(request, "blog.html", {"request": request, "posts": posts})

@router.get("/api/blog/{post_id}")
async def get_post(post_id: int):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.id, p.title, p.body, p.summary, p.post_type, p.status, p.created_at, p.updated_at, p.cover_image_id, u.username
        FROM posts p
        JOIN users u ON p.author_id = u.id
        WHERE p.id = ?
    """, (post_id,))
    post = cursor.fetchone()

    if not post:
        conn.close()
        raise HTTPException(status_code=404, detail="Post not found")

    cursor.execute("""
        SELECT id, filename, is_video FROM post_images
        WHERE post_id = ?
        ORDER BY display_order
    """, (post_id,))
    images = cursor.fetchall()

    cursor.execute("""
        SELECT COALESCE(
            (SELECT filename FROM post_images WHERE id = ?),
            (SELECT filename FROM post_images WHERE post_id = ? AND is_video = 0 ORDER BY display_order LIMIT 1)
        ) as cover_image
    """, (post["cover_image_id"], post_id))
    cover_row = cursor.fetchone()
    cover_image = cover_row["cover_image"] if cover_row else None

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
        "cover_image": cover_image,
        "images": [{"id": img["id"], "filename": img["filename"], "is_video": img["is_video"] if "is_video" in img.keys() else 0} for img in images]
    })
