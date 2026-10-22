"""测试环境准备：在导入 app 之前设置配置。

本地运行（隔离 POC 库需已启动）：
  AI_DB_PASSWORD=... 等从仓库根 .env 读取后传入，或直接使用下面默认值。
"""
from __future__ import annotations

import os
import socket

import pytest

# 默认指向 docker-compose.ai-poc.yml 暴露的 55435；真实运行时用环境变量覆盖
_admin_pw = os.environ.get("AI_DB_PASSWORD", "ai_dba_pw")
_ro_pw = os.environ.get("AI_RO_PASSWORD", "ai_ro_pw")
_audit_pw = os.environ.get("AI_AUDIT_PASSWORD", "ai_audit_pw")

os.environ.setdefault(
    "AI_RO_DSN", "postgresql://ai_ro:%s@127.0.0.1:55435/campus_ai_poc" % _ro_pw
)
os.environ.setdefault(
    "AI_AUDIT_DSN",
    "postgresql://ai_audit_writer:%s@127.0.0.1:55435/campus_ai_poc" % _audit_pw,
)
os.environ.setdefault(
    "AI_ADMIN_DSN", "postgresql://ai_dba:%s@127.0.0.1:55435/campus_ai_poc" % _admin_pw
)
os.environ.setdefault("AI_POC_TOKEN", "poc-test-token")
os.environ.setdefault("AI_PLANNER", "rule")


def _db_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 55435), timeout=1):
            return True
    except OSError:
        return False


if not _db_reachable():
    pytest.skip(
        "AI POC 数据库 127.0.0.1:55435 不可用：先运行 "
        "docker compose -f docker-compose.ai-poc.yml up -d",
        allow_module_level=True,
    )
