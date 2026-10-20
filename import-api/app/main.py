"""FastAPI 入口。

接口清单（与 docs/IMPORT-API.md 保持一致）：
  POST /imports/preview          上传并解析，返回预览与列映射
  POST /imports/{id}/validate    执行校验，写入异常明细
  POST /imports/{id}/commit      事务提交，幂等
  GET  /imports/{id}             查询批次状态与异常报告
  GET  /imports                  批次列表
  GET  /health                   存活与数据库连通性

身份说明：X-Actor 头在阶段 1 仅用于演示审计链路，
未经认证，不能作为真实权限依据（见 docs/SECURITY-CHECKLIST.md）。
"""
from __future__ import annotations

import base64
import binascii
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from psycopg import Error as DatabaseError
from pydantic import BaseModel, Field

from . import queries, service
from .config import settings
from .db import close_pool, open_pool, pool


@asynccontextmanager
async def lifespan(_app: FastAPI):
    open_pool()
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


def _actor(header_value: Optional[str]) -> str:
    return (header_value or settings.actor_fallback).strip()[:150]


def _handle(exc: service.ServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@app.get("/health")
def health() -> Dict[str, Any]:
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.fetchone()
    except Exception as exc:  # 数据库不可用时应返回 503，而不是假装健康
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc
    return {"status": "ok", "database": "ok", "version": app.version}


@app.post("/imports/preview")
def preview_import(
    file: UploadFile = File(..., description="xlsx 或 csv 文件"),
    target_type: str = Form(..., description="students | student_changes"),
    x_actor: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    data = file.file.read()
    try:
        return service.create_batch(data, file.filename or "upload.xlsx", target_type, _actor(x_actor))
    except service.ServiceError as exc:
        raise _handle(exc) from exc


class Base64Upload(BaseModel):
    """Appsmith FilePicker 只能提供 base64，故提供 JSON 版本的上传入口。"""

    filename: str = Field(..., max_length=255)
    content_base64: str
    target_type: str


def _decode_base64(raw: str) -> bytes:
    """兼容 Appsmith FilePicker 的两种输出：纯 base64，或带 data URL 前缀的 base64。"""
    text = raw.strip()
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    text = "".join(text.split())  # 去掉换行与空白
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        # 宽松模式兜底：部分组件会输出 URL-safe 字符或省略填充
        return base64.b64decode(text, validate=False)


@app.post("/imports/preview-base64")
def preview_import_base64(
    payload: Base64Upload,
    x_actor: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    try:
        data = _decode_base64(payload.content_base64)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"base64 解码失败：{exc}") from exc
    if not data:
        raise HTTPException(status_code=400, detail="base64 解码结果为空")
    try:
        return service.create_batch(data, payload.filename, payload.target_type, _actor(x_actor))
    except service.ServiceError as exc:
        raise _handle(exc) from exc


@app.post("/imports/{batch_id}/validate")
def validate_import(batch_id: int, x_actor: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    try:
        return service.validate_batch(batch_id, _actor(x_actor))
    except service.ServiceError as exc:
        raise _handle(exc) from exc


@app.post("/imports/{batch_id}/commit")
def commit_import(batch_id: int, x_actor: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    try:
        return service.commit_batch(batch_id, _actor(x_actor))
    except service.ServiceError as exc:
        raise _handle(exc) from exc
    except DatabaseError as exc:
        reason = getattr(getattr(exc, "diag", None), "message_primary", None) or str(exc)
        raise HTTPException(
            status_code=500,
            detail=f"提交失败，已整体回滚：{reason}",
        ) from exc


@app.get("/imports/{batch_id}")
def get_import(batch_id: int) -> Dict[str, Any]:
    try:
        return service.get_batch(batch_id)
    except service.ServiceError as exc:
        raise _handle(exc) from exc


@app.get("/imports")
def list_imports(limit: int = 50) -> List[Dict[str, Any]]:
    return service.list_batches(limit)


# ---------------------------------------------------------------- 只读查询
# 说明：以下接口为 React 前端补充，浏览器不直连数据库。
# 全部使用 campus_app 账号的参数化查询，只暴露 SELECT 能力。


@app.get("/students")
def list_students(
    keyword: Optional[str] = Query(default=None, max_length=100, description="学号或姓名模糊匹配"),
    college: Optional[str] = Query(default=None, max_length=100),
    class_name: Optional[str] = Query(default=None, max_length=100),
    status: Optional[str] = Query(default=None, max_length=20),
    include_inactive: bool = Query(default=False, description="是否包含已停用记录"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> Dict[str, Any]:
    return queries.list_students(
        keyword=keyword,
        college=college,
        class_name=class_name,
        status=status,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )


@app.get("/students/{student_no}")
def get_student(student_no: str) -> Dict[str, Any]:
    try:
        return queries.get_student(student_no)
    except service.ServiceError as exc:
        raise _handle(exc) from exc


@app.get("/meta/filters")
def get_filters() -> Dict[str, Any]:
    return queries.get_filters()


@app.get("/stats/overview")
def get_overview() -> Dict[str, Any]:
    return queries.get_overview()
