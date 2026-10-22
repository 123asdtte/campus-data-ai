"""PR-C：导入批次归属、批次级授权、逐行学院校验与批次审计。

只在开启态 + 独立测试库运行：
    INTERNAL_AUTH_ENABLED=true CAMPUS_TEST_DATABASE_URL=... \
    CAMPUS_TEST_ADMIN_DATABASE_URL=... pytest tests/test_import_scope.py
"""
from __future__ import annotations

import os

import pytest

from tests import auth_helper as H
from tests.conftest import requires_admin_dsn, requires_auth_enabled, requires_db

pytestmark = [requires_db, requires_admin_dsn, requires_auth_enabled]

DEPT_A = "1762000000000000101"
DEPT_B = "1762000000000000102"

WHO_B = {
    **H.WHO_COLLEGE,
    "user": "ry:college_b",
    "college": H.COLLEGE_B,
    "colleges": H.COLLEGE_B,
    "dept_id": DEPT_B,
}


def _csv(student_no: str, college: str) -> bytes:
    return f"学号,姓名,学院\n{student_no},测试同学,{college}\n".encode("utf-8")


def _preview(client, content: bytes, who, filename: str = "scope.csv"):
    return H.request(
        client,
        "POST",
        "/imports/preview",
        file_bytes=content,
        filename=filename,
        form={"target_type": "students"},
        who=who,
    )


def _validate(client, batch_id: int, who):
    return H.request(client, "POST", f"/imports/{batch_id}/validate", who=who)


def _commit(client, batch_id: int, who):
    return H.request(client, "POST", f"/imports/{batch_id}/commit", who=who)


def _student_count(admin_conn, student_no: str) -> int:
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM campus.students WHERE student_no = %s",
            (student_no,),
        )
        return int(cur.fetchone()[0])


def _batch_dept(admin_conn, batch_id: int):
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT created_dept_id FROM campus.import_batches WHERE id = %s",
            (batch_id,),
        )
        row = cur.fetchone()
        return None if row is None else row[0]


# ---------------------------------------------------------------- 批次归属


def test_批次写入归属部门(db_client, admin_conn):
    response = _preview(db_client, _csv("PRIV-SCOPE-A1", H.COLLEGE_A), H.WHO_COLLEGE)
    assert response.status_code == 200, response.text
    batch_id = response.json()["batch_id"]
    assert int(_batch_dept(admin_conn, batch_id)) == int(DEPT_A)


def test_学院列表只看本部门批次(db_client):
    a_resp = _preview(db_client, _csv("PRIV-SCOPE-A2", H.COLLEGE_A), H.WHO_COLLEGE)
    b_resp = _preview(db_client, _csv("PRIV-SCOPE-B2", H.COLLEGE_B), WHO_B)
    assert a_resp.status_code == 200, a_resp.text
    assert b_resp.status_code == 200, b_resp.text
    a = a_resp.json()
    b = b_resp.json()
    a_ids = {row["id"] for row in _list(db_client, H.WHO_COLLEGE)}
    b_ids = {row["id"] for row in _list(db_client, WHO_B)}
    assert a["batch_id"] in a_ids and b["batch_id"] not in a_ids
    assert b["batch_id"] in b_ids and a["batch_id"] not in b_ids


def _list(client, who):
    response = H.request(client, "GET", "/imports", who=who)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- 跨批次授权


def test_跨学院批次详情被拒(db_client):
    b = _preview(db_client, _csv("PRIV-SCOPE-B3", H.COLLEGE_B), WHO_B).json()
    response = H.request(db_client, "GET", f"/imports/{b['batch_id']}", who=H.WHO_COLLEGE)
    assert response.status_code == 403


def test_跨学院批次提交被拒且不落库(db_client, admin_conn):
    b = _preview(db_client, _csv("PRIV-SCOPE-B4", H.COLLEGE_B), WHO_B).json()
    assert _validate(db_client, b["batch_id"], WHO_B).status_code == 200
    response = _commit(db_client, b["batch_id"], H.WHO_COLLEGE)
    assert response.status_code == 403
    assert _student_count(admin_conn, "PRIV-SCOPE-B4") == 0


def test_历史NULL批次仅管理员可见(db_client, admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO campus.import_batches
                (batch_code, source_filename, file_sha256, target_type, total_rows,
                 batch_status, created_by, created_dept_id)
            VALUES ('IMP-LEGACY-NULL', 'legacy.csv', repeat('a', 64), 'students', 0,
                    'uploaded', 'legacy', NULL)
            RETURNING id
            """
        )
        legacy_id = cur.fetchone()[0]

    a_ids = {row["id"] for row in _list(db_client, H.WHO_COLLEGE)}
    assert legacy_id not in a_ids
    assert H.request(db_client, "GET", f"/imports/{legacy_id}", who=H.WHO_COLLEGE).status_code == 403
    assert H.request(db_client, "GET", f"/imports/{legacy_id}", who=H.WHO_ADMIN).status_code == 200


# ---------------------------------------------------------------- 逐行授权


def test_批次内跨学院行整批拒绝(db_client, admin_conn):
    # A 学院用户上传的文件里混入 B 学院行：批次归属仍是 A，但提交必须整批拒绝
    mixed = (
        "学号,姓名,学院\n"
        f"PRIV-SCOPE-A5,甲同学,{H.COLLEGE_A}\n"
        f"PRIV-SCOPE-B5,乙同学,{H.COLLEGE_B}\n"
    ).encode("utf-8")
    batch = _preview(db_client, mixed, H.WHO_COLLEGE).json()
    assert _validate(db_client, batch["batch_id"], H.WHO_COLLEGE).status_code == 200
    response = _commit(db_client, batch["batch_id"], H.WHO_COLLEGE)
    assert response.status_code == 403
    assert _student_count(admin_conn, "PRIV-SCOPE-A5") == 0
    assert _student_count(admin_conn, "PRIV-SCOPE-B5") == 0


# ---------------------------------------------------------------- 正向与审计


def test_本学院提交成功并写审计(db_client, admin_conn):
    batch = _preview(db_client, _csv("PRIV-SCOPE-A6", H.COLLEGE_A), H.WHO_COLLEGE).json()
    assert _validate(db_client, batch["batch_id"], H.WHO_COLLEGE).status_code == 200
    response = _commit(db_client, batch["batch_id"], H.WHO_COLLEGE)
    assert response.status_code == 200, response.text
    assert _student_count(admin_conn, "PRIV-SCOPE-A6") == 1

    with admin_conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) AS n
              FROM campus.operation_logs
             WHERE object_type = 'import_batches'
               AND actor_user_id = 'ry:college_a'
            """
        )
        assert int(cur.fetchone()[0]) >= 1


def test_管理员可跨学院访问(db_client):
    b = _preview(db_client, _csv("PRIV-SCOPE-B7", H.COLLEGE_B), WHO_B).json()
    assert H.request(db_client, "GET", f"/imports/{b['batch_id']}", who=H.WHO_ADMIN).status_code == 200
    admin_ids = {row["id"] for row in _list(db_client, H.WHO_ADMIN)}
    assert b["batch_id"] in admin_ids
