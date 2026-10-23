"""身份与权限：所有范围均由服务端从数据库读取，绝不信任请求体。

角色约定（POC）：
  - admin           ：可查全部学院，可用全部意图；
  - college_viewer  ：仅本学院，可做聚合与按学号/姓名检索；
  - readonly        ：仅本学院，只允许聚合类问题，不允许检索个人。
"""
from __future__ import annotations

from typing import Any

import psycopg


class Forbidden(Exception):
    """越权访问。"""


AGGREGATE_INTENTS = {"student_count", "inactive_students", "import_summary", "data_quality"}
SEARCH_INTENTS = {"student_search"}

ROLE_INTENTS = {
    "admin": AGGREGATE_INTENTS | SEARCH_INTENTS,
    "college_viewer": AGGREGATE_INTENTS | SEARCH_INTENTS,
    "readonly": AGGREGATE_INTENTS,
}


def load_user(cur: psycopg.Cursor, username: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT username, display_name, role, college_code FROM ai.users WHERE username = %s",
        (username,),
    )
    return cur.fetchone()


def resolve_scope(user: dict[str, Any], requested_college: str | None) -> str | None:
    """返回生效的学院范围；None 表示全部学院（仅 admin 可获得）。

    - 非 admin 请求其他学院 → 403；
    - 非 admin 未指定学院 → 自动限制到本学院；
    - admin 指定则按指定，未指定则全部。
    """
    role = user["role"]
    own = user["college_code"]
    if role == "admin":
        return requested_college
    if requested_college and requested_college != own:
        raise Forbidden("无权访问其他学院的数据")
    return own


def check_intent(user: dict[str, Any], intent: str) -> None:
    if intent == "help":
        return  # 帮助信息对所有角色开放
    allowed = ROLE_INTENTS.get(user["role"], set())
    if intent not in allowed:
        raise Forbidden(f"角色 {user['role']} 不允许执行 {intent}")
