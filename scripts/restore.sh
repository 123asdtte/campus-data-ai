#!/usr/bin/env bash
# Restore the campus business database from a .sql.gz backup.
# Usage: ./scripts/restore.sh backups/campus_YYYYmmdd_HHMMSS.sql.gz
set -euo pipefail

cd "$(dirname "$0")/.."

if [ $# -ne 1 ]; then
  echo "Usage: $0 <backup-file.sql.gz>" >&2
  exit 1
fi

BACKUP="$1"
if [ ! -f "$BACKUP" ]; then
  echo "ERROR: backup file not found: $BACKUP" >&2
  exit 1
fi

DB_USER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2)
DB_NAME=$(grep '^POSTGRES_DB=' .env | cut -d= -f2)

echo "This will OVERWRITE database '${DB_NAME}' with ${BACKUP}."
printf "Type the database name to confirm: "
read -r CONFIRM
if [ "$CONFIRM" != "$DB_NAME" ]; then
  echo "aborted"
  exit 1
fi

echo "restoring ..."
gunzip -c "$BACKUP" | docker compose exec -T campus-db \
  psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q

echo "restore finished; re-applying role grants ..."
APP_PW=$(grep '^APP_DB_PASSWORD=' .env | cut -d= -f2)
RO_PW=$(grep '^RO_DB_PASSWORD=' .env | cut -d= -f2)
docker compose exec -T campus-db psql -U "$DB_USER" -d "$DB_NAME" \
  -v app_password="$APP_PW" -v ro_password="$RO_PW" -q -f - < sql/003_roles.sql

echo "done"
