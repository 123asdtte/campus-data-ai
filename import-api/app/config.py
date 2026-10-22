"""应用配置：全部通过环境变量注入，不在代码中出现凭据。"""
from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False, extra="ignore")

    database_url: str
    actor_fallback: str = "import-api"
    max_upload_mb: int = 10
    max_rows: int = 10000
    keep_upload_files: bool = False
    upload_dir: str = "/data/uploads"

    # 内部请求认证（默认关闭；开启后所有业务路由要求 X-Internal-* 签名）
    internal_auth_enabled: bool = False
    internal_hmac_secret: str = ""
    internal_auth_max_skew_seconds: int = 60
    internal_nonce_ttl_hours: int = 24

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @model_validator(mode="after")
    def _validate_internal_auth(self) -> "Settings":
        if self.internal_auth_enabled and len(self.internal_hmac_secret) < 32:
            # 导入期失败：容器直接起不来，好过运行期每个请求 500
            raise ValueError(
                "INTERNAL_AUTH_ENABLED=true 时 INTERNAL_HMAC_SECRET 至少 32 字符"
            )
        if self.internal_auth_max_skew_seconds < 1 or self.internal_auth_max_skew_seconds > 600:
            raise ValueError("INTERNAL_AUTH_MAX_SKEW_SECONDS 必须在 1..600 之间")
        if self.internal_nonce_ttl_hours < 1 or self.internal_nonce_ttl_hours > 168:
            raise ValueError("INTERNAL_NONCE_TTL_HOURS 必须在 1..168 之间")
        return self


settings = Settings()
