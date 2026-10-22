"""pytest 全局配置与夹具。

本文件在**模块顶层**完成环境准备，原因有三条硬约束：

1. `app.config.Settings` 在导入时实例化，`database_url` 是必填项。
2. `app.db.pool` 同样在导入时按 `settings.database_url` 构造。
3. 认证开关 `INTERNAL_AUTH_ENABLED` 在 `app.internal_auth` 导入时定型，并决定
   `PUT /students/{no}` 是否注册；两种模式必须在**不同进程**中运行。

所以环境变量必须在任何 `app.*` 导入之前注入，放在 fixture 里就晚了。

环境变量：
- `CAMPUS_TEST_DATABASE_URL`      业务测试连接（应为 campus_app 身份）
- `CAMPUS_TEST_ADMIN_DATABASE_URL` 管理连接（初始化/清理），CI 必填
- `INTERNAL_AUTH_ENABLED`         是否开启验签（决定路由注册）
- `INTERNAL_HMAC_SECRET`          开启时必填（≥32 字符）

禁止把测试 DSN 指向主库 `campus`——用例会清空业务表。
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

TEST_DSN_ENV = "CAMPUS_TEST_DATABASE_URL"
ADMIN_DSN_ENV = "CAMPUS_TEST_ADMIN_DATABASE_URL"
TEST_DSN = os.environ.get(TEST_DSN_ENV, "").strip()
ADMIN_DSN = os.environ.get(ADMIN_DSN_ENV, "").strip()
IS_CI = bool(os.environ.get("CI"))

# 占位 DSN 仅用于满足 Settings 必填校验；未设置测试库时不会真正连接
os.environ.setdefault(
    "DATABASE_URL", TEST_DSN or "postgresql://campus_app:placeholder@127.0.0.1:1/campus"
)
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="campus-api-tests-"))
os.environ.setdefault("INTERNAL_HMAC_SECRET", "campus-test-secret-0123456789abcdef0123")

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

AUTH_ENABLED = os.environ.get("INTERNAL_AUTH_ENABLED", "").lower() in ("1", "true", "yes")

requires_db = pytest.mark.skipif(
    not TEST_DSN, reason=f"未设置 {TEST_DSN_ENV}，跳过真库集成测试"
)
requires_admin_dsn = pytest.mark.skipif(
    not ADMIN_DSN, reason=f"未设置 {ADMIN_DSN_ENV}，跳过权限/清理相关用例"
)
requires_auth_enabled = pytest.mark.skipif(
    not AUTH_ENABLED, reason="仅在 INTERNAL_AUTH_ENABLED=true 的进程中运行"
)
requires_auth_disabled = pytest.mark.skipif(
    AUTH_ENABLED, reason="仅在 INTERNAL_AUTH_ENABLED=false 的进程中运行"
)


# ------------------------------------------------------------------ 夹具数据
@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return SAMPLES_DIR


@pytest.fixture(scope="session")
def load_sample(samples_dir: Path):
    def _load(name: str) -> bytes:
        path = samples_dir / name
        assert path.exists(), f"缺少夹具文件：{path}"
        return path.read_bytes()

    return _load


# ------------------------------------------------------------------ 服务实例
@pytest.fixture
def api_client():
    """不带 lifespan 的 TestClient（纯逻辑用例，不打开连接池）。"""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


# ------------------------------------------------------------------ 真库
@pytest.fixture(scope="session")
def db_session():
    """打开连接池；整轮 DB 用例共用。"""
    if not TEST_DSN:
        pytest.skip(f"未设置 {TEST_DSN_ENV}")
    if IS_CI and not ADMIN_DSN:
        pytest.fail(
            f"CI 环境必须设置 {ADMIN_DSN_ENV}：否则 campus_app 无 TRUNCATE 权限，"
            "权限用例也会被静默跳过"
        )

    from app.db import close_pool, open_pool, pool

    open_pool()
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('campus.students') AS oid")
                if cur.fetchone()["oid"] is None:
                    pytest.fail(
                        "测试库缺少 campus schema：先执行 "
                        f"python scripts/init-test-db.py --admin-dsn <DSN>（当前 DSN={TEST_DSN}）"
                    )
        yield
    finally:
        close_pool()


def _truncate_with_admin() -> None:
    """用管理连接清空业务表（campus_app 无 TRUNCATE 权限）。"""
    import psycopg

    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('campus.internal_nonce') AS oid")
            has_nonce = cur.fetchone()[0] is not None
            tables = [
                "campus.import_issues",
                "campus.student_changes",
                "campus.students",
                "campus.import_batches",
                "campus.operation_logs",
            ]
            if has_nonce:
                tables.append("campus.internal_nonce")
            cur.execute(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")


@pytest.fixture
def clean_db(db_session, tmp_path, monkeypatch):
    """清空业务表并把上传目录切到临时目录。"""
    from app.config import settings
    from app.db import pool

    if ADMIN_DSN:
        _truncate_with_admin()
    else:
        # 本地无管理连接时的兼容路径：要求测试 DSN 本身具备 TRUNCATE 权限
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
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def admin_conn():
    """管理连接：仅用于断言副作用快照与权限测试。"""
    import psycopg

    if not ADMIN_DSN:
        pytest.skip(f"未设置 {ADMIN_DSN_ENV}")

    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        yield conn
