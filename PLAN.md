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
- Colors: Black (#0a0a0a) dominant, white/silver text, gold (#C9A84C) accent
- Tone: Clean, minimal, community-first

## Phases

### Phase 1 — Foundation ✓
- [x] 1.1 Project scaffold (uv, .envrc, .gitignore, pyproject)
- [x] 1.2 FastAPI app structure
- [x] 1.3 Landing page — hero, about, schedule, social links
- [x] 1.4 Git + GitHub repo (github.com/Rakadetyo/xilfa-impera)
- [x] 1.5 CI/CD — GitHub Actions → deploy.sh impera 8000
- [ ] 1.6 Nginx server block for impera.xilfa.tech
- [ ] 1.7 Update deploy.sh on server to support uvicorn

### Phase 2 — Community Features
- [ ] Event/game schedule management
- [ ] Announcements board
- [ ] Member roster (public view)
- [ ] Admin panel (auth-gated)

### Phase 3 — Engagement
- [ ] Game results + stats
- [ ] Photo gallery
- [ ] Registration / join form

## Server Setup Notes

### deploy.sh update required
Current deploy.sh starts apps with `nohup flask run`. Needs updating to
support uvicorn for FastAPI apps. Pass port as 3rd arg.

See updated deploy.sh snippet in DEVLOG.md — 2025-04-23 entry.

### Nginx server block (impera.xilfa.tech)
```nginx
server {
    listen 80;
    server_name impera.xilfa.tech;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Add to `/etc/nginx/sites-available/impera.xilfa.tech` and symlink to `sites-enabled/`.
Then: `sudo nginx -t && sudo systemctl reload nginx`

### GitHub Actions secrets required
Same secrets as xilfa-stash:
- `SERVER_HOST`
- `SERVER_USER`
- `DEPLOY_SSH_KEY`
