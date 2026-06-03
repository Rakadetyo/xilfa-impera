import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_db
from app.deps import get_current_user
from app.templating import templates
from app.services.settings import get_page_settings, set_setting

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/manage/page_settings/homepage", response_class=HTMLResponse)
async def page_settings(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    settings = get_page_settings("homepage")
    return templates.TemplateResponse(request, "page_settings.html", {
        "request": request,
        "user": user,
        "settings": settings,
        "active": "page_settings",
    })

@router.post("/manage/page_settings/homepage")
async def save_page_settings(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/masukgan", status_code=302)

    form = await request.form()
    username = user["username"]

    try:
        for key, value in form.items():
            if key.startswith("hero_"):
                section = "hero"
                setting_key = key[5:]
            elif key.startswith("about_"):
                section = "about"
                setting_key = key[6:]
            elif key.startswith("schedule_"):
                section = "schedule"
                setting_key = key[9:]
            elif key.startswith("social_"):
                section = "social"
                setting_key = key[7:]
            else:
                continue

            set_setting("homepage", section, setting_key, value)

        logger.info(f"[PAGE_SETTINGS] Saved homepage settings by {username}")
        return RedirectResponse("/manage/page_settings/homepage?success=Settings saved", status_code=302)
    except Exception as e:
        logger.error(f"[PAGE_SETTINGS] Error saving settings by {username}: {str(e)}")
        return RedirectResponse(f"/manage/page_settings/homepage?error={str(e)}", status_code=302)

@router.get("/preview", response_class=HTMLResponse)
async def preview_homepage(request: Request):
    """Preview homepage with settings from query params (before saving)"""
    from urllib.parse import parse_qs

    qs = parse_qs(request.url.query)
    settings = {
        "hero": {},
        "about": {},
        "schedule": {},
        "social": {}
    }

    for key, values in qs.items():
        value = values[0] if values else ""
        if key.startswith("hero_"):
            settings["hero"][key[5:]] = value
        elif key.startswith("about_"):
            settings["about"][key[6:]] = value
        elif key.startswith("schedule_"):
            settings["schedule"][key[9:]] = value
        elif key.startswith("social_"):
            settings["social"][key[7:]] = value

    # Use defaults for empty values
    defaults = {
        "hero": {"youtube_video_id": "rBW1uZnZhbo", "headline": "IMPERA", "tagline": "BSD — Gading Serpong", "subtitle": "", "cta_primary_text": "Play With Us", "cta_primary_link": "#schedule", "cta_secondary_text": "Learn More", "cta_secondary_link": "#about", "logo": "/assets/impera-logo-only-white.png"},
        "about": {"title": "Built for Those Who Play.", "body": "", "stat_1_label": "Members", "stat_1_value": "90+", "stat_2_label": "Sessions", "stat_2_value": "100+", "stat_3_label": "Home Court", "stat_3_value": "Jetz", "stat_4_label": "Every Week", "stat_4_value": "SAT"},
        "schedule": {"day": "Saturday", "time": "18:00", "location": "BSD — Gading Serpong Area"},
        "social": {"instagram": "", "whatsapp": "", "reclub": ""}
    }

    for section in settings:
        for key in defaults[section]:
            if not settings[section].get(key):
                settings[section][key] = defaults[section][key]

    return templates.TemplateResponse(request, "index.html", {"request": request, "settings": settings})
