"""暂存文件与 sidecar 的生命周期。

矩阵 §6/§7 的空白：暂存文件是 remap 与二次校验的唯一依据，什么时候该在、
什么时候该删，此前没有任何断言。sidecar（`.mapping.json`）更是只在 remap
链路里被读写，全靠本文件覆盖。

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


def staged_path_of(batch_id: int) -> str:
    from app.db import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT staged_path FROM campus.import_batches WHERE id = %s", (batch_id,))
            return cur.fetchone()["staged_path"]


def sidecar_of(staged_path: str) -> str:
    return f"{os.path.splitext(staged_path)[0]}.mapping.json"


class TestStagedFileLifecycle:
    def test_预览后暂存文件与sidecar同时落盘(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]

        path = staged_path_of(batch_id)
        assert os.path.exists(path)
        assert os.path.exists(sidecar_of(path))

    def test_校验后暂存文件必须保留(self, db_client, load_sample) -> None:
        """remap 与重复校验都靠它，提交前删掉等于让整个批次失效。"""
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]

        db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)

        path = staged_path_of(batch_id)
        assert path and os.path.exists(path)

    def test_提交成功后暂存文件被删除且路径置空(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]
        db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        path = staged_path_of(batch_id)

        db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)

        assert not os.path.exists(path)
        assert staged_path_of(batch_id) is None

    def test_配置保留文件时提交后不删除(self, db_client, load_sample, monkeypatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "keep_upload_files", True)
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]
        db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        path = staged_path_of(batch_id)

        db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)

        assert os.path.exists(path)
        assert staged_path_of(batch_id) == path

    def test_暂存文件缺失时校验返回409(self, db_client, load_sample) -> None:
        """文件被运维清掉时，必须明确报错，而不是拿空数据继续跑。"""
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]
        os.remove(staged_path_of(batch_id))

        response = db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)

        assert response.status_code == 409
        assert "暂存文件已不存在" in response.json()["detail"]

    def test_暂存文件缺失时remap返回409(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]
        os.remove(staged_path_of(batch_id))

        response = db_client.post(f"/imports/{batch_id}/remap", json={}, headers=HEADERS)

        assert response.status_code == 409


class TestSidecarCleanup:
    """矩阵 §10-1 已修复：提交成功后连同 sidecar 一起清理。"""

    def test_提交成功后sidecar应一并清理(self, db_client, load_sample) -> None:
        content = load_sample("test_alias_variants.csv")
        batch_id = preview(db_client, "test_alias_variants.csv", content).json()["batch_id"]
        db_client.post(f"/imports/{batch_id}/validate", headers=HEADERS)
        sidecar = sidecar_of(staged_path_of(batch_id))

        db_client.post(f"/imports/{batch_id}/commit", headers=HEADERS)

        assert not os.path.exists(sidecar)
