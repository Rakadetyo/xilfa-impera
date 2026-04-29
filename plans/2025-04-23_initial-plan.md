# Xilfa Impera — Project Plan

## Overview
Landing page for Impera, a basketball community in BSD-Gading Serpong.
Plays every Saturday at 18:00. Built on FastAPI + Jinja2. Designed to grow
into a full community platform over time.

## Tech Stack
- **Backend**: Python (FastAPI + Uvicorn)
- **Frontend**: Jinja2 templates + TailwindCSS (CDN)
- **Database**: SQLite (for blog/users)
- **Images**: Local storage (`app/static/img/comics/`)
- **Auth**: Hashed passwords with passlib + salt
- **Hosting**: GCP — impera.xilfa.tech (port 8000)
- **Deploy**: GitHub Actions → SSH → deploy.sh

## Design
- Theme: Comic-book / Spider-Verse streetball aesthetic
- Colors: Black (#0a0a0a) dominant, warm cream (#F5F5F0) text, gold (#C9A84C) accent, silver (#71717A) secondary
- Fonts: Bangers (display), Permanent Marker (accents), Inter (body)
- Effects: Halftone dots, comic borders, stripe dividers, glitch text shadows

---

## Phase 1 — Foundation ✓
- [x] 1.1 Project scaffold (uv, .envrc, .gitignore, pyproject)
- [x] 1.2 FastAPI app structure
- [x] 1.3 Landing page — hero, about, schedule, social links
- [x] 1.4 Git + GitHub repo (github.com/Rakadetyo/xilfa-impera)
- [x] 1.5 CI/CD — GitHub Actions → deploy.sh impera 8000
- [x] 1.6 Caddy block for impera.xilfa.tech → localhost:8000
- [x] 1.7 deploy.sh updated on server to support uvicorn + port arg
- [x] 1.8 DNS A record on Cloudflare → 34.69.152.71 (proxied)
- [x] 1.9 GitHub Actions secrets set
- [x] 1.10 Hero redesign — video bg, halftone pattern, comic styling, animated crown logo

---

## Phase 2 — Comic Blog System

### 2.1 Database Schema
```sql
-- Users table (admins)
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Posts table
CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    author_id INTEGER NOT NULL,
    status TEXT CHECK(status IN ('draft', 'published')) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (author_id) REFERENCES users(id)
);

-- Post images table (multiple per post)
CREATE TABLE post_images (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    display_order INTEGER DEFAULT 0,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
);
```

### 2.2 Backend API Endpoints
```
Public:
- GET  /blog              → List published posts (grid view)
- GET  /blog/{post_id}    → Get single post (returns JSON for modal)
- GET  /                   → Landing page (add link to /blog)

Admin (require auth):
- GET  /masukgan          → Login page
- POST /masukgan          → Handle login
- GET  /admin             → Dashboard (list all posts, drafts)
- GET  /admin/new         → Create new post form
- POST /admin/posts       → Create post
- GET  /admin/posts/{id}  → Edit post form
- POST /admin/posts/{id}  → Update post
- POST /admin/posts/{id}/delete → Delete post
- POST /admin/logout      → Logout
```

### 2.3 Frontend Pages

**Blog Page (`/blog`)**
- Grid of "closed comic books" — each card looks like a comic cover
- Non-symmetrical masonry-style grid (varying heights)
- Comic cover: thumbnail image, title overlay, date
- Hover effect: slight lift + border glow
- Click opens modal

**Comic Modal (on click)**
- Full-screen overlay with dark backdrop
- Centered "open comic book" layout:
  - Left page (60%): Image grid — non-symmetrical layout, multiple photos
  - Right page (40%): Title, author, date, body text
- Close button (X) top-right
- Comic book binding visual in center
- Smooth open/close animation

**Login Page (`/masukgan`)**
- Hidden URL (not linked from anywhere)
- Comic-style login form
- Username + password fields
- Comic border styling
- Error messages in speech bubble style

**Admin Dashboard (`/admin`)**
- List of all posts (drafts + published)
- Status badges (Draft = gray, Published = gold)
- Actions: Edit, Delete, Toggle Publish
- "New Post" button
- Quick stats: Total posts, Drafts, Published

**Create/Edit Post Form**
- Title input
- Body textarea (rich text or markdown)
- Image upload (multiple) — drag & drop zone
- Image reordering
- Preview button
- Save as Draft / Publish buttons

### 2.4 Design Details

**Closed Comic Card:**
- Thick border (comic style)
- Corner fold effect (CSS triangle)
- Title at bottom with gradient overlay
- Date badge in corner
- Shadow offset effect

**Open Comic Modal:**
- Two-page spread look
- Center spine (vertical line/gradient)
- Left: photo grid (masonry, 2-3 columns)
- Right: Typography for reading
- Page numbers (optional)
- Comic halftone texture overlay

**Color Palette (Blog):**
- Same as main site + add:
  - Comic red accents for CTAs
  - Yellow/gold for published badges

### 2.5 Image Handling
- Upload to `app/static/img/comics/`
- Auto-generate thumbnails for grid
- Original for modal
- Supported: jpg, png, webp
- Max size: 5MB per image
- Lazy loading for performance

### 2.6 Auth Flow
- Session-based auth (cookie)
- Passwords hashed with bcrypt
- 30-day session expiry
- Protected routes redirect to /masukgan

---

## Phase 3 — Future
- [ ] Event/game schedule management
- [ ] Announcements board
- [ ] Member roster (public view)
- [ ] Game results + stats
- [ ] Registration / join form

---

## Task Breakdown

### Backend
- [ ] 2.2.1 Setup SQLite DB and create tables
- [ ] 2.2.2 Add user model with password hashing
- [ ] 2.2.3 Create auth endpoints (/masukgan)
- [ ] 2.2.4 Create blog API endpoints
- [ ] 2.2.5 Add image upload handling

### Frontend
- [ ] 2.3.1 Create blog page template (/blog)
- [ ] 2.3.2 Create comic card grid (closed state)
- [ ] 2.3.3 Create comic modal (open state)
- [ ] 2.3.4 Create login page (/masukgan)
- [ ] 2.3.5 Create admin dashboard (/admin)
- [ ] 2.3.6 Create post form (/admin/new, /admin/posts/{id})

### Integration
- [ ] 2.4.1 Connect blog to main nav
- [ ] 2.4.2 Test auth flow
- [ ] 2.4.3 Test image upload
- [ ] 2.4.4 Mobile responsive check

---

## Server Notes

- **Reverse proxy**: Caddy (not nginx) at `/etc/caddy/Caddyfile`
- **App port**: 8000
- **App dir**: `~/apps/impera`
- **Logs**: `~/logs/impera.log`
- **DNS**: Cloudflare, proxied — zone `4259168f6dc9cd639d4c088059a4f626`
