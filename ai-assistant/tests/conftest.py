"""测试环境准备：在导入 app 之前设置配置。

本地运行（隔离 POC 库需已启动）：
  AI_DB_PASSWORD=... 等从仓库根 .env 读取后传入，或直接使用下面默认值。
"""
from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest

# 默认指向 docker-compose.ai-poc.yml 暴露的 127.0.0.1:55435；
# CI 的 services.postgres 使用 5432，通过 AI_DB_PORT 覆盖。
# 下面的默认口令仅用于本地/CI 的一次性测试库，禁止用于任何共享环境。
_admin_pw = os.environ.get("AI_DB_PASSWORD", "ai_dba_pw")
_ro_pw = os.environ.get("AI_RO_PASSWORD", "ai_ro_pw")
_audit_pw = os.environ.get("AI_AUDIT_PASSWORD", "ai_audit_pw")
_db_host = os.environ.get("AI_DB_HOST", "127.0.0.1")
_db_port = os.environ.get("AI_DB_PORT", "55435")

os.environ.setdefault(
    "AI_RO_DSN",
    "postgresql://ai_ro:%s@%s:%s/campus_ai_poc" % (_ro_pw, _db_host, _db_port),
)
os.environ.setdefault(
    "AI_AUDIT_DSN",
    "postgresql://ai_audit_writer:%s@%s:%s/campus_ai_poc" % (_audit_pw, _db_host, _db_port),
)
os.environ.setdefault(
    "AI_ADMIN_DSN",
    "postgresql://ai_dba:%s@%s:%s/campus_ai_poc" % (_admin_pw, _db_host, _db_port),
)
os.environ.setdefault("AI_POC_TOKEN", "poc-test-token")
os.environ.setdefault("AI_PLANNER", "rule")


def _db_reachable() -> bool:
    parsed = urlparse(os.environ["AI_RO_DSN"])
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


if not _db_reachable():
    pytest.skip(
        "AI POC 数据库不可用：先运行 docker compose -f docker-compose.ai-poc.yml up -d"
        "（CI 由 services.postgres 提供）",
        allow_module_level=True,
    )
