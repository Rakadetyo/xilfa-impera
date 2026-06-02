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
    *)
        echo "Usage: ./manage.sh run -p [port]"
        exit 1
        ;;
esac
