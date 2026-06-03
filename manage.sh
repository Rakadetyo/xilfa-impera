#!/usr/bin/env bash
set -e

COMMAND=$1
PORT=5000

shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--port) PORT=$2; shift 2 ;;
        *) shift ;;
    esac
done

case $COMMAND in
    run)
        source .venv/bin/activate
        uvicorn main:app --reload --port "$PORT"
        ;;
    deploy)
        git checkout master
        git merge develop --no-edit
        git push origin master
        git checkout develop
        echo "Deployed: develop → master"
        ;;
    *)
        echo "Usage: ./manage.sh <command>"
        echo "  run [-p port]  Start dev server"
        echo "  deploy         Merge develop into master and push"
        exit 1
        ;;
esac
