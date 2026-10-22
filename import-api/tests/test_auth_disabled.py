"""关闭态（默认）行为：旧接口兼容，新增写路由不存在。

本文件只在 INTERNAL_AUTH_ENABLED=false 的进程中有效。
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures()


def _openapi(client) -> dict:
    return client.get("/openapi.json").json()


def test_开关关闭时写路由未注册(api_client):
    paths = _openapi(api_client)["paths"]
    assert "/students/{student_no}" in paths
    assert "put" not in paths["/students/{student_no}"], "关闭态不得注册 PUT，否则等于开放无认证写入口"


def test_关闭态_PUT_返回405且无副作用(api_client, db_client, admin_conn):
    from tests.conftest import AUTH_ENABLED

    if AUTH_ENABLED:  # 防御：文件被误在两个模式跑
        pytest.skip("仅在关闭态运行")

    def counts():
        with admin_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM campus.students")
            students = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM campus.operation_logs")
            logs = cur.fetchone()[0]
        return students, logs

    before = counts()
    response = db_client.put("/students/POCA0001", json={"student_name": "x"})
    # 同一路径的 GET 存在，未注册的 PUT 由框架返回 405（不是 404）
    assert response.status_code == 405
    assert counts() == before


def test_关闭态_旧接口仍可匿名访问(db_client):
    assert db_client.get("/students").status_code == 200
    assert db_client.get("/meta/filters").status_code == 200
    assert db_client.get("/stats/overview").status_code == 200
    assert db_client.get("/imports").status_code == 200


def test_健康检查只返回最小状态(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}, "liveness 不应暴露数据库/版本等细节"
