#!/usr/bin/env python
"""在隔离测试库上运行 import-api 的完整测试链。

默认连接本机 ``campus-test-db``（127.0.0.1:5433/campus_test）。
脚本只允许数据库名包含 ``test`` 的目标，避免误把主库 ``campus`` 当成测试库
（真库用例会 TRUNCATE 业务表）。

用法：
    python scripts/dev/test-import-api.py

可用环境变量覆盖：
    CAMPUS_TEST_ADMIN_DATABASE_URL
    CAMPUS_TEST_DATABASE_URL
    CAMPUS_TEST_APP_PASSWORD
    INTERNAL_HMAC_SECRET
"""
from __future__ import annotations

import sys as _sys

if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "import-api"

ADMIN_DSN = os.environ.get(
    "CAMPUS_TEST_ADMIN_DATABASE_URL",
    "postgresql://campus_test:campus_test@127.0.0.1:5433/campus_test",
)
APP_DSN = os.environ.get(
    "CAMPUS_TEST_DATABASE_URL",
    "postgresql://campus_app:campus_test_app_pw@127.0.0.1:5433/campus_test",
)
APP_PASSWORD = os.environ.get("CAMPUS_TEST_APP_PASSWORD", "campus_test_app_pw")
HMAC_SECRET = os.environ.get(
    "INTERNAL_HMAC_SECRET", "campus-test-secret-0123456789abcdef0123"
)

SECURITY_TESTS = [
    "tests/test_internal_auth.py",
    "tests/test_route_matrix.py",
    "tests/test_db_privileges.py",
    "tests/test_import_scope.py",
    "tests/test_student_write.py",
    "tests/test_pr_e_hardening.py",
    "tests/test_import_audit_summary.py",
]


def fail(message: str) -> None:
    print(f"[test-import-api] {message}", file=sys.stderr)
    raise SystemExit(2)


def db_name(dsn: str) -> str:
    return urlparse(dsn).path.lstrip("/")


def check_target() -> None:
    for label, dsn in (("管理连接", ADMIN_DSN), ("业务连接", APP_DSN)):
        name = db_name(dsn)
        if "test" not in name.lower():
            fail(f"{label}目标库为 {name!r}，不是测试库。拒绝执行 TRUNCATE 用例。")
    parsed = urlparse(ADMIN_DSN)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError as exc:
        fail(
            f"测试库 {host}:{port} 不可达：{exc}\n"
            "请先启动隔离测试库，例如：\n"
            "  docker run --rm -d --name campus-test-db \\\n"
            "    -e POSTGRES_USER=campus_test -e POSTGRES_PASSWORD=campus_test \\\n"
            "    -e POSTGRES_DB=campus_test -p 127.0.0.1:5433:5432 postgres:16.15-alpine"
        )


def run(cmd: list[str], env: dict[str, str]) -> None:
    print(f"\n[test-import-api] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=API_DIR, env=env, check=True)


def main() -> None:
    check_target()
    env = os.environ.copy()
    env.update(
        {
            "CAMPUS_TEST_ADMIN_DATABASE_URL": ADMIN_DSN,
            "CAMPUS_TEST_DATABASE_URL": APP_DSN,
            "CAMPUS_TEST_APP_PASSWORD": APP_PASSWORD,
            "INTERNAL_HMAC_SECRET": HMAC_SECRET,
            "PYTHONUTF8": "1",
        }
    )
    env.pop("INTERNAL_AUTH_ENABLED", None)

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "init-test-db.py"),
            "--admin-dsn",
            ADMIN_DSN,
            "--app-password",
            APP_PASSWORD,
            "--verify",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )

    run([sys.executable, "-m", "pytest", "-q"], env)

    auth_env = {**env, "INTERNAL_AUTH_ENABLED": "true"}
    run([sys.executable, "-m", "pytest", "-q", *SECURITY_TESTS], auth_env)
    print("\n[test-import-api] 全部通过（关闭态 + 安全开启态）")


if __name__ == "__main__":
    main()
