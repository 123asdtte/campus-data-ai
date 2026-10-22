"""AI 校园助手原型：环境配置。

所有配置来自环境变量，不读取仓库内文件；默认值与 POC 隔离栈一致。
正式部署必须由密钥管理注入 DSN 与 token，禁止写入镜像。
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    ro_dsn: str
    audit_dsn: str
    poc_token: str
    planner: str          # rule | llm
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    max_rows: int
    llm_timeout: float

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            ro_dsn=_env("AI_RO_DSN", "postgresql://ai_ro:ai_ro_pw@ai-db:5432/campus_ai_poc"),
            audit_dsn=_env(
                "AI_AUDIT_DSN",
                "postgresql://ai_audit_writer:ai_audit_pw@ai-db:5432/campus_ai_poc",
            ),
            poc_token=_env("AI_POC_TOKEN", ""),
            planner=_env("AI_PLANNER", "rule").lower(),
            llm_base_url=_env("AI_LLM_BASE_URL", "").rstrip("/"),
            llm_api_key=_env("AI_LLM_API_KEY", ""),
            llm_model=_env("AI_LLM_MODEL", "gpt-4o-mini"),
            max_rows=max(1, int(_env("AI_MAX_ROWS", "20"))),
            llm_timeout=float(_env("AI_LLM_TIMEOUT", "10")),
        )


SETTINGS = Settings.from_env()
