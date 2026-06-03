from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user
from app.templating import templates

router = APIRouter()


@router.get("/api/resolve-google-maps")
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

@router.get("/manage/arena", response_class=HTMLResponse)
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

    return templates.TemplateResponse(request, "manage/arena.html", {
        "request": request,
        "user": user,
        "arenas": arenas,
        "stats": {
            "total": total_arenas,
            "total_price": total_price,
            "arenas_played": arenas_played
        },
        "arena_game_counts": arena_game_counts,
        "arena_game_list": arena_rows,
        "active": "arena"
    })

@router.post("/manage/arena")
async def create_arena(request: Request, location_name: str = Form(...), address: str = Form(""), price: float = Form(0), contact_person: str = Form(""), map_url: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO arena (location_name, address, price, contact_person, map_url) VALUES (?, ?, ?, ?, ?)",
        (location_name, address, price, contact_person, map_url)
    )
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/arena", status_code=302)

@router.post("/manage/arena/{arena_id}")
async def update_arena(request: Request, arena_id: int, location_name: str = Form(...), address: str = Form(""), price: float = Form(0), contact_person: str = Form(""), map_url: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE arena SET location_name = ?, address = ?, price = ?, contact_person = ?, map_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (location_name, address, price, contact_person, map_url, arena_id)
    )
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/arena", status_code=302)

@router.post("/manage/arena/{arena_id}/delete")
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
