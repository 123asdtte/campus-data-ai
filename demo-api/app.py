#!/usr/bin/env python
"""本地演示数据只读服务：按网关身份返回授权范围内的数据。

- 学生：本人档案 + 本人班级课表 + 本人异动；
- 辅导员：本人所带班级/学生/异动；
- 学工处、管理员：全校演示数据；
- 四件套 Excel 仅学工处/管理员可下载。

数据文件只存在于服务端镜像，不再由 web/public 公开提供。
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
import threading
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "demo-data.json"
FOUR_SHEET_PATH = BASE_DIR / "data" / "four-sheet.xlsx"
STATE_DIR = Path(os.environ.get("STATE_DIR", str(BASE_DIR / "state")))
STATE_PATH = STATE_DIR / "ledger.json"
ASSISTANT_LOG_PATH = STATE_DIR / "assistant-audit.jsonl"
ASSISTANT_LOG_KEEP = 500
GATEWAY_BASE = os.environ.get("GATEWAY_BASE", "http://gateway:9180").rstrip("/")
CLIENT_ID = os.environ.get(
    "GATEWAY_CLIENT_ID", "e5cd7e4891bf95d1d19206ce24a7b32e"
)
STAFF_ROLES = {"xgb", "superadmin"}
CHANGE_TYPES = {"休学", "复学", "退学", "转专业", "保留学籍", "跟读生转正式", "预科生转正", "留级"}
CHANGE_STATUSES = {"审批中", "已批", "退回"}
MAX_LOCAL_CHANGES = 500
MAX_IMPORT_ROWS = 200
MAX_BODY_BYTES = 64 * 1024
MAX_CONCURRENT_REQUESTS = max(1, int(os.environ.get("MAX_CONCURRENT_REQUESTS", "32")))
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CHANGE_NO_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
STATE_LOCK = threading.Lock()

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WEEKDAY_NUMBERS = {str(index + 1): day for index, day in enumerate(WEEKDAYS)}
CN_NUMBERS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
PERIOD_SCOPES = {
    "上午": {1, 2, 3, 4},
    "下午": {5, 6, 7, 8},
    "晚上": {9, 10, 11, 12},
}
SENSITIVE_PATTERN = re.compile(
    r"成绩|分数|其他学生|别人|电话|手机号|身份证|学号|导出|名单|请假|处分|心理|宿舍|家庭"
)
MAX_QUESTION_CHARS = 200

# Docker Desktop 会注入 127.0.0.1:8080 代理；容器内没有该代理。
# 网关调用必须直连，不能被环境代理劫持。
NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

try:
    DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    print(f"demo-api: 无法加载 {DATA_PATH}: {exc}", file=sys.stderr)
    raise SystemExit(1)


def normalize_weekday(value: object) -> str:
    text = str(value or "").strip()
    if text in WEEKDAYS:
        return text
    if text in WEEKDAY_NUMBERS:
        return WEEKDAY_NUMBERS[text]
    text = text.replace("星期", "").replace("礼拜", "").replace("周", "")
    return {
        "一": "周一", "二": "周二", "三": "周三", "四": "周四",
        "五": "周五", "六": "周六", "日": "周日", "天": "周日",
    }.get(text, str(value or "").strip())


# 源表里有 1-5 的数字星期，统一成中文星期，避免课表和问答漏课。
for _row in DATA.get("schedule") or []:
    _row["weekday"] = normalize_weekday(_row.get("weekday"))


def counts(items: list[str]) -> list[dict]:
    return [
        {"name": name, "count": value}
        for name, value in Counter(item for item in items if item).most_common()
    ]


class LedgerUnavailable(RuntimeError):
    """台账文件存在却读不出来。此时绝不能把它当成空表写回去，否则已有异动记录会静默丢失。"""


def empty_ledger() -> dict:
    return {"changes": [], "checked": {}}


def quarantine_ledger(reason: str) -> None:
    # 隔离副本是为了「事后还能救」，所以这一步自己失败也不能盖掉真正的原因。
    target = STATE_PATH.with_name(
        f"ledger.corrupt-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S-%f')}.json"
    )
    try:
        target.write_bytes(STATE_PATH.read_bytes())
        os.chmod(target, 0o600)
        print(f"[demo-api] 台账损坏（{reason}），原文件已隔离为 {target}", file=sys.stderr)
    except OSError as error:
        print(f"[demo-api] 台账损坏（{reason}），隔离副本写入失败：{error}", file=sys.stderr)


def load_ledger() -> dict:
    """读取台账。文件不存在就是空台账；文件读不动或结构不合法则抛错，交由调用方决定降级还是拒绝。"""
    try:
        raw = STATE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return empty_ledger()
    except (OSError, UnicodeDecodeError) as error:
        quarantine_ledger(f"读取失败：{error}")
        raise LedgerUnavailable("学籍异动台账文件无法读取") from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        quarantine_ledger(f"JSON 解析失败（第 {error.lineno} 行）")
        raise LedgerUnavailable("学籍异动台账文件不是合法 JSON") from error
    changes = payload.get("changes") if isinstance(payload, dict) else None
    checked = payload.get("checked") if isinstance(payload, dict) else None
    if not isinstance(changes, list) or not isinstance(checked, dict):
        quarantine_ledger("结构应为 {changes: [], checked: {}}")
        raise LedgerUnavailable("学籍异动台账文件结构不合法")
    return {"changes": changes, "checked": checked}


def read_ledger_for_display() -> dict:
    """展示链路（/data、AI 问数）遇到损坏台账时退回基础演示数据，不能让整站 500。"""
    try:
        return load_ledger()
    except LedgerUnavailable as error:
        print(f"[demo-api] {error}，本次展示仅使用基础演示数据", file=sys.stderr)
        return empty_ledger()


def save_ledger(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, STATE_PATH)


def counselor_keys(user: dict) -> tuple[set[str], set[str]]:
    counselor = (user.get("nickName") or user.get("userName") or "").strip()
    username = (user.get("userName") or "").strip()
    students = [
        s for s in (DATA.get("students") or [])
        if s.get("counselor") in {counselor, username}
    ]
    uids = {s.get("uid") for s in students if s.get("uid")}
    class_keys = {
        key
        for s in students
        for key in (s.get("class_name"), s.get("class_short"))
        if key
    }
    return uids, class_keys


def visible_uids(user: dict, roles: set[str]) -> set[str] | None:
    """None 表示全校；空集合表示无可见范围。"""
    if roles & STAFF_ROLES:
        return None
    if "counselor" in roles:
        return counselor_keys(user)[0]
    uid = (user.get("userName") or "").strip()
    return {uid} if uid else set()


def merge_ledger(user: dict, roles: set[str], state: dict) -> tuple[list[dict], list[str]]:
    uids = visible_uids(user, roles)
    all_changes = list(DATA.get("changes") or []) + list(state["changes"])
    if uids is not None:
        all_changes = [c for c in all_changes if c.get("uid") in uids]
    numbers = {c.get("change_no") for c in all_changes}
    checked = [no for no in state["checked"] if no in numbers]
    return all_changes, checked


def pending_check_rows(changes: list[dict], checked: list[str]) -> list[dict]:
    """已批但平台还没核对的异动。这个衔接口径只在这里定义一次，供助手与台账共用。"""
    done = set(checked or [])
    return [
        change for change in changes
        if "已批" in (change.get("status") or "") and change.get("change_no") not in done
    ]


COLLEGE_ALIASES = {
    "计算机": "人工智能学院",
    "人工智能": "人工智能学院",
    "护理": "康养护理学院",
    "康养": "康养护理学院",
    "汽车": "汽车工程学院",
    "财经": "财经商贸学院",
    "会计": "财经商贸学院",
    "轨道": "轨道交通学院",
    "智能装备": "智能装备学院",
    "机电": "智能装备学院",
}


def week_matches(weeks: object, current_week: int) -> bool:
    text = str(weeks or "")
    if not text:
        return True
    if "单" in text and current_week % 2 == 0:
        return False
    if "双" in text and current_week % 2 == 1:
        return False
    ranges = re.findall(r"(\d+)\s*-\s*(\d+)", text)
    if ranges:
        return any(int(start) <= current_week <= int(end) for start, end in ranges)
    numbers = [int(number) for number in re.findall(r"\d+", text)]
    return not numbers or current_week in numbers


def period_numbers(period: object) -> set[int]:
    return {int(number) for number in re.findall(r"\d+", str(period or ""))}


def course_place(row: dict) -> str:
    return str(row.get("room") or row.get("note") or "地点待定")


def course_card(row: dict, date_text: str | None = None) -> dict:
    return {
        "weekday": row.get("weekday") or "",
        "period": row.get("period") or "",
        "course": row.get("course") or "",
        "teacher": row.get("teacher") or "教师待定",
        "room": course_place(row),
        "date": date_text,
    }


def resolve_scope(question: str, now: datetime, current_week: int) -> dict:
    week = current_week
    day_index = now.weekday()
    whole_week = False
    explicit_day = re.search(r"(下|本|这)?(?:周|星期|礼拜)([一二三四五六日天])", question)
    if explicit_day:
        day_index = CN_NUMBERS[explicit_day.group(2)] - 1
        if explicit_day.group(1) == "下":
            week += 1
        elif explicit_day.group(1) in ("本", "这"):
            week = current_week
    elif re.search(r"大后天", question):
        day_index = (day_index + 3) % 7
    elif re.search(r"后天", question):
        day_index = (day_index + 2) % 7
    elif re.search(r"明天|明日", question):
        day_index = (day_index + 1) % 7
    elif re.search(r"下周|下星期|下礼拜", question):
        week += 1
        whole_week = True
    elif re.search(r"本周|这周|这星期|这礼拜", question):
        week = current_week
        whole_week = True

    scope_numbers: set[int] | None = None
    scope_label = ""
    for label, numbers in PERIOD_SCOPES.items():
        if label in question:
            scope_numbers = numbers
            scope_label = label
            break
    single = re.search(r"第\s*([一二三四五六七八九十]|\d{1,2})\s*节", question)
    if single:
        raw = single.group(1)
        number = int(raw) if raw.isdigit() else CN_NUMBERS.get(raw, 0)
        if number:
            scope_numbers = {number}
            scope_label = f"第{number}节"

    return {
        "week": week,
        "day_index": day_index,
        "whole_week": whole_week,
        "periods": scope_numbers,
        "period_label": scope_label,
        "explicit_day": bool(explicit_day),
        "week_ref": explicit_day.group(1) if explicit_day else None,
    }


def date_for_scope(now: datetime, current_week: int, week: int, day_index: int) -> str:
    monday = now.date() - timedelta(days=now.weekday())
    return (monday + timedelta(weeks=week - current_week, days=day_index)).isoformat()


def format_period_times(period_times: list[dict]) -> dict[str, str]:
    return {
        str(item.get("period") or ""): f"{item.get('start') or ''}–{item.get('end') or ''}"
        for item in period_times
    }


def schedule_answer(
    question: str,
    student: dict,
    schedule: list[dict],
    metrics: dict,
    now: datetime,
) -> dict:
    schedule_meta = metrics.get("schedule_meta") or {}
    current_week = int(schedule_meta.get("current_week") or 1)
    period_times = schedule_meta.get("period_times") or []
    time_by_period = format_period_times(period_times)
    base_note = f"按第 {current_week} 周演示课表；最终以青果/教务处为准。"
    base = {
        "courses": [],
        "action": None,
        "note": base_note,
        "as_of": now.isoformat(timespec="seconds"),
    }

    if SENSITIVE_PATTERN.search(question):
        return {
            **base,
            "intent": "refused",
            "answer": "学生助手只回答你自己的课表和本人学籍信息；学号、证件号、联系方式、成绩、其他学生信息和名单导出不在这里提供。",
            "scope": {"label": "仅本人课表", "week": current_week},
        }

    # 本人档案字段在 /portal 页面已经展示，这里只是同一份数据的另一种问法；学号与联系方式不回答。
    profile_fields = [
        (("学籍", "在籍", "学籍状态"), "学籍状态", student.get("status")),
        (("班级", "哪个班", "什么班", "几班"), "班级", student.get("class_short") or student.get("class_name")),
        (("专业",), "专业", student.get("major")),
        (("学院",), "学院", student.get("college")),
        (("年级", "入学", "几级"), "年级", student.get("grade")),
        (("辅导员", "班主任"), "辅导员", student.get("counselor")),
    ]
    timetable_words = ("有课", "上课", "没课", "课表", "教室", "节", "星期", "周", "几点", "明天", "后天", "今天", "下午", "上午")
    matched = [(label, value) for words, label, value in profile_fields if any(word in question for word in words)]
    hits = [(label, value) for label, value in matched if value]
    if hits and not any(word in question for word in timetable_words):
        detail = "；".join(f"{label}：{value}" for label, value in hits)
        return {
            **base,
            "intent": "profile",
            "answer": f"你的{detail}。这些来自你本人学籍档案，和自助填报页“我的信息”一致。",
            "scope": {"label": "仅本人档案"},
            "note": "学号、证件号、联系方式不在回答里；如需修改信息请走自助填报。",
            "action": {"label": "打开自助填报", "to": "/portal"},
        }

    if not schedule:
        return {
            **base,
            "intent": "no_data",
            "answer": f"当前演示课表里没有你的排课数据（{student.get('class_short') or student.get('class_name') or '本人班级'}）。请以教务处/青果为准。",
            "scope": {"label": "仅本人课表", "week": current_week},
        }

    help_words = ("帮助", "能做什么", "怎么用", "你好", "你是谁")
    if any(word in question for word in help_words):
        return {
            **base,
            "intent": "help",
            "answer": "我是课表助手，只能看到你自己的班级课表和本人学籍档案。可以问：明天下午有什么课、今天还剩几节课、这周五第一节在哪、下周有哪些课、我的学籍状态是什么。",
            "scope": {"label": "仅本人课表", "week": current_week},
            "suggestions": ["明天下午有什么课？", "今天还剩几节课？", "这周五第一节在哪？", "下周有哪些课？", "我的学籍状态是什么？"],
        }

    scope = resolve_scope(question, now, current_week)
    week = scope["week"]
    day_index = scope["day_index"]
    week_rows = [row for row in schedule if week_matches(row.get("weeks"), week)]
    if not week_rows:
        return {
            **base,
            "intent": "no_data",
            "answer": f"第 {week} 周演示课表里没有你的排课。请以教务处/青果为准。",
            "scope": {"label": f"第 {week} 周", "week": week},
        }

    remaining = bool(re.search(r"还剩|还有|剩下|剩余", question)) and not scope["whole_week"]
    rows = week_rows
    if not scope["whole_week"]:
        rows = [row for row in rows if row.get("weekday") == WEEKDAYS[day_index]]
    if scope["periods"] is not None:
        rows = [row for row in rows if period_numbers(row.get("period")) & scope["periods"]]

    if remaining and date_for_scope(now, current_week, week, day_index) == now.date().isoformat():
        rows = [
            row for row in rows
            if time_by_period.get(str(row.get("period")), "99:99").split("–")[-1] > now.strftime("%H:%M")
        ]

    rows.sort(key=lambda row: (
        WEEKDAYS.index(row.get("weekday")) if row.get("weekday") in WEEKDAYS else 9,
        min(period_numbers(row.get("period")) or {99}),
    ))

    if scope["whole_week"]:
        label = "本周" if week == current_week else f"第 {week} 周"
        days = []
        for day in WEEKDAYS:
            day_rows = [row for row in rows if row.get("weekday") == day]
            if not day_rows:
                continue
            line = "；".join(
                f"{row['period']} {row['course']}（{row.get('teacher') or '教师待定'}，{course_place(row)}）"
                for row in day_rows
            )
            days.append(f"{day}：{line}")
        if not days:
            answer = f"{label}没有符合条件的课程。{base_note}"
        else:
            answer = f"{label}共 {len(rows)} 门课：\n" + "\n".join(days) + f"\n{base_note}"
        day_text = None
        weekday_text = None
        date_text = None
    else:
        weekday_text = WEEKDAYS[day_index]
        date_text = date_for_scope(now, current_week, week, day_index)
        if week == current_week:
            if not scope["explicit_day"] and day_index == now.weekday():
                label = "今天"
            elif not scope["explicit_day"] and day_index == (now.weekday() + 1) % 7:
                label = "明天"
            elif not scope["explicit_day"] and day_index == (now.weekday() + 2) % 7:
                label = "后天"
            elif scope["week_ref"] in ("本", "这"):
                label = f"本周{weekday_text[1:]}"
            else:
                label = weekday_text
        else:
            label = f"下{weekday_text[1:]}"
        suffix = f"（{scope['period_label']}）" if scope["period_label"] else ""
        if remaining:
            if rows:
                answer = (
                    f"{label}{suffix}还剩 {len(rows)} 门课（截至 {now.strftime('%H:%M')}）：\n"
                    + "\n".join(
                        f"{row['period']} {row['course']}（{course_place(row)}）" for row in rows
                    )
                    + f"\n{base_note}"
                )
            else:
                answer = f"{label}{suffix}的课已经结束或没有剩余课程。{base_note}"
        elif rows:
            date_label = f"{date_text} {weekday_text}" if label in ("今天", "明天", "后天") else date_text
            answer = (
                f"{label}（{date_label}）{suffix}有 {len(rows)} 门课：\n"
                + "\n".join(
                    f"{row['period']} {time_by_period.get(str(row.get('period')), '')} · {row['course']}"
                    f"（{row.get('teacher') or '教师待定'}，{course_place(row)}）"
                    for row in rows
                )
                + f"\n{base_note}"
            )
        else:
            answer = f"{label}{suffix}没有课。{base_note}"

    return {
        **base,
        "intent": "schedule_remaining" if remaining else ("schedule_week" if scope["whole_week"] else "schedule_day"),
        "answer": answer,
        "scope": {
            "label": label,
            "date": date_text,
            "weekday": weekday_text,
            "week": week,
            "period": scope["period_label"] or None,
        },
        "courses": [
            course_card(row, date_for_scope(now, current_week, week, WEEKDAYS.index(row["weekday"])))
            if row.get("weekday") in WEEKDAYS else course_card(row)
            for row in rows
        ],
        "suggestions": ["今天还剩几节课？", "明天下午有什么课？", "这周五第一节在哪？", "下周有哪些课？"],
    }


def staff_answer(question: str, payload: dict, roles: set[str]) -> dict:
    students = payload.get("students") or []
    metrics = payload.get("metrics") or {}
    changes = payload.get("changes") or []
    is_counselor = "counselor" in roles and not (roles & STAFF_ROLES)
    scope_label = "本班范围" if is_counselor else "全校范围"
    report_target = "/counselor" if is_counselor else "/reports"
    change_target = "/changes"
    base = {"courses": [], "note": f"{scope_label}演示数据；不返回身份证、电话或原始学号。", "action": None}
    q = question

    raw_sensitive = re.search(r"身份证|电话|手机号|原始学号|成绩", q)
    if raw_sensitive:
        return {
            **base,
            "intent": "refused",
            "answer": "我不会返回身份证、电话、原始学号或成绩明细；如需名单请使用报表中心，并按角色权限导出脱敏字段。",
            "scope": {"label": scope_label},
        }

    if any(word in q for word in ("帮助", "能做什么", "怎么用", "你好", "你是谁")):
        return {
            **base,
            "intent": "help",
            "answer": "我可以按当前账号的数据范围统计人数、学籍状态、异动分布和数据质量，并引导你到对应页面。当前是本地规则模式，不调用外部模型。",
            "scope": {"label": scope_label},
            "suggestions": ["人工智能学院有多少学生？", "全校休学和退学各有多少人？", "数据质量怎么样？", "最近的学籍异动情况"],
            "action": {"label": "打开数据工作台", "to": "/workbench" if not is_counselor else "/counselor"},
        }

    college = next((item.get("name") for item in metrics.get("college_counts") or [] if item.get("name") and item["name"] in q), None)
    if not college:
        college = next((name for alias, name in COLLEGE_ALIASES.items() if alias in q), None)
    if college and is_counselor:
        # 辅导员载荷里的 college_counts 只覆盖本人所带的班，直接播报会变成“班级数冒充学院数”。
        return {
            **base,
            "intent": "out_of_scope",
            "answer": (
                f"{college}的全院人数不在你的数据范围内：你可见的是所带班级共 {len(students)} 人，"
                f"而 {college} 是更大的口径。需要全院数字请向学工处或管理员查询。"
            ),
            "scope": {"label": scope_label},
            "action": {"label": "打开辅导员台", "to": "/counselor"},
        }
    base_students = [student for student in students if student.get("college") == college] if college else students
    scope = college or scope_label
    statuses = [
        item.get("name") for item in metrics.get("status_counts") or []
        if item.get("name") and item["name"] in q
    ]
    if "在校" in q and "在籍" not in statuses:
        statuses.append("在籍")

    # “今天数据有什么问题？”是最自然的说法，不能只认“数据质量”这四个字。
    if any(word in q for word in ("数据质量", "缺失", "异常", "同名", "数据标记")) or ("数据" in q and "问题" in q):
        quality = metrics.get("data_quality") or {}
        if not quality:
            return {
                **base,
                "intent": "quality",
                "answer": "当前角色没有全校数据质量统计范围；请联系学工处或管理员。",
                "scope": {"label": scope_label},
            }
        return {
            **base,
            "intent": "quality",
            "answer": (
                f"{scope_label}共 {len(students)} 名学生。需重点核对：重复学号 "
                f"{(quality.get('duplicate_rows') or {}).get('count', 0)} 行、同班同名 "
                f"{(quality.get('same_name_groups') or {}).get('count', 0)} 组、身份证校验异常 "
                f"{(quality.get('id_invalid') or {}).get('count', 0)} 条、班级名称未匹配 "
                f"{(quality.get('class_not_found') or {}).get('count', 0)} 人、转专业已批但花名册未更新 "
                f"{(quality.get('transfer_conflicts') or {}).get('count', 0)} 条。同名同姓 "
                f"{(quality.get('same_name_all') or {}).get('count', 0)} 组仅作提示。"
            ),
            "scope": {"label": scope_label},
            "action": {"label": "查看数据工作台", "to": "/workbench" if not is_counselor else "/counselor"},
        }

    if any(word in q for word in ("名单", "报表", "导出", "表格")):
        template = "退学名单" if "退学" in q else ("学籍异动名单" if "异动" in q else "班级花名册")
        return {
            **base,
            "intent": "report",
            "answer": f"可以到报表中心使用「{template}」模板：选择字段与范围后导出。导出只含 UID 和脱敏字段，并记录操作人与时间。",
            "scope": {"label": scope_label},
            "action": {"label": "打开报表中心" if not is_counselor else "打开辅导员台", "to": report_target},
        }

    if any(word in q for word in ("待核对", "没核对", "未核对", "待处理", "未处理", "审批中", "待审批", "核对进度")):
        if any(word in q for word in ("审批中", "待审批")):
            rows = [change for change in changes if "审批中" in (change.get("status") or "")]
            label = "条异动仍在审批中"
            hint = "审批通过后才会进入平台核对。"
        else:
            rows = pending_check_rows(changes, payload.get("platform_checked") or [])
            label = "条异动已批但平台未核对"
            hint = "在台账里按异动编号搜索即可定位并点“核对”。"
        preview = "、".join(
            f"{change.get('change_no')}（{change.get('type')} {change.get('date') or '未填日期'}）"
            for change in rows[:5]
        )
        return {
            **base,
            "intent": "pending",
            "answer": (
                f"{scope_label}有 {len(rows)} {label}"
                + (f"：{preview}" + ("，其余略。" if len(rows) > 5 else "。") if rows else "。")
                + hint
            ),
            "scope": {"label": scope_label},
            "action": {"label": "打开学籍异动", "to": change_target},
        }

    # “异动/条/记录”才是台账口径；只说“休学”“退学”时问的是学生当前学籍状态人数，两者不能混。
    wants_change_rows = any(word in q for word in ("异动", "台账", "审批", "核对", "变化", "记录", "条"))
    count_words = any(word in q for word in ("多少", "人数", "几个", "几名", "统计", "哪些"))
    change_types = [name for name in CHANGE_TYPES if name in q]

    if statuses and not wants_change_rows:
        parts = [
            f"{status} {sum(1 for student in base_students if student.get('status') == status)} 人"
            for status in statuses[:4]
        ]
        return {
            **base,
            "intent": "count",
            "answer": f"{scope}：{'，'.join(parts)}。按学生当前学籍状态统计（演示数据），不是异动条数。",
            "scope": {"label": scope_label},
            "action": {"label": "查看数据工作台", "to": "/workbench" if not is_counselor else "/counselor"},
        }

    if change_types and count_words and (wants_change_rows or not statuses):
        parts = [
            f"{name} {sum(1 for change in changes if change.get('type') == name)} 条"
            for name in change_types
        ]
        # “留级和复学各多少人”问的是人数，但这两类只存在于异动台账里，必须说清给的是条数。
        note = "" if statuses or wants_change_rows else "这两类不是当前学籍状态，只能按异动台账条数回答。"
        return {
            **base,
            "intent": "change_count",
            "answer": f"{scope_label}学籍异动记录共 {len(changes)} 条；{'，'.join(parts)}。统计范围为演示台账。{note}",
            "scope": {"label": scope_label},
            "action": {"label": "打开学籍异动", "to": change_target},
        }

    if wants_change_rows:
        type_counts = metrics.get("change_type_counts") or []
        top = "、".join(f"{item.get('name')} {item.get('count')}" for item in type_counts[:3])
        orphan = metrics.get("orphan_changes") or 0
        return {
            **base,
            "intent": "changes",
            "answer": (
                f"{scope_label}共有 {len(changes)} 条学籍异动记录"
                + (f"；主要类型：{top}。" if top else "。")
                + (f"另有 {orphan} 条学号未匹配的异动不在可核对清单里。" if orphan else "")
                + "异动需教务确认后才联动学生状态。"
            ),
            "scope": {"label": scope_label},
            "action": {"label": "打开学籍异动", "to": change_target},
        }

    # “哪些/多少”本身不指向学生：问收件箱、导入批次时不能回一句人数，宁落回 unknown 的引导。
    about_students = any(word in q for word in ("学生", "人数", "人", "学籍", "在读", "全校", "学院", "班", "名"))
    if count_words and about_students:
        return {
            **base,
            "intent": "count",
            "answer": f"{scope}共有 {len(base_students)} 名学生，其中在籍 {sum(1 for student in base_students if student.get('status') == '在籍')} 人。",
            "scope": {"label": scope_label},
        }

    return {
        **base,
        "intent": "unknown",
        "answer": "我暂时只理解人数统计、学籍状态、数据质量、学籍异动和报表引导。你可以试试：“人工智能学院有多少学生”“全校休学和退学各有多少人”。",
        "scope": {"label": scope_label},
        "suggestions": ["人工智能学院有多少学生？", "全校休学和退学各有多少人？", "数据质量怎么样？", "最近的学籍异动情况"],
        "action": {"label": "打开数据工作台", "to": "/workbench" if not is_counselor else "/counselor"},
    }


def validate_change(body: dict, user: dict, roles: set[str]) -> tuple[dict | None, int, str]:
    uid = str(body.get("uid") or "").strip()
    change_type = str(body.get("type") or "").strip()
    date = str(body.get("date") or "").strip()
    reason = str(body.get("reason") or "").strip()
    target = str(body.get("target") or "").strip() or "—"
    if not uid:
        return None, 400, "缺少学生 UID"
    if change_type not in CHANGE_TYPES:
        return None, 400, "异动类型不在允许范围"
    if not DATE_PATTERN.match(date):
        return None, 400, "异动日期格式应为 YYYY-MM-DD"
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return None, 400, "异动日期不是有效日期"
    if not 1 <= len(reason) <= 200 or len(target) > 200:
        return None, 400, "原因需为 1-200 字，去向不超过 200 字"
    if not any(s.get("uid") == uid for s in (DATA.get("students") or [])):
        return None, 404, "学生不存在"
    scope = visible_uids(user, roles)
    if scope is not None and uid not in scope:
        return None, 403, "该学生不在当前账号的数据范围内"
    return {
        "uid": uid,
        "type": change_type,
        "date": date,
        "reason": reason,
        "target": target,
    }, 0, ""


def next_change_no(existing: set[str]) -> str:
    while True:
        change_no = f"YD-LOCAL-{datetime.now():%Y%m%d%H%M%S}-{secrets.token_hex(2)}"
        if change_no not in existing:
            return change_no


def scope_metrics(students: list[dict], changes: list[dict], classes: list[dict]) -> dict:
    base = DATA.get("metrics") or {}
    return {
        "disclaimer": base.get("disclaimer", ""),
        "generated_at": base.get("generated_at", ""),
        "source": base.get("source", ""),
        "total_students": len(students),
        "total_classes": len(classes),
        "roster_class_names": len(classes),
        "total_colleges": len({s.get("college") for s in students if s.get("college")}),
        "total_majors": len({s.get("major") for s in students if s.get("major")}),
        "total_counselors": len({s.get("counselor") for s in students if s.get("counselor")}),
        "status_counts": counts([s.get("status", "") for s in students]),
        "college_counts": counts([s.get("college", "") for s in students]),
        "grade_counts": counts([s.get("grade", "") for s in students]),
        "top_majors": [],
        "change_total": len(changes),
        "change_type_counts": counts([c.get("type", "") for c in changes]),
        "change_status_counts": counts([c.get("status", "") for c in changes]),
        "orphan_changes": 0,
        "registration": {},
        "data_quality": {},
        "affairs": [],
        "source_files": [],
        "schedule_meta": base.get("schedule_meta") or {},
    }


def record_assistant_audit(user: dict, roles: set[str], result: dict, question: str, page: str) -> None:
    """服务端问数审计：只留身份、角色、意图、范围与问题长度，不落问题原文（问题里可能带姓名等信息）。"""
    entry = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "actor": (user.get("userName") or "").strip(),
        "roles": sorted(roles),
        "intent": result.get("intent"),
        "scope": (result.get("scope") or {}).get("label"),
        "page": page or None,
        "question_chars": len(question),
    }
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        with STATE_LOCK:
            with open(ASSISTANT_LOG_PATH, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            lines = ASSISTANT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-ASSISTANT_LOG_KEEP:]
            ASSISTANT_LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"[demo-api] 问数审计写入失败：{error}", file=sys.stderr)


def scoped_payload(user: dict, roles: set[str]) -> dict | None:
    """返回该身份可见的数据；无权限返回 None。"""
    with STATE_LOCK:
        state = read_ledger_for_display()

    if roles & STAFF_ROLES:
        changes, checked = merge_ledger(user, roles, state)
        metrics = dict(DATA.get("metrics") or {})
        metrics.update({
            "change_total": len(changes),
            "change_type_counts": counts([c.get("type", "") for c in changes]),
            "change_status_counts": counts([c.get("status", "") for c in changes]),
        })
        return {**DATA, "metrics": metrics, "changes": changes, "platform_checked": checked}

    students_all = DATA.get("students") or []
    if "student_portal" in roles:
        uid = (user.get("userName") or "").strip()
        student = next((s for s in students_all if s.get("uid") == uid), None)
        if not student:
            return None
        class_keys = {student.get("class_name"), student.get("class_short")} - {None, ""}
        schedule = [
            row for row in (DATA.get("schedule") or [])
            if row.get("class_name") in class_keys or row.get("class_short") in class_keys
        ]
        changes, checked = merge_ledger(user, roles, state)
        classes = [
            c for c in (DATA.get("class_summary") or [])
            if c.get("class_name") in class_keys or c.get("class_short") in class_keys
        ]
        return {
            "meta": DATA.get("meta") or {},
            "metrics": scope_metrics([student], changes, classes),
            "students": [student],
            "schedule": schedule,
            "changes": changes,
            "class_summary": classes,
            "anomalies": [],
            "platform_checked": checked,
        }

    if "counselor" in roles:
        counselor = (user.get("nickName") or user.get("userName") or "").strip()
        username = (user.get("userName") or "").strip()
        uids, class_keys = counselor_keys(user)
        students = [s for s in students_all if s.get("uid") in uids]
        schedule = [
            row for row in (DATA.get("schedule") or [])
            if row.get("class_name") in class_keys or row.get("class_short") in class_keys
        ]
        changes, checked = merge_ledger(user, roles, state)
        classes = [
            c for c in (DATA.get("class_summary") or [])
            if c.get("counselor") in {counselor, username}
        ]
        return {
            "meta": DATA.get("meta") or {},
            "metrics": scope_metrics(students, changes, classes),
            "students": students,
            "schedule": schedule,
            "changes": changes,
            "class_summary": classes,
            "anomalies": [],
            "platform_checked": checked,
        }

    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "campus-demo-api"
    sys_version = ""
    # 慢请求/半开连接最多占用一个线程 10 秒，避免公网试用时线程被拖满
    timeout = 10

    def log_message(self, fmt: str, *args) -> None:
        print("[demo-api] " + (fmt % args), file=sys.stderr)

    def _send(self, status: int, body: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _identify(self) -> dict | None:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._json(401, {"error": "未登录"})
            return None
        request = urllib.request.Request(
            GATEWAY_BASE + "/system/user/getInfo",
            headers={
                "Authorization": auth,
                "clientid": CLIENT_ID,
                "Accept": "application/json",
            },
        )
        try:
            with NO_PROXY_OPENER.open(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self._json(401 if exc.code == 401 else 503, {"error": "身份校验失败"})
            return None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            print(f"demo-api: 网关不可用: {exc}", file=sys.stderr)
            self._json(503, {"error": "身份服务暂不可用"})
            return None
        if payload.get("code") != 200 or not payload.get("data"):
            self._json(401, {"error": "身份校验失败"})
            return None
        data = payload["data"]
        return {
            "user": data.get("user") or {},
            "roles": set(data.get("roles") or []),
        }

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return
        if path not in ("/data", "/four-sheet"):
            self._json(404, {"error": "not found"})
            return

        identity = self._identify()
        if identity is None:
            return
        roles = identity["roles"]
        if path == "/four-sheet":
            if not (roles & STAFF_ROLES):
                self._json(403, {"error": "当前角色无权下载全校四件套"})
                return
            try:
                body = FOUR_SHEET_PATH.read_bytes()
            except OSError:
                self._json(503, {"error": "四件套文件不可用"})
                return
            self._send(
                200, body,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "four-sheet.xlsx",
            )
            return

        payload = scoped_payload(identity["user"], roles)
        if payload is None:
            self._json(403, {"error": "当前角色没有可用的数据范围"})
            return
        self._json(200, payload)

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            self._json(400, {"error": "请求体为空"})
            return None
        if length > MAX_BODY_BYTES:
            self._json(413, {"error": "请求体过大"})
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "请求体不是合法 JSON"})
            return None
        if not isinstance(payload, dict):
            self._json(400, {"error": "请求体必须是对象"})
            return None
        return payload

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in ("/changes", "/changes/import", "/changes/check", "/assistant/query"):
            self._json(404, {"error": "not found"})
            return
        identity = self._identify()
        if identity is None:
            return
        user = identity["user"]
        roles = identity["roles"]
        if path == "/assistant/query":
            self._assistant_query(user, roles)
            return
        if not (roles & STAFF_ROLES or "counselor" in roles):
            self._json(403, {"error": "当前角色不能管理学籍异动"})
            return
        body = self._read_json()
        if body is None:
            return
        try:
            if path == "/changes":
                self._create_change(user, roles, body)
            elif path == "/changes/import":
                self._import_changes(user, roles, body)
            else:
                self._check_change(user, roles, body)
        except LedgerUnavailable as error:
            # 台账读不出来就写，等于把已有异动记录覆盖成只剩这一条，必须硬拦。
            self._json(
                503,
                {"error": f"{error}，为避免覆盖已有台账已拒绝写入；请管理员执行 scripts/demo/restore-ledger.ps1 恢复"},
            )
        except OSError as error:
            print(f"[demo-api] 台账写入失败：{error}", file=sys.stderr)
            self._json(500, {"error": "学籍异动台账写入失败，本次操作未生效，请重试"})

    def _assistant_query(self, user: dict, roles: set[str]) -> None:
        body = self._read_json()
        if body is None:
            return
        question = str(body.get("question") or "").strip()
        if not 1 <= len(question) <= MAX_QUESTION_CHARS:
            self._json(400, {"error": f"问题需为 1-{MAX_QUESTION_CHARS} 字"})
            return
        page = str(body.get("page") or "").strip()[:60]
        payload = scoped_payload(user, roles)
        if payload is None:
            record_assistant_audit(user, roles, {"intent": "denied"}, question, page)
            self._json(403, {"error": "当前角色没有可用的数据范围"})
            return

        now = datetime.now().astimezone()
        if "student_portal" in roles:
            students = payload.get("students") or []
            if not students:
                self._json(403, {"error": "当前账号没有绑定的学生档案"})
                return
            result = schedule_answer(
                question,
                students[0],
                payload.get("schedule") or [],
                payload.get("metrics") or {},
                now,
            )
        elif roles & STAFF_ROLES or "counselor" in roles:
            result = staff_answer(question, payload, roles)
        else:
            self._json(403, {"error": "当前角色不能使用 AI 助手"})
            return

        result["context"] = page
        username = (user.get("userName") or "").strip()
        print(
            f"[demo-api] assistant {result.get('intent')} by {username} page={page or '-'}",
            file=sys.stderr,
        )
        record_assistant_audit(user, roles, result, question, page)
        self._json(200, result)

    def _create_change(self, user: dict, roles: set[str], body: dict) -> None:
        fields, status, error = validate_change(body, user, roles)
        if fields is None:
            self._json(status, {"error": error})
            return

        username = (user.get("userName") or "").strip()
        with STATE_LOCK:
            state = load_ledger()
            if len(state["changes"]) >= MAX_LOCAL_CHANGES:
                self._json(409, {"error": "本地演示台账已达上限，请清理 state/ledger.json"})
                return
            existing = {c.get("change_no") for c in (DATA.get("changes") or [])}
            existing.update(c.get("change_no") for c in state["changes"])
            change = {
                **fields,
                "change_no": next_change_no(existing),
                "status": "审批中",
                "created_by": username,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            state["changes"].insert(0, change)
            save_ledger(state)
        print(f"[demo-api] change created by {username}: {change['change_no']} {fields['uid']} {fields['type']}", file=sys.stderr)
        self._json(201, {"change": change})

    def _import_changes(self, user: dict, roles: set[str], body: dict) -> None:
        rows = body.get("changes")
        if not isinstance(rows, list) or not rows:
            self._json(400, {"error": "changes 必须是非空数组"})
            return
        if len(rows) > MAX_IMPORT_ROWS:
            self._json(413, {"error": f"单次最多导入 {MAX_IMPORT_ROWS} 条"})
            return

        skipped: list[dict] = []
        valid: list[dict] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                skipped.append({"row": index + 1, "reason": "记录不是对象"})
                continue
            fields, _, error = validate_change(row, user, roles)
            if fields is None:
                skipped.append({"row": index + 1, "uid": str(row.get("uid") or ""), "reason": error})
                continue
            status = str(row.get("status") or "审批中").strip()
            provided = str(row.get("change_no") or "").strip()
            valid.append({
                **fields,
                "status": status if status in CHANGE_STATUSES else "审批中",
                "_provided_no": provided if CHANGE_NO_PATTERN.match(provided) else "",
            })
        if not valid:
            self._json(400, {"error": "没有可导入的记录", "skipped": skipped[:20]})
            return

        username = (user.get("userName") or "").strip()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with STATE_LOCK:
            state = load_ledger()
            existing = {c.get("change_no") for c in (DATA.get("changes") or [])}
            existing.update(c.get("change_no") for c in state["changes"])
            remaining = MAX_LOCAL_CHANGES - len(state["changes"])
            imported: list[dict] = []
            for item in valid:
                if remaining <= 0:
                    skipped.append({"row": "剩余", "uid": item["uid"], "reason": "台账已达上限"})
                    continue
                provided = item.pop("_provided_no")
                change_no = provided or next_change_no(existing)
                if change_no in existing:
                    suffix = 1
                    while f"{provided}-IMP{suffix}" in existing:
                        suffix += 1
                    change_no = f"{provided}-IMP{suffix}"
                existing.add(change_no)
                change = {
                    **item,
                    "change_no": change_no,
                    "created_by": username,
                    "created_at": now,
                }
                state["changes"].insert(0, change)
                imported.append(change)
                remaining -= 1
            save_ledger(state)
        print(
            f"[demo-api] import by {username}: {len(imported)} imported, {len(skipped)} skipped",
            file=sys.stderr,
        )
        self._json(200, {"imported": imported, "skipped": skipped[:20], "skipped_total": len(skipped)})

    def _check_change(self, user: dict, roles: set[str], body: dict) -> None:
        change_no = str(body.get("change_no") or "").strip()
        if not change_no:
            self._json(400, {"error": "缺少异动编号"})
            return
        with STATE_LOCK:
            state = load_ledger()
            change = next(
                (c for c in state["changes"] if c.get("change_no") == change_no),
                None,
            ) or next(
                (c for c in (DATA.get("changes") or []) if c.get("change_no") == change_no),
                None,
            )
            if not change:
                self._json(404, {"error": "异动记录不存在"})
                return
            scope = visible_uids(user, roles)
            if scope is not None and change.get("uid") not in scope:
                self._json(403, {"error": "该异动不在当前账号的数据范围内"})
                return
            username = (user.get("userName") or "").strip()
            state["checked"][change_no] = {
                "by": username,
                "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            save_ledger(state)
        print(f"[demo-api] change checked by {username}: {change_no}", file=sys.stderr)
        self._json(200, {"change_no": change_no, "checked": True})


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

    def process_request(self, request, client_address) -> None:
        if not self._slots.acquire(blocking=False):
            # 先读掉请求头再回 503，避免 Windows 上未读数据触发 RST 使客户端收不到响应
            try:
                request.settimeout(0.5)
                data = b""
                while b"\r\n\r\n" not in data and len(data) < 8192:
                    chunk = request.recv(1024)
                    if not chunk:
                        break
                    data += chunk
            except OSError:
                pass
            body = json.dumps({"error": "服务繁忙，请稍后重试"}, ensure_ascii=False).encode("utf-8")
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Type: application/json; charset=utf-8\r\n"
                    b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n"
                    b"Connection: close\r\n\r\n" + body
                )
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = Server(("0.0.0.0", port), Handler)
    print(f"demo-api listening on :{port}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
