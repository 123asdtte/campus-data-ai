"""PR-E：004 / 005 / 006 迁移与回退演练（隔离库，不接触正式库）。

用法（在仓库根目录）：
    python scripts/rehearse_migrations.py \
        --admin-dsn postgresql://campus_test:campus_test@127.0.0.1:5433/campus_test

演练内容：
1. 新建一次性数据库 `campus_rehearsal` 与 `gateway_rehearsal`；
2. 业务库：001 → 004 → 006，每步验证对象存在；
3. 004 重复执行（幂等）→ 回退（删函数/表）→ 再执行；
4. 006 重复执行（幂等）→ 回退（删触发器/函数/索引/列）→ 再执行；
5. 网关库：005 单次执行并验证 sys_* 表与种子数据；
6. 默认演练结束后删除两个一次性数据库（--keep 可保留）。

说明：
- `003_roles.sql` 是集群级角色脚本（含 psql 元命令），不属于单库迁移，本脚本跳过；
  测试库所属集群已存在 `campus_app` / `campus_ro` / `campus_nonce_cleaner`。
- 004 回退**不删除** `campus_nonce_cleaner` 角色（集群级，其他库仍在使用）。
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import psycopg


def db_dsn(admin_dsn: str, dbname: str) -> str:
    """把管理连接指向另一数据库（保留 host/port/user/password）。"""
    params = psycopg.conninfo.conninfo_to_dict(admin_dsn)
    params.pop("dbname", None)
    return psycopg.conninfo.make_conninfo(dbname=dbname, **params)

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"

BUSINESS_DB = "campus_rehearsal"
GATEWAY_DB = "gateway_rehearsal"


def log(ok: bool, step: str, detail: str = "") -> None:
    """统一输出 PASS/FAIL 行，便于 CI 或人工留档。"""
    print(f"{'PASS' if ok else 'FAIL'}\t{step}\t{detail}")


def exec_sql(conn: psycopg.Connection, path: Path) -> float:
    """执行整份 SQL 文件并返回耗时（秒）。"""
    sql = path.read_text(encoding="utf-8")
    started = time.monotonic()
    with conn.cursor() as cur:
        cur.execute(sql)
    return time.monotonic() - started


def scalar(conn: psycopg.Connection, sql: str, params: tuple = ()):
    with conn.cursor() as cur:
        # psycopg 在传入空参数元组时也会解析 % 占位符，故无参数时不传 params
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        row = cur.fetchone()
    return row[0] if row else None


def recreate_db(admin: psycopg.Connection, name: str) -> None:
    """删除并重建一次性数据库。"""
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        cur.execute(f'CREATE DATABASE "{name}"')


def drop_db(admin: psycopg.Connection, name: str) -> None:
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def rehearse_business(admin: psycopg.Connection, admin_dsn: str) -> bool:
    """业务库 001/004/006 的升级、幂等与回退演练。"""
    ok = True
    recreate_db(admin, BUSINESS_DB)
    dsn = db_dsn(admin_dsn, BUSINESS_DB)

    with psycopg.connect(dsn, autocommit=True) as conn:
        elapsed = exec_sql(conn, SQL_DIR / "001_schema.sql")
        has_schema = scalar(conn, "SELECT to_regnamespace('campus') IS NOT NULL")
        log(bool(has_schema), "001 建库结构", f"{elapsed:.2f}s")
        ok &= bool(has_schema)

        for round_no in (1, 2):
            elapsed = exec_sql(conn, SQL_DIR / "004_internal_auth.sql")
            nonce_ok = scalar(conn, "SELECT to_regclass('campus.internal_nonce') IS NOT NULL")
            func_ok = scalar(conn, "SELECT to_regprocedure('campus.cleanup_internal_nonce()') IS NOT NULL")
            log(bool(nonce_ok and func_ok), f"004 第 {round_no} 次执行（幂等）", f"{elapsed:.2f}s")
            ok &= bool(nonce_ok and func_ok)

        with conn.cursor() as cur:
            cur.execute("DROP FUNCTION IF EXISTS campus.cleanup_internal_nonce()")
            cur.execute("DROP TABLE IF EXISTS campus.internal_nonce")
        rolled_back = scalar(conn, "SELECT to_regclass('campus.internal_nonce') IS NULL")
        log(bool(rolled_back), "004 回退（删函数/表；保留集群级角色）")
        ok &= bool(rolled_back)

        elapsed = exec_sql(conn, SQL_DIR / "004_internal_auth.sql")
        re_ok = scalar(conn, "SELECT to_regclass('campus.internal_nonce') IS NOT NULL")
        log(bool(re_ok), "004 回退后重放", f"{elapsed:.2f}s")
        ok &= bool(re_ok)

        for round_no in (1, 2):
            elapsed = exec_sql(conn, SQL_DIR / "006_import_scope.sql")
            col_ok = scalar(
                conn,
                "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='campus' AND table_name='import_batches' AND column_name='created_dept_id')",
            )
            trig_ok = scalar(
                conn,
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgname IN ('trg_import_batches_audit','trg_import_issues_audit') AND NOT tgisinternal",
            )
            log(bool(col_ok and trig_ok == 2), f"006 第 {round_no} 次执行（幂等）", f"{elapsed:.2f}s")
            ok &= bool(col_ok and trig_ok == 2)

        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS trg_import_issues_audit ON campus.import_issues")
            cur.execute("DROP TRIGGER IF EXISTS trg_import_batches_audit ON campus.import_batches")
            cur.execute("DROP FUNCTION IF EXISTS campus.audit_import_stmt()")
            cur.execute("DROP INDEX IF EXISTS campus.idx_batches_dept")
            cur.execute("ALTER TABLE campus.import_batches DROP COLUMN IF EXISTS created_dept_id")
        gone = scalar(
            conn,
            "SELECT NOT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='campus' AND table_name='import_batches' AND column_name='created_dept_id')",
        )
        log(bool(gone), "006 回退（触发器/函数/索引/列）")
        ok &= bool(gone)

        elapsed = exec_sql(conn, SQL_DIR / "006_import_scope.sql")
        re_ok = scalar(
            conn,
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='campus' AND table_name='import_batches' AND column_name='created_dept_id')",
        )
        log(bool(re_ok), "006 回退后重放", f"{elapsed:.2f}s")
        ok &= bool(re_ok)

        # 升级前后数据一致性：在一个空库上应是 0 行；这里显式验证迁移不做数据改写
        students = scalar(conn, "SELECT count(*) FROM campus.students")
        log(students == 0, "迁移未写入业务行", f"students={students}")
        ok &= students == 0
    return ok


def rehearse_gateway(admin: psycopg.Connection, admin_dsn: str) -> bool:
    """网关库 005 单次初始化演练（005 非幂等，不能重复执行）。"""
    recreate_db(admin, GATEWAY_DB)
    dsn = db_dsn(admin_dsn, GATEWAY_DB)
    with psycopg.connect(dsn, autocommit=True) as conn:
        elapsed = exec_sql(conn, SQL_DIR / "005_gateway_bootstrap.sql")
        users = scalar(conn, "SELECT count(*) FROM sys_user")
        menus = scalar(conn, "SELECT count(*) FROM sys_menu")
        clients = scalar(conn, "SELECT count(*) FROM sys_client")
        colleges = scalar(conn, "SELECT count(*) FROM sys_dept WHERE dept_name IN ('计算机学院','电子信息学院')")
        import_perms = scalar(
            conn,
            "SELECT count(*) FROM sys_menu WHERE perms LIKE 'import:batch:%'",
        )
        ok = users >= 3 and menus > 50 and clients >= 1 and colleges == 2 and import_perms == 6
        log(ok, "005 网关库初始化", f"{elapsed:.2f}s users={users} menus={menus} import_perms={import_perms}")
        return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-dsn", required=True, help="测试库集群的管理连接（campus_test）")
    parser.add_argument("--keep", action="store_true", help="保留演练数据库")
    args = parser.parse_args()

    ok = True
    started = time.monotonic()
    with psycopg.connect(args.admin_dsn, autocommit=True) as admin:
        print(f"演练集群：{admin.info.host}:{admin.info.port}")
        ok &= rehearse_business(admin, args.admin_dsn)
        ok &= rehearse_gateway(admin, args.admin_dsn)
        if not args.keep:
            drop_db(admin, BUSINESS_DB)
            drop_db(admin, GATEWAY_DB)
            log(True, "清理演练数据库")
    print(f"=== 演练{'通过' if ok else '失败'}，总耗时 {time.monotonic() - started:.2f}s ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
