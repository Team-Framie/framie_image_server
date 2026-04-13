#!/usr/bin/env bash
set -euo pipefail
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001} --workers ${UVICORN_WORKERS:-1} --limit-concurrency ${UVICORN_LIMIT:-8}
