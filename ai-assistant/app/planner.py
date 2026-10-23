"""问题 → 结构化意图。

两种 planner：
  - rule（默认）：确定性关键词/正则，不访问任何外部服务；
  - llm（可选）：调用 OpenAI 兼容接口，只发送“问题 + 意图模式”，
    绝不发送学生数据；返回的 JSON 必须通过白名单校验，否则退化为 rule。

无论哪种 planner，最终只能产出固定意图与受限参数；执行层不做自由 SQL。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .config import SETTINGS

INTENTS = {
    "student_count",
    "inactive_students",
    "student_search",
    "import_summary",
    "data_quality",
    "help",
}
ARGS_BY_INTENT = {
    "student_count": {"college", "status"},
    "inactive_students": {"college"},
    "student_search": {"college", "keyword"},
    "import_summary": {"college"},
    "data_quality": {"college"},
    "help": set(),
}

COLLEGE_ALIASES = {
    "计算机学院": "CS",
    "计算机": "CS",
    "电子信息学院": "EE",
    "电信学院": "EE",
    "电信": "EE",
    "外国语学院": "FL",
    "外语": "FL",
}

STOPWORDS = {"学生", "一下", "所有", "全部", "多少", "人数", "情况", "数据"}
# LLM 返回的 keyword 与规则 planner 使用同一字符集，避免通配符等意外输入
KEYWORD_RE = re.compile(r"^[A-Za-z0-9\u4e00-\u9fa5_-]{1,32}$")


@dataclass
class Plan:
    intent: str
    args: dict[str, Any] = field(default_factory=dict)
    source: str = "rule"
    note: str = ""


def _extract_college(question: str) -> str | None:
    for alias, code in COLLEGE_ALIASES.items():
        if alias in question:
            return code
    return None


def _extract_keyword(question: str) -> str | None:
    patterns = [
        r"(?:学号|姓名)\s*[:：]?\s*([A-Za-z0-9\u4e00-\u9fa5_-]{2,32})",
        r"(?:查|找|搜索)(?:一下|询)?\s*[:：]?\s*([A-Za-z0-9\u4e00-\u9fa5_-]{2,32})",
    ]
    for pattern in patterns:
        match = re.search(pattern, question)
        if not match:
            continue
        keyword = match.group(1).strip()
        if keyword and keyword not in STOPWORDS:
            return keyword
    return None


def rule_plan(question: str) -> Plan:
    q = (question or "").strip()
    if not q or any(word in q for word in ("帮助", "能做什么", "怎么用")):
        return Plan("help")

    college = _extract_college(q)

    if "导入" in q:
        return Plan("import_summary", {"college": college} if college else {})

    if any(word in q for word in ("缺", "手机号", "邮箱", "数据质量", "不完整")):
        return Plan("data_quality", {"college": college} if college else {})

    if any(word in q for word in ("休学", "退学", "停学", "不在校")):
        return Plan("inactive_students", {"college": college} if college else {})

    if "学号" in q or "姓名" in q or re.search(r"(?:查|找|搜索)", q):
        keyword = _extract_keyword(q)
        if keyword:
            args: dict[str, Any] = {"keyword": keyword}
            if college:
                args["college"] = college
            return Plan("student_search", args)

    if "多少" in q or "人数" in q or "统计" in q:
        args = {}
        if college:
            args["college"] = college
        for status in ("在校", "休学", "退学"):
            if status in q:
                args["status"] = status
                break
        return Plan("student_count", args)

    return Plan("help", note="未识别的问题")


def _llm_request(question: str) -> dict[str, Any]:
    system = (
        "你是校园数据助手的意图解析器。只输出 JSON，不要输出解释。\n"
        "允许的 intent：student_count、inactive_students、student_search、"
        "import_summary、data_quality、help。\n"
        "参数只能是：college（CS/EE/FL 或不填）、status（在校/休学/退学）、keyword（字符串）。\n"
        '输出格式：{"intent":"...","args":{...}}\n'
        "你只看到问题本身，不会看到任何学生数据；不要编造学号或姓名。"
    )
    body = {
        "model": SETTINGS.llm_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if SETTINGS.llm_api_key:
        headers["Authorization"] = "Bearer " + SETTINGS.llm_api_key
    req = urllib.request.Request(
        SETTINGS.llm_base_url + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=SETTINGS.llm_timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    return json.loads(content)


def _sanitize(raw: dict[str, Any]) -> Plan | None:
    intent = raw.get("intent")
    if intent not in INTENTS:
        return None
    args = raw.get("args") or {}
    if not isinstance(args, dict):
        return None
    allowed = ARGS_BY_INTENT[intent]
    clean: dict[str, Any] = {}
    for key, value in args.items():
        if key not in allowed:
            continue
        if not isinstance(value, (str, int)):
            continue
        if key == "college" and value not in {"CS", "EE", "FL"}:
            continue
        if key == "status" and value not in {"在校", "休学", "退学"}:
            continue
        if key == "keyword":
            value = str(value).strip()[:32]
            if not KEYWORD_RE.match(value):
                continue
        clean[key] = value
    return Plan(intent, clean, source="llm")


def plan(question: str) -> Plan:
    if SETTINGS.planner == "llm" and SETTINGS.llm_base_url:
        try:
            sanitized = _sanitize(_llm_request(question))
            if sanitized is not None:
                return sanitized
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError):
            # 外部模型不可用时不影响可用性：退化为确定性规则
            pass
    return rule_plan(question)
