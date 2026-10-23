"""聚合与筛选接口：认证 + student:list + SQL 层学院过滤。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from .. import queries
from ..internal_auth import Who, identity, require_perm, scope_colleges

router = APIRouter()


@router.get("/meta/filters")
def get_filters(current: Optional[Who] = Depends(identity)) -> Dict[str, Any]:
    require_perm(current, "student:list")
    return queries.get_filters(colleges=scope_colleges(current))


@router.get("/stats/overview")
def get_overview(current: Optional[Who] = Depends(identity)) -> Dict[str, Any]:
    require_perm(current, "student:list")
    return queries.get_overview(colleges=scope_colleges(current))


@router.get("/meta/data-quality")
def get_data_quality(current: Optional[Who] = Depends(identity)) -> Dict[str, Any]:
    """数据质量看板（命中教务#5/#6/#9 数据核对痛点）。"""
    require_perm(current, "student:list")
    return queries.get_data_quality(colleges=scope_colleges(current))
