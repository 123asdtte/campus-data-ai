"""AI 校园助手只读原型（FastAPI）。

安全模型（详见 docs/AI-ASSISTANT-POC.md）：
  1. 身份：X-AI-Token（POC 共享口令）+ X-AI-User；角色与学院从数据库读取；
  2. 权限：服务端按角色与学院收口，客户端无法通过参数越权；
  3. 数据：只连隔离 POC 库，读账号只有 SELECT；返回前对姓名/联系方式脱敏；
  4. 审计：每次请求（含拒绝/未知意图）写 ai.audit；审计失败则拒绝返回数据；
  5. 规划：默认规则 planner，不访问外网；可选 LLM 只发送问题与意图模式。
"""
from __future__ import annotations

import hmac
from typing import Any, NoReturn

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import planner, queries
from .audit import AuditError, write_audit
from .config import SETTINGS
from .db import read_cursor
from .policy import Forbidden, check_intent, load_user, resolve_scope

app = FastAPI(title="AI 校园助手（只读 POC）", version="0.1.0")

COLLEGE_NAMES = {"CS": "计算机学院", "EE": "电子信息学院", "FL": "外国语学院"}


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def _deny_unauthenticated(username: str | None, reason: str) -> NoReturn:
    """认证失败也要留痕（含尝试的用户名），审计失败则 fail-closed。"""
    try:
        write_audit(
            requester=(username or "unknown")[:64],
            role="unknown",
            college=None,
            question="（认证失败）",
            intent="auth",
            status="denied",
            detail={"reason": reason},
        )
    except AuditError as exc:
        raise HTTPException(status_code=503, detail="审计不可用，已拒绝请求") from exc
    raise HTTPException(status_code=401, detail=reason)


def authenticate(
    x_ai_user: str | None = Header(default=None, alias="X-AI-User"),
    x_ai_token: str | None = Header(default=None, alias="X-AI-Token"),
) -> dict[str, Any]:
    if not SETTINGS.poc_token or not x_ai_token:
        _deny_unauthenticated(x_ai_user, "缺少访问口令")
    if not hmac.compare_digest(x_ai_token, SETTINGS.poc_token):
        _deny_unauthenticated(x_ai_user, "访问口令无效")
    if not x_ai_user:
        _deny_unauthenticated(None, "缺少用户标识")
    with read_cursor() as cur:
        user = load_user(cur, x_ai_user)
    if user is None:
        _deny_unauthenticated(x_ai_user, "未知用户")
    return user


def _scope_label(scope: str | None) -> str:
    return COLLEGE_NAMES.get(scope, "全部学院") if scope else "全部学院"


def _answer(plan: planner.Plan, data: dict[str, Any], scope: str | None) -> str:
    label = _scope_label(scope)
    if plan.intent == "student_count":
        status = plan.args.get("status")
        suffix = f"（状态：{status}）" if status else ""
        return f"{label}共有 {data['count']} 名学生{suffix}。"
    if plan.intent == "inactive_students":
        if not data["counts"]:
            return f"{label}当前没有休学或退学的学生。"
        parts = "、".join(f"{row['status']} {row['count']} 人" for row in data["counts"])
        return f"{label}非在校学生共 {data['total']} 人：{parts}。"
    if plan.intent == "student_search":
        if not data["rows"]:
            return f"在{label}没有找到匹配“{plan.args.get('keyword', '')}”的学生。"
        return (
            f"在{label}找到 {data['count']} 名匹配学生（最多返回 {data['limit']} 条，"
            "姓名已脱敏，不返回联系方式）。"
        )
    if plan.intent == "import_summary":
        failed = sum(1 for b in data["batches"] if b["status"] == "failed")
        issue = data["issues"][0]["issue_code"] if data["issues"] else "无"
        return (
            f"{label}最近 {len(data['batches'])} 个导入批次中 {failed} 个失败；"
            f"累计异常最多的是 {issue}。"
        )
    if plan.intent == "data_quality":
        return (
            f"{label}共 {data['total']} 名学生，缺手机号 {data['missing_phone']} 人，"
            f"缺邮箱 {data['missing_email']} 人。"
        )
    return (
        "我可以回答：某学院学生人数、休学/退学人数、导入批次与异常分布、"
        "数据完整性问题，以及按学号/姓名检索（教师角色）。请补充学院或关键词。"
    )


def _execute(plan: planner.Plan, scope: str | None) -> tuple[dict[str, Any], int]:
    with read_cursor() as cur:
        if plan.intent == "student_count":
            return queries.count_students(cur, scope, plan.args.get("status")), 1
        if plan.intent == "inactive_students":
            data = queries.count_inactive(cur, scope)
            return data, len(data["counts"])
        if plan.intent == "student_search":
            data = queries.search_students(
                cur, scope, str(plan.args.get("keyword", "")), SETTINGS.max_rows
            )
            return data, data["count"]
        if plan.intent == "data_quality":
            return queries.data_quality(cur, scope), 1
        if plan.intent == "import_summary":
            data = queries.import_summary(cur, scope)
            return data, len(data["batches"])
        return {}, 0


@app.get("/healthz")
def healthz() -> dict[str, str]:
    try:
        with read_cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="数据库不可用") from exc
    return {"status": "ok"}


@app.post("/query")
def query(
    body: QueryRequest,
    user: dict[str, Any] = Depends(authenticate),
) -> dict[str, Any]:
    question = body.question.strip()
    plan = planner.plan(question)
    # help 且带 note = 无法识别；其余（含主动求助）记为 ok
    if plan.intent == "help":
        status = "unknown" if plan.note else "ok"
    else:
        status = "ok"
    scope: str | None = None

    try:
        check_intent(user, plan.intent)
        if plan.intent != "help":
            scope = resolve_scope(user, plan.args.get("college"))
            data, row_count = _execute(plan, scope)
        else:
            data, row_count = {}, 0
    except Forbidden as exc:
        try:
            write_audit(
                requester=user["username"],
                role=user["role"],
                college=user["college_code"],
                question=question,
                intent=plan.intent,
                status="denied",
                detail={
                    "reason": "policy_denied",
                    "requested_college": plan.args.get("college"),
                },
            )
        except AuditError as audit_exc:
            raise HTTPException(status_code=503, detail="审计不可用，已拒绝返回数据") from audit_exc
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        try:
            write_audit(
                requester=user["username"],
                role=user["role"],
                college=user["college_code"],
                question=question,
                intent=plan.intent,
                status="error",
                detail={"error": type(exc).__name__},
            )
        except AuditError as audit_exc:
            # 错误请求同样必须留痕；审计不可用时 fail-closed
            raise HTTPException(status_code=503, detail="审计不可用，已拒绝返回数据") from audit_exc
        raise HTTPException(status_code=500, detail="查询执行失败") from exc

    try:
        write_audit(
            requester=user["username"],
            role=user["role"],
            college=user["college_code"],
            question=question,
            intent=plan.intent,
            status=status,
            row_count=row_count,
            detail={"scope": scope, "source": plan.source},
        )
    except AuditError as exc:
        # 审计写不进去时不返回任何业务数据（fail-closed）
        raise HTTPException(status_code=503, detail="审计不可用，已拒绝返回数据") from exc

    return {
        "answer": _answer(plan, data, scope),
        "intent": plan.intent,
        "data": data,
        "meta": {
            "requester": user["username"],
            "role": user["role"],
            "scope": scope or "all",
            "planner": plan.source,
            "row_count": row_count,
        },
    }
