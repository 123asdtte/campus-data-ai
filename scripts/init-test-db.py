#!/usr/bin/env python
"""把 sql/001_schema.sql 应用到测试库。

CI 与本地共用：GitHub Actions 的 runner 不保证装了 psql 客户端，
而 psycopg 本来就是项目依赖，直接用它对测试库执行建表脚本最省事。

用法：
    python scripts/init-test-db.py                       # 读 CAMPUS_TEST_DATABASE_URL
    python scripts/init-test-db.py postgresql://...      # 显式给 DSN
    python scripts/init-test-db.py --force               # 已有 campus schema 也重建（仅删 schema）

安全约束：只对「campus schema 不存在」或显式 --force 的库执行，
避免误把建表脚本打到已有数据的主库上。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = ROOT / "sql" / "001_schema.sql"

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("缺少 psycopg：先执行 pip install -r import-api/requirements-dev.txt")


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化测试库结构")
    parser.add_argument("dsn", nargs="?", default=os.environ.get("CAMPUS_TEST_DATABASE_URL", ""))
    parser.add_argument("--force", action="store_true", help="已存在 campus schema 时先删除再重建")
    args = parser.parse_args()

    dsn = (args.dsn or "").strip()
    if not dsn:
        sys.exit("未提供 DSN：设置 CAMPUS_TEST_DATABASE_URL 或作为第一个参数传入")
    if not SCHEMA_SQL.exists():
        sys.exit(f"找不到建表脚本：{SCHEMA_SQL}")

    script = SCHEMA_SQL.read_text(encoding="utf-8")
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('campus.students') AS oid")
            exists = cur.fetchone()[0] is not None

        if exists and not args.force:
            print("测试库已存在 campus schema，跳过初始化（需要重建请加 --force）")
            return 0
        if exists:
            print("--force：删除既有 campus schema")
            conn.execute("DROP SCHEMA campus CASCADE")

        conn.execute(script)
        print(f"已应用 {SCHEMA_SQL.name} → {_redact(dsn)}")
    return 0


def _redact(dsn: str) -> str:
    """打印时隐藏密码，避免日志泄露凭据。"""
    if "@" not in dsn or "//" not in dsn:
        return dsn
    head, tail = dsn.split("//", 1)
    credentials, host = tail.split("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{head}//{user}:***@{host}"


if __name__ == "__main__":
    raise SystemExit(main())
