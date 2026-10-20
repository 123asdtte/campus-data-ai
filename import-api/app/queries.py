"""只读查询：学生列表、学生详情、筛选项。

设计约束：
1. 全部参数化查询，不做字符串拼接。
2. 不新建数据库账号，复用 campus_app（已有 SELECT 权限）。
3. 分页上限 200，避免一次拉全表。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .db import pool
from .service import ServiceError

MAX_PAGE_SIZE = 200


def _clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    return page, page_size


def list_students(
    keyword: Optional[str] = None,
    college: Optional[str] = None,
    class_name: Optional[str] = None,
    status: Optional[str] = None,
    include_inactive: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    page, page_size = _clamp_page(page, page_size)

    where: List[str] = []
    params: List[Any] = []

    if not include_inactive:
        where.append("is_active")
    if keyword:
        where.append("(student_no ILIKE %s OR student_name ILIKE %s)")
        like = f"%{keyword.strip()}%"
        params.extend([like, like])
    if college:
        where.append("college_name = %s")
        params.append(college)
    if class_name:
        where.append("class_name = %s")
        params.append(class_name)
    if status:
        where.append("student_status = %s")
        params.append(status)

    clause = f"WHERE {' AND '.join(where)}" if where else ""

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS total FROM campus.students {clause}", params)
            total = cur.fetchone()["total"]

            cur.execute(
                f"""
                SELECT id, student_no, student_name, college_name, major_name,
                       class_name, enrollment_year, student_status, is_active,
                       created_at, updated_at
                  FROM campus.students
                  {clause}
                 ORDER BY student_no
                 LIMIT %s OFFSET %s
                """,
                [*params, page_size, (page - 1) * page_size],
            )
            items = cur.fetchall()

    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_student(student_no: str) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, student_no, student_name, college_name, major_name,
                       class_name, enrollment_year, student_status, is_active,
                       created_at, updated_at
                  FROM campus.students
                 WHERE student_no = %s
                """,
                (student_no,),
            )
            student = cur.fetchone()
            if student is None:
                raise ServiceError(f"学生不存在：{student_no}", 404)

            cur.execute(
                """
                SELECT c.id, c.change_type, c.effective_date, c.change_reason,
                       c.record_status, c.source_batch_id, c.source_row_number,
                       c.created_at
                  FROM campus.student_changes c
                 WHERE c.student_id = %s
                 ORDER BY c.effective_date DESC, c.id DESC
                 LIMIT 20
                """,
                (student["id"],),
            )
            changes = cur.fetchall()

            cur.execute(
                """
                SELECT count(*) AS total FROM campus.student_changes WHERE student_id = %s
                """,
                (student["id"],),
            )
            change_total = cur.fetchone()["total"]

    return {**student, "changes": changes, "change_total": change_total}


def get_overview() -> Dict[str, Any]:
    """首页总览：一次性取回概览数字、分布、趋势与最近批次。"""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FILTER (WHERE is_active) AS students_active,
                       count(*) AS students_total
                  FROM campus.students
                """
            )
            student_row = cur.fetchone()

            cur.execute(
                """
                SELECT count(*) AS changes_total,
                       count(*) FILTER (WHERE record_status = 'pending_review') AS pending_review
                  FROM campus.student_changes WHERE is_active
                """
            )
            change_row = cur.fetchone()

            cur.execute(
                """
                SELECT count(*) AS batches_total,
                       count(*) FILTER (WHERE batch_status = 'imported') AS imported_batches,
                       max(created_at) AS last_import_at
                  FROM campus.import_batches
                """
            )
            batch_row = cur.fetchone()

            cur.execute(
                """
                SELECT count(*) AS open_errors
                  FROM campus.import_issues
                 WHERE issue_status = 'open' AND severity = 'error'
                """
            )
            open_errors = cur.fetchone()["open_errors"]

            cur.execute(
                """
                SELECT student_status, count(*) AS cnt
                  FROM campus.students WHERE is_active
                 GROUP BY student_status
                """
            )
            status_counts = {row["student_status"]: row["cnt"] for row in cur.fetchall()}

            cur.execute(
                """
                SELECT change_type, count(*) AS cnt
                  FROM campus.student_changes WHERE is_active
                 GROUP BY change_type ORDER BY cnt DESC
                """
            )
            change_type_counts = cur.fetchall()

            cur.execute(
                """
                SELECT to_char(effective_date, 'YYYY-MM') AS month, count(*) AS cnt
                  FROM campus.student_changes
                 WHERE is_active AND effective_date >= (CURRENT_DATE - INTERVAL '5 months')
                 GROUP BY 1 ORDER BY 1
                """
            )
            monthly = cur.fetchall()

            cur.execute(
                """
                SELECT id, batch_code, source_filename, target_type, batch_status,
                       total_rows, valid_rows, invalid_rows, created_at
                  FROM campus.import_batches
                 ORDER BY created_at DESC LIMIT 5
                """
            )
            recent_batches = cur.fetchall()

    return {
        "students_active": student_row["students_active"],
        "students_total": student_row["students_total"],
        "changes_total": change_row["changes_total"],
        "pending_review": change_row["pending_review"],
        "batches_total": batch_row["batches_total"],
        "imported_batches": batch_row["imported_batches"],
        "last_import_at": batch_row["last_import_at"],
        "open_errors": open_errors,
        "status_counts": status_counts,
        "change_type_counts": change_type_counts,
        "monthly": monthly,
        "recent_batches": recent_batches,
    }


def get_filters() -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT college_name FROM campus.students
                 WHERE is_active AND college_name IS NOT NULL
                 GROUP BY college_name ORDER BY college_name
                """
            )
            colleges = [r["college_name"] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT class_name FROM campus.students
                 WHERE is_active AND class_name IS NOT NULL
                 GROUP BY class_name ORDER BY class_name
                """
            )
            classes = [r["class_name"] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT student_status, count(*) AS cnt
                  FROM campus.students WHERE is_active
                 GROUP BY student_status
                """
            )
            status_counts = {r["student_status"]: r["cnt"] for r in cur.fetchall()}

            cur.execute("SELECT count(*) AS total FROM campus.students WHERE is_active")
            total_active = cur.fetchone()["total"]

            cur.execute("SELECT count(*) AS total FROM campus.student_changes WHERE is_active")
            change_total = cur.fetchone()["total"]

    return {
        "colleges": colleges,
        "classes": classes,
        "status_counts": status_counts,
        "total_active": total_active,
        "change_total": change_total,
    }
