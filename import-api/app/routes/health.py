"""健康检查：liveness 与 readiness 分离。

`/health` 有意豁免业务签名（容器 healthcheck 与运维探活使用），
只返回最小状态，不暴露数据库、版本或异常细节。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..db import pool

router = APIRouter()


@router.get("/health")
def health() -> Dict[str, Any]:
    """存活探针：进程能处理请求即返回 200。"""
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready() -> Dict[str, Any]:
    """就绪探针：数据库不可用时返回 503，错误细节不对外暴露。"""
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "ok"}
