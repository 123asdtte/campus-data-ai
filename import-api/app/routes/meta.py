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
