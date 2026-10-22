#!/usr/bin/env python
"""初始化测试库：001 结构 → 003 角色 → 004 内部认证 nonce。

为什么不是「按编号全跑」：
- 002 是**演示数据**（200 学生 / 300 异动），且会对 operation_logs 执行宽范围
  DELETE，会污染审计基线，因此默认不执行；需要时显式 --with-demo。
- 003 需要 psql 变量（密码）与 \\gexec，CI 里没有 psql，故内置最小加载器。

两种连接身份（CI 强制区分）：
- 管理连接（--admin-dsn / CAMPUS_TEST_ADMIN_DATABASE_URL）：建表、建角色、授权、清理；
- 业务连接（CAMPUS_TEST_DATABASE_URL，campus_app 身份）：跑测试与权限断言。

用法：
    python scripts/init-test-db.py --admin-dsn postgresql://... \
        --app-password pw --verify
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"

try:
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("缺少 psycopg：先执行 pip install -r import-api/requirements-dev.txt")


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_psql_script(conn, path: Path, variables: dict[str, str]) -> None:
    """执行只含 \\set / :'var' / \\gexec 的 psql 脚本（003 的用法）。"""
    buffer: list[str] = []
    statements = 0

    def flush() -> None:
        nonlocal buffer, statements
        sql = "\n".join(buffer).strip()
        buffer = []
        if not sql:
            return
        for name, value in variables.items():
            sql = sql.replace(f":'{name}'", _literal(value))
        if re.search(r":'[a-z_]+'", sql):
            raise SystemExit(f"{path.name}: 存在未提供的 psql 变量：{sql[:120]}")
        conn.execute(sql)
        statements += 1

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("\\set"):
            continue
        if line == "\\gexec":
            sql = "\n".join(buffer).strip()
            buffer = []
            if not sql:
                continue
            for name, value in variables.items():
                sql = sql.replace(f":'{name}'", _literal(value))
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
            for row in rows:
                if row and row[0]:
                    conn.execute(row[0])
            statements += 1
            continue
        if line.startswith("\\"):
            raise SystemExit(f"{path.name}: 不支持的 psql 元命令 {line}")
        buffer.append(raw)

    flush()
    print(f"  {path.name}: 执行 {statements} 段")


def apply_sql_file(conn, path: Path) -> None:
    conn.execute(path.read_text(encoding="utf-8"))
    print(f"  {path.name}: 已执行")


def app_dsn_from(admin_dsn: str, password: str) -> str:
    params = conninfo_to_dict(admin_dsn)
    params["user"] = "campus_app"
    params["password"] = password
    return make_conninfo(**params)


def verify(admin_dsn: str, app_password: str) -> None:
    """以业务账号验证权限：正向通过 + 负向拒绝，任一失败即非零退出。"""
    dsn = app_dsn_from(admin_dsn, app_password)
    failures: list[str] = []
    checks: list[tuple[str, bool]] = []

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user")
            checks.append(("业务连接身份为 campus_app", cur.fetchone()[0] == "campus_app"))

            cur.execute("SELECT count(*) FROM campus.students")
            cur.fetchone()
            checks.append(("可读 students", True))

            cur.execute("SELECT to_regclass('campus.internal_nonce') IS NOT NULL")
            checks.append(("internal_nonce 表存在", cur.fetchone()[0]))

            for table, privilege, expected in [
                ("campus.import_issues", "DELETE", True),
                ("campus.students", "DELETE", False),
                ("campus.operation_logs", "INSERT", False),
                ("campus.internal_nonce", "DELETE", False),
                ("campus.internal_nonce", "UPDATE", False),
            ]:
                cur.execute("SELECT has_table_privilege('campus_app', %s, %s)", (table, privilege))
                checks.append((f"{table} {privilege} == {expected}", cur.fetchone()[0] is expected))

            cur.execute(
                "INSERT INTO campus.internal_nonce (nonce) VALUES ('init-verify') "
                "ON CONFLICT DO NOTHING"
            )
            checks.append(("可写入 nonce", True))
            try:
                cur.execute("DELETE FROM campus.internal_nonce WHERE nonce = 'init-verify'")
                failures.append("campus_app 不应能直接 DELETE nonce")
            except psycopg.errors.InsufficientPrivilege:
                checks.append(("不能直接 DELETE nonce", True))

            cur.execute("SELECT campus.cleanup_internal_nonce()")
            checks.append(("清理函数可调用", cur.fetchone()[0] >= 0))

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute("DELETE FROM campus.internal_nonce WHERE nonce = 'init-verify'")

    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} | {name}")
        if not ok:
            failures.append(name)

    if failures:
        raise SystemExit("权限校验失败：\n  - " + "\n  - ".join(failures))
    print(f"  权限校验通过（{len(checks)} 项）")


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化测试库（001 → 003 → 004）")
    parser.add_argument("dsn", nargs="?", default="", help="管理 DSN（兼容旧用法）")
    parser.add_argument("--admin-dsn", default=os.environ.get("CAMPUS_TEST_ADMIN_DATABASE_URL", ""))
    parser.add_argument("--app-password", default=os.environ.get("CAMPUS_TEST_APP_PASSWORD", "campus_test_app_pw"))
    parser.add_argument("--ro-password", default=os.environ.get("CAMPUS_TEST_RO_PASSWORD", "campus_test_ro_pw"))
    parser.add_argument("--force", action="store_true", help="已存在 campus schema 时先删除再重建")
    parser.add_argument("--with-demo", action="store_true", help="额外执行 002 演示数据（默认不执行）")
    parser.add_argument("--verify", action="store_true", help="以 campus_app 身份做正负向权限校验")
    args = parser.parse_args()

    admin_dsn = (args.admin_dsn or args.dsn or os.environ.get("CAMPUS_TEST_DATABASE_URL", "")).strip()
    if not admin_dsn:
        sys.exit("未提供管理 DSN：--admin-dsn 或 CAMPUS_TEST_ADMIN_DATABASE_URL")

    print(f"初始化测试库（管理连接：{admin_dsn.split('@')[-1]}）")
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        if args.force:
            conn.execute("DROP SCHEMA IF EXISTS campus CASCADE")
            print("  --force：已删除 campus schema")

        exists = conn.execute(
            "SELECT to_regclass('campus.students') IS NOT NULL"
        ).fetchone()[0]
        if exists and not args.force:
            print("  campus schema 已存在，跳过 001（重建请加 --force）")
        else:
            apply_sql_file(conn, SQL_DIR / "001_schema.sql")
        run_psql_script(conn, SQL_DIR / "003_roles.sql",
                        {"app_password": args.app_password, "ro_password": args.ro_password})
        apply_sql_file(conn, SQL_DIR / "004_internal_auth.sql")

        if args.with_demo:
            apply_sql_file(conn, SQL_DIR / "002_seed_demo.sql")
            print("  注意：--with-demo 已写入演示数据，会污染审计基线，仅限本地演示")

    if args.verify:
        verify(admin_dsn, args.app_password)
    print("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
