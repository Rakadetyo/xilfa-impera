# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Xilfa Impera — basketball community management web app built with FastAPI + SQLite.

## Running Locally

```bash
source .venv/bin/activate
uvicorn main:app --reload        # port 8000
uvicorn main:app --reload --port 5000
./manage.sh run                  # alias for port 5000
./manage.sh deploy               # merge develop → master → push
```

## Deployment

- **Push to master** → GitHub Actions → SSH deploy to server
- Server: `ssh xilfa` → app at `~/apps/impera/`
- Deploy script: `~/scripts/deploy.sh` (preserves `*.db` across deploys)
- Ports: 5000 (manual), 8000 (GitHub Actions)

## Structure

```
main.py                  # one-liner shim: from app.main import app
app/
  main.py                # FastAPI() + middleware + mounts + include_router (~45 lines)
  config.py              # Config class (SECRET_KEY, DEBUG)
  deps.py                # get_current_user, is_superadmin, require_auth, require_superadmin
  auth.py                # verify_password only
  database.py            # get_db() + thin init_db()/seed_admin() wrappers
  templating.py          # Jinja2Templates + urlencode filter
  db/
    migrations.py        # run_migrations(conn) — all CREATE TABLE + ALTER blocks
    seed.py              # seed_admin() + member_period backfill
  routers/
    analytics.py
    public.py            # / , /blog, /api/blog/{id}
    auth.py              # /masukgan, /joinbang, /setup, logout
    users.py             # /manage/users/*
    players.py           # /manage/players/*
    posts.py             # /manage, /manage/posts/*
    members.py           # /manage/members/*, WhatsApp import
    partners.py          # /manage/partners/*
    arena.py             # /manage/arena/*, /api/resolve-google-maps
    page_settings.py     # /manage/page_settings/*, /preview
    invite.py            # /invite/*
    games/
      __init__.py        # aggregates all game sub-routers
      crud.py            # list/new/edit/delete/detail, assets, finance, invite token
      attendees.py       # attendee add/edit/delete/pay/attend/assign
      teams.py           # team CRUD + generate/randomize/clear
      groups.py          # player group management
      schedule.py        # schedule generate/reorder/clear/add/update/delete
      partners.py        # game partner pay/delete/add
      scoring.py         # scoring board + match scores + player stats
  services/
    analytics.py
    settings.py          # get_setting, set_setting, get_page_settings
    team_balance.py      # compute_player_values, generate_balanced_teams
    schedule.py          # round_robin, single/double_elimination, group_knockout, king_of_court
  templates/
    public/              # index.html, blog.html
    auth/                # login.html, register.html, setup_password.html
    manage/              # _sidebar.html, dashboard.html, admin.html, players.html,
                         # members.html, users.html, arena.html, page_settings.html,
                         # analytics.html, post_form.html
    games/               # list.html, new.html, edit.html, detail.html, scoring.html
    invite/              # landing.html, player.html, post_game.html, teams.html, schedule.html
    partners/            # list.html, new.html, edit.html, detail.html
  static/
```

## Database

- SQLite: `impera.db` (gitignored)
- Schema + migrations: `app/db/migrations.py` → `run_migrations(conn)`
- Seed: `app/db/seed.py` → `seed_admin()`
- Both called via `app/database.py` `init_db()` / `seed_admin()` on startup
- **Adding a new column**: add `ALTER TABLE ADD COLUMN` check in `app/db/migrations.py`
- Seed admin: `admin` / `impera123`

## Key Patterns

- **Session auth**: `get_current_user(request)` from `app.deps` — returns user row or None
- **Role check**: `is_superadmin(user)` from `app.deps`
- **DB queries**: `conn = get_db()` → cursor → `?` params → commit → `conn.close()`
- **Templates**: `templates.TemplateResponse(request, "subfolder/name.html", {...})`
- **Settings**: `get_setting / set_setting / get_page_settings` from `app.services.settings`
- **New router**: create in `app/routers/`, add `app.include_router(mod.router)` in `app/main.py`

## Common Routes

| Path | Description |
|------|-------------|
| `/` | Home |
| `/masukgan` | Login |
| `/manage` | Dashboard |
| `/manage/players` | Player CRUD |
| `/manage/members` | Member CRUD |
| `/manage/arena` | Arena CRUD |
| `/manage/users` | User CRUD (superadmin only) |
| `/manage/games` | Game list |
| `/manage/analytics` | Analytics dashboard |
