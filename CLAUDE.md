# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Xilfa Impera — basketball community management web app for the Impera community (BSD — Gading Serpong). FastAPI + SQLite + Jinja2, server-rendered, session auth.

The app is a **game-day operations tool**, not a CMS with games attached. Nearly everything hangs off one entity: `game`. A typical session flows: create game → fill attendees → group friends → generate balanced teams → generate schedule → score matches → share invite link → collect post-game ratings → review analytics.

## Running Locally

```bash
source .venv/bin/activate
uvicorn main:app --reload        # port 8000
uvicorn main:app --reload --port 5000
./manage.sh run                  # alias for port 5000
./manage.sh run -p 8000          # override port
./manage.sh deploy               # merge develop → master → push
```

Work on `develop`. `master` is the deploy branch — only `./manage.sh deploy` should move it.

## Deployment

- **Push to master** → GitHub Actions (`.github/workflows/deploy.yml`) → SSH deploy
- Server: `ssh xilfa` → app at `~/apps/impera/`
- Deploy script on server: `~/scripts/deploy.sh impera <repo> 8000` (preserves `*.db` across deploys)
- Ports: 5000 (local dev), 8000 (server)

## Structure

```
main.py                  # one-liner shim: from app.main import app
manage.sh                # run / deploy
plans/                   # dated planning docs — see plans/README.md
scripts/                 # one-off backfill scripts
app/
  main.py                # FastAPI() + SessionMiddleware + mounts + include_router
  config.py              # Config class — currently UNUSED (see Dead Code)
  deps.py                # get_current_user, is_superadmin, require_auth, require_superadmin
  auth.py                # passlib verify_password — currently UNUSED (see Dead Code)
  database.py            # get_db() + thin init_db()/seed_admin() wrappers
  templating.py          # Jinja2Templates + urlencode filter
  db/
    migrations.py        # run_migrations(conn) — all CREATE TABLE + ALTER blocks
    seed.py              # seed_admin() + member_period backfill
  routers/
    public.py            # / , /blog, /api/blog/{id}
    auth.py              # /masukgan (login), /joinbang (register), /setup/{token}, logout
    users.py             # /manage/users/*
    players.py           # /manage/players/*
    members.py           # /manage/members/*, WhatsApp payment-list import
    posts.py             # /manage, /manage/posts/*
    arena.py             # /manage/arena/*, /api/resolve-google-maps
    partners.py          # /manage/partners/*, /api/partners/search
    page_settings.py     # /manage/page_settings/*, /preview
    analytics.py         # /manage/analytics + 5 JSON endpoints
    invite.py            # /invite/* — PUBLIC, token-auth only
    games/
      __init__.py        # aggregates all game sub-routers
      crud.py            # list/new/edit/delete/detail, assets, finance, invite token
      attendees.py       # attendee add/edit/delete/pay/attend/assign/lock
      teams.py           # team CRUD + generate/randomize/clear
      groups.py          # player group management
      schedule.py        # schedule generate/reorder/clear/add/update/delete
      partners.py        # game partner pay/delete/add
      scoring.py         # scoring board + match scores + player stats
  services/
    analytics.py         # get_game_activity, get_player_stats, get_all_player_games,
                         # get_finance_stats, get_quality_stats, get_member_stats
    settings.py          # get_setting, set_setting, get_page_settings
    team_balance.py      # compute_player_values, generate_balanced_teams
    schedule.py          # round_robin, single/double_elimination, group_knockout,
                         # king_of_court, SUGGESTIONS map
  templates/
    public/              # index.html, blog.html
    auth/                # login.html, register.html, setup_password.html
    manage/              # _sidebar.html, dashboard.html, admin.html, players.html,
                         # members.html, users.html, arena.html, page_settings.html,
                         # analytics.html, post_form.html
    games/               # list.html, new.html, edit.html, detail.html, scoring.html
    invite/              # landing.html, player.html, post_game.html, teams.html, schedule.html
    partners/            # list.html, new.html, edit.html, detail.html
  static/                # css, img (incl. img/comics uploads), video
assets/                  # mounted at /assets — logos, deck images
```

## Database

- SQLite: `impera.db` (gitignored, lives beside `main.py`)
- Schema + migrations: `app/db/migrations.py` → `run_migrations(conn)`
- Seed: `app/db/seed.py` → `seed_admin()`
- Both called on startup via `app/database.py` `init_db()` / `seed_admin()`
- Seed admin: `admin` / `impera123`

### Tables

| Table | Purpose |
|-------|---------|
| `users` | Admin accounts. `role` = `admin` \| `superadmin`, `invite_token` for password setup |
| `player` | Person. skill_level 1-5, position_1/2, status, contact, instagram, reclub |
| `member` | Monthly membership. `UNIQUE(player_id, member_period)`, period format `"May 2026"` |
| `arena` | Venue. price, contact, map_url |
| `game` | Session. datetime, arena, pricing, num_teams, schedule_format, invite_token, status |
| `game_attendee` | Player in a game. team_id, slot_type, is_paid, is_attend, locked |
| `game_team` | Team within a game. team_name, team_color, team_color_name |
| `game_player_group` / `_members` | Friends pinned to the same team during generation |
| `game_match` | Fixture. round_number, bracket_slot, scores, winner, is_tbd |
| `game_player_stat` | Box score per match per player. `UNIQUE(match_id, player_id)` |
| `game_partner` | Partner engaged for a game (videographer, photographer, referee). fee, is_paid |
| `partner` | Partner directory. types, default_fee, internal_rating, is_active |
| `game_asset` | Video/photo links for a game, optionally attributed to a game_partner |
| `game_rating` | Post-game feedback. rating 1-5, great_things/could_be_improved (CSV tags), feedback |
| `game_finance_entry` | Manual income/expense line items per game |
| `posts` / `post_images` | Public blog. status draft\|published, cover_image_id |
| `site_settings` | Homepage CMS. `UNIQUE(page, section, key)` |
| `changelog` | Audit table — created but currently unused |

### Adding a column

Add a guarded `ALTER TABLE ADD COLUMN` in `app/db/migrations.py`. **The guard must handle a fresh DB** — `PRAGMA table_info` on a table that does not exist yet returns an empty list, so an unguarded ALTER will crash on a new install. Follow the `game_player_stat` pattern (`if cols and 'x' not in cols`), and always place ALTER blocks *after* the matching `CREATE TABLE`.

Verify any migration change against an empty database before committing:

```bash
python3 -c "import sqlite3; from app.db.migrations import run_migrations; run_migrations(sqlite3.connect(':memory:')); print('ok')"
```

## Key Patterns

- **Session auth**: `get_current_user(request)` from `app.deps` — returns a `sqlite3.Row` or `None`
- **Guard style**: HTML routes redirect (`RedirectResponse("/masukgan", 302)`), JSON routes return `JSONResponse({"error": ...}, 401)`
- **Role check**: `is_superadmin(user)` from `app.deps`
- **DB queries**: `conn = get_db()` → cursor → `?` params → `commit()` → `conn.close()`. No ORM, no connection pool.
- **`sqlite3.Row` has no `.get()`** — use `row["col"]`, or `dict(row)` first if you need `.get()`. `app/services/team_balance.py` expects plain dicts, so callers do `[dict(a) for a in cursor.fetchall()]`.
- **Templates**: `templates.TemplateResponse(request, "subfolder/name.html", {...})` (request-first signature)
- **Settings**: `get_setting / set_setting / get_page_settings` from `app.services.settings`
- **New router**: create in `app/routers/`, add to the import tuple in `app/main.py`
- **Redirect-with-message**: errors and successes are passed as query params (`?error=...`, `?success=...`) and read back off `request.query_params`

## Domain Logic

### Team balancing (`services/team_balance.py`)
`compute_player_values(attendees, skill_weight)` scores each player as
`skill_percentile × skill_weight + position_scarcity × (1 - skill_weight)`, scaled to 0-100.
`generate_balanced_teams` then seeds locked groups first (assigning each to the team with the fewest groups, tie-broken by lowest skill sum), and snake-drafts the remaining solo players, biasing picks toward teams that have no group. `skill_weight` is per-game and tunable from the UI.

### Schedule formats (`services/schedule.py`)
- `round_robin` — modular rotation for odd team counts, greedy no-back-to-back pairing for even
- `single_elimination` / `double_elimination` (currently aliased to single)
- `group_knockout` — group stage sized by team count, then TBD knockout slots
- `king_of_court` — first match seeded, rest TBD
- `SUGGESTIONS` maps team count (2-8) to a recommended format

### Invite flow (`routers/invite.py`)
Public, unauthenticated, gated only by `game.invite_token`. Player picks their name from the attendee list, then can view their team, the schedule, and submit a post-game rating. There is no per-player secret — anyone with the link can act as any attendee.

### Analytics (`routers/analytics.py` + `services/analytics.py`)
One HTML page loads five JSON endpoints (`/manage/analytics/{players,players/all,finance,quality,members}`). Filters are passed as query params (`year`, `date_from`, `date_until`, `packed_months`).

## Routes

Roughly 120 routes. Entry points:

| Path | Description |
|------|-------------|
| `/` | Public homepage (content from `site_settings`) |
| `/blog`, `/api/blog/{id}` | Public blog |
| `/masukgan` | Login |
| `/joinbang` | Registration — **public, see Security** |
| `/setup/{token}` | Password setup via invite token |
| `/manage` | Dashboard |
| `/manage/players` | Player CRUD |
| `/manage/members` | Membership CRUD + WhatsApp import |
| `/manage/arena` | Arena CRUD |
| `/manage/partners` | Partner directory |
| `/manage/users` | User admin |
| `/manage/games` | Game list → `/manage/games/{id}` detail (tabbed) |
| `/manage/games/{id}/scoring` | Scoring board |
| `/manage/analytics` | Analytics dashboard |
| `/manage/page_settings/homepage` | Homepage CMS, `/preview` to preview |
| `/invite/{token}` | Public game invite |

Game detail is tabbed via `?tab=` — `overview` (default), `general`, `players`, `teams`, `schedule`, `scores`, `results`.

## Known Issues

Do not treat these as intentional. Confirm before building on top of them.

- **`/joinbang` is open public registration** with no invite or approval, and `users.role` defaults to `'admin'`. Anyone who finds the URL gets a full admin account.
- **`/manage/users` GET and POST only check that the caller is logged in**, not that they are superadmin — so any admin can list users and create more admins. Delete and invite *are* superadmin-gated.
- **`SECRET_KEY` falls back to a hardcoded default** in `app/main.py` when the env var is missing. Sessions are forgeable if the server's `.env` is not set.
- **`GET /manage/games/{id}` writes to the database** — it auto-populates `game_attendee` from the current month's members when the attendee list is empty. Prefetch or a double-load can insert rows.

## Dead Code

- `app/auth.py` — passlib `verify_password`, imported nowhere. Routers call `bcrypt` directly.
- `app/config.py` — `Config` class, imported nowhere. Config is read via `os.getenv` in `app/main.py`.
- `changelog` table — created by migrations, never written to.
- `pyproject.toml` dependencies are incomplete (missing `bcrypt`, `passlib`, `python-multipart`, `itsdangerous`). `requirements.txt` is the accurate list.

## Testing

`tests/` currently contains only `__init__.py` — there are no tests. There is no CI check; the only workflow is deploy-on-push-to-master. Verify changes by running the app locally.

## Plans

Planning docs live in `plans/` as `YYYY-MM-DD_plan-name.md` with a checklist. See `plans/README.md` for the format — checklists are required, and steps get marked done as they land.
