#!/bin/bash
# Azure App Service startup script.
# $PORT is injected by Azure at runtime.

# Ensure writable data directory exists (SQLite dev default, R2 placeholder).
mkdir -p /home/site/wwwroot/data

exec gunicorn \
  -w 2 \
  -k uvicorn.workers.UvicornWorker \
  app.main:app \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --access-logfile '-' \
  --error-logfile '-'
