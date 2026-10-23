"""全局操作审计：管理员视角查看全校所有字段级编辑留痕。"""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query

from .. import queries, service
from ..internal_auth import Who, identity, require_college, require_perm
from ._shared import handle

router = APIRouter()


@router.get("/audit-logs")
def list_audit_logs(
    current: Optional[Who] = Depends(identity),
    keyword: Optional[str] = Query(default=None, max_length=100, description="学号或姓名模糊匹配"),
    actor: Optional[str] = Query(default=None, max_length=150, description="操作人"),
    action: Optional[str] = Query(default=None, max_length=20, description="insert/update/delete"),
    from_date: Optional[str] = Query(default=None, description="起始时间 ISO，含"),
    until_date: Optional[str] = Query(default=None, description="截止时间 ISO，不含"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> Dict:
    """全库操作日志；学生类对象关联出学号与姓名便于定位。"""
    require_perm(current, "student:list")
    try:
        return queries.list_audit_logs(
            keyword=keyword,
            actor=actor,
            action=action,
            from_date=from_date,
            until_date=until_date,
            page=page,
            page_size=page_size,
            forced_college=require_college(current),
        )
    except service.ServiceError as exc:  # noqa: BLE001
        raise handle(exc) from exc


@router.get("/audit-logs/summary")
def audit_summary(
    current: Optional[Who] = Depends(identity),
    from_date: Optional[str] = Query(default=None, description="起始时间 ISO，含"),
    until_date: Optional[str] = Query(default=None, description="截止时间 ISO，不含"),
    limit: int = Query(default=20, ge=1, le=100),
) -> Dict:
    """按操作人维度的增改删统计（管理员监督视角）。"""
    require_perm(current, "student:list")
    try:
        return queries.get_audit_summary(
            forced_college=require_college(current),
            from_date=from_date,
            until_date=until_date,
            limit=limit,
        )
    except service.ServiceError as exc:  # noqa: BLE001
        raise handle(exc) from exc
