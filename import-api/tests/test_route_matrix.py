"""逐路由权限矩阵：11 条业务路由 × 无签名 / 缺权限 / 管理员限制 / 范围 / 副作用。

不依赖结构测试：每条路由都实际发请求并核对数据库与文件系统副作用。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests import auth_helper as H

AUTH_ENABLED = os.environ.get("INTERNAL_AUTH_ENABLED", "").lower() in ("1", "true", "yes")
pytestmark = pytest.mark.skipif(not AUTH_ENABLED, reason="仅在开启态进程运行")

CSV = "学号,姓名,学院\nSA001,甲同学,计算机学院\n".encode()

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
DATA_ROUTES = [r for r in ROUTES if not r[1].startswith("/imports")]

TABLES = ("students", "student_changes", "import_batches", "import_issues", "operation_logs")


def _send(client, method, path, kind, who=None, **kwargs):
    if kind == "file":
        return H.request(client, method, path, file_bytes=CSV,
                         form={"target_type": "students"}, who=who, **kwargs)
    if kind == "json":
        body = {"filename": "a.csv", "content_base64": "", "target_type": "students"} \
            if path.endswith("/preview-base64") else {}
        return H.request(client, method, path, json_body=body, who=who, **kwargs)
    return H.request(client, method, path, who=who, **kwargs)


def _snapshot(conn, upload_dir: Path):
    with conn.cursor() as cur:
        counts = {}
        for table in TABLES:
            cur.execute(f"SELECT count(*) FROM campus.{table}")
            counts[table] = cur.fetchone()[0]
    files = len([p for p in upload_dir.glob("*") if p.is_file()]) if upload_dir.exists() else 0
    return counts, files


@pytest.fixture
def snapshot(admin_conn, tmp_path):
    from app.config import settings

    upload_dir = Path(settings.upload_dir)
    return lambda: _snapshot(admin_conn, upload_dir)


@pytest.mark.parametrize("method,path,perm,kind", ROUTES)
def test_matrix_无签名一律401(db_client, method, path, perm, kind):
    if kind == "file":
        response = db_client.post(path, files={"file": ("a.csv", CSV, "text/csv")},
                                  data={"target_type": "students"})
    elif kind == "json":
        response = db_client.post(path, json={})
    else:
        response = db_client.request(method, path)
    assert response.status_code == 401, f"{method} {path}"


@pytest.mark.parametrize("method,path,perm,kind", ROUTES)
def test_matrix_缺对应权限一律403(db_client, method, path, perm, kind):
    who = dict(H.WHO_COLLEGE)
    who["perms"] = "student:list" if perm != "student:list" else "import:batch:list"
    response = _send(db_client, method, path, kind, who=who)
    assert response.status_code == 403, f"{method} {path} 应因缺少 {perm} 被拒"


@pytest.mark.parametrize("method,path,perm,kind", IMPORT_ROUTES)
def test_matrix_导入接口管理员硬限制(db_client, method, path, perm, kind):
    # WHO_COLLEGE 持全部 import:batch:*，但仍非管理员 → 403
    response = _send(db_client, method, path, kind, who=H.WHO_COLLEGE)
    assert response.status_code == 403, f"{method} {path} 应受 PR-C 前的管理员限制"


@pytest.mark.parametrize("method,path,perm,kind", DATA_ROUTES)
def test_matrix_被拒请求无副作用(db_client, snapshot, method, path, perm, kind):
    before = snapshot()
    who = dict(H.WHO_COLLEGE)
    who["perms"] = ""  # 有学院、无权限
    response = _send(db_client, method, path, kind, who=who)
    assert response.status_code == 403
    assert snapshot() == before, "被拒绝的请求不得产生数据或文件副作用"


def test_matrix_无签名请求无副作用(db_client, snapshot):
    before = snapshot()
    assert db_client.get("/students").status_code == 401
    assert db_client.post("/imports/preview",
                          files={"file": ("a.csv", CSV, "text/csv")},
                          data={"target_type": "students"}).status_code == 401
    assert snapshot() == before
