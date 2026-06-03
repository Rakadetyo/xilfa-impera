import logging
import re
import datetime
import calendar

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user, is_superadmin
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/manage/members", response_class=HTMLResponse)
async def members_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

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
    # Calculate period start/end dates for game counting
    period_start = f"{filter_year}-{filter_month:02d}-01"
    if filter_month == 12:
        period_end = f"{filter_year + 1}-01-01"
    else:
        period_end = f"{filter_year}-{filter_month + 1:02d}-01"

    cursor.execute("""
        SELECT m.id, m.player_id, m.member_start_date, m.member_end_date, m.is_paid, m.membership_price, m.member_period, m.games_played,
               p.name, p.nickname,
               (SELECT COUNT(*) FROM member m2 WHERE m2.player_id = m.player_id) as n_members,
               (SELECT m2.member_period FROM member m2 WHERE m2.player_id = m.player_id AND m2.member_start_date < m.member_start_date ORDER BY m2.member_start_date DESC LIMIT 1) as last_member_period
        FROM member m
        JOIN player p ON m.player_id = p.id
        WHERE m.member_period = ?
        ORDER BY p.name ASC
    """, (member_period,))

    members = cursor.fetchall()

    # Update games_played for each member in this period
    for m in members:
        cursor.execute("""
            UPDATE member SET games_played = (
                SELECT COUNT(DISTINCT ga.game_id) FROM game_attendee ga
                JOIN game g ON ga.game_id = g.id
                WHERE ga.player_id = ?
                AND ga.is_attend = 1
                AND g.datetime >= ?
                AND g.datetime < ?
            ) WHERE id = ?
        """, (m["player_id"], period_start, period_end, m["id"]))
    conn.commit()

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

    # 3. New members this period (members where this is their first membership)
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM member m
        WHERE m.member_period = ?
        AND (SELECT COUNT(*) FROM member m2 WHERE m2.player_id = m.player_id) = 1
    """, (member_period,))
    new_this_month = cursor.fetchone()["cnt"]

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

    return templates.TemplateResponse(request, "manage/members.html", {
        "request": request,
        "user": user,
        "members": members,
        "players": players,
        "stats": stats,
        "filter_month": filter_month,
        "filter_year": filter_year,
        "months": months,
        "years": years,
        "active": "members"
    })

@router.post("/manage/members/{member_id}/toggle-paid")
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

@router.post("/manage/members")
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

@router.post("/api/import-whatsapp-members")
async def import_whatsapp_members(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()
    chat_text = data.get("chat_text", "")
    filter_month = data.get("month")
    filter_year = data.get("year")

    # Find the member list section
    lines = chat_text.split('\n')
    members = []

    # Pattern: number. name price or number. name  price
    member_pattern = re.compile(r'^\d+[.)\s]+(.+?)\s+(\d+)\s*$')

    for line in lines:
        line = line.strip()
        # Remove emoji/特殊characters at start
        line = re.sub(r'^[​-‏ - ]', '', line)
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
        if datetime.datetime(filter_year, filter_month, day).weekday() == 5:
            first_saturday = day
            break

    last_saturday = None
    for day in range(last_day, last_day - 7, -1):
        if datetime.datetime(filter_year, filter_month, day).weekday() == 5:
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

@router.post("/api/import-whatsapp-members/confirm")
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

@router.get("/api/generate-whatsapp-chat")
async def generate_whatsapp_chat(request: Request, month: int, year: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Get first and last Saturday
    last_day = calendar.monthrange(year, month)[1]

    first_saturday = None
    for day in range(1, 8):
        if datetime.datetime(year, month, day).weekday() == 5:
            first_saturday = day
            break

    last_saturday = None
    for day in range(last_day, last_day - 7, -1):
        if datetime.datetime(year, month, day).weekday() == 5:
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

@router.post("/manage/members/{member_id}")
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

@router.post("/manage/members/{member_id}/delete")
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
