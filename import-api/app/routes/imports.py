"""导入接口：认证 + 权限点；批次范围与逐行校验在 PR-C 接入。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from psycopg import Error as DatabaseError
from pydantic import BaseModel, Field

from .. import service
from ..internal_auth import (
    Who,
    identity,
    require_perm,
    resolve_actor,
    scope_colleges,
)
from ._shared import decode_base64, handle, parse_mapping

router = APIRouter()


class Base64Upload(BaseModel):
    """Appsmith FilePicker 只能提供 base64，故提供 JSON 版本的上传入口。"""

    filename: str = Field(..., max_length=255)
    content_base64: str
    target_type: str
    sheet_name: Optional[str] = None
    header_row: Optional[int] = None
    mapping: Optional[Dict[str, Optional[str]]] = None


class RemapRequest(BaseModel):
    """调整工作表、表头行或列映射后重新解析。"""

    sheet_name: Optional[str] = None
    header_row: Optional[int] = None
    mapping: Optional[Dict[str, Optional[str]]] = None


@router.post("/imports/preview")
def preview_import(
    current: Optional[Who] = Depends(identity),
    file: UploadFile = File(..., description="xlsx 或 csv 文件"),
    target_type: str = Form(..., description="students | student_changes"),
    sheet_name: Optional[str] = Form(default=None, description="指定工作表；留空自动识别"),
    header_row: Optional[int] = Form(default=None, description="指定表头行号；留空自动识别"),
    mapping: Optional[str] = Form(default=None, description='JSON：{"原始列名": "字段名"}'),
    x_actor: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_perm(current, "import:batch:upload")
    data = file.file.read()
    overrides = parse_mapping(mapping)
    try:
        return service.create_batch(
            data,
            file.filename or "upload.xlsx",
            target_type,
            resolve_actor(current, x_actor),
            created_dept_id=current.dept_id if current else None,
            sheet_name=sheet_name,
            header_row=header_row,
            overrides=overrides,
        )
    except service.ServiceError as exc:
        raise handle(exc) from exc


@router.post("/imports/preview-base64")
def preview_import_base64(
    payload: Base64Upload,
    current: Optional[Who] = Depends(identity),
    x_actor: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_perm(current, "import:batch:upload")
    try:
        data = decode_base64(payload.content_base64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"base64 解码失败：{exc}") from exc
    if not data:
        raise HTTPException(status_code=400, detail="base64 解码结果为空")
    try:
        return service.create_batch(
            data,
            payload.filename,
            payload.target_type,
            resolve_actor(current, x_actor),
            created_dept_id=current.dept_id if current else None,
            sheet_name=payload.sheet_name,
            header_row=payload.header_row,
            overrides=payload.mapping,
        )
    except service.ServiceError as exc:
        raise handle(exc) from exc


@router.post("/imports/{batch_id}/remap")
def remap_import(
    batch_id: int,
    payload: RemapRequest,
    current: Optional[Who] = Depends(identity),
    x_actor: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_perm(current, "import:batch:remap")
    try:
        return service.remap_batch(
            batch_id,
            resolve_actor(current, x_actor),
            sheet_name=payload.sheet_name,
            header_row=payload.header_row,
            overrides=payload.mapping,
            dept_id=current.dept_id if current else None,
        )
    except service.ServiceError as exc:
        raise handle(exc) from exc


@router.post("/imports/{batch_id}/validate")
def validate_import(
    batch_id: int,
    current: Optional[Who] = Depends(identity),
    x_actor: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_perm(current, "import:batch:validate")
    try:
        return service.validate_batch(
            batch_id,
            resolve_actor(current, x_actor),
            dept_id=current.dept_id if current else None,
        )
    except service.ServiceError as exc:
        raise handle(exc) from exc


@router.post("/imports/{batch_id}/commit")
def commit_import(
    batch_id: int,
    current: Optional[Who] = Depends(identity),
    x_actor: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_perm(current, "import:batch:commit")
    try:
        scope = scope_colleges(current)
        return service.commit_batch(
            batch_id,
            resolve_actor(current, x_actor),
            dept_id=current.dept_id if current else None,
            allowed_colleges=set(scope) if scope is not None else None,
        )
    except service.ServiceError as exc:
        raise handle(exc) from exc
    except DatabaseError as exc:
        reason = getattr(getattr(exc, "diag", None), "message_primary", None) or str(exc)
        raise HTTPException(status_code=500, detail=f"提交失败，已整体回滚：{reason}") from exc


@router.get("/imports/{batch_id}")
def get_import(
    batch_id: int,
    current: Optional[Who] = Depends(identity),
) -> Dict[str, Any]:
    require_perm(current, "import:batch:detail")
    try:
        return service.get_batch(batch_id, dept_id=current.dept_id if current else None)
    except service.ServiceError as exc:
        raise handle(exc) from exc


@router.get("/imports")
def list_imports(
    current: Optional[Who] = Depends(identity),
    limit: int = 50,
) -> List[Dict[str, Any]]:
    require_perm(current, "import:batch:list")
    return service.list_batches(limit, dept_id=current.dept_id if current else None)
