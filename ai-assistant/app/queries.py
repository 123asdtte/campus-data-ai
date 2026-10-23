"""固定查询模板。

原则：
  - 不使用自由 SQL / 字符串拼接值；所有参数走占位符；
  - 每条查询都接受 scope（None=全部学院，仅 admin 可获得）；
  - 检索类查询强制 LIMIT，且不返回手机号/邮箱原文。
"""
from __future__ import annotations

from typing import Any

import psycopg

MAX_SEARCH_ROWS = 20


def _mask_name(name: str) -> str:
    if not name:
        return ""
    if len(name) == 1:
        return "*"
    return name[0] + "*" * (len(name) - 1)


def _scope_sql(scope: str | None, column: str = "college_code") -> tuple[str, list[Any]]:
    if scope is None:
        return "", []
    return f" AND {column} = %s", [scope]


def _escape_like(value: str) -> str:
    """转义 LIKE/ILIKE 通配符，避免用户输入 % / _ 扩大匹配范围。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def count_students(cur: psycopg.Cursor, scope: str | None, status: str | None) -> dict[str, Any]:
    where, params = _scope_sql(scope)
    sql = "SELECT count(*) AS total FROM ai.students WHERE 1=1" + where
    if status:
        sql += " AND status = %s"
        params.append(status)
    cur.execute(sql, params)
    return {"count": int(cur.fetchone()["total"]), "status": status}


def count_inactive(cur: psycopg.Cursor, scope: str | None) -> dict[str, Any]:
    where, params = _scope_sql(scope)
    cur.execute(
        "SELECT status, count(*) AS total FROM ai.students WHERE status <> '在校'"
        + where
        + " GROUP BY status ORDER BY status",
        params,
    )
    rows = [{"status": row["status"], "count": int(row["total"])} for row in cur.fetchall()]
    return {"counts": rows, "total": sum(row["count"] for row in rows)}


def search_students(
    cur: psycopg.Cursor, scope: str | None, keyword: str, limit: int
) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_SEARCH_ROWS))
    where, params = _scope_sql(scope)
    pattern = "%" + _escape_like(keyword) + "%"
    cur.execute(
        "SELECT student_no, name, college_code, major, class_name, status "
        "FROM ai.students WHERE (student_no ILIKE %s ESCAPE '\\' OR name ILIKE %s ESCAPE '\\')"
        + where
        + " ORDER BY student_no LIMIT %s",
        [pattern, pattern] + params + [limit],
    )
    rows = [
        {
            "student_no": row["student_no"],
            "name": _mask_name(row["name"]),
            "college_code": row["college_code"],
            "major": row["major"],
            "class_name": row["class_name"],
            "status": row["status"],
        }
        for row in cur.fetchall()
    ]
    return {"rows": rows, "count": len(rows), "limit": limit}


def data_quality(cur: psycopg.Cursor, scope: str | None) -> dict[str, Any]:
    where, params = _scope_sql(scope)
    cur.execute(
        "SELECT count(*) AS total, "
        "count(*) FILTER (WHERE phone IS NULL OR btrim(phone) = '') AS missing_phone, "
        "count(*) FILTER (WHERE email IS NULL OR btrim(email) = '') AS missing_email "
        "FROM ai.students WHERE 1=1" + where,
        params,
    )
    row = cur.fetchone()
    return {
        "total": int(row["total"]),
        "missing_phone": int(row["missing_phone"]),
        "missing_email": int(row["missing_email"]),
    }


def import_summary(cur: psycopg.Cursor, scope: str | None, limit: int = 5) -> dict[str, Any]:
    limit = max(1, min(limit, 20))
    where, params = _scope_sql(scope)
    cur.execute(
        "SELECT batch_code, status, total_rows, valid_rows, invalid_rows, created_at "
        "FROM ai.import_batches WHERE 1=1"
        + where
        + " ORDER BY created_at DESC LIMIT %s",
        params + [limit],
    )
    batches = [
        {
            "batch_code": row["batch_code"],
            "status": row["status"],
            "total_rows": row["total_rows"],
            "valid_rows": row["valid_rows"],
            "invalid_rows": row["invalid_rows"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in cur.fetchall()
    ]

    # 异常统计也必须按学院收口：显式指定带表别名的列，避免字符串替换失效
    issue_where, issue_params = _scope_sql(scope, "b.college_code")
    cur.execute(
        "SELECT i.issue_code, sum(i.count) AS total FROM ai.import_issues i "
        "JOIN ai.import_batches b ON b.id = i.batch_id WHERE 1=1"
        + issue_where
        + " GROUP BY i.issue_code ORDER BY total DESC",
        issue_params,
    )
    issues = [{"issue_code": row["issue_code"], "count": int(row["total"])} for row in cur.fetchall()]
    return {"batches": batches, "issues": issues}
