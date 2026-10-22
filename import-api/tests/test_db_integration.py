"""真库集成测试：状态机、事务、幂等与审计链路。

这些是 mock 测不到的部分——尤其「审计触发器和业务写入同事务」，
只有真的连上 PostgreSQL 才能验证。

启用条件：设置环境变量 `CAMPUS_TEST_DATABASE_URL` 指向一个已执行过
sql/001_schema.sql 的**独立测试库**。未设置时整组跳过，本地无 Docker 也能全绿。

严禁指向主库：用例会 TRUNCATE 业务表。
"""
from __future__ import annotations

import os

import pytest

TEST_DSN = os.environ.get("CAMPUS_TEST_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not TEST_DSN, reason="未设置 CAMPUS_TEST_DATABASE_URL，跳过真库集成测试")

HEADERS = {"X-Actor": "ci.tester"}


def preview(client, name: str, content: bytes, target: str = "students"):
    return client.post(
        "/imports/preview",
        data={"target_type": target},
        files={"file": (name, content, "text/csv")},
        headers=HEADERS,
    )


def table_count(table: str) -> int:
    from app.db import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM campus.{table}")
            return cur.fetchone()["n"]


class TestHealth:
    def test_数据库可用时返回200(self, db_client) -> None:
        response = db_client.get("/health/ready")

        assert response.status_code == 200
        assert response.json()["database"] == "ok"


class TestFullImportFlow:
    """场景 9、10：校验 → 提交 → 重复提交被拒。"""

    def test_导入全链路(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")

        previewed = preview(db_client, "test_alias_variants.csv", content)
        assert previewed.status_code == 200
        body = previewed.json()
        assert body["status"] == "uploaded"
        assert body["total_rows"] == 2
        assert body["missing_required"] == []
        batch_id = body["batch_id"]

        validated = db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        assert validated.status_code == 200
        assert validated.json()["valid_rows"] == 2
        assert validated.json()["invalid_rows"] == 0

        committed = db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)
        assert committed.status_code == 200
        assert committed.json()["inserted_rows"] == 2

        assert table_count("students") == 2
        assert table_count("import_batches") == 1

    def test_重复提交返回409且不新增数据(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "same.csv", content).json()["batch_id"]
        db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)

        again = db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)

        assert again.status_code == 409
        assert table_count("students") == 2

    def test_未校验直接提交返回409(self, db_client, load_sample) -> None:
        batch_id = preview(db_client, "x.csv", load_sample("test_alias_variants.csv")).json()["batch_id"]

        response = db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)

        assert response.status_code == 409
        assert "不能提交" in response.json()["detail"]

    def test_已导入的批次不能再次校验(self, db_client, load_sample) -> None:
        batch_id = preview(db_client, "x.csv", load_sample("test_alias_variants.csv")).json()["batch_id"]
        db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)

        response = db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)

        assert response.status_code == 409

    def test_不存在的批次返回404(self, db_client) -> None:
        assert db_client.post("/imports/999999/validate", headers=HEADERS).status_code == 404


class TestAuditTrail:
    """审计由数据库触发器写入，actor 来自事务级 GUC。"""

    def test_提交后写入审计且操作人正确(self, db_client, load_sample) -> None:
        batch_id = preview(db_client, "x.csv", load_sample("test_alias_variants.csv")).json()["batch_id"]
        db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)

        from app.db import pool

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT actor_user_id, action, object_type, count(*) AS n
                      FROM campus.operation_logs
                     WHERE object_type = 'students'
                     GROUP BY actor_user_id, action, object_type
                    """
                )
                rows = cur.fetchall()

        assert rows == [
            {"actor_user_id": "ci.tester", "action": "insert", "object_type": "students", "n": 2}
        ]

    def test_操作人来自请求头而非数据库账号(self, db_client, load_sample) -> None:
        """审计里的操作人取自 X-Actor，而不是数据库连接角色。

        注：这里必须用 ASCII 值。中文操作人会被 httpx 在构造请求时拒绝，
        该限制已由 test_api_contract.py 的 xfail 用例单独固化。
        """
        batch_id = preview(db_client, "x.csv", load_sample("test_acceptance.csv")).json()["batch_id"]
        db_client.post(f"/imports/{batch_id}/validate", headers={"X-Actor": "other.actor"})
        db_client.post(f"/imports/{batch_id}/commit", headers={"X-Actor": "other.actor"})

        from app.db import pool

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT actor_user_id FROM campus.operation_logs")
                actors = {row["actor_user_id"] for row in cur.fetchall()}

        assert actors == {"other.actor"}


class TestRowNumberOffset:
    """场景 11：表头第 4 行时，问题行号必须指向真实的 Excel 行。"""

    def test_缺姓名的行报Excel第6行(self, db_client, load_sample) -> None:
        content = load_sample("test_title_rows_bad.csv")
        body = preview(db_client, "test_title_rows_bad.csv", content).json()
        assert body["header_row"] == 4
        # 预览行号同样要带偏移：表头 4 + 第一条数据 = 第 5 行
        assert body["preview"][0]["__row"] == 5

        validated = db_client.post(f"/imports/{body['batch_id']}/validate", headers=HEADERS).json()

        assert validated["total_rows"] == 3
        assert validated["valid_rows"] == 2
        assert validated["invalid_rows"] == 1
        missing = [i for i in validated["issues"] if i["issue_code"] == "MISSING_REQUIRED"]
        assert [i["row_number"] for i in missing] == [6]
        assert missing[0]["field_name"] == "student_name"


class TestRejectPaths:
    def test_缺必需列时校验返回422(self, db_client, load_sample) -> None:
        """场景 6：预览把批次标成 failed，校验阶段明确拒绝。"""
        body = preview(db_client, "test_missing_required.csv", load_sample("test_missing_required.csv")).json()

        assert body["status"] == "failed"
        assert body["missing_required"] == ["student_name"]

        response = db_client.post(f"/imports/{body['batch_id']}/validate", headers=HEADERS)

        assert response.status_code == 422
        assert "缺少必需列" in response.json()["detail"]

    def test_脏数据样例同时报出四类异常(self, db_client, load_sample) -> None:
        """student_changes_demo.xlsx 是刻意做脏的样例：越界日期、非法类型、空学号、查无此人。"""
        body = preview(
            db_client,
            "student_changes_demo.xlsx",
            load_sample("student_changes_demo.xlsx"),
            target="student_changes",
        ).json()

        validated = db_client.post(f"/imports/{body['batch_id']}/validate", headers=HEADERS).json()

        assert validated["total_rows"] == 9
        # 本用例前 students 已被 TRUNCATE，9 行学号全部查无此人，
        # 因此受影响行数等于总行数；四类异常是叠加在不同行上的。
        assert validated["invalid_rows"] == 9
        assert {i["issue_code"] for i in validated["issues"]} == {
            "UNKNOWN_STUDENT",  # 库中没有任何学生
            "INVALID_DATE",  # 2026-13-45
            "INVALID_ENUM",  # change_type=出国
            "MISSING_REQUIRED",  # 最后一行学号为空
        }

    def test_一个单元格出错不掩盖同批次其他问题(self, db_client, load_sample) -> None:
        body = preview(
            db_client,
            "student_changes_demo.xlsx",
            load_sample("student_changes_demo.xlsx"),
            target="student_changes",
        ).json()

        validated = db_client.post(f"/imports/{body['batch_id']}/validate", headers=HEADERS).json()

        fields = {(i["row_number"], i["field_name"]) for i in validated["issues"]}
        assert (10, "student_no") in fields
        assert (9, "change_type") in fields
        assert (8, "effective_date") in fields


class TestDuplicateBatchWarning:
    def test_同一文件再次上传给出警告但不阻断(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        first = preview(db_client, "x.csv", content).json()
        db_client.post(f"/imports/{first['batch_id']}/validate", headers=HEADERS)
        db_client.post(f"/imports/{first['batch_id']}/commit", headers=HEADERS)

        second = preview(db_client, "x.csv", content)

        assert second.status_code == 200
        codes = [i["issue_code"] for i in second.json()["issues"]]
        assert "DUPLICATE_BATCH" in codes

    def test_重复导入同一批学生不会产生重复行(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        first = preview(db_client, "a.csv", content).json()
        db_client.post(f"/imports/{first['batch_id']}/validate", headers=HEADERS)
        db_client.post(f"/imports/{first['batch_id']}/commit", headers=HEADERS)

        second = preview(db_client, "a.csv", content).json()
        db_client.post(f"/imports/{second['batch_id']}/validate", headers=HEADERS)
        committed = db_client.post(f"/imports/{second['batch_id']}/commit", headers=HEADERS).json()

        # 第二批次的两行在校验阶段就因「学号已存在」被判无效，提交时整体排除
        assert committed["inserted_rows"] == 0
        assert committed["invalid_rows_excluded"] == 2
        assert table_count("students") == 2
