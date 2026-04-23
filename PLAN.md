# Xilfa Impera — Project Plan

## Overview
Landing page for Impera, a basketball community in BSD-Gading Serpong.
Plays every Saturday at 18:00. Built on FastAPI + Jinja2. Designed to grow
into a full community platform over time.

## Tech Stack
- **Backend**: Python (FastAPI + Uvicorn)
- **Frontend**: Jinja2 templates + TailwindCSS (CDN)
- **Database**: SQLite (reserved for future features)
- **Hosting**: GCP — impera.xilfa.tech (port 8000)
- **Deploy**: GitHub Actions → SSH → deploy.sh

## Design
- Theme: Comic-book / Spider-Verse streetball aesthetic
- Colors: Black (#0a0a0a) dominant, white/silver text, gold (#C9A84C) accent, silver (#71717A) secondary
- Fonts: Bangers (display), Permanent Marker (accents), Inter (body)
- Effects: Halftone dots, comic borders, stripe dividers, glitch text shadows

## Phases

### Phase 1 — Foundation ✓
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

### Phase 2 — Community Features
- [ ] Event/game schedule management
- [ ] Announcements board
- [ ] Member roster (public view)
- [ ] Admin panel (auth-gated)

### Phase 3 — Engagement
- [ ] Game results + stats
- [ ] Photo gallery
- [ ] Registration / join form

## Server Notes

- **Reverse proxy**: Caddy (not nginx) at `/etc/caddy/Caddyfile`
- **App port**: 8000
- **App dir**: `~/apps/impera`
- **Logs**: `~/logs/impera.log`
- **DNS**: Cloudflare, proxied — zone `4259168f6dc9cd639d4c088059a4f626`
