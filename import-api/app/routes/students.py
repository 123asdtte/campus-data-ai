"""学生接口：只读两条常驻；写接口仅在认证开启时注册。"""
from __future__ import annotations

import datetime
from io import BytesIO
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
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


@router.get("/students/export")
def export_students(
    current: Optional[Who] = Depends(identity),
    fields: Optional[str] = Query(default=None, description="逗号分隔的导出字段，缺省导出核心字段"),
    keyword: Optional[str] = Query(default=None, max_length=100),
    college: Optional[str] = Query(default=None, max_length=100, description="仅导出该学院（split_by_college 时忽略）"),
    class_name: Optional[str] = Query(default=None, max_length=100),
    status: Optional[str] = Query(default=None, max_length=20),
    include_inactive: bool = Query(default=False),
    split_by_college: bool = Query(default=False, description="true 时每个学院单独一个工作表"),
) -> StreamingResponse:
    """按需字段导出为 Excel（命中教务#17 / 学工(二) 表头不统一痛点）。

    支持两种形态：
      - 单表：直接返回一张「学生信息」表（可按 college 过滤）；
      - 按学院拆分：split_by_college=true 时，每个学院一个工作表，便于分部门下发。

    必须注册在 /students/{student_no} 之前，否则会被参数路由抢占而 404。
    """
    require_perm(current, "student:list")
    forced = require_college(current)
    field_list = fields.split(",") if fields else list(queries.EXPORT_DEFAULT_FIELDS)
    base_kwargs = dict(
        keyword=keyword,
        class_name=class_name,
        status=status,
        include_inactive=include_inactive,
        forced_college=forced or None,
    )

    def _style_sheet(ws, fields_used):
        headers = [queries.EXPORT_FIELD_LABELS.get(f, f) for f in fields_used]
        ws.append(headers)
        header_fill = PatternFill("solid", fgColor="1F6FEB")
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for col in ws.columns:
            width = 10
            for cell in col:
                val = "" if cell.value is None else str(cell.value)
                length = sum(2 if ord(ch) > 0x2E80 else 1 for ch in val)
                width = max(width, min(length + 2, 40))
            ws.column_dimensions[col[0].column_letter].width = width

    wb = Workbook()
    wb.remove(wb.active)

    if split_by_college:
        colleges = queries.list_college_names(forced or None)
        if not colleges:
            colleges = ["（无学院数据）"]
        for c in colleges:
            data = queries.export_students(field_list, college=c, **base_kwargs)
            ws = wb.create_sheet(title=(c or "未分组")[:31])
            _style_sheet(ws, data["fields"])
            for row in data["rows"]:
                ws.append([row.get(f) if row.get(f) is not None else "" for f in data["fields"]])
    else:
        data = queries.export_students(field_list, college=college, **base_kwargs)
        ws = wb.create_sheet(title="学生信息")
        _style_sheet(ws, data["fields"])
        for row in data["rows"]:
            ws.append([row.get(f) if row.get(f) is not None else "" for f in data["fields"]])

    if not wb.sheetnames:
        wb.create_sheet(title="学生信息")

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"students_export_{stamp}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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


@router.get("/students/{student_no}/audit")
def get_student_audit(
    student_no: str,
    current: Optional[Who] = Depends(identity),
    limit: int = Query(default=30, ge=1, le=200),
) -> Dict[str, Any]:
    """字段级编辑审计（operation_logs）。与详情共用存在性/学院越权校验。"""
    require_perm(current, "student:list")
    forced = require_college(current)
    try:
        student = queries.get_student(student_no)
    except service.ServiceError as exc:
        raise handle(exc) from exc
    if forced and student.get("college_name") != forced:
        raise HTTPException(status_code=403, detail="越权：不能查看其他学院的学生")
    return queries.get_student_audit(student_no, limit=limit)


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
