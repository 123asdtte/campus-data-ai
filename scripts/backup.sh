#!/usr/bin/env bash
# Backup the campus business database to backups/ as gzip-compressed SQL.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "ERROR: .env not found" >&2
  exit 1
fi

DB_USER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2)
DB_NAME=$(grep '^POSTGRES_DB=' .env | cut -d= -f2)

mkdir -p backups
STAMP=$(date +%Y%m%d_%H%M%S)
OUT="backups/campus_${STAMP}.sql.gz"

echo "backing up ${DB_NAME} ..."
docker compose exec -T campus-db \
  pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl --clean --if-exists \
  | gzip -9 > "$OUT"

echo "written: $OUT"
ls -lh "$OUT"
