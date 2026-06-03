from fastapi import APIRouter
from app.routers.games import crud, attendees, teams, groups, schedule, partners, scoring

router = APIRouter()
router.include_router(crud.router)
router.include_router(attendees.router)
router.include_router(teams.router)
router.include_router(groups.router)
router.include_router(schedule.router)
router.include_router(partners.router)
router.include_router(scoring.router)
