#!/usr/bin/env python3
"""Build a local, de-identified demo dataset from the WorkBuddy pilot materials.

Source data is fictional (see the library's 00_数据性质说明). The generated
public dataset contains only a stable demo UID, masked PII and non-sensitive
business fields. The UID -> original record mapping is written outside the
repository for the data steward and is never served by the web app.

Usage:
    python scripts/demo/build_demo_dataset.py \
      --source "C:/Users/luofeng/Desktop/思科职院AI试点交付材料" \
      --out web/public/demo \
      --private "Z:/ai/本地部署/demo-private"
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[2]
STATUS_ORDER = ["在籍", "跟读", "预科", "休学", "退学", "保留学籍"]
STATUS_TONE = {
    "在籍": "success",
    "跟读": "info",
    "预科": "info",
    "休学": "warning",
    "退学": "danger",
    "保留学籍": "muted",
}
ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
ID_CHECK = "10X98765432"
# Some class rows use FD#nnn placeholders as counselor IDs. For the demo,
# map them to stable fictional names so the UI reads like a real roster.
COUNSELOR_ALIASES = [
    "陈静", "李敏", "王磊", "张倩", "刘洋", "赵晨", "周宁", "吴昊", "徐婷", "孙悦",
    "马超", "朱琳", "胡杰", "郭静", "何伟", "高媛", "林峰", "罗婷", "梁宇", "宋佳",
    "郑凯", "谢楠", "韩雪", "唐磊", "许晴", "邓超", "冯霞", "曹阳", "彭博", "董洁",
    "袁野", "蒋欣", "余波", "杜娟", "魏然", "程浩", "苏晴", "吕梁", "丁宁", "任杰",
]


def text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def mask_name(value: str) -> str:
    value = value.strip()
    if not value:
        return "—"
    if len(value) == 1:
        return "*"
    return value[0] + "*" * (len(value) - 1)


def mask_id(value: str) -> str:
    value = value.strip().upper()
    if len(value) >= 4:
        return "****" + value[-4:]
    return "—"


def mask_phone(value: str) -> str:
    value = re.sub(r"\D", "", value)
    if len(value) == 11:
        return value[:3] + "****" + value[-4:]
    if len(value) >= 4:
        return "****" + value[-4:]
    return "—"


def mask_address(value: str) -> str:
    value = value.strip()
    if not value:
        return "—"
    if "市" in value:
        return value.split("市")[0] + "市"
    return value[:8] + ("…" if len(value) > 8 else "")


def display_counselor(value: str) -> str:
    value = value.strip()
    match = re.fullmatch(r"FD#(\d+)", value)
    if not match:
        return value
    index = int(match.group(1))
    alias = COUNSELOR_ALIASES[index % len(COUNSELOR_ALIASES)]
    return f"{alias}老师"


def id_valid(value: str) -> bool:
    value = value.strip().upper()
    if not re.fullmatch(r"\d{17}[\dX]", value):
        return False
    total = sum(int(value[i]) * ID_WEIGHTS[i] for i in range(17))
    return ID_CHECK[total % 11] == value[17]


def read_sheet(path: Path, sheet: str | None = None) -> list[dict[str, str]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    header = [text(v) for v in rows[0]]
    result: list[dict[str, str]] = []
    for row in rows[1:]:
        if not any(text(v) for v in row):
            continue
        result.append({header[i]: text(row[i]) if i < len(row) else "" for i in range(len(header))})
    return result


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        return [{text(k): text(v) for k, v in row.items()} for row in reader]


def sheet_counts(path: Path) -> list[dict[str, Any]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    result = []
    for ws in wb.worksheets:
        result.append({"sheet": ws.title, "rows": max(ws.max_row - 1, 0)})
    wb.close()
    return result


def build(source: Path, out_dir: Path, private_dir: Path) -> dict[str, Any]:
    roster_path = source / "全校教学基础数据/05_学生花名册.xlsx"
    class_path = source / "全校教学基础数据/04_班级信息表.xlsx"
    change_path = source / "全校教学基础数据/10_学籍异动记录表.xlsx"
    admissions_path = source / "全校教学基础数据/13_招生录取数据（UTF-8）.csv"
    affairs_path = source / "思科职院AI资料库（共享）/02_学工业务数据（只读）/学工业务数据_2026年9-10月.xlsx"
    registration_path = source / "思科职院AI资料库（共享）/03_教务业务数据（只读）/学籍注册进度_2026-2027学年.xlsx"
    schedule_path = source / "全校教学基础数据/08_排课表（2026-2027学年第一学期）.xlsx"

    for path in [roster_path, class_path, change_path, admissions_path]:
        if not path.exists():
            raise FileNotFoundError(path)

    roster_rows = read_sheet(roster_path, "数据")
    class_rows = read_sheet(class_path, "数据")
    change_rows = read_sheet(change_path, "数据")
    admissions = read_csv(admissions_path)

    classes: dict[str, dict[str, str]] = {}
    class_counts_by_name: Counter[str] = Counter()
    for row in class_rows:
        name = row.get("班级名称", "")
        if not name:
            continue
        classes[name] = row
        if row.get("班级简称"):
            classes[row["班级简称"]] = row
        class_counts_by_name[name] += 1

    # Deduplicate the roster by student_no. The delivery pack intentionally
    # contains 3 duplicate rows; stats are based on the unique population.
    unique: dict[str, dict[str, str]] = {}
    duplicate_rows: list[dict[str, str]] = []
    for row in roster_rows:
        no = row.get("学号", "")
        if not no:
            continue
        if no in unique:
            duplicate_rows.append(row)
            continue
        unique[no] = row

    students = sorted(
        unique.values(),
        key=lambda r: (
            int(r.get("入学年份") or 0),
            r.get("二级学院", ""),
            r.get("班级", ""),
            r.get("学号", ""),
        ),
    )

    # Stable demo UID; never derived from the real student number.
    uid_by_no: dict[str, str] = {}
    sequence_by_year: Counter[str] = Counter()
    for row in students:
        year = row.get("入学年份") or "0000"
        sequence_by_year[year] += 1
        uid_by_no[row["学号"]] = f"SK-{year}-{sequence_by_year[year]:06d}"

    # Cross-reference helpers.
    same_name_groups: dict[str, list[str]] = defaultdict(list)
    for row in students:
        same_name_groups[row.get("姓名", "")].append(row["学号"])

    class_not_found: list[dict[str, str]] = []
    class_not_found_names: set[str] = set()
    id_errors: list[dict[str, str]] = []
    missing_phone: list[dict[str, str]] = []
    missing_parent: list[dict[str, str]] = []
    transfer_conflicts: list[dict[str, str]] = []

    changes_by_no: dict[str, list[dict[str, str]]] = defaultdict(list)
    change_type_counts: Counter[str] = Counter()
    change_status_counts: Counter[str] = Counter()
    orphan_changes = 0
    for row in change_rows:
        no = row.get("学号", "")
        change_type_counts[row.get("异动类型", "") or "未分类"] += 1
        change_status_counts[row.get("审批状态", "") or "未填"] += 1
        if no not in uid_by_no:
            orphan_changes += 1
            continue
        changes_by_no[no].append(row)

    for row in students:
        no = row["学号"]
        name = row.get("姓名", "")
        class_name = row.get("班级", "")
        major = row.get("专业名称", "")
        id_no = row.get("身份证号", "")
        phone = row.get("本人电话", "")
        parent_phone = row.get("家长电话", "")

        if id_no and not id_valid(id_no):
            id_errors.append({"uid": uid_by_no[no], "name": mask_name(name)})
        if not phone:
            missing_phone.append({"uid": uid_by_no[no], "name": mask_name(name)})
        if not parent_phone:
            missing_parent.append({"uid": uid_by_no[no], "name": mask_name(name)})
        if class_name and class_name not in class_counts_by_name:
            class_not_found_names.add(class_name)
            class_not_found.append({"uid": uid_by_no[no], "name": mask_name(name), "class_name": class_name})

    # Known transfer-major difference: the roster keeps the first placement;
    # the change ledger holds the target. Count only approved transfer records.
    for row in change_rows:
        if "转专业" not in row.get("异动类型", ""):
            continue
        if "已批" not in row.get("审批状态", ""):
            continue
        no = row.get("学号", "")
        if no not in unique:
            continue
        roster_major = unique[no].get("专业名称", "")
        target = row.get("异动后去向", "")
        if roster_major and target and roster_major not in target and target not in roster_major:
            transfer_conflicts.append(
                {
                    "uid": uid_by_no[no],
                    "name": mask_name(unique[no].get("姓名", "")),
                    "change_no": row.get("异动编号", ""),
                    "from_major": roster_major,
                    "to": target,
                }
            )

    # Admissions ↔ 2026 roster comparison by ID. Counts only; never emit IDs.
    roster_2026_ids = {r.get("身份证号", "").upper() for r in students if r.get("入学年份") == "2026" and r.get("身份证号")}
    admission_ids = {r.get("身份证号", "").upper() for r in admissions if r.get("身份证号")}
    admitted_not_in_roster = len(admission_ids - roster_2026_ids)
    roster_2026_not_admitted = len(roster_2026_ids - admission_ids)

    # Public student records: UID + masked PII + non-sensitive fields.
    public_students: list[dict[str, Any]] = []
    for row in students:
        no = row["学号"]
        class_name = row.get("班级", "")
        class_info = classes.get(class_name) or classes.get(row.get("班级简称", "")) or {}
        status = row.get("学籍状态", "") or "其他"
        flags: list[str] = []
        if row.get("身份证号") and not id_valid(row.get("身份证号", "")):
            flags.append("身份证校验异常")
        if not row.get("本人电话"):
            flags.append("缺本人电话")
        if not row.get("家长电话"):
            flags.append("缺家长电话")
        if class_name and class_name not in class_counts_by_name:
            flags.append("班级不在班级表")
        change_count = len(changes_by_no.get(no, []))
        if change_count:
            flags.append("有学籍异动")
        public_students.append(
            {
                "uid": uid_by_no[no],
                "name": mask_name(row.get("姓名", "")),
                "gender": row.get("性别", ""),
                "college": row.get("二级学院", ""),
                "major": row.get("专业名称", ""),
                "class_name": class_name,
                "class_short": row.get("班级简称", ""),
                "grade": row.get("年级", ""),
                "enrollment_year": int(row["入学年份"]) if row.get("入学年份", "").isdigit() else None,
                "status": status,
                "status_tone": STATUS_TONE.get(status, "muted"),
                "counselor": display_counselor(class_info.get("辅导员", "")) or "—",
                "phone": mask_phone(row.get("本人电话", "")),
                "id_card": mask_id(row.get("身份证号", "")),
                "source_region": row.get("生源地", ""),
                "is_active": status in ("在籍", "跟读", "预科"),
                "change_count": change_count,
                "flags": flags,
            }
        )

    public_students.sort(
        key=lambda s: (-(s["enrollment_year"] or 0), s["college"], s["class_name"], s["uid"])
    )

    # Public change records, keyed by UID only.
    public_changes: list[dict[str, Any]] = []
    for row in change_rows:
        no = row.get("学号", "")
        if no not in uid_by_no:
            continue
        public_changes.append(
            {
                "uid": uid_by_no[no],
                "change_no": row.get("异动编号", ""),
                "type": row.get("异动类型", ""),
                "reason": row.get("异动原因", ""),
                "date": row.get("异动日期", ""),
                "target": row.get("异动后去向", ""),
                "status": row.get("审批状态", ""),
            }
        )

    # Class summary, using the roster count rather than the class table's
    # self-reported count (the library's stated rule).
    class_students: Counter[str] = Counter()
    class_status: dict[str, Counter[str]] = defaultdict(Counter)
    for row in students:
        class_name = row.get("班级", "")
        class_students[class_name] += 1
        class_status[class_name][row.get("学籍状态", "")] += 1

    class_summary: list[dict[str, Any]] = []
    for name, count in sorted(class_students.items(), key=lambda kv: (-kv[1], kv[0])):
        info = classes.get(name, {})
        class_summary.append(
            {
                "class_name": name,
                "class_short": info.get("班级简称", ""),
                "class_code": info.get("班级编码", ""),
                "college": info.get("二级学院", ""),
                "major": info.get("专业名称", ""),
                "counselor": display_counselor(info.get("辅导员", "")),
                "students": count,
                "status": dict(class_status[name]),
            }
        )

    college_counts: Counter[str] = Counter()
    college_active: Counter[str] = Counter()
    grade_counts: Counter[str] = Counter()
    major_counts: Counter[str] = Counter()
    counselor_set: set[str] = set()
    status_counts: Counter[str] = Counter()
    for row in students:
        college = row.get("二级学院", "") or "未填"
        college_counts[college] += 1
        if row.get("学籍状态") in ("在籍", "跟读", "预科"):
            college_active[college] += 1
        grade_counts[row.get("年级", "") or "未填"] += 1
        major_counts[row.get("专业名称", "") or "未填"] += 1
        status = row.get("学籍状态", "") or "其他"
        status_counts[status] += 1
        class_name = row.get("班级", "")
        info = classes.get(class_name) or classes.get(row.get("班级简称", "")) or {}
        if info.get("辅导员"):
            counselor_set.add(display_counselor(info["辅导员"]))

    # Class schedule (read-only, by class) from the academic affairs export.
    # The schedule file uses class short names; normalize to the class table.
    schedule_rows = read_sheet(schedule_path, "数据") if schedule_path.exists() else []
    short_to_full = {
        row.get("班级简称", ""): row.get("班级名称", "")
        for row in class_rows
        if row.get("班级简称") and row.get("班级名称")
    }
    full_to_short = {full: short for short, full in short_to_full.items()}
    full_names = {row.get("班级名称", "") for row in class_rows if row.get("班级名称")}

    def resolve_class(raw: str) -> tuple[str, str] | None:
        raw = raw.strip()
        if raw in full_names:
            return raw, full_to_short.get(raw, raw)
        if raw in short_to_full:
            return short_to_full[raw], raw
        trimmed = raw[:-1] if raw.endswith("班") else raw
        if trimmed in short_to_full:
            return short_to_full[trimmed], trimmed
        if raw + "班" in full_names:
            return raw + "班", raw
        return None

    schedule: list[dict[str, Any]] = []
    schedule_unmatched = 0
    for row in schedule_rows:
        resolved = resolve_class(row.get("上课班级", ""))
        if not resolved:
            schedule_unmatched += 1
            continue
        class_name, class_short = resolved
        weekday = row.get("星期", "").replace("星期", "周")
        schedule.append(
            {
                "class_name": class_name,
                "class_short": class_short,
                "course": row.get("课程名称", ""),
                "teacher": row.get("任课教师", ""),
                "weekday": weekday,
                "period": row.get("节次", ""),
                "weeks": row.get("周次", ""),
                "room": row.get("教室", ""),
                "campus": row.get("校区", ""),
                "term": row.get("学年学期", ""),
                "note": row.get("备注", ""),
            }
        )

    period_times = [
        {"period": "1-2节", "start": "08:00", "end": "09:40", "slot": "上午"},
        {"period": "3-4节", "start": "10:00", "end": "11:40", "slot": "上午"},
        {"period": "5-6节", "start": "14:00", "end": "15:40", "slot": "下午"},
        {"period": "7-8节", "start": "16:00", "end": "17:40", "slot": "下午"},
        {"period": "9-10节", "start": "19:00", "end": "20:40", "slot": "晚上"},
    ]

    # Student-affairs sheets: counts only, no personal details.
    affairs: list[dict[str, Any]] = []
    if affairs_path.exists():
        for item in sheet_counts(affairs_path):
            affairs.append(item)

    registration: dict[str, Any] = {}
    if registration_path.exists():
        wb = load_workbook(registration_path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            header = [text(v) for v in rows[0]]
            records = [
                {header[i]: text(row[i]) if i < len(row) else "" for i in range(len(header))}
                for row in rows[1:]
                if any(text(v) for v in row)
            ]
            key = "new" if "新生" in ws.title else "old"
            target = "新生总数" if key == "new" else "应注册人数"
            registered = "在籍(已注册)" if key == "new" else "已注册(在籍)"
            total = sum(int(r[target]) for r in records if r.get(target, "").isdigit())
            done = sum(int(r[registered]) for r in records if r.get(registered, "").isdigit())
            registration[key] = {
                "label": ws.title,
                "classes": len(records),
                "total": total,
                "registered": done,
                "rate": round(done / total * 100, 1) if total else None,
            }
        wb.close()

    same_name_all_count = sum(1 for name, nos in same_name_groups.items() if name and len(nos) > 1)
    same_name_class_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in students:
        same_name_class_groups[(row.get("姓名", ""), row.get("班级", ""))].append(row["学号"])

    same_name_examples = []
    same_name_groups_count = 0
    for (name, class_name), nos in same_name_class_groups.items():
        if name and len(nos) > 1:
            same_name_groups_count += 1
            same_name_examples.append(
                {
                    "name": mask_name(name),
                    "class_name": class_name,
                    "count": len(nos),
                    "uids": [uid_by_no[n] for n in nos[:4]],
                }
            )

    data_quality = {
        "duplicate_rows": {
            "count": len(duplicate_rows),
            "label": "重复学号行",
            "description": "花名册中的完全重复行；统计以去重后人数为准。",
        },
        "same_name_groups": {
            "count": same_name_groups_count,
            "label": "同班同名（重点核对）",
            "description": "同一个班内出现同名但不同学号的学生；跨表核对必须以学号为键，不能按姓名匹配。",
            "examples": same_name_examples[:6],
        },
        "same_name_all": {
            "count": same_name_all_count,
            "label": "同名同姓（全库提示）",
            "description": "全库同名同姓很常见，不等于错误；只作为核对提示，任何匹配都必须以学号为键。",
            "examples": [],
        },
        "id_invalid": {
            "count": len(id_errors),
            "label": "身份证校验异常",
            "description": "位数或校验位不正确；不得猜测补齐，需人工复核。",
            "examples": id_errors[:6],
        },
        "missing_phone": {
            "count": len(missing_phone),
            "label": "缺本人电话",
            "description": "本人电话为空，需学生自助补录或辅导员核对。",
            "examples": missing_phone[:6],
        },
        "missing_parent": {
            "count": len(missing_parent),
            "label": "缺家长电话",
            "description": "家长联系方式为空，需补录；不得用其他字段推测。",
            "examples": missing_parent[:6],
        },
        "class_not_found": {
            "count": len(class_not_found),
            "class_names": len(class_not_found_names),
            "label": "班级不在班级表",
            "description": "花名册中的班级名称无法在班级信息表中匹配；需核对班级编码。",
            "examples": class_not_found[:6],
        },
        "transfer_conflicts": {
            "count": len(transfer_conflicts),
            "label": "转专业已批但花名册未更新",
            "description": "以学号为键关联异动表与花名册；花名册保留首次编班，去向以异动表为准。",
            "examples": transfer_conflicts[:6],
        },
        "admissions": {
            "count": admitted_not_in_roster + roster_2026_not_admitted,
            "label": "招生与 2026 级花名册差异",
            "description": "按身份证号比对；包含已录取未报到、跟读/预科等口径差异。",
            "admitted_not_in_roster": admitted_not_in_roster,
            "roster_2026_not_admitted": roster_2026_not_admitted,
            "admissions_rows": len(admissions),
            "roster_2026_rows": len(roster_2026_ids),
        },
    }

    metrics = {
        "disclaimer": "演示数据，非真实人员信息；仅用于流程验证，不得用于评奖、处分、注册或上报。",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": str(source),
        "total_students": len(students),
        "total_classes": len({r.get("班级名称", "") for r in class_rows if r.get("班级名称")}),
        "roster_class_names": len(class_students),
        "total_colleges": len([c for c in college_counts if c != "未填"]),
        "total_majors": len([m for m in major_counts if m != "未填"]),
        "total_counselors": len(counselor_set),
        "status_counts": [
            {"name": s, "count": status_counts.get(s, 0), "tone": STATUS_TONE.get(s, "muted")}
            for s in STATUS_ORDER + [s for s in status_counts if s not in STATUS_ORDER]
        ],
        "college_counts": [
            {"name": c, "count": n, "active": college_active.get(c, 0)}
            for c, n in sorted(college_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "grade_counts": [
            {"name": g, "count": n} for g, n in sorted(grade_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "top_majors": [
            {"name": m, "count": n} for m, n in sorted(major_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
        ],
        "change_total": len(change_rows),
        "change_type_counts": [
            {"name": t, "count": n} for t, n in sorted(change_type_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "change_status_counts": [
            {"name": s, "count": n} for s, n in sorted(change_status_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "orphan_changes": orphan_changes,
        "registration": registration,
        "data_quality": data_quality,
        "affairs": affairs,
        "schedule_meta": {
            "rows": len(schedule),
            "unmatched_rows": schedule_unmatched,
            "classes": len({row["class_name"] for row in schedule}),
            "current_week": 8,
            "period_times": period_times,
            "note": "按 2026-2027 学年第一学期第 8 周演示；作息时间待教务处确认。",
        },
        "source_files": [
            {"name": p.name, "rows": len(rows) if isinstance(rows, list) else 0}
            for p, rows in [
                (roster_path, roster_rows),
                (class_path, class_rows),
                (change_path, change_rows),
                (admissions_path, admissions),
                (schedule_path, schedule_rows),
            ]
        ],
    }

    payload = {
        "meta": {
            "title": "思科职院学生数据中台 · 本地演示",
            "source": "WorkBuddy 校园试点交付材料（虚构数据）",
            "data_nature": "演示数据，非真实人员信息",
            "uid_rule": "SK-<入学年份>-<6位流水>；与真实学号解耦",
            "generated_at": metrics["generated_at"],
        },
        "metrics": metrics,
        "students": public_students,
        "changes": public_changes,
        "class_summary": class_summary,
        "schedule": schedule,
        "anomalies": [
            data_quality["duplicate_rows"],
            data_quality["same_name_groups"],
            data_quality["same_name_all"],
            data_quality["id_invalid"],
            data_quality["missing_phone"],
            data_quality["missing_parent"],
            data_quality["class_not_found"],
            data_quality["transfer_conflicts"],
            data_quality["admissions"],
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "demo-data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_private_mapping(private_dir, students, uid_by_no, classes)
    write_four_sheet(out_dir, public_students, public_changes, data_quality, metrics)
    write_readme(out_dir, metrics)
    return payload


def write_private_mapping(
    private_dir: Path,
    students: Iterable[dict[str, str]],
    uid_by_no: dict[str, str],
    classes: dict[str, dict[str, str]],
) -> None:
    path = private_dir / "uid_map.private.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "uid",
                "student_no",
                "name",
                "id_card",
                "phone",
                "parent_name",
                "parent_phone",
                "address",
                "college",
                "major",
                "class_name",
            ]
        )
        for row in students:
            no = row["学号"]
            class_info = classes.get(row.get("班级", "")) or classes.get(row.get("班级简称", "")) or {}
            writer.writerow(
                [
                    uid_by_no[no],
                    no,
                    row.get("姓名", ""),
                    row.get("身份证号", ""),
                    row.get("本人电话", ""),
                    row.get("家长姓名", ""),
                    row.get("家长电话", ""),
                    row.get("家庭住址", ""),
                    row.get("二级学院", ""),
                    row.get("专业名称", ""),
                    row.get("班级", ""),
                ]
            )
    (private_dir / "README.txt").write_text(
        "本目录包含 UID 与原学号/姓名/身份证/电话的映射。\n"
        "仅供数据管理员本地核对，不得进入演示数据库、不得上传云端、不得提交 Git。\n"
        "真实数据接入时，必须加密保存并限定访问人；演示环境只使用脱敏副本。\n",
        encoding="utf-8",
    )


def write_four_sheet(
    out_dir: Path,
    students: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    data_quality: dict[str, Any],
    metrics: dict[str, Any],
) -> None:
    wb = Workbook()
    header_fill = PatternFill("solid", fgColor="E8E4D8")
    header_font = Font(bold=True)
    thin = Alignment(vertical="top", wrap_text=True)

    ws = wb.active
    ws.title = "标准化数据"
    headers = ["UID", "姓名", "性别", "二级学院", "专业", "班级", "年级", "入学年份", "学籍状态", "辅导员", "本人电话", "身份证", "生源地", "异动次数"]
    ws.append(headers)
    for s in students:
        ws.append(
            [
                s["uid"],
                s["name"],
                s["gender"],
                s["college"],
                s["major"],
                s["class_name"],
                s["grade"],
                s["enrollment_year"],
                s["status"],
                s["counselor"],
                s["phone"],
                s["id_card"],
                s["source_region"],
                s["change_count"],
            ]
        )

    ws2 = wb.create_sheet("异常清单")
    ws2.append(["异常类型", "数量", "UID", "姓名", "说明"])
    for key, item in data_quality.items():
        examples = item.get("examples") or []
        if examples:
            for ex in examples:
                ws2.append([item["label"], item["count"], ex.get("uid", ""), ex.get("name", ""), item["description"]])
        else:
            detail = item["description"]
            if key == "duplicate_rows":
                detail += "（重复行不展示原始明细）"
            ws2.append([item["label"], item["count"], "", "", detail])

    ws3 = wb.create_sheet("字段映射")
    ws3.append(["源字段", "标准字段", "处理方式", "是否待确认"])
    mapping = [
        ("序号", "—", "丢弃", "否"),
        ("学号", "内部匹配键", "不导出；用于跨表核对", "否"),
        ("姓名", "姓名（脱敏）", "首字 + *", "否"),
        ("性别", "性别", "原样", "否"),
        ("出生日期", "出生日期", "YYYY-MM-DD", "否"),
        ("身份证号", "身份证（脱敏）", "仅保留后4位", "否"),
        ("考生号", "考生号", "不进入演示库", "否"),
        ("年级/入学年份", "年级/入学年份", "原样", "否"),
        ("学籍状态", "学籍状态", "按口径归一", "否"),
        ("二级学院/专业名称/班级", "组织归属", "按班级表与专业表核对", "否"),
        ("本人电话/家长电话", "联系方式（脱敏）", "中间4位掩码", "否"),
        ("家庭住址", "生源地", "只保留市/区", "否"),
        ("宿舍号/是否住宿", "住宿信息", "演示不展示", "否"),
        ("异动表", "异动记录", "以学号为键关联；去向以异动表为准", "否"),
    ]
    for row in mapping:
        ws3.append(row)

    ws4 = wb.create_sheet("核对汇总")
    ws4.append(["指标", "值"])
    summary = [
        ("数据性质", metrics["disclaimer"]),
        ("学生总数（去重后）", metrics["total_students"]),
        ("班级数（班级表）", metrics["total_classes"]),
        ("花名册班级名称数", metrics.get("roster_class_names", "")),
        ("学院数", metrics["total_colleges"]),
        ("专业数", metrics["total_majors"]),
        ("辅导员数", metrics["total_counselors"]),
        ("异动记录数", metrics["change_total"]),
        ("重复学号行", metrics["data_quality"]["duplicate_rows"]["count"]),
        ("同班同名（重点核对）", metrics["data_quality"]["same_name_groups"]["count"]),
        ("同名同姓（全库提示）", metrics["data_quality"]["same_name_all"]["count"]),
        ("身份证校验异常", metrics["data_quality"]["id_invalid"]["count"]),
        ("缺本人电话", metrics["data_quality"]["missing_phone"]["count"]),
        ("缺家长电话", metrics["data_quality"]["missing_parent"]["count"]),
        ("班级不在班级表", metrics["data_quality"]["class_not_found"]["count"]),
        ("转专业已批但花名册未更新", metrics["data_quality"]["transfer_conflicts"]["count"]),
        ("招生与2026级差异", metrics["data_quality"]["admissions"]["count"]),
        ("UID 规则", "SK-<入学年份>-<6位流水>"),
        ("说明", "本文件仅用于流程演示，不得用于真实业务。"),
    ]
    for row in summary:
        ws4.append(row)

    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.freeze_panes = "A2"
        for idx, column in enumerate(sheet.columns, 1):
            width = min(max(len(str(c.value or "")) for c in column) + 2, 70)
            sheet.column_dimensions[get_column_letter(idx)].width = max(width, 10)
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = thin

    wb.save(out_dir / "four-sheet.xlsx")


def write_readme(out_dir: Path, metrics: dict[str, Any]) -> None:
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                "# 本地演示数据",
                "",
                "- 数据性质：**演示数据，非真实人员信息**。源数据来自 WorkBuddy 校园试点的虚构数据集。",
                f"- 去重后学生数：**{metrics['total_students']}**；班级：**{metrics['total_classes']}**；学院：**{metrics['total_colleges']}**。",
                "- UID：`SK-<入学年份>-<6位流水>`，与原始学号解耦；页面不展示原始学号。",
                "- 姓名、身份证、电话已脱敏；家庭住址只保留到市/区。",
                "- `demo-data.json`：本地演示页面数据；`four-sheet.xlsx`：标准化数据/异常清单/字段映射/核对汇总。",
                "- 生成脚本：`scripts/demo/build_demo_dataset.py`。",
                "- 辅导员中的 FD# 代码已映射为稳定的虚构别名，便于演示。",
                "- 本目录不得放入真实学生数据；真实数据的映射表必须离线加密保存。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local de-identified demo dataset")
    parser.add_argument(
        "--source",
        default=r"C:/Users/luofeng/Desktop/思科职院AI试点交付材料",
        help="WorkBuddy pilot delivery folder",
    )
    parser.add_argument("--out", default="demo-api/data", help="server-only demo data output directory")
    parser.add_argument(
        "--private",
        default=r"Z:/ai/本地部署/demo-private",
        help="private UID mapping directory (never served by the web app)",
    )
    args = parser.parse_args()

    source = Path(args.source)
    out_dir = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    private_dir = Path(args.private)
    payload = build(source, out_dir, private_dir)
    print("demo dataset built")
    print(f"students={payload['metrics']['total_students']} classes={payload['metrics']['total_classes']}")
    print(f"output={out_dir}")
    print(f"private mapping={private_dir} (do not commit or serve)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
