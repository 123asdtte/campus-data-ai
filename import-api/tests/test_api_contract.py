"""HTTP 契约层：入参校验与错误码。

这些用例刻意只覆盖「进入数据库之前就应该失败」的路径，
因此不需要数据库也能跑（TestClient 不带 lifespan，不会打开连接池）。

状态码约定见 docs/IMPORT-API.md：400 参数/内容问题，413 越限，422 缺必需列。
"""
from __future__ import annotations

import pytest

CSV_OK = "学号,姓名\nS001,甲\nS002,乙\n".encode("utf-8")


def post_preview(client, **kwargs):
    payload = {"target_type": "students"}
    payload.update(kwargs.pop("data", {}))
    files = kwargs.pop("files", {"file": ("名单.csv", CSV_OK, "text/csv")})
    return client.post("/imports/preview", data=payload, files=files)


class TestPreviewValidation:
    def test_mapping不是JSON返回400(self, api_client) -> None:
        response = post_preview(api_client, data={"mapping": "{坏掉的json"})

        assert response.status_code == 400
        assert "JSON" in response.json()["detail"]

    def test_mapping不是对象返回400(self, api_client) -> None:
        response = post_preview(api_client, data={"mapping": '["学号"]'})

        assert response.status_code == 400
        assert "对象" in response.json()["detail"]

    def test_目标类型不支持返回400(self, api_client) -> None:
        response = post_preview(api_client, data={"target_type": "teachers"})

        assert response.status_code == 400
        assert "不支持的目标类型" in response.json()["detail"]

    def test_缺少target_type由框架返回422(self, api_client) -> None:
        response = api_client.post(
            "/imports/preview", files={"file": ("名单.csv", CSV_OK, "text/csv")}
        )
        assert response.status_code == 422

    def test_缺少文件由框架返回422(self, api_client) -> None:
        response = api_client.post("/imports/preview", data={"target_type": "students"})
        assert response.status_code == 422

    def test_空文件返回400(self, api_client) -> None:
        response = post_preview(
            api_client, files={"file": ("空.csv", b"", "text/csv")}
        )

        assert response.status_code == 400
        assert "上传文件为空" in response.json()["detail"]

    def test_超过大小上限返回413(self, api_client, monkeypatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "max_upload_mb", 0)
        response = post_preview(api_client)

        assert response.status_code == 413
        assert "上限" in response.json()["detail"]

    def test_超过行数上限返回413(self, api_client, monkeypatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "max_rows", 1)
        response = post_preview(api_client)

        assert response.status_code == 413
        assert "行上限" in response.json()["detail"]

    def test_只有表头没有数据行返回400(self, api_client) -> None:
        response = post_preview(
            api_client, files={"file": ("空表.csv", "学号,姓名\n".encode("utf-8"), "text/csv")}
        )

        assert response.status_code == 400
        assert "没有可导入的数据行" in response.json()["detail"]


class TestBase64Preview:
    """Appsmith FilePicker 只能给 base64，因此有独立入口。"""

    def test_非法base64返回400(self, api_client) -> None:
        response = api_client.post(
            "/imports/preview-base64",
            json={"filename": "x.csv", "content_base64": "!!!not-base64!!!", "target_type": "students"},
        )

        assert response.status_code == 400

    def test_解码结果为空返回400(self, api_client) -> None:
        response = api_client.post(
            "/imports/preview-base64",
            json={"filename": "x.csv", "content_base64": "", "target_type": "students"},
        )

        assert response.status_code == 400
        assert "为空" in response.json()["detail"]


class TestHealthWithoutDatabase:
    def test_数据库不可用时返回503(self, api_client) -> None:
        """健康检查不能假装健康——连接池未打开时必须 503。"""
        response = api_client.get("/health")

        assert response.status_code == 503
        assert "database unavailable" in response.json()["detail"]


class TestQueryValidation:
    @pytest.mark.parametrize(
        "query",
        [
            "?page_size=999",
            "?page=0",
            f"?keyword={'学' * 101}",
            "?status=" + "x" * 21,
        ],
    )
    def test_查询参数越界返回422(self, api_client, query: str) -> None:
        assert api_client.get(f"/students{query}").status_code == 422

    def test_路径参数类型错误返回422(self, api_client) -> None:
        assert api_client.post("/imports/abc/validate").status_code == 422

    def test_不存在的路由返回404(self, api_client) -> None:
        assert api_client.get("/not-exist").status_code == 404


class TestActorHeader:
    """操作人通过 X-Actor 请求头传递，没有认证，值完全由客户端决定。

    这是 README 已声明的「仅具演示价值」的一部分，此处只固化现状边界。
    """

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "已知缺陷：HTTP 头值只接受 ASCII/latin-1，X-Actor 无法承载中文操作人。"
            "学校场景的操作人基本都是中文姓名，修复时需改为请求体字段或自建编码方案；"
            "修复后请移除此标记，让本用例正式断言中文操作人可用"
        ),
    )
    def test_中文操作人无法通过X_Actor传递(self, api_client) -> None:
        api_client.post("/imports/abc/validate", headers={"X-Actor": "张老师"})
