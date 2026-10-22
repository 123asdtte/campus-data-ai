"""新增写接口 PUT /students/{no} 的开启态验收。

审查发现：该路由在 PR-A 中新增，但此前只有"关闭态不注册"的测试，
缺少 401/403/跨学院/副作用/审计五类证据，本文件补齐。
"""
from __future__ import annotations

import os

import pytest

from tests import auth_helper as H

AUTH_ENABLED = os.environ.get("INTERNAL_AUTH_ENABLED", "").lower() in ("1", "true", "yes")
pytestmark = pytest.mark.skipif(not AUTH_ENABLED, reason="仅在开启态进程运行")


@pytest.fixture
def seeded(admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO campus.students (student_no, student_name, college_name, class_name, student_status)
            VALUES ('SA001', '甲同学', '计算机学院', '软件2601', 'enrolled'),
                   ('SB001', '乙同学', '电子信息学院', '电子2601', 'enrolled')
            ON CONFLICT (student_no) DO NOTHING
            """
        )
    return None


def _snapshot(admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute("SELECT student_no, student_name, college_name FROM campus.students ORDER BY student_no")
        students = cur.fetchall()
        cur.execute("SELECT count(*) FROM campus.operation_logs WHERE object_type = 'students'")
        audits = cur.fetchone()[0]
    return students, audits


def test_未签名返回401(db_client, seeded):
    response = db_client.put("/students/SA001", json={"student_name": "新名字"})
    assert response.status_code == 401


def test_缺写权限返回403(db_client, seeded):
    # WHO_READONLY 只有 student:list，没有 student:write
    response = H.request(db_client, "PUT", "/students/SA001",
                         json_body={"student_name": "新名字"}, who=H.WHO_READONLY)
    assert response.status_code == 403


def test_跨学院返回403且无副作用(db_client, seeded, admin_conn):
    before = _snapshot(admin_conn)
    response = H.request(db_client, "PUT", "/students/SB001",
                         json_body={"student_name": "越权改名"}, who=H.WHO_COLLEGE)
    assert response.status_code == 403
    assert _snapshot(admin_conn) == before, "越权请求不得改数据或写审计"


def test_合法更新成功且审计操作人可信(db_client, seeded, admin_conn):
    response = H.request(db_client, "PUT", "/students/SA001",
                         json_body={"student_name": "甲同学改"}, who=H.WHO_COLLEGE)
    assert response.status_code == 200, response.text
    assert response.json()["student"]["student_name"] == "甲同学改"

    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT student_name FROM campus.students WHERE student_no = 'SA001'"
        )
        assert cur.fetchone()[0] == "甲同学改"
        cur.execute(
            "SELECT actor_user_id, changed_fields FROM campus.operation_logs "
            "WHERE object_type = 'students' ORDER BY id DESC LIMIT 1"
        )
        actor, changed = cur.fetchone()
    assert actor == "ry:college_a"
    assert "student_name" in changed


def test_伪造身份头不改变审计操作人(db_client, seeded, admin_conn):
    response = H.request(db_client, "PUT", "/students/SA001",
                         json_body={"class_name": "软件2602"},
                         who=H.WHO_COLLEGE,
                         extra_headers={"X-Actor": "attacker"})
    assert response.status_code == 200
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT actor_user_id FROM campus.operation_logs "
            "WHERE object_type = 'students' ORDER BY id DESC LIMIT 1"
        )
        assert cur.fetchone()[0] == "ry:college_a"


def test_不存在学生返回404(db_client, seeded):
    response = H.request(db_client, "PUT", "/students/NOT-EXIST",
                         json_body={"student_name": "新名字"}, who=H.WHO_COLLEGE)
    assert response.status_code == 404


def test_空请求体返回400(db_client, seeded):
    response = H.request(db_client, "PUT", "/students/SA001", json_body={}, who=H.WHO_COLLEGE)
    assert response.status_code == 400


@pytest.mark.parametrize("payload", [{"student_name": "   "}, {"student_name": None}])
def test_非法姓名返回4xx而非500(db_client, seeded, payload):
    response = H.request(db_client, "PUT", "/students/SA001", json_body=payload, who=H.WHO_COLLEGE)
    assert 400 <= response.status_code < 500, f"应返回 4xx，实际 {response.status_code}"
