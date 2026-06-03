import os
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

from app.database import init_db, seed_admin
from app.routers import (
    analytics,
    public,
    auth,
    users,
    players,
    posts,
    members,
    partners,
    arena,
    page_settings,
    invite,
)
from app.routers.games import router as games_router

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

app = FastAPI(title="Impera")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

for router_module in (analytics, public, auth, users, players, posts, members, partners, arena, page_settings, invite):
    app.include_router(router_module.router)

app.include_router(games_router)


@app.on_event("startup")
async def startup():
    init_db()
    seed_admin()
