"""开启态（INTERNAL_AUTH_ENABLED=true）安全用例。

只在开启态进程运行：
    INTERNAL_AUTH_ENABLED=true INTERNAL_HMAC_SECRET=... pytest tests/test_internal_auth.py
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from tests import auth_helper as H

AUTH_ENABLED = os.environ.get("INTERNAL_AUTH_ENABLED", "").lower() in ("1", "true", "yes")
pytestmark = pytest.mark.skipif(not AUTH_ENABLED, reason="仅在开启态进程运行")

CSV = "学号,姓名,学院\nSA001,甲同学,计算机学院\n".encode()

# 11 个业务路由：(method, path, 所需权限, 是否需要请求体)
ROUTES = [
    ("GET", "/students", "student:list", None),
    ("GET", "/students/SA001", "student:list", None),
    ("GET", "/imports", "import:batch:list", None),
    ("GET", "/imports/1", "import:batch:detail", None),
    ("POST", "/imports/preview", "import:batch:upload", "file"),
    ("POST", "/imports/preview-base64", "import:batch:upload", "json"),
    ("POST", "/imports/1/remap", "import:batch:remap", "json"),
    ("POST", "/imports/1/validate", "import:batch:validate", "none"),
    ("POST", "/imports/1/commit", "import:batch:commit", "none"),
    ("GET", "/meta/filters", "student:list", None),
    ("GET", "/stats/overview", "student:list", None),
]
IMPORT_ROUTES = [r for r in ROUTES if r[1].startswith("/imports")]


def _call(client, method: str, path: str, kind, who=None, **kwargs):
    if kind == "file":
        return H.request(client, method, path, file_bytes=CSV, form={"target_type": "students"},
                         who=who, **kwargs)
    if kind == "json":
        body = {"filename": "a.csv", "content_base64": "", "target_type": "students"} \
            if path.endswith("/preview-base64") else {}
        return H.request(client, method, path, json_body=body, who=who, **kwargs)
    if kind == "none":
        return H.request(client, method, path, who=who, **kwargs)
    return H.request(client, method, path, who=who, **kwargs)


def _seed(admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO campus.students (student_no, student_name, college_name, class_name, student_status)
            VALUES ('SA001', '甲同学', '计算机学院', '软件2601', 'enrolled'),
                   ('SB001', '乙同学', '电子信息学院', '电子2601', 'enrolled')
            ON CONFLICT (student_no) DO NOTHING
            """
        )


# ---------------------------------------------------------------- 基础拒绝


@pytest.mark.parametrize("method,path,kind", [(m, p, k) for m, p, _, k in ROUTES])
def test_无签名头返回401(db_client, method, path, kind):
    if kind == "file":
        response = db_client.post(path, files={"file": ("a.csv", CSV, "text/csv")},
                                  data={"target_type": "students"})
    elif kind == "json":
        response = db_client.post(path, json={})
    else:
        response = db_client.request(method, path)
    assert response.status_code == 401


def test_缺任意一个签名头返回401(db_client):
    headers = H.sign("GET", "/students")
    for name in list(headers):
        partial = dict(headers)
        partial.pop(name)
        response = db_client.get("/students", headers=partial)
        assert response.status_code == 401, f"缺少 {name} 时应 401，实际 {response.status_code}"


def test_签名篡改返回401(db_client):
    response = H.request(db_client, "GET", "/students", tamper=True)
    assert response.status_code == 401


@pytest.mark.parametrize("delta", [-120, 120])
def test_时间戳越界返回401(db_client, delta):
    import time

    ts = str(int(time.time()) + delta)
    response = H.request(db_client, "GET", "/students", ts=ts)
    assert response.status_code == 401


def test_时间戳非数字返回401(db_client):
    response = H.request(db_client, "GET", "/students", ts="abc")
    assert response.status_code == 401


@pytest.mark.parametrize("value", ["TRUE", "1", "yes"])
def test_管理员声明必须严格小写(db_client, value):
    headers = H.sign("GET", "/students")
    headers["X-Internal-Admin"] = value
    response = db_client.get("/students", headers=headers)
    assert response.status_code == 401


# ---------------------------------------------------------------- 完整性


def test_query被篡改返回401(db_client):
    headers = H.sign("GET", "/students", query={"limit": "1"})
    response = db_client.get("/students?limit=2", headers=headers)
    assert response.status_code == 401


def test_JSON_body被替换返回401(db_client):
    import json

    body_a = json.dumps({"filename": "a.csv", "content_base64": "", "target_type": "students"}).encode()
    body_b = json.dumps({"filename": "b.csv", "content_base64": "", "target_type": "students"}).encode()
    headers = H.sign("POST", "/imports/preview-base64", body=body_a)
    headers["Content-Type"] = "application/json"
    response = db_client.post("/imports/preview-base64", content=body_b, headers=headers)
    assert response.status_code == 401


def test_multipart表单字段被篡改返回401(db_client):
    headers = H.sign("POST", "/imports/preview", file_bytes=CSV, form={"target_type": "students"})
    response = db_client.post(
        "/imports/preview",
        headers=headers,
        files={"file": ("a.csv", CSV, "text/csv")},
        data={"target_type": "student_changes"},
    )
    assert response.status_code == 401


def test_文件内容被替换返回401(db_client):
    headers = H.sign("POST", "/imports/preview", file_bytes=CSV, form={"target_type": "students"})
    other = "学号,姓名,学院\nSA999,替换,计算机学院\n".encode()
    response = db_client.post(
        "/imports/preview",
        headers=headers,
        files={"file": ("a.csv", other, "text/csv")},
        data={"target_type": "students"},
    )
    assert response.status_code == 401


def test_重放返回409(db_client):
    headers = H.sign("GET", "/students")
    assert db_client.get("/students", headers=headers).status_code == 200
    assert db_client.get("/students", headers=headers).status_code == 409


def test_并发同nonce仅一个成功(db_client):
    import time

    headers = H.sign("GET", "/students", nonce="a" * 32, ts=str(int(time.time())))

    def call(_):
        # 不使用 with：会触发 lifespan 关闭全局连接池，影响后续用例
        return TestClient(db_client.app).get("/students", headers=headers).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(call, range(2)))
    assert results == [200, 409], f"并发应恰好一成一败，实际 {results}"


# ---------------------------------------------------------------- 授权与范围


def test_低权限调用上传返回403(db_client):
    response = H.request(db_client, "POST", "/imports/preview", file_bytes=CSV,
                         form={"target_type": "students"}, who=H.WHO_READONLY)
    assert response.status_code == 403


@pytest.mark.parametrize("method,path,_,kind", IMPORT_ROUTES)
def test_非管理员即使持全部导入权限也被拒(db_client, method, path, _, kind):
    if kind == "file":
        response = H.request(db_client, method, path, file_bytes=CSV,
                             form={"target_type": "students"}, who=H.WHO_COLLEGE)
    elif kind == "json":
        body = {"filename": "a.csv", "content_base64": "", "target_type": "students"} \
            if path.endswith("/preview-base64") else {}
        response = H.request(db_client, method, path, json_body=body, who=H.WHO_COLLEGE)
    else:
        response = H.request(db_client, method, path, who=H.WHO_COLLEGE)
    assert response.status_code == 403, "PR-C 前导入接口仅限管理员"


def test_无学院声明访问聚合接口返回403(db_client):
    assert H.request(db_client, "GET", "/stats/overview", who=H.WHO_NO_COLLEGE).status_code == 403
    assert H.request(db_client, "GET", "/meta/filters", who=H.WHO_NO_COLLEGE).status_code == 403


def test_跨学院详情返回403(db_client, admin_conn):
    _seed(admin_conn)
    response = H.request(db_client, "GET", "/students/SB001", who=H.WHO_COLLEGE)
    assert response.status_code == 403


def test_跨学院列表被范围过滤(db_client, admin_conn):
    _seed(admin_conn)
    response = H.request(db_client, "GET", "/students", query={"college": H.COLLEGE_B},
                         who=H.WHO_COLLEGE)
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_伪造身份头不改变审计操作人(db_client, admin_conn):
    response = H.request(
        db_client, "POST", "/imports/preview",
        file_bytes=CSV, form={"target_type": "students"},
        who=H.WHO_ADMIN, extra_headers={"X-Actor": "attacker"},
    )
    assert response.status_code == 200, response.text
    with admin_conn.cursor() as cur:
        cur.execute("SELECT created_by FROM campus.import_batches ORDER BY id DESC LIMIT 1")
        assert cur.fetchone()[0] == "ry:admin"


# ---------------------------------------------------------------- 契约与结构


def test_金标向量(): 
    signature = H.hmac.new(
        H.GOLDEN_SECRET.encode(),
        H.canonical(**H.GOLDEN_INPUT).encode(),
        H.hashlib.sha256,
    ).hexdigest()
    assert signature == H.GOLDEN_SIGNATURE

    from app import internal_auth as auth

    canonical = auth._canonical(
        "GET", "/imports", "limit=1", "1700000000", "0123456789abcdef",
        H.GOLDEN_INPUT["payload_sha"], "", "ry:test", "college",
        H.GOLDEN_INPUT["college"], H.GOLDEN_INPUT["colleges"],
        "1762000000000000101", "false", "import:batch:list",
    ).decode()
    assert canonical == H.canonical(**H.GOLDEN_INPUT)


def test_所有业务路由都挂了身份依赖(api_client):
    from fastapi.routing import APIRoute

    from app.internal_auth import identity
    from app.main import app

    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path.startswith("/health"):
            continue
        if not any(dep.call is identity for dep in route.dependant.dependencies):
            missing.append(f"{sorted(route.methods)} {route.path}")
    assert missing == [], f"以下路由未挂身份依赖：{missing}"
