"""FastAPI 入口：装配路由与生命周期。

认证开关在导入期定型（修改后必须重启进程）：
- 关闭：11 个业务路由保持旧行为，PUT /students/{no} 不注册；
- 开启：业务路由要求 X-Internal-* 签名，PUT 注册。

`/health` 与 `/health/ready` 是有意豁免签名的基础设施端点。
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from . import internal_auth
from .db import close_pool, open_pool
from .routes import audit, health, imports, meta, students

log = logging.getLogger("import-api")

# 过期 nonce 的周期清理间隔（秒）。启动时先清理一次，随后按此间隔执行，
# 避免长期运行的容器只清理一次导致表无限增长。
NONCE_CLEANUP_INTERVAL_SECONDS = 3600


async def _nonce_cleanup_loop() -> None:
    """后台周期清理；异常只记日志，不影响业务请求。"""
    while True:
        await asyncio.sleep(NONCE_CLEANUP_INTERVAL_SECONDS)
        try:
            removed = await asyncio.to_thread(internal_auth.cleanup_nonce)
            if removed:
                log.info("已清理过期 nonce：%s 条", removed)
        except Exception as exc:  # noqa: BLE001
            log.warning("周期 nonce 清理失败：%s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    open_pool()
    cleanup_task: asyncio.Task | None = None
    if internal_auth.AUTH_ENABLED:
        # 开了开关却没执行 004 时，启动即失败，避免每个请求 500
        internal_auth.assert_nonce_ready()
        try:
            removed = internal_auth.cleanup_nonce()
            if removed:
                log.info("已清理过期 nonce：%s 条", removed)
        except Exception as exc:  # noqa: BLE001
            log.warning("nonce 清理失败：%s", exc)
        cleanup_task = asyncio.create_task(_nonce_cleanup_loop())
    log.info("internal_auth=%s", "enabled" if internal_auth.AUTH_ENABLED else "disabled")
    try:
        yield
    finally:
        if cleanup_task is not None:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
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
app.include_router(audit.router)        # 全局操作审计（管理员视角）

# 写接口始终注册：认证开启时由 require_internal 验签并强制权限/数据范围；
# 关闭时（本地演示/单用户）走匿名身份，操作人回落到 ACTOR_FALLBACK 或由
# 调用方通过 X-Actor 头声明。字段级编辑经触发器自动写入 operation_logs 留痕。
app.include_router(students.write_router)
