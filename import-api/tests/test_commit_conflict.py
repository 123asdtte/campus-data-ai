"""commit 的 ON CONFLICT 分支：幂等链条上唯一没有兜底验证的一环。

矩阵 §2 指出的缺口：现有的「重复导入不产生重复行」走的是校验阶段整体排除。
写这组用例时确认了一个更重要的事实——**通过 API 正常操作走不到 ON CONFLICT**：

    commit_batch 在 INSERT 之前会调 _revalidate 再算一次业务问题，
    同学号会被判 DUPLICATE_STUDENT_NO（error）从而整体排除，
    根本到不了 INSERT ... ON CONFLICT。

所以 ON CONFLICT 是**并发兜底**而非主路径：只有当「校验完成后、提交开始前」
被另一个事务插入了同学号时才会命中。本文件用 monkeypatch 模拟这个窗口
（`_fetch_known_students` 返回空集），并另设一条用例固化正常路径的行为，
防止有人误以为 skipped_rows 是常规可达路径而改动它。

启用条件同 test_db_integration.py：需要 CAMPUS_TEST_DATABASE_URL。
"""
from __future__ import annotations

import os

import pytest

TEST_DSN = os.environ.get("CAMPUS_TEST_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not TEST_DSN, reason="未设置 CAMPUS_TEST_DATABASE_URL，跳过真库集成测试"
)

HEADERS = {"X-Actor": "ci.tester"}

# 与 samples/test_alias_variants.csv 的第一行学号相同，另加一行新学号
MIXED_CSV = "学号,姓名\nA2026001,张三\nZ2026009,新同学\n".encode("utf-8")


def preview(client, name: str, content: bytes, target: str = "students"):
    return client.post(
        "/imports/preview",
        data={"target_type": target},
        files={"file": (name, content, "text/csv")},
        headers=HEADERS,
    )


def validate(client, batch_id: int) -> dict:
    response = client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def commit(client, batch_id: int) -> dict:
    response = client.post(f"/imports/{batch_id}/commit", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def table_count(table: str) -> int:
    from app.db import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM campus.{table}")
            return cur.fetchone()["n"]


def issue_codes(batch_id: int) -> list[str]:
    from app.db import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT issue_code FROM campus.import_issues WHERE batch_id = %s", (batch_id,)
            )
            return [row["issue_code"] for row in cur.fetchall()]


def commit_first_batch(client, load_sample) -> None:
    batch_id = preview(client, "a.csv", load_sample("test_alias_variants.csv")).json()["batch_id"]
    validate(client, batch_id)
    committed = commit(client, batch_id)
    assert committed["inserted_rows"] == 2


class TestNormalPath:
    def test_正常流程下冲突行在提交前的二次校验中被排除(self, db_client, load_sample) -> None:
        """固化现状：串行导入时走的是 invalid_rows_excluded，不是 skipped_rows。"""
        commit_first_batch(db_client, load_sample)

        second = preview(db_client, "a.csv", load_sample("test_alias_variants.csv")).json()["batch_id"]
        validated = validate(db_client, second)
        assert validated["invalid_rows"] == 2

        committed = commit(db_client, second)

        assert committed["inserted_rows"] == 0
        assert committed["invalid_rows_excluded"] == 2
        assert committed["skipped_rows"] == []
        assert table_count("students") == 2


class TestConcurrentWindow:
    """模拟「校验通过后、提交前」被别的事务插进了同学号。"""

    @pytest.fixture(autouse=True)
    def blind_to_existing(self, monkeypatch) -> None:
        from app import service

        monkeypatch.setattr(service, "_fetch_known_students", lambda cur, numbers: set())

    def test_两行全部撞冲突时跳过并记为警告(self, db_client, load_sample) -> None:
        commit_first_batch(db_client, load_sample)

        second = preview(db_client, "a.csv", load_sample("test_alias_variants.csv")).json()["batch_id"]
        assert validate(db_client, second)["invalid_rows"] == 0

        committed = commit(db_client, second)

        assert committed["inserted_rows"] == 0
        assert committed["invalid_rows_excluded"] == 0
        assert committed["skipped_rows"] == [
            {"row_number": 2, "reason": "学号已存在，未写入"},
            {"row_number": 3, "reason": "学号已存在，未写入"},
        ]
        assert issue_codes(second).count("DUPLICATE_STUDENT_NO") == 2
        assert table_count("students") == 2

    def test_部分撞冲突时只跳过已存在的行(self, db_client, load_sample) -> None:
        commit_first_batch(db_client, load_sample)

        second = preview(db_client, "mixed.csv", MIXED_CSV).json()["batch_id"]
        assert validate(db_client, second)["invalid_rows"] == 0

        committed = commit(db_client, second)

        assert committed["inserted_rows"] == 1
        assert committed["skipped_rows"] == [{"row_number": 2, "reason": "学号已存在，未写入"}]
        assert table_count("students") == 3
