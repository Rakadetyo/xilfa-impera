# Devlog — Xilfa Impera

## 2025-04-23 — Foundation

### Done
- Project scaffold: uv, FastAPI, Jinja2, uvicorn, python-dotenv, aiofiles
- Landing page: hero / about / schedule / social — black+white+gold palette
- GitHub repo: github.com/Rakadetyo/xilfa-impera
- CI/CD: GitHub Actions → SSH → deploy.sh impera 8000

### Pending (server-side)
1. Update `~/scripts/deploy.sh` on GCP to support uvicorn:

```bash
#!/bin/bash
APP_NAME=$1
GIT_REPO=$2
APP_PORT=${3:-5000}
APP_DIR=~/apps/$APP_NAME

mkdir -p $APP_DIR

if [ -d "$APP_DIR/.git" ]; then
    cd $APP_DIR && git pull
else
    rm -rf $APP_DIR && git clone $GIT_REPO $APP_DIR && cd $APP_DIR
fi

[ ! -d ".venv" ] && python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p instance

pkill -f ":$APP_PORT" 2>/dev/null || true

if grep -rq "fastapi" pyproject.toml 2>/dev/null; then
    nohup uvicorn main:app --host=0.0.0.0 --port=$APP_PORT > ~/logs/$APP_NAME.log 2>&1 &
else
    FLASK_APP=main.py nohup flask run --host=0.0.0.0 --port=$APP_PORT > ~/logs/$APP_NAME.log 2>&1 &
fi

echo "Deployed $APP_NAME → port $APP_PORT"
```

2. Add nginx server block for `impera.xilfa.tech` → see PLAN.md
3. Add GitHub Actions secrets to xilfa-impera repo (same values as stash)

### Next
- Fill in real social links (Instagram, WhatsApp, Reclub)
- Fill in member/session count stats on About section
- Phase 2 planning once landing is live
