# 2026-05-08 Modular Restructure (split monolithic main.py)

## Why

`main.py` is **4063 lines / 95 routes** in one file — routing, helpers, business logic, and migrations all mixed. Hard to navigate and edit safely.

Concrete pain points:
- `get_current_user` defined twice — `main.py:39` (reads `role`) AND `app/auth.py:9` (no role) — divergent.
- Schedule generators duplicated: `alg.py` (root, unused) AND inline at `main.py:3130-3340`.
- Root `config.py` defines `Config` class but never imported — `main.py` reads `os.getenv` directly.
- `init_db()` in `app/database.py` is 200+ lines of inline `CREATE TABLE` + `ALTER TABLE`.
- `app/__init__.py` empty — no real package factory.
- Templates partially organized (`games/`, `invite/`, `partners/` subfolders) but most live flat.

Goal: APIRouter-per-domain layout, extracted services, deduped helpers, split migrations, domain-organized templates. Behavior unchanged.

## Target Structure

```
xilfa-impera/
  main.py                  # one-liner: from app.main import app
  impera.db
  scripts/  tests/  assets/
  app/
    __init__.py
    main.py                # FastAPI() + middleware + mounts + include_router (~60 lines)
    config.py              # Config class (was root config.py)
    deps.py                # current_user, require_auth, require_superadmin (Depends)
    templating.py          # Jinja2Templates + filters
    auth.py                # verify_password only
    database.py            # get_db only
    db/
      migrations.py        # all CREATE TABLE + ALTER blocks
      seed.py              # seed_admin + member_period backfill
    routers/
      public.py            # / , /blog, /api/blog/{id}
      auth.py              # /masukgan, /joinbang, /setup, logout
      users.py             # /manage/users/*
      players.py           # /manage/players/*
      posts.py             # /manage, /manage/posts/*, /manage/new
      members.py           # /manage/members/*, WhatsApp
      partners.py          # /manage/partners/*
      arena.py             # /manage/arena/*, /api/resolve-google-maps
      page_settings.py     # /manage/page_settings/*, /preview
      invite.py            # /invite/*
      games/
        __init__.py        # parent APIRouter, prefix=/manage/games
        crud.py            # list/new/edit/delete/detail
        attendees.py
        teams.py
        groups.py
        schedule.py
        partners.py        # game-partner toggles
    services/
      settings.py          # get_setting, set_setting, get_page_settings
      team_balance.py      # compute_player_values, generate_balanced_teams
      schedule.py          # _rr_modular, _rr_greedy, generate_round_robin, single/double_elimination, group_knockout, king_of_court, SUGGESTIONS
      whatsapp.py          # import + chat-gen
    templates/
      public/   (index.html, blog.html)
      auth/     (login.html, register.html, setup_password.html)
      manage/   (_sidebar.html, dashboard.html, admin.html, post_form.html, players.html, members.html, users.html, arena.html, page_settings.html)
      games/    invite/    partners/   (unchanged)
    static/
```

Delete: `alg.py` (dead), root `config.py` (moved).

## Checklist

### Step 1 — Package skeleton + entry shim
- [ ] Create `app/main.py` = current `main.py` body verbatim
- [ ] Replace root `main.py` with one-liner `from app.main import app`
- [ ] Move `config.py` → `app/config.py`, delete root
- [ ] Delete `alg.py`
- [ ] Verify: `uvicorn main:app --reload`, `/`, `/blog`, `/manage` load

### Step 2 — Extract templating + deps
- [ ] Create `app/templating.py` (Jinja2Templates + urlencode filter)
- [ ] Create `app/deps.py` (`get_current_user`, `require_auth`, `require_superadmin`)
- [ ] Delete duplicate `get_current_user` + `is_superadmin` in `app/main.py`
- [ ] Trim `app/auth.py` to `verify_password` only
- [ ] Update all call sites in `app/main.py` to import from `app.deps`
- [ ] Verify: login + /manage flow

### Step 3 — Extract services
- [ ] `app/services/settings.py` (from `app/main.py:53-89`)
- [ ] `app/services/team_balance.py` (from `app/main.py:2014-2148`)
- [ ] `app/services/schedule.py` (from `app/main.py:3131-3340`)
- [ ] `app/services/whatsapp.py` (from `app/main.py:1145-1390`)
- [ ] Update imports, delete moved bodies from `app/main.py`
- [ ] Verify: create game → generate teams → generate round-robin schedule → WhatsApp import

### Step 4 — Split migrations
- [ ] `app/db/migrations.py` with `run_migrations(conn)` (all CREATE/ALTER from `init_db`)
- [ ] `app/db/seed.py` with `seed_admin(conn)` + `member_period` backfill
- [ ] Slim `app/database.py` to `get_db()` + thin `init_db()` calling both
- [ ] Verify: copy DB, drop, boot — schema recreates identical (`sqlite3 .schema` diff)

### Step 5 — Extract routers (one commit per domain)
- [ ] `routers/public.py` (3 routes)
- [ ] `routers/auth.py` (7 routes)
- [ ] `routers/page_settings.py` (3 routes)
- [ ] `routers/users.py` (4 routes)
- [ ] `routers/arena.py` (5 routes)
- [ ] `routers/posts.py` (7 routes)
- [ ] `routers/players.py` (5 routes)
- [ ] `routers/partners.py` (7 routes)
- [ ] `routers/members.py` (6 routes)
- [ ] `routers/invite.py` (5 routes)
- [ ] `routers/games/` package — split into `crud.py`, `attendees.py`, `teams.py`, `groups.py`, `schedule.py`, `partners.py`; aggregate in `__init__.py` (~50 routes)
- [ ] After each domain: smoke test in browser, app boots between every move

### Step 6 — Reorganize templates
- [ ] Move flat templates into `public/`, `auth/`, `manage/` subfolders
- [ ] Update `templates.TemplateResponse` paths in routers
- [ ] Update `{% extends %}` and `{% include %}` paths inside templates (notably `_sidebar.html`)
- [ ] Verify: every page renders

### Step 7 — Final cleanup
- [ ] `app/main.py` ~60 lines (imports, app, middleware, mounts, include_router, startup)
- [ ] Root `main.py` is one-liner shim
- [ ] Remove unused imports
- [ ] Update `CLAUDE.md` with new structure

## Verification (end-to-end smoke)

1. `source .venv/bin/activate && uvicorn main:app --reload`
2. `/` → `/blog` → `/masukgan` (admin/impera123) → `/manage` → `/manage/players` (add test) → `/manage/games/new` → add attendees → generate teams → generate round-robin → `/manage/members` → WhatsApp import dry-run → `/manage/partners` → `/manage/arena` → `/preview` → invite token in incognito (`/invite/{token}`)
3. `python scripts/backfill_games.py --help` (imports `app.database`)
4. Schema diff before/after: `sqlite3 impera.db .schema` identical
5. Deploy: push to `master`, GitHub Actions, prod loads

## Out of Scope

- No new features
- No DB schema changes
- No HTML/CSS edits beyond moving files + updating extends/includes
- No tests added (none exist)
- No changes to `scripts/backfill_games.py` beyond keeping `app.database` import valid
