#!/bin/sh
# 初始化 AI POC 库：把 compose 传入的角色密码作为 psql 变量执行 schema/seed。
# 只在数据卷为空时由 postgres 镜像的 initdb 机制执行一次。
set -e

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v ai_ro_password="$AI_RO_PASSWORD" \
  -v ai_audit_password="$AI_AUDIT_PASSWORD" \
  -f /opt/ai-sql/001_schema.sql
