"""只读查询与学生更新：全部参数化，范围过滤在 SQL 层强制。

设计约束：
1. 不新建数据库账号，复用 campus_app。
2. 分页上限 200。
3. 非管理员的范围由调用方传入 colleges/forced_college；None 表示全范围。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .db import pool
from .service import ServiceError

MAX_PAGE_SIZE = 200

# 与 sql/001_schema.sql 的 students_status_enum 保持一致
STUDENT_STATUS_VALUES = ("enrolled", "suspended", "withdrawn", "graduated", "other")
ALLOWED_STUDENT_UPDATE_FIELDS = (
    "student_name",
    "class_name",
    "major_name",
    "enrollment_year",
    "student_status",
)


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
    forced_college: Optional[str] = None,
) -> Dict[str, Any]:
    page, page_size = _clamp_page(page, page_size)

    where: List[str] = []
    params: List[Any] = []

    if not include_inactive:
        where.append("is_active")
    if forced_college:
        where.append("college_name = %s")
        params.append(forced_college)
    if college:
        # 与授权范围取交集：越界筛选返回空集，而不是扩大范围
        where.append("college_name = %s")
        params.append(college)
    if keyword:
        where.append("(student_no ILIKE %s OR student_name ILIKE %s)")
        like = f"%{keyword.strip()}%"
        params.extend([like, like])
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
                "SELECT count(*) AS total FROM campus.student_changes WHERE student_id = %s",
                (student["id"],),
            )
            change_total = cur.fetchone()["total"]

    return {**student, "changes": changes, "change_total": change_total}


def update_student(
    student_no: str,
    fields: Dict[str, Any],
    actor_user: str,
    forced_college: str = "",
) -> Dict[str, Any]:
    """按白名单更新学生；范围在 WHERE 中强制，审计操作人来自可信身份。"""
    unknown = sorted(set(fields) - set(ALLOWED_STUDENT_UPDATE_FIELDS))
    if unknown:
        raise ServiceError(f"不允许修改的字段：{', '.join(unknown)}", 422)

    if "student_status" in fields and fields["student_status"] not in STUDENT_STATUS_VALUES:
        raise ServiceError(
            f"student_status 非法：{fields['student_status']}，可选 {', '.join(STUDENT_STATUS_VALUES)}",
            422,
        )
    if "enrollment_year" in fields and fields["enrollment_year"] is not None:
        year = int(fields["enrollment_year"])
        if not 1990 <= year <= 2100:
            raise ServiceError("enrollment_year 必须在 1990..2100", 422)

    columns = ", ".join(f"{name} = %s" for name in fields)
    params: List[Any] = list(fields.values())
    where = "student_no = %s"
    params.append(student_no)
    if forced_college:
        where += " AND college_name = %s"
        params.append(forced_college)

    with pool.connection() as conn:
        with conn.cursor() as cur:
            # 审计触发器从会话变量取操作人，必须与 DML 同事务
            cur.execute("SELECT set_config('campus.actor_user_id', %s, true)", (actor_user[:150],))
            cur.execute(
                f"""
                UPDATE campus.students
                   SET {columns}
                 WHERE {where}
             RETURNING id, student_no, student_name, college_name, major_name,
                       class_name, enrollment_year, student_status, updated_at
                """,
                params,
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT college_name FROM campus.students WHERE student_no = %s",
                    (student_no,),
                )
                exists = cur.fetchone()
                if exists is None:
                    raise ServiceError(f"学生不存在：{student_no}", 404)
                raise ServiceError("越权：不能修改其他学院的学生", 403)

    return {"student": row, "changed_fields": sorted(fields)}


def get_overview(colleges: Optional[List[str]] = None) -> Dict[str, Any]:
    """首页总览。colleges=None 表示全范围（管理员）；否则 SQL 层按学院过滤。

    非管理员不返回批次相关字段：批次范围保护在 PR-C 落地，当前不适合暴露。
    """
    college_scope = colleges if colleges else None
    scope = (college_scope, college_scope)

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FILTER (WHERE is_active) AS students_active,
                       count(*) AS students_total
                  FROM campus.students
                 WHERE (%s::text[] IS NULL OR college_name = ANY(%s::text[]))
                """,
                scope,
            )
            student_row = cur.fetchone()

            cur.execute(
                """
                SELECT count(*) AS changes_total,
                       count(*) FILTER (WHERE c.record_status = 'pending_review') AS pending_review
                  FROM campus.student_changes c
                  JOIN campus.students s ON s.id = c.student_id
                 WHERE c.is_active
                   AND (%s::text[] IS NULL OR s.college_name = ANY(%s::text[]))
                """,
                scope,
            )
            change_row = cur.fetchone()

            if college_scope is None:
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
                    SELECT id, batch_code, source_filename, target_type, batch_status,
                           total_rows, valid_rows, invalid_rows, created_at
                      FROM campus.import_batches
                     ORDER BY created_at DESC LIMIT 5
                    """
                )
                recent_batches = cur.fetchall()
            else:
                # 非管理员：不暴露任何批次信息
                batch_row = {"batches_total": 0, "imported_batches": 0, "last_import_at": None}
                open_errors = 0
                recent_batches = []

            cur.execute(
                """
                SELECT student_status, count(*) AS cnt
                  FROM campus.students
                 WHERE is_active
                   AND (%s::text[] IS NULL OR college_name = ANY(%s::text[]))
                 GROUP BY student_status
                """,
                scope,
            )
            status_counts = {row["student_status"]: row["cnt"] for row in cur.fetchall()}

            cur.execute(
                """
                SELECT c.change_type, count(*) AS cnt
                  FROM campus.student_changes c
                  JOIN campus.students s ON s.id = c.student_id
                 WHERE c.is_active
                   AND (%s::text[] IS NULL OR s.college_name = ANY(%s::text[]))
                 GROUP BY c.change_type ORDER BY cnt DESC
                """,
                scope,
            )
            change_type_counts = cur.fetchall()

            cur.execute(
                """
                SELECT to_char(c.effective_date, 'YYYY-MM') AS month, count(*) AS cnt
                  FROM campus.student_changes c
                  JOIN campus.students s ON s.id = c.student_id
                 WHERE c.is_active AND c.effective_date >= (CURRENT_DATE - INTERVAL '5 months')
                   AND (%s::text[] IS NULL OR s.college_name = ANY(%s::text[]))
                 GROUP BY 1 ORDER BY 1
                """,
                scope,
            )
            monthly = cur.fetchall()

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


def get_filters(colleges: Optional[List[str]] = None) -> Dict[str, Any]:
    """筛选项。colleges=None 为全范围；否则只返回授权学院内的选项。"""
    college_scope = colleges if colleges else None
    scope = (college_scope, college_scope)

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT college_name FROM campus.students
                 WHERE is_active AND college_name IS NOT NULL
                   AND (%s::text[] IS NULL OR college_name = ANY(%s::text[]))
                 GROUP BY college_name ORDER BY college_name
                """,
                scope,
            )
            college_list = [r["college_name"] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT class_name FROM campus.students
                 WHERE is_active AND class_name IS NOT NULL
                   AND (%s::text[] IS NULL OR college_name = ANY(%s::text[]))
                 GROUP BY class_name ORDER BY class_name
                """,
                scope,
            )
            classes = [r["class_name"] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT student_status, count(*) AS cnt
                  FROM campus.students
                 WHERE is_active
                   AND (%s::text[] IS NULL OR college_name = ANY(%s::text[]))
                 GROUP BY student_status
                """,
                scope,
            )
            status_counts = {r["student_status"]: r["cnt"] for r in cur.fetchall()}

            cur.execute(
                """
                SELECT count(*) AS total FROM campus.students
                 WHERE is_active
                   AND (%s::text[] IS NULL OR college_name = ANY(%s::text[]))
                """,
                scope,
            )
            total_active = cur.fetchone()["total"]

            cur.execute(
                """
                SELECT count(*) AS total
                  FROM campus.student_changes c
                  JOIN campus.students s ON s.id = c.student_id
                 WHERE c.is_active
                   AND (%s::text[] IS NULL OR s.college_name = ANY(%s::text[]))
                """,
                scope,
            )
            change_total = cur.fetchone()["total"]

    return {
        "colleges": college_list,
        "classes": classes,
        "status_counts": status_counts,
        "total_active": total_active,
        "change_total": change_total,
    }
