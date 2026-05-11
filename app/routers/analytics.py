from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user
from app.templating import templates
from app.services import analytics as analytics_service

router = APIRouter()


@router.get("/manage/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    conn = get_db()
    try:
        game_activity = analytics_service.get_game_activity(conn)
        player_stats = analytics_service.get_player_stats(conn)
        finance_stats = analytics_service.get_finance_stats(conn)
        quality_stats = analytics_service.get_quality_stats(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(request, "analytics.html", {
        "user": user,
        "active": "analytics",
        "game_activity": game_activity,
        "player_stats": player_stats,
        "finance_stats": finance_stats,
        "quality_stats": quality_stats,
    })
