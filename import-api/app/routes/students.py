"""学生接口：只读两条常驻；写接口仅在认证开启时注册。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from .. import queries, service
from ..internal_auth import Who, identity, require_college, require_perm, resolve_actor
from ._shared import handle

router = APIRouter()
write_router = APIRouter()


class StudentUpdate(BaseModel):
    """学生可修改字段白名单（未传的字段不参与更新）。"""

    student_name: Optional[str] = None
    class_name: Optional[str] = None
    major_name: Optional[str] = None
    enrollment_year: Optional[int] = None
    student_status: Optional[str] = None


@router.get("/students")
def list_students(
    current: Optional[Who] = Depends(identity),
    keyword: Optional[str] = Query(default=None, max_length=100, description="学号或姓名模糊匹配"),
    college: Optional[str] = Query(default=None, max_length=100),
    class_name: Optional[str] = Query(default=None, max_length=100),
    status: Optional[str] = Query(default=None, max_length=20),
    include_inactive: bool = Query(default=False, description="是否包含已停用记录"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> Dict[str, Any]:
    require_perm(current, "student:list")
    forced = require_college(current)
    return queries.list_students(
        keyword=keyword,
        college=college,            # 客户端筛选与授权范围在 SQL 层取交集
        forced_college=forced or None,
        class_name=class_name,
        status=status,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )


@router.get("/students/{student_no}")
def get_student(
    student_no: str,
    current: Optional[Who] = Depends(identity),
) -> Dict[str, Any]:
    require_perm(current, "student:list")
    forced = require_college(current)
    try:
        student = queries.get_student(student_no)
    except service.ServiceError as exc:
        raise handle(exc) from exc
    if forced and student.get("college_name") != forced:
        raise HTTPException(status_code=403, detail="越权：不能查看其他学院的学生")
    return student


@write_router.put("/students/{student_no}")
def update_student(
    student_no: str,
    payload: StudentUpdate,
    current: Optional[Who] = Depends(identity),
    x_actor: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_perm(current, "student:write")
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="没有可修改的字段")
    try:
        return queries.update_student(
            student_no,
            fields,
            resolve_actor(current, x_actor),
            forced_college=require_college(current),
        )
    except service.ServiceError as exc:
        raise handle(exc) from exc
