"""审计写入：每次请求（含拒绝）都必须留痕。

失败策略：审计写不进去时，请求整体失败（fail-closed），不返回数据。
"""
from __future__ import annotations

import json
from typing import Any

from .db import audit_connection


class AuditError(RuntimeError):
    """审计写入失败。"""


def write_audit(
    *,
    requester: str,
    role: str,
    college: str | None,
    question: str,
    intent: str,
    status: str,
    row_count: int = 0,
    detail: dict[str, Any] | None = None,
) -> None:
    try:
        with audit_connection() as cur:
            cur.execute(
                "INSERT INTO ai.audit "
                "(requester, role, college, question, intent, status, row_count, detail) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                (
                    requester[:64],
                    role[:32],
                    college,
                    (question or "")[:500],
                    intent[:32],
                    status[:16],
                    row_count,
                    json.dumps(detail or {}, ensure_ascii=False),
                ),
            )
    except Exception as exc:  # noqa: BLE001 - 审计失败必须显式上抛
        raise AuditError("审计写入失败") from exc
