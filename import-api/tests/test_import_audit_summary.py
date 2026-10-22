"""导入审计（方案 C）：批次行级审计 + 异常明细摘要，禁止逐行噪声。

启用条件同其他真库用例；在开启态下运行以验证可信 actor。
"""
from __future__ import annotations

import os

import psycopg
import pytest

from tests import auth_helper as H

TEST_DSN = os.environ.get("CAMPUS_TEST_DATABASE_URL", "").strip()
AUTH_ENABLED = os.environ.get("INTERNAL_AUTH_ENABLED", "").lower() in ("1", "true", "yes")
pytestmark = pytest.mark.skipif(
    not TEST_DSN, reason="未设置 CAMPUS_TEST_DATABASE_URL，跳过真库集成测试"
)

CSV = "学号,姓名,学院\nPEA001,,计算机学院\nPEA002,,计算机学院\n"


def _preview(client) -> int:
    response = H.request(
        client, "POST", "/imports/preview",
        file_bytes=CSV.encode("utf-8"), form={"target_type": "students"},
    )
    assert response.status_code == 200, response.text
    return response.json()["batch_id"]


def _audit_rows(admin_conn, batch_id: int):
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT action, details FROM campus.operation_logs "
            "WHERE object_type = 'import_issues' AND object_id = %s ORDER BY id",
            (str(batch_id),),
        )
        return cur.fetchall()


def test_异常明细只写摘要不写逐行审计(db_client, admin_conn):
    batch_id = _preview(db_client)

    validated = H.request(db_client, "POST", f"/imports/{batch_id}/validate")
    assert validated.status_code == 200, validated.text
    assert validated.json()["invalid_rows"] == 2

    rows = _audit_rows(admin_conn, batch_id)
    # 预览阶段先写 1 条 rows=0 摘要，校验再写 1 条（共 2 条，均非逐行）
    assert len(rows) == 2, f"首次校验后应有 2 条摘要，实际 {len(rows)}"
    assert rows[0][1]["trigger"] == "preview" and rows[0][1]["rows"] == 0
    action, details = rows[1]
    assert action == "insert"
    assert details["trigger"] == "validate"
    assert details["rows"] == 2
    assert details["by_code"].get("MISSING_REQUIRED") == 2

    # 再校验一次：clear 写 1 条删除摘要 + record 写 1 条新摘要，仍无逐行噪声
    again = H.request(db_client, "POST", f"/imports/{batch_id}/validate")
    assert again.status_code == 200, again.text
    rows = _audit_rows(admin_conn, batch_id)
    assert len(rows) == 4, f"二次校验后应有 4 条摘要，实际 {len(rows)}"
    assert rows[2][0] == "delete" and rows[2][1]["deleted"] == 2
    assert rows[3][0] == "insert" and rows[3][1]["rows"] == 2

    # 批次状态跃迁仍由行级触发器记录
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM campus.operation_logs "
            "WHERE object_type = 'import_batches' AND object_id = %s",
            (str(batch_id),),
        )
        assert cur.fetchone()[0] >= 2


def test_删除函数是唯一删除入口(db_client, admin_conn):
    batch_id = _preview(db_client)
    H.request(db_client, "POST", f"/imports/{batch_id}/validate")

    from app.db import pool

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM campus.import_issues WHERE batch_id = %s", (batch_id,))

    # 受控函数仍可正常清理
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT campus.clear_import_issues(%s, 'test') AS removed", (batch_id,))
            assert cur.fetchone()["removed"] == 2


@pytest.mark.skipif(not AUTH_ENABLED, reason="仅在开启态验证可信 actor")
def test_摘要操作人来自可信身份(db_client, admin_conn):
    batch_id = _preview(db_client)
    H.request(db_client, "POST", f"/imports/{batch_id}/validate")
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT actor_user_id FROM campus.operation_logs "
            "WHERE object_type = 'import_issues' AND object_id = %s",
            (str(batch_id),),
        )
        actors = {row[0] for row in cur.fetchall()}
    assert actors == {"ry:college_a"}
