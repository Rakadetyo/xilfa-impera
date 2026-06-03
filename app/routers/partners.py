from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user, is_superadmin
from app.templating import templates

router = APIRouter()


def parse_types(types_str):
    """Parse comma-separated types string into cleaned list."""
    if not types_str:
        return []
    return [t.strip() for t in types_str.split(",") if t.strip()]

def format_types(types_list):
    """Join list into comma-separated string."""
    return ",".join(t.strip() for t in types_list if t.strip())


@router.get("/manage/partners")
async def list_partners(request: Request, type_filter: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.*,
               COUNT(DISTINCT gp.id) as game_count,
               COALESCE(SUM(gp.fee), 0) as total_earned,
               MAX(g.datetime) as last_game_date
        FROM partner p
        LEFT JOIN game_partner gp ON gp.partner_id = p.id
        LEFT JOIN game g ON gp.game_id = g.id
        WHERE p.is_active = 1
        GROUP BY p.id
        ORDER BY p.name
    """)
    partners = cursor.fetchall()

    all_types = set()
    for p in partners:
        for t in parse_types(p["types"]):
            all_types.add(t)

    conn.close()

    if type_filter:
        partners = [p for p in partners if type_filter in parse_types(p["types"])]

    return templates.TemplateResponse(request, "partners/list.html", {
        "user": user,
        "partners": partners,
        "all_types": sorted(all_types),
        "type_filter": type_filter,
        "parse_types": parse_types,
        "active": "partners",
    })

@router.get("/manage/partners/new")
async def new_partner_form(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT types FROM partner WHERE types != ''")
    existing_types = set()
    for row in cursor.fetchall():
        for t in parse_types(row["types"]):
            existing_types.add(t)
    conn.close()

    suggested_types = sorted(existing_types | {
        "referee", "videographer", "photographer",
        "sponsor", "jersey", "equipment", "other"
    })

    return templates.TemplateResponse(request, "partners/new.html", {
        "user": user,
        "suggested_types": suggested_types,
        "active": "partners",
    })

@router.post("/manage/partners/new")
async def create_partner(
    request: Request,
    name: str = Form(...),
    company: str = Form(""),
    types: str = Form(""),
    contact: str = Form(""),
    social_media: str = Form(""),
    default_fee: float = Form(0),
    internal_rating: int = Form(0),
    notes: str = Form(""),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO partner (name, company, types, contact, social_media, default_fee, internal_rating, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, company, types, contact, social_media, default_fee, internal_rating, notes))
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/partners", status_code=302)

@router.get("/manage/partners/{partner_id}/edit")
async def edit_partner_form(request: Request, partner_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM partner WHERE id = ?", (partner_id,))
    partner = cursor.fetchone()
    if not partner:
        conn.close()
        raise HTTPException(status_code=404)

    cursor.execute("SELECT types FROM partner WHERE types != ''")
    existing_types = set()
    for row in cursor.fetchall():
        for t in parse_types(row["types"]):
            existing_types.add(t)
    conn.close()

    suggested_types = sorted(existing_types | {
        "referee", "videographer", "photographer",
        "sponsor", "jersey", "equipment", "other"
    })

    return templates.TemplateResponse(request, "partners/edit.html", {
        "user": user,
        "partner": partner,
        "suggested_types": suggested_types,
        "parse_types": parse_types,
        "active": "partners",
    })

@router.post("/manage/partners/{partner_id}/edit")
async def update_partner(
    request: Request,
    partner_id: int,
    name: str = Form(...),
    company: str = Form(""),
    types: str = Form(""),
    contact: str = Form(""),
    social_media: str = Form(""),
    default_fee: float = Form(0),
    internal_rating: int = Form(0),
    notes: str = Form(""),
    is_active: int = Form(1),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE partner
        SET name=?, company=?, types=?, contact=?, social_media=?, default_fee=?,
            internal_rating=?, notes=?, is_active=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (name, company, types, contact, social_media, default_fee, internal_rating, notes, is_active, partner_id))
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/partners", status_code=302)

@router.post("/manage/partners/{partner_id}/delete")
async def delete_partner(request: Request, partner_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE partner SET is_active = 0 WHERE id = ?", (partner_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/manage/partners", status_code=302)

@router.get("/manage/partners/{partner_id}")
async def partner_detail(request: Request, partner_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM partner WHERE id = ?", (partner_id,))
    partner = cursor.fetchone()
    if not partner:
        conn.close()
        raise HTTPException(status_code=404)

    cursor.execute("""
        SELECT gp.*, g.datetime, a.location_name as arena_name
        FROM game_partner gp
        JOIN game g ON gp.game_id = g.id
        LEFT JOIN arena a ON g.arena_id = a.id
        WHERE gp.partner_id = ?
        ORDER BY g.datetime DESC
    """, (partner_id,))
    history = cursor.fetchall()
    conn.close()

    total_earned = sum(h["fee"] for h in history)
    total_paid = sum(h["fee"] for h in history if h["is_paid"])

    return templates.TemplateResponse(request, "partners/detail.html", {
        "user": user,
        "partner": partner,
        "history": history,
        "total_earned": total_earned,
        "total_paid": total_paid,
        "parse_types": parse_types,
        "active": "partners",
    })

@router.get("/api/partners/search")
async def search_partners(request: Request, q: str = ""):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"results": []})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, types, contact, default_fee
        FROM partner
        WHERE is_active = 1 AND name LIKE ?
        ORDER BY name
        LIMIT 8
    """, (f"%{q}%",))
    results = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return JSONResponse({"results": results})
