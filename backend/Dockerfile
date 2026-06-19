# MetoCare Backend — internal DEV deployment
# Python 3.11 slim (matches requires-python = ">=3.11")
FROM python:3.11-slim

# System deps: libpq for psycopg2-binary; curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create writable dirs for SQLite dev db (not used in internal deploy but keeps
# the app happy if storage_mode=local)
RUN mkdir -p /app/data /app/storage && chmod 777 /app/data /app/storage

# Non-root user for defence-in-depth
RUN useradd -m -u 1001 mcp && chown -R mcp:mcp /app

# Writable tmp dir for Gunicorn control socket (avoids Permission denied on /tmp)
RUN mkdir -p /tmp/gunicorn && chown mcp:mcp /tmp/gunicorn

USER mcp

EXPOSE 8000

# Use Gunicorn + UvicornWorker explicitly — single worker to avoid SQLite
# race condition on create_all during startup. Azure App Service sometimes
# overrides uvicorn CMD with its own gunicorn launcher, causing 2+ workers
# to compete on the same SQLite file.
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "120", "--graceful-timeout", "30", "--worker-tmp-dir", "/tmp/gunicorn"]
