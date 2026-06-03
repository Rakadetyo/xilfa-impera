from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.database import get_db
from app.deps import get_current_user
from app.templating import templates
from app.services import analytics as analytics_service

router = APIRouter()


@router.get("/manage/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request, packed_months: int = 6):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)
    if packed_months not in (3, 6, 12, 0):
        packed_months = 6
    conn = get_db()
    try:
        game_activity = analytics_service.get_game_activity(conn, packed_months=packed_months)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "analytics.html", {
        "user": user,
        "active": "analytics",
        "game_activity": game_activity,
        "packed_months": packed_months,
    })


@router.get("/manage/analytics/players")
async def analytics_players(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    conn = get_db()
    try:
        return JSONResponse(analytics_service.get_player_stats(conn))
    finally:
        conn.close()


@router.get("/manage/analytics/finance")
async def analytics_finance(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    conn = get_db()
    try:
        return JSONResponse(analytics_service.get_finance_stats(conn))
    finally:
        conn.close()


@router.get("/manage/analytics/quality")
async def analytics_quality(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    conn = get_db()
    try:
        return JSONResponse(analytics_service.get_quality_stats(conn))
    finally:
        conn.close()


@router.get("/manage/analytics/members")
async def analytics_members(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    conn = get_db()
    try:
        return JSONResponse(analytics_service.get_member_stats(conn))
    finally:
        conn.close()
