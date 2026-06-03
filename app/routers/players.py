from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user, is_superadmin
from app.templating import templates

router = APIRouter()


@router.get("/manage/players", response_class=HTMLResponse)
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
        SELECT p.id, p.name, p.nickname, p.position_1, p.position_2, p.skill_level, p.contact_no, p.instagram, p.reclub, p.join_date, p.created_at, p.status, p.notes, p.join_source,
               (SELECT MAX(g.datetime) FROM game_attendee ga JOIN game g ON ga.game_id = g.id WHERE ga.player_id = p.id AND g.datetime <= datetime('now')) as last_played
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

    cursor.execute("SELECT COUNT(*) as cnt FROM player WHERE status = 1")
    active_players = cursor.fetchone()["cnt"]

    cursor.execute("""
        SELECT COUNT(DISTINCT player_id) as cnt FROM member
        WHERE member_start_date <= date('now') AND member_end_date >= date('now')
    """)
    member_players = cursor.fetchone()["cnt"]

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
            "active": active_players,
            "inactive": total_players - active_players,
            "members": member_players,
            "avg_skill": round(avg_skill, 1),
            "positions": position_dict,
            "positions_1": position_dict_1,
            "positions_2": position_dict_2,
            "skill_dist": {row["skill_level"]: row["cnt"] for row in skill_counts}
        },
        "active": "players"
    })

@router.post("/manage/players")
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
    status: int = Form(1),
    notes: str = Form(""),
    join_source: str = Form("")
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
        INSERT INTO player (name, nickname, position_1, position_2, skill_level, contact_no, instagram, reclub, join_date, status, notes, join_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, date('now'), ?, ?, ?)
    """, (name, nickname, position_1, position_2, skill_level, contact_no, instagram, reclub, status, notes, join_source))

    conn.commit()
    conn.close()

    return RedirectResponse("/manage/players?success=Player added", status_code=302)

@router.post("/manage/players/{player_id}")
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
    notes: str = Form(""),
    join_source: str = Form(""),
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
        UPDATE player SET name = ?, nickname = ?, position_1 = ?, position_2 = ?, skill_level = ?, contact_no = ?, instagram = ?, reclub = ?, join_date = ?, status = ?, notes = ?, join_source = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (name, nickname, position_1, position_2, skill_level, contact_no, instagram, reclub, join_date or None, status, notes, join_source, player_id))
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

@router.post("/manage/players/{player_id}/delete")
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
