"""聚合/筛选接口，以及「异常文件」在 HTTP 层的行为。

对应 `docs/TEST-COVERAGE-MATRIX.md` §11「仍未覆盖」的前三项，并顺带补掉 §4 的夹具缺口：

1. 异常文件此前只在解析层（`test_parsing_edge.py`）覆盖，HTTP 层行为未固定；
2. `get_filters` / `get_overview` 零行为覆盖——React 首页与筛选栏正在读这两个接口；
3. `samples/` 中 `bad_headers.xlsx`、`students_demo.xlsx`、`test_conflict_columns.csv` 零引用。

用例性质有三种，注释里逐一标明：

- **正常断言**：当前行为就是期望行为；
- **现状固化**：行为与直觉相反但本轮不改（若将来改行为，请同步改本用例）；
- **xfail(strict)**：期望行为当前不满足，已记入矩阵 §10，修复后 XPASS 会强制提醒删标记。

启用条件同其余真库用例：需要 `CAMPUS_TEST_DATABASE_URL`。
"""
from __future__ import annotations

import io
import json
import os

import pytest

TEST_DSN = os.environ.get("CAMPUS_TEST_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not TEST_DSN, reason="未设置 CAMPUS_TEST_DATABASE_URL，跳过真库集成测试"
)

HEADERS = {"X-Actor": "ci.tester"}


# ------------------------------------------------------------------ 造数工具
def insert_student(
    student_no: str,
    *,
    name: str = "测试甲",
    college: str = "计算机学院",
    class_name: str = "软件2601",
    status: str = "enrolled",
    active: bool = True,
) -> int:
    """直接写库造数；显式设置 actor，避免在审计表里留下 NULL 噪声。"""
    from app.db import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('campus.actor_user_id', %s, true)", ("ci.tester",))
            cur.execute(
                """
                INSERT INTO campus.students
                    (student_no, student_name, college_name, class_name, student_status, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (student_no, name, college, class_name, status, active),
            )
            return cur.fetchone()["id"]


def insert_change(
    student_id: int,
    change_type: str = "suspend",
    record_status: str = "confirmed",
) -> None:
    from app.db import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('campus.actor_user_id', %s, true)", ("ci.tester",))
            cur.execute(
                """
                INSERT INTO campus.student_changes
                    (student_id, change_type, effective_date, record_status)
                VALUES (%s, %s, CURRENT_DATE, %s)
                """,
                (student_id, change_type, record_status),
            )


def preview(client, name: str, content: bytes, *, target: str = "students", mapping=None):
    data = {"target_type": target}
    if mapping is not None:
        data["mapping"] = json.dumps(mapping, ensure_ascii=False)
    return client.post(
        "/imports/preview",
        data=data,
        files={"file": (name, content, "application/octet-stream")},
        headers=HEADERS,
    )


def make_xlsx(rows) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def table_count(table: str) -> int:
    from app.db import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM campus.{table}")
            return cur.fetchone()["n"]


# ------------------------------------------------------------------ 筛选接口
class TestMetaFilters:
    """`GET /meta/filters`：React 筛选栏的数据源，此前零行为覆盖。"""

    def test_返回启用学生的学院与班级去重列表(self, db_client) -> None:
        insert_student("F001", college="计算机学院", class_name="软件2601")
        insert_student("F002", college="计算机学院", class_name="软件2601")
        insert_student("F003", college="电子信息学院", class_name="物联2601")

        response = db_client.get("/meta/filters", headers=HEADERS)

        assert response.status_code == 200
        body = response.json()
        # 只断言集合：中文排序依赖数据库 collation，断言顺序会让用例绑死环境
        assert set(body["colleges"]) == {"计算机学院", "电子信息学院"}
        assert set(body["classes"]) == {"软件2601", "物联2601"}
        assert body["total_active"] == 3
        assert body["change_total"] == 0
        assert body["status_counts"] == {"enrolled": 3}

    def test_停用学生不进入选项与计数(self, db_client) -> None:
        insert_student("F101", college="计算机学院")
        insert_student("F102", college="电子信息学院", active=False)

        body = db_client.get("/meta/filters", headers=HEADERS).json()

        assert body["colleges"] == ["计算机学院"]
        assert body["total_active"] == 1

    def test_空库返回空选项与零计数(self, db_client) -> None:
        body = db_client.get("/meta/filters", headers=HEADERS).json()

        assert body["colleges"] == []
        assert body["classes"] == []
        assert body["status_counts"] == {}
        assert body["total_active"] == 0
        assert body["change_total"] == 0


# ------------------------------------------------------------------ 总览接口
class TestOverview:
    """`GET /stats/overview`：React 首页的数据源，此前零行为覆盖。"""

    def test_学生与异动计数(self, db_client) -> None:
        alice = insert_student("O001", college="计算机学院")
        bob = insert_student("O002", college="计算机学院", status="suspended")
        insert_student("O003", college="电子信息学院", active=False)
        # 让 suspend 明显多于 resume：change_type_counts 按 cnt DESC 排序，计数相同时
        # 数据库不保证顺序，等量构造会让断言变成赌执行计划
        insert_change(alice, "suspend", "confirmed")
        insert_change(alice, "suspend", "pending_review")
        insert_change(bob, "resume", "confirmed")

        body = db_client.get("/stats/overview", headers=HEADERS).json()

        assert body["students_total"] == 3
        assert body["students_active"] == 2
        assert body["changes_total"] == 3
        assert body["pending_review"] == 1
        # status_counts 只统计启用中的学生（与学生总数口径不同，容易读错）
        assert body["status_counts"] == {"enrolled": 1, "suspended": 1}
        assert body["change_type_counts"][0] == {"change_type": "suspend", "cnt": 2}
        assert sum(item["cnt"] for item in body["monthly"]) == 3

    def test_最近批次最多五条且最新在前(self, db_client, load_sample) -> None:
        content = load_sample("test_acceptance.csv")
        codes = [preview(db_client, "acceptance.csv", content).json()["batch_code"] for _ in range(6)]
        # 六次 preview 落在同一瞬间，created_at 会完全相同；显式改成递增时间戳，
        # 否则「倒序」这条断言是在赌数据库的物理行序
        from app.db import pool

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('campus.actor_user_id', %s, true)", ("ci.tester",))
                cur.execute(
                    "UPDATE campus.import_batches "
                    "SET created_at = timestamptz '2026-01-01 00:00:00+08' + (id || ' minutes')::interval"
                )

        body = db_client.get("/stats/overview", headers=HEADERS).json()

        assert body["batches_total"] == 6
        assert body["imported_batches"] == 0
        assert body["last_import_at"] is not None
        assert len(body["recent_batches"]) == 5
        assert [item["batch_code"] for item in body["recent_batches"]] == codes[::-1][:5]

    def test_空库时批次字段为零且列表为空(self, db_client) -> None:
        body = db_client.get("/stats/overview", headers=HEADERS).json()

        assert body["batches_total"] == 0
        assert body["imported_batches"] == 0
        assert body["last_import_at"] is None
        assert body["open_errors"] == 0
        assert body["recent_batches"] == []


# ------------------------------------------------------------------ 异常文件（HTTP 层）
class TestAbnormalFileOverHttp:
    """矩阵 §3 在 API 层的固化：解析层已有用例，但「用户实际会拿到什么」没有。"""

    def test_无可识别表头被包含匹配接受(self, db_client, load_sample) -> None:
        """现状固化：`bad_headers.xlsx` 的表头是「编号 / 名字」，不是标准列名。

        「名字」按别名精确命中 `student_name`，「编号」靠 contains 模糊命中
        `student_no`（置信度 0.78），于是这份**表头不合规**的文件被正常接收，
        用户看不到任何「列名不规范」的提示。若将来要求 contains 命中必须提示
        或必须人工确认，本用例需改为断言 warning / 400。
        """
        response = preview(db_client, "bad_headers.xlsx", load_sample("bad_headers.xlsx"))

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "uploaded"
        assert body["total_rows"] == 1
        assert body["column_mapping"] == {"编号": "student_no", "名字": "student_name"}
        mapping = {item["source"]: item for item in body["mapping"]}
        assert mapping["编号"]["method"] == "contains"

    def test_仅表头的xlsx返回400(self, db_client) -> None:
        """CSV 版本已有用例（`test_api_contract`），xlsx 空工作表走同一分支但未测。"""
        content = make_xlsx([["学号", "姓名"]])

        response = preview(db_client, "empty.xlsx", content)

        assert response.status_code == 400
        assert "没有可导入的数据行" in response.json()["detail"]

    def test_未知后缀按内容识别(self, db_client) -> None:
        """现状固化（矩阵 §10-2）：扩展名白名单实际未生效。

        `.txt` 只要内容是 CSV 就会被正常导入；`service._read_frame` 里那句
        「仅支持 .xlsx / .csv」是不可达的死代码。若改为拒绝未知后缀，改用例。
        """
        response = preview(db_client, "名单.txt", "学号,姓名\nS001,甲\n".encode())

        assert response.status_code == 200
        assert response.json()["status"] == "uploaded"

    def test_xlsm后缀按Excel解析(self, db_client) -> None:
        """`_is_xlsx` / `create_batch` / `_read_frame` 都列了 `.xlsm`，但无任何用例。"""
        content = make_xlsx([["学号", "姓名"], ["M001", "甲"]])

        response = preview(db_client, "名单.xlsm", content)

        assert response.status_code == 200
        assert response.json()["total_rows"] == 1

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "已知缺陷（矩阵 §10-4）：扩展名是 .xlsx 但内容不是 zip 包时，"
            "openpyxl 的异常直接冒到 FastAPI，用户拿到 500 而不是 400。"
            "修复后本用例会 XPASS，请删掉这个标记转为正式断言。"
        ),
    )
    def test_损坏的xlsx应返回400(self, db_client) -> None:
        """期望 400，当前 500——openpyxl 的异常没被转成 `ServiceError`（矩阵 §10-4）。

        `TestClient` 默认把服务端异常抛出来，这里关掉才能断言「用户看到的状态码」，
        否则用例会变成一个与生产行为无关的 raise 断言。
        """
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)

        response = preview(client, "broken.xlsx", b"this is definitely not a zip archive")

        assert response.status_code == 400


# ------------------------------------------------------------------ 冲突夹具端到端
class TestConflictFixture:
    """矩阵 §4：冲突场景此前只靠内存构造列名，夹具 `test_conflict_columns.csv` 零引用。"""

    def test_同一字段被两列命中时给出冲突(self, db_client, load_sample) -> None:
        body = preview(
            db_client, "test_conflict_columns.csv", load_sample("test_conflict_columns.csv")
        ).json()

        assert body["conflicts"] == ["学生学号"]
        assert body["column_mapping"]["学号"] == "student_no"
        # 冲突不阻断：保留置信度最高的一列，批次仍然 uploaded
        assert body["status"] == "uploaded"
        assert body["missing_required"] == []

    def test_手动指定可解除冲突并成功提交(self, db_client, load_sample) -> None:
        content = load_sample("test_conflict_columns.csv")

        overridden = preview(
            db_client,
            "test_conflict_columns.csv",
            content,
            mapping={"学号": None, "学生学号": "student_no"},
        ).json()

        assert overridden["conflicts"] == []
        assert overridden["column_mapping"] == {
            "学生学号": "student_no",
            "姓名": "student_name",
            "班级": "class_name",
        }
        assert "学号" in overridden["unmapped_columns"]

        batch_id = overridden["batch_id"]
        validated = db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        assert validated.status_code == 200
        assert validated.json()["valid_rows"] == 1

        committed = db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)
        assert committed.status_code == 200
        assert committed.json()["inserted_rows"] == 1

        from app.db import pool

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT student_no FROM campus.students")
                assert [row["student_no"] for row in cur.fetchall()] == ["E2026001X"]


# ------------------------------------------------------------------ 演示夹具端到端
class TestDemoFixture:
    """矩阵 §8 剩余项 3：`students_demo.xlsx` 只在文档里手工验过，测试零引用。

    文档口径（`docs/TEST-PLAN.md`、`docs/REACT-TEST-REPORT.md`）：15 行 / 10 有效 /
    5 异常（行号 12–16）。这条用例把这个口径变成可执行的断言——文档与实现一旦
    对不上，CI 会先报错。
    """

    def test_演示文件十五行中十行有效并可提交(self, db_client, load_sample) -> None:
        content = load_sample("students_demo.xlsx")

        previewed = preview(db_client, "students_demo.xlsx", content).json()
        assert previewed["total_rows"] == 15
        assert previewed["missing_required"] == []

        batch_id = previewed["batch_id"]
        validated = db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        assert validated.status_code == 200
        assert validated.json()["valid_rows"] == 10
        assert validated.json()["invalid_rows"] == 5

        committed = db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)
        assert committed.status_code == 200
        assert committed.json()["inserted_rows"] == 10
        assert table_count("students") == 10
