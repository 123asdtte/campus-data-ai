"""FastAPI 入口：装配路由与生命周期。

认证开关在导入期定型（修改后必须重启进程）：
- 关闭：11 个业务路由保持旧行为，PUT /students/{no} 不注册；
- 开启：业务路由要求 X-Internal-* 签名，PUT 注册。

`/health` 与 `/health/ready` 是有意豁免签名的基础设施端点。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import internal_auth
from .db import close_pool, open_pool
from .routes import health, imports, meta, students

log = logging.getLogger("import-api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    open_pool()
    if internal_auth.AUTH_ENABLED:
        # 开了开关却没执行 004 时，启动即失败，避免每个请求 500
        internal_auth.assert_nonce_ready()
        try:
            removed = internal_auth.cleanup_nonce()
            if removed:
                log.info("已清理过期 nonce：%s 条", removed)
        except Exception as exc:  # noqa: BLE001
            log.warning("nonce 清理失败：%s", exc)
    log.info("internal_auth=%s", "enabled" if internal_auth.AUTH_ENABLED else "disabled")
    try:
        yield
    finally:
        close_pool()


app = FastAPI(
    title="Campus Import API",
    version="0.1.0",
    description="校园数据导入校验服务（阶段 1：虚构数据验证）",
    lifespan=lifespan,
)

app.include_router(health.router)      # 公开：liveness + readiness
app.include_router(imports.router)     # 7 条导入路由
app.include_router(students.router)    # 2 条只读学生路由
app.include_router(meta.router)        # 筛选项与总览

if internal_auth.AUTH_ENABLED:
    # 新增写接口只在认证开启时存在；关闭时物理不注册（同路径 GET 存在 → 405）
    app.include_router(students.write_router)
