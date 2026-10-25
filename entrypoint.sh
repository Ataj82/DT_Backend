#!/bin/sh
set -e

# Run database migrations
echo "[entrypoint] Checking and applying database migrations (alembic upgrade head)..."
alembic upgrade head

# Execute CMD
exec "$@"
