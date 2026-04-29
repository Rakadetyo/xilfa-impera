# 2026-04-29 Manage Dashboard

## Why
Replace /admin with a proper internal dashboard at /manage. Light-background UI, user account management, and DB schema ready for future features (arena, game, player, member).

## Checklist

### 1. Rename /admin → /manage
- [x] Replace all `/admin` route decorators and redirects in `main.py`
- [x] Update all `RedirectResponse("/admin")` → `/manage`
- [x] Rename template links in `admin.html`, `post_form.html`, `index.html`, `blog.html`

### 2. DB — New Tables
- [x] Add `arena` table: id, location_name, address, price, contact_person, created_at, updated_at
- [x] Add `game` table: id, datetime, arena_id (FK), is_video, is_photo, is_referee, price_per_person, price_per_member, created_at, updated_at
- [x] Add `player` table: id, name, nickname, position_1, position_2, skill_level (1-5), is_member, contact_no, instagram, reclub, join_date, created_at, updated_at
- [x] Add `member` table: id, player_id (FK), member_start_date, member_end_date, is_paid, created_at, updated_at
- [x] Add `game_attendee` table: id, game_id (FK), player_id (FK), team_name, created_at, updated_at
- [x] Add `changelog` table: id, user_id (FK), action TEXT, created_at, updated_at
- [x] Wire all new tables into `init_db()`

### 3. User Management (in /manage)
- [x] Add GET `/manage/users` — list all users (admin only)
- [x] Add POST `/manage/users` — create new user (admin only)
- [x] Add POST `/manage/users/{user_id}/delete` — delete user (admin only, cannot delete self)
- [x] Render user list + create form within dashboard

### 4. Dashboard UI Redesign (admin.html)
- [x] Switch to light background (white/light gray base, no dark comic bg)
- [x] Add left sidebar: logo, nav links (Posts, Users; greyed-out stubs for Arena, Games, Players, Members)
- [x] Top bar: current user, logout button
- [x] Posts section: existing table, stats cards (total / drafts / published)
- [x] Users section: user list table + create account form
- [x] Link to existing login (`/masukgan`) and signup (`/joinbang`) from the UI where appropriate
- [x] Keep gold/black accent colors for buttons and badges

### 5. Cleanup
- [x] Update `post_form.html` cancel/back links → `/manage`
- [x] App loads without errors (smoke test pass)
