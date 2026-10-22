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

# 004 与 006 必须在 003 之后重放：
# - 003 的 GRANT DELETE ON campus.import_issues 是历史遗留，006 会收回；
#   若恢复后只跑 003，campus_app 将重新获得直接删除异常明细的权限。
# - 006 还负责创建审计函数与触发器、授予受控函数执行权，均为幂等操作。
docker compose exec -T campus-db psql -U "$DB_USER" -d "$DB_NAME" -q -v ON_ERROR_STOP=1 -f - < sql/004_internal_auth.sql
docker compose exec -T campus-db psql -U "$DB_USER" -d "$DB_NAME" -q -v ON_ERROR_STOP=1 -f - < sql/006_import_scope.sql

echo "verifying restored permissions ..."
DELETE_PRIV=$(docker compose exec -T campus-db psql -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT has_table_privilege('campus_app','campus.import_issues','DELETE');" | tr -d '[:space:]')
if [ "$DELETE_PRIV" != "f" ]; then
  echo "ERROR: 恢复后 campus_app 仍可 DELETE import_issues（期望 f，实际 ${DELETE_PRIV}）" >&2
  exit 1
fi
FUNC_COUNT=$(docker compose exec -T campus-db psql -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace \
   WHERE n.nspname = 'campus' AND p.proname IN ('clear_import_issues','record_import_issues');" | tr -d '[:space:]')
if [ "$FUNC_COUNT" != "2" ]; then
  echo "ERROR: 恢复后缺少受控审计函数（期望 2，实际 ${FUNC_COUNT}）" >&2
  exit 1
fi

echo "done"
