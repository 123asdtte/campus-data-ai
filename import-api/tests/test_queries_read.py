"""只读查询层（`queries.py`）的行为覆盖。

矩阵 §8 的空白：这层是 React 前端实际在读的接口，此前只有 422 参数校验，
零行为断言——分页算错、范围过滤失效这类问题在 CI 里完全不可见。

审计说明：这里直接 INSERT 造数据，因此显式设置事务级 GUC
`campus.actor_user_id`，让测试数据也走正常审计路径——既避免留下 actor 为 NULL
的噪声，也能在触发器被意外禁用时暴露出来。

启用条件同 test_db_integration.py：需要 CAMPUS_TEST_DATABASE_URL。
"""
from __future__ import annotations

import os
from datetime import date

import pytest

TEST_DSN = os.environ.get("CAMPUS_TEST_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not TEST_DSN, reason="未设置 CAMPUS_TEST_DATABASE_URL，跳过真库集成测试"
)


def insert_student(
    student_no: str,
    *,
    name: str = "测试甲",
    college: str = "计算机学院",
    status: str = "enrolled",
    active: bool = True,
) -> int:
    from app.db import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('campus.actor_user_id', %s, true)", ("ci.tester",))
            cur.execute(
                """
                INSERT INTO campus.students
                    (student_no, student_name, college_name, student_status, is_active)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (student_no, name, college, status, active),
            )
            return cur.fetchone()["id"]


def insert_change(student_id: int, change_type: str, effective: date) -> None:
    from app.db import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('campus.actor_user_id', %s, true)", ("ci.tester",))
            cur.execute(
                """
                INSERT INTO campus.student_changes
                    (student_id, change_type, effective_date, record_status)
                VALUES (%s, %s, %s, 'confirmed')
                """,
                (student_id, change_type, effective),
            )


class TestListStudents:
    def test_默认只返回启用中的学生(self, db_client) -> None:
        insert_student("S001", name="张三")
        insert_student("S002", name="李四", active=False)

        from app import queries

        result = queries.list_students()

        assert [row["student_no"] for row in result["items"]] == ["S001"]
        assert result["total"] == 1

    def test_include_inactive包含已停用记录(self, db_client) -> None:
        insert_student("S001", name="张三")
        insert_student("S002", name="李四", active=False)

        from app import queries

        result = queries.list_students(include_inactive=True)

        assert [row["student_no"] for row in result["items"]] == ["S001", "S002"]

    @pytest.mark.parametrize("keyword", ["001", "张三"])
    def test_keyword同时命中学号与姓名(self, db_client, keyword: str) -> None:
        insert_student("S001", name="张三")
        insert_student("S002", name="李四")

        from app import queries

        result = queries.list_students(keyword=keyword)

        assert [row["student_no"] for row in result["items"]] == ["S001"]

    def test_college筛选只返回该学院(self, db_client) -> None:
        insert_student("S001", name="张三", college="计算机学院")
        insert_student("S002", name="李四", college="电子信息学院")

        from app import queries

        result = queries.list_students(college="电子信息学院")

        assert [row["student_no"] for row in result["items"]] == ["S002"]

    def test_授权范围与筛选条件取交集(self, db_client) -> None:
        """学院管理员越界筛选时返回空集，而不是被放大成全量。"""
        insert_student("S001", name="张三", college="计算机学院")
        insert_student("S002", name="李四", college="电子信息学院")

        from app import queries

        result = queries.list_students(college="计算机学院", forced_college="电子信息学院")

        assert result["items"] == []
        assert result["total"] == 0

    def test_授权范围为空时缩小到本学院(self, db_client) -> None:
        insert_student("S001", name="张三", college="计算机学院")
        insert_student("S002", name="李四", college="电子信息学院")

        from app import queries

        result = queries.list_students(forced_college="电子信息学院")

        assert [row["student_no"] for row in result["items"]] == ["S002"]


class TestPagination:
    def test_分页返回总数与当前页(self, db_client) -> None:
        for index in range(1, 6):
            insert_student(f"S00{index}", name=f"学生{index}")

        from app import queries

        first = queries.list_students(page=1, page_size=2)
        second = queries.list_students(page=2, page_size=2)

        assert first["total"] == 5
        assert [row["student_no"] for row in first["items"]] == ["S001", "S002"]
        assert [row["student_no"] for row in second["items"]] == ["S003", "S004"]

    def test_分页参数越界被夹回合法区间(self, db_client) -> None:
        insert_student("S001")

        from app import queries

        result = queries.list_students(page=0, page_size=0)
        assert (result["page"], result["page_size"]) == (1, 1)

        clamped = queries.list_students(page_size=1000)
        assert clamped["page_size"] == 200


class TestGetStudent:
    def test_不存在的学号经接口返回404(self, db_client) -> None:
        response = db_client.get("/students/NOT_EXIST")

        assert response.status_code == 404

    def test_异动按生效日期倒序返回(self, db_client) -> None:
        student_id = insert_student("S001", name="张三")
        insert_change(student_id, "suspend", date(2025, 1, 10))
        insert_change(student_id, "resume", date(2026, 5, 20))

        from app import queries

        student = queries.get_student("S001")

        assert student["student_name"] == "张三"
        assert [c["effective_date"] for c in student["changes"]] == [
            date(2026, 5, 20),
            date(2025, 1, 10),
        ]
        assert student["change_total"] == 2
