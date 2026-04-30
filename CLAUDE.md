# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Xilfa Impera — basketball community management web app built with FastAPI + SQLite.

## Running Locally

```bash
# Activate venv
source .venv/bin/activate

# Run dev server (port 5000)
uvicorn main:app --reload

# Or with Flask-style
flask run --reload
```

## Deployment

- **Push to master** → triggers GitHub Actions → deploys to server via SSH
- Server: `ssh xilfa` → app at `~/apps/impera/`
- Deploy script: `~/scripts/deploy.sh` (preserves `*.db` files across deploys)
- Ports: 5000 (manual), 8000 (GitHub Actions)

## Database

- SQLite: `impera.db` (gitignored — not tracked)
- Schema: `app/database.py` — `init_db()` runs on every startup with `CREATE TABLE IF NOT EXISTS`
- Migrations: Add `ALTER TABLE ADD COLUMN` checks in `init_db()` for new columns
- Seed admin: `admin` / `impera123`

## Key Patterns

- **Session auth**: `get_current_user(request)` reads `request.session["user_id"]`
- **Role check**: `is_superadmin(user)` checks `user.role == "superadmin"`
- **DB queries**: Use `get_db()` → cursor → execute with `?` params → commit → close
- **Template rendering**: `templates.TemplateResponse(request, "name.html", {...})`

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

## Important Notes

- `impera.db` must NOT be committed to git — already in `.gitignore`
- When adding new DB columns, add migration check in `app/database.py` `init_db()`
- Use `ON CONFLICT` for upsert operations (SQLite)
- All form inputs use FastAPI `Form(...)` parameters
