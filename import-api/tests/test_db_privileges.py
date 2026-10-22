"""数据库权限验收：业务账号 campus_app 的正向能力与负向边界。

要求 CAMPUS_TEST_DATABASE_URL 指向 campus_app 身份、CAMPUS_TEST_ADMIN_DATABASE_URL
为管理连接。CI 必须两条都设置；缺管理连接时本文件 skip，并在 db_session 中由
CI 检查兜底（不允许静默通过）。
"""
from __future__ import annotations

import os

import psycopg
import pytest

from tests.conftest import ADMIN_DSN, TEST_DSN

pytestmark = [
    pytest.mark.skipif(not TEST_DSN, reason="未设置业务测试 DSN"),
    pytest.mark.skipif(not ADMIN_DSN, reason="未设置管理 DSN"),
]


def _app_conn():
    return psycopg.connect(TEST_DSN, autocommit=True)


def test_业务连接身份必须是_campus_app():
    with _app_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_user")
        assert cur.fetchone()[0] == "campus_app", (
            "业务测试必须使用 campus_app；用超级用户跑会掩盖权限问题"
        )


def test_正向_可读学生表():
    with _app_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM campus.students")
        assert cur.fetchone()[0] >= 0


def test_正向_可在事务内写入并回滚():
    with _app_conn() as conn:
        with conn.transaction(force_rollback=True):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO campus.students (student_no, student_name, college_name) "
                    "VALUES ('PRIV-TMP', '权限探针', '计算机学院')"
                )


def test_正向_set_config_后审计记录真实操作人(admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute("DELETE FROM campus.students WHERE student_no = 'PRIV-AUDIT'")
        cur.execute(
            "INSERT INTO campus.students (student_no, student_name, college_name) "
            "VALUES ('PRIV-AUDIT', '审计探针', '计算机学院')"
        )
    # is_local=true 的 GUC 只在当前事务内有效；autocommit 下必须显式开事务
    with _app_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('campus.actor_user_id', 'ry:priv-test', true)")
                cur.execute(
                    "UPDATE campus.students SET student_name = '审计探针2' "
                    "WHERE student_no = 'PRIV-AUDIT'"
                )
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT actor_user_id FROM campus.operation_logs "
            "WHERE object_type = 'students' ORDER BY id DESC LIMIT 1"
        )
        assert cur.fetchone()[0] == "ry:priv-test"


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO campus.operation_logs (actor_db_role, action, object_type) VALUES ('x','insert','students')",
        "UPDATE campus.operation_logs SET actor_user_id = 'forged' WHERE id = 1",
        "DELETE FROM campus.operation_logs WHERE id = 1",
        "DELETE FROM campus.students WHERE student_no = 'PRIV-AUDIT'",
        "DELETE FROM campus.import_issues WHERE batch_id = -1",
        "TRUNCATE campus.students",
        "CREATE TABLE campus.priv_probe (x int)",
    ],
)
def test_负向_禁止的操作必须被拒绝(sql):
    with _app_conn() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(sql)


def test_nonce_可写入但不可直接删除():
    with _app_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO campus.internal_nonce (nonce) VALUES ('priv-nonce-1') "
            "ON CONFLICT DO NOTHING"
        )
    with _app_conn() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM campus.internal_nonce WHERE nonce = 'priv-nonce-1'")


def test_nonce_清理函数只删过期记录(admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute("DELETE FROM campus.internal_nonce")
        cur.execute(
            "INSERT INTO campus.internal_nonce (nonce, expires_at) VALUES "
            "('priv-expired', now() - interval '1 hour'), "
            "('priv-live', now() + interval '1 hour')"
        )
    with _app_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT campus.cleanup_internal_nonce()")
        assert cur.fetchone()[0] >= 1
        cur.execute("SELECT nonce FROM campus.internal_nonce ORDER BY nonce")
        remaining = [r[0] for r in cur.fetchall()]
    assert "priv-live" in remaining
    assert "priv-expired" not in remaining


def test_授权回归_只读与删除边界(admin_conn):
    checks = {
        ("campus.import_issues", "DELETE"): False,  # 006 收口：只能经受控函数删除
        ("campus.import_issues", "INSERT"): True,   # 预览/提交仍由应用写入明细
        ("campus.students", "DELETE"): False,
        ("campus.student_changes", "DELETE"): False,
        ("campus.import_batches", "DELETE"): False,
        ("campus.operation_logs", "INSERT"): False,
        ("campus.internal_nonce", "UPDATE"): False,
    }
    with admin_conn.cursor() as cur:
        for (table, privilege), expected in checks.items():
            cur.execute(
                "SELECT has_table_privilege('campus_app', %s, %s)", (table, privilege)
            )
            assert cur.fetchone()[0] is expected, f"{table} {privilege} 授权与预期不符"

def test_清理函数属主与执行权限(admin_conn):
    """审查项：专用 NOLOGIN 属主、固定 search_path、PUBLIC 不可执行。"""
    with admin_conn.cursor() as cur:
        cur.execute(
            """
            SELECT pg_get_userbyid(p.proowner) AS owner,
                   r.rolcanlogin AS can_login,
                   coalesce(array_to_string(p.proconfig, ','), '') AS config,
                   coalesce(array_to_string(p.proacl, ','), '-') AS acl
              FROM pg_proc p
              JOIN pg_roles r ON r.oid = p.proowner
             WHERE p.proname = 'cleanup_internal_nonce'
            """
        )
        owner, can_login, config, acl = cur.fetchone()

    assert owner == "campus_nonce_cleaner"
    assert can_login is False, "清理函数属主必须是 NOLOGIN"
    assert "search_path=campus, pg_temp" in config
    assert ",=X/" not in acl and not acl.startswith("=X/"), f"PUBLIC 不应可执行：{acl}"

    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT has_function_privilege('campus_app', 'campus.cleanup_internal_nonce()', 'EXECUTE')"
        )
        assert cur.fetchone()[0] is True


def test_清理函数属主不能触达业务表(admin_conn):
    with admin_conn.cursor() as cur:
        for table, privilege in [
            ("campus.students", "SELECT"),
            ("campus.students", "DELETE"),
            ("campus.operation_logs", "INSERT"),
            ("campus.import_batches", "UPDATE"),
        ]:
            cur.execute("SELECT has_table_privilege('campus_nonce_cleaner', %s, %s)",
                        (table, privilege))
            assert cur.fetchone()[0] is False, f"{table} {privilege} 不应授予清理属主"
