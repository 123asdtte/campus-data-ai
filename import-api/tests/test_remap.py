"""remap 接口：前端「改完映射重新校验」这条主流程的唯一入口。

覆盖矩阵 §4 的最大缺口——此前整个接口零行为测试，只在认证矩阵里被当作
权限检查的一个路径名出现过。remap 会重写 sidecar、清零校验结果并把批次
状态打回 uploaded，任何一处回归都会让「改映射」按钮看似生效、实际失效。

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


def preview(client, name: str, content: bytes, target: str = "students"):
    return client.post(
        "/imports/preview",
        data={"target_type": target},
        files={"file": (name, content, "text/csv")},
        headers=HEADERS,
    )


def remap(client, batch_id: int, **payload):
    return client.post(f"/imports/{batch_id}/remap", json=payload, headers=HEADERS)


class TestRemapChangesMapping:
    def test_改映射后列映射与预览同步更新(self, db_client, load_sample) -> None:
        """test_conflict_columns.csv 有「学号」「学生学号」两列争同一个字段。"""
        content = load_sample("test_conflict_columns.csv")
        body = preview(db_client, "test_conflict_columns.csv", content).json()
        batch_id = body["batch_id"]
        # column_mapping 的方向是「源列名 → 目标字段」
        assert body["column_mapping"]["学号"] == "student_no"

        remapped = remap(
            db_client, batch_id, mapping={"学生学号": "student_no", "学号": None}
        )

        assert remapped.status_code == 200
        out = remapped.json()
        assert out["column_mapping"]["学生学号"] == "student_no"
        assert "学号" not in out["column_mapping"]
        assert out["missing_required"] == []
        # 预览取的是新映射列的值，而不是旧的
        assert out["preview"][0]["student_no"] == "E2026001X"

    def test_手动指定会解除原占用列的映射(self, db_client, load_sample) -> None:
        """同一字段被新列占用后，旧列必须退位，否则两列会静默写入同一个字段。"""
        content = load_sample("test_conflict_columns.csv")
        batch_id = preview(db_client, "test_conflict_columns.csv", content).json()["batch_id"]

        out = remap(db_client, batch_id, mapping={"学生学号": "student_no"}).json()

        assert out["column_mapping"]["学生学号"] == "student_no"
        assert "学号" in out["conflicts"]
        assert out["preview"][0]["student_no"] == "E2026001X"

    def test_取消必需列映射只在当次响应生效(self, db_client, load_sample) -> None:
        """现状固化：置空某列会让本次批次转 failed，但「忽略该列」不会持久化。

        sidecar 只保存正向映射（源列 → 目标字段），被置空的列在下次解析时
        会被 `auto_map` 重新占用。因此用户无法通过 remap 永久取消某一列，
        「缺必需列」状态也只存在于当次响应里。

        若后续改为持久化「忽略该列」，本用例需同步更新。
        """
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]

        out = remap(db_client, batch_id, mapping={"学生名称": None}).json()
        assert out["status"] == "failed"
        assert out["missing_required"] == ["student_name"]

        validated = db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        assert validated.status_code == 200
        assert validated.json()["column_mapping"]["学生名称"] == "student_name"


class TestRemapResetsState:
    """remap 会清零校验结果，前端必须重新校验才能提交。"""

    def test_校验后remap状态回退uploaded(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]

        validated = db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS).json()
        assert validated["status"] == "validated"
        assert validated["valid_rows"] == 2

        out = remap(db_client, batch_id).json()
        assert out["status"] == "uploaded"
        assert out["total_rows"] == 2

    def test_remap后不能直接提交必须重新校验(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]
        db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        remap(db_client, batch_id)

        rejected = db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)

        assert rejected.status_code == 409
        assert "不能提交" in rejected.json()["detail"]

        db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        committed = db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)
        assert committed.status_code == 200
        assert committed.json()["inserted_rows"] == 2


class TestRemapRejectPaths:
    def test_已导入的批次不能remap(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]
        db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)

        response = remap(db_client, batch_id)

        assert response.status_code == 409
        assert "已导入" in response.json()["detail"]

    def test_不存在的批次remap返回404(self, db_client) -> None:
        assert remap(db_client, 999999).status_code == 404

    def test_两个并行批次的remap互不干扰(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        first = preview(db_client, "a.csv", content).json()["batch_id"]
        second = preview(db_client, "a.csv", content).json()["batch_id"]

        out = remap(db_client, first, mapping={"行政班级": "major_name"}).json()
        assert out["column_mapping"]["行政班级"] == "major_name"

        # 第二个批次不受影响：它的 sidecar 是独立的
        validated = db_client.post(f"/imports/{second}/validate", headers=HEADERS).json()
        assert validated["column_mapping"]["行政班级"] == "class_name"
        assert validated["valid_rows"] == 2
