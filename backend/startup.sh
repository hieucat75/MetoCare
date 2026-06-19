#!/bin/bash
# Azure App Service startup script.
# $PORT is injected by Azure at runtime.
exec gunicorn \
  -w 2 \
  -k uvicorn.workers.UvicornWorker \
  app.main:app \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --access-logfile '-' \
  --error-logfile '-'
