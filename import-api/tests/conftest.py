"""pytest 全局配置与夹具。

本文件在**模块顶层**完成环境准备，原因有两条硬约束：

1. `app.config.Settings` 在导入时实例化，`database_url` 是必填项。
   没有 `DATABASE_URL` 时，`import app.main` 直接抛 ValidationError，
   测试连收集阶段都过不去。
2. `app.db.pool` 同样在导入时按 `settings.database_url` 构造，
   导入之后无法再按用例切换目标库（`from .db import pool` 是按值绑定）。

所以环境变量必须在任何 `app.*` 导入之前注入，放在 fixture 里就晚了。

真库用例的开关是环境变量 `CAMPUS_TEST_DATABASE_URL`：
- 未设置：整组 DB 用例 skip，本地无需 Docker 也能全绿；
- 已设置：`DATABASE_URL` 指向该库，用例执行前先 TRUNCATE。

禁止把该变量指向主库 `campus`——用例会清空业务表。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
API_DIR = TESTS_DIR.parent
ROOT_DIR = API_DIR.parent
SAMPLES_DIR = ROOT_DIR / "samples"

# 真库集成测试：只有显式提供测试库 DSN 时才启用
TEST_DSN_ENV = "CAMPUS_TEST_DATABASE_URL"
TEST_DSN = os.environ.get(TEST_DSN_ENV, "").strip()

# 占位 DSN 仅用于满足 Settings 的必填校验；除非用例真的触达数据库，否则不会被连接
os.environ.setdefault(
    "DATABASE_URL", TEST_DSN or "postgresql://campus_app:placeholder@127.0.0.1:1/campus"
)
# 上传目录指向临时目录，避免 create_batch 往 /data/uploads 写文件
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="campus-api-tests-"))

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

requires_db = pytest.mark.skipif(
    not TEST_DSN, reason=f"未设置 {TEST_DSN_ENV}，跳过真库集成测试"
)


# ------------------------------------------------------------------ 夹具数据
@pytest.fixture(scope="session")
def samples_dir() -> Path:
    """仓库内 samples/ 目录，全部为虚构数据。"""
    return SAMPLES_DIR


@pytest.fixture(scope="session")
def load_sample(samples_dir: Path):
    """按文件名读取 samples/ 下的字节内容。"""

    def _load(name: str) -> bytes:
        path = samples_dir / name
        assert path.exists(), f"缺少夹具文件：{path}"
        return path.read_bytes()

    return _load


# ------------------------------------------------------------------ 服务实例
@pytest.fixture
def api_client():
    """不带 lifespan 的 TestClient。

    不使用 `with TestClient(app)`，因为那会触发 lifespan 去打开连接池；
    纯逻辑用例不应该为此依赖一个可连接的数据库。
    """
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


# ------------------------------------------------------------------ 真库
@pytest.fixture(scope="session")
def db_session():
    """打开连接池；整轮 DB 用例共用，结束时关闭。

    要求 `CAMPUS_TEST_DATABASE_URL` 指向一个**已经执行过 sql/001_schema.sql**
    的空库，且所用角色具备 TRUNCATE 权限（否则 clean_db 会失败）。
    """
    if not TEST_DSN:
        pytest.skip(f"未设置 {TEST_DSN_ENV}")

    from app.db import close_pool, open_pool, pool

    open_pool()
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('campus.students') AS oid")
                if cur.fetchone()["oid"] is None:
                    pytest.fail(
                        f"测试库缺少 campus schema：请先执行 psql -f sql/001_schema.sql（DSN={TEST_DSN}）"
                    )
        yield
    finally:
        close_pool()


@pytest.fixture
def clean_db(db_session, tmp_path, monkeypatch):
    """清空业务表并把上传目录切到临时目录，保证用例之间互不影响。"""
    from app.config import settings
    from app.db import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE campus.import_issues,
                         campus.student_changes,
                         campus.students,
                         campus.import_batches,
                         campus.operation_logs
                RESTART IDENTITY CASCADE
                """
            )
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    return None


@pytest.fixture
def db_client(clean_db):
    """真库用例使用的客户端：连接池已由 db_session 打开。"""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)
