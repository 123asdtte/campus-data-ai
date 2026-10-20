"""应用配置：全部通过环境变量注入，不在代码中出现凭据。"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False, extra="ignore")

    database_url: str
    actor_fallback: str = "import-api"
    max_upload_mb: int = 10
    max_rows: int = 10000
    keep_upload_files: bool = False
    upload_dir: str = "/data/uploads"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
