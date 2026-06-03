# Devlog — Xilfa Impera

## 2025-04-23 — Foundation + Live Deploy

### Done
- Project scaffold: uv, FastAPI, Jinja2, uvicorn, python-dotenv, aiofiles
- Landing page: hero / about / schedule / social — black+white+gold palette
- GitHub repo: github.com/Rakadetyo/xilfa-impera
- CI/CD: GitHub Actions → SSH → deploy.sh impera 8000
- GitHub Actions secrets set (SERVER_HOST, SERVER_USER, DEPLOY_SSH_KEY)
- `~/scripts/deploy.sh` updated on GCP — now supports uvicorn + port arg, backwards-compatible with stash
- Server uses **Caddy** (not nginx) — added `@impera` block proxying `:8000`
- DNS A record added on Cloudflare for `impera.xilfa.tech` → 34.69.152.71 (proxied)
- First deploy ran successfully — app live at impera.xilfa.tech

### Fixes during setup
- `TemplateResponse` signature changed in Starlette 1.0 — updated to `templates.TemplateResponse(request, "index.html")`
- Empty `app/static/` dir not tracked by git — added `.gitkeep` files

### Next
- Fill in real social links (Instagram, WhatsApp, Reclub)
- Fill in member/session count stats on About section
- Phase 2 planning

---

## 2025-04-23 — Hero Redesign (Comic Style)

### Done
- Add Bangers + Permanent Marker fonts for comic aesthetic
- Add video background placeholder (YouTube iframe)
- Add halftone dot pattern with center vignette
- Add dark vignette behind IMPERA text for readability
- Add comic borders + stripe dividers throughout
- Update colors: gold accent (#C9A84C), silver secondary (#71717A), black/white base
- Add layered shadow on IMPERA text (gold + silver)
- Add 1px black stroke on IMPERA
- Update stats: 90+ members, 100+ sessions, Jetz home court
- Add social links: Instagram, Reclub (WhatsApp pending)
- Add spinning crown logo above IMPERA text
- Reorder hero: IMPERA above BSD text

### Visual Effects
- Halftone dots: visible in center, fades toward edges
- Hero vignette: dark overlay behind text area
- Comic borders: thick black with offset shadow
- Stripe dividers: diagonal silver lines between sections
- Glitch text: gold + silver layered shadows

### Next
- Replace video placeholder with real basketball footage
- Add WhatsApp link when available
- Mobile responsiveness check
