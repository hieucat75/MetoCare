#!/bin/bash
# Azure App Service startup script.
# $PORT is injected by Azure at runtime.
#
# IMPORTANT: Schema is managed exclusively by Alembic (run in CI/CD via
# `alembic upgrade head` before container restart). This script MUST NOT
# call create_all(), run migrations, or perform any schema bootstrap.
# Single worker (--workers 1) is mandatory when using SQLite; kept as 1
# for production PostgreSQL as well to simplify horizontal scaling via
# multiple App Service instances rather than intra-process workers.

exec gunicorn \
  --workers 1 \
  -k uvicorn.workers.UvicornWorker \
  app.main:app \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --graceful-timeout 30 \
  --worker-tmp-dir /tmp/gunicorn \
  --access-logfile '-' \
  --error-logfile '-'
