"""列名映射与受控枚举。

设计原则：
- 中文表头 → 内部字段名的映射集中在此，页面与接口不重复维护。
- 枚举同时接受中文标签与内部代码；无法识别时保留原值，交由校验环节报 INVALID_ENUM。
"""
from __future__ import annotations

from typing import Dict, List

# ---------------------------------------------------------------- 学生信息
STUDENT_FIELDS: List[str] = [
    "student_no",
    "student_name",
    "college_name",
    "major_name",
    "class_name",
    "enrollment_year",
    "student_status",
]

STUDENT_LABELS: Dict[str, str] = {
    "student_no": "学号",
    "student_name": "姓名",
    "college_name": "学院",
    "major_name": "专业",
    "class_name": "班级",
    "enrollment_year": "入学年份",
    "student_status": "在校状态",
}

STUDENT_ALIASES: Dict[str, str] = {
    "学号": "student_no",
    "学生学号": "student_no",
    "姓名": "student_name",
    "学生姓名": "student_name",
    "学院": "college_name",
    "院系": "college_name",
    "二级学院": "college_name",
    "专业": "major_name",
    "班级": "class_name",
    "行政班": "class_name",
    "入学年份": "enrollment_year",
    "年级": "enrollment_year",
    "在校状态": "student_status",
    "学籍状态": "student_status",
}

# ---------------------------------------------------------------- 学籍异动
CHANGE_FIELDS: List[str] = [
    "student_no",
    "change_type",
    "effective_date",
    "change_reason",
    "record_status",
]

CHANGE_LABELS: Dict[str, str] = {
    "student_no": "学号",
    "change_type": "异动类型",
    "effective_date": "生效日期",
    "change_reason": "异动原因",
    "record_status": "记录状态",
}

CHANGE_ALIASES: Dict[str, str] = {
    "学号": "student_no",
    "学生学号": "student_no",
    "异动类型": "change_type",
    "学籍异动类型": "change_type",
    "生效日期": "effective_date",
    "异动日期": "effective_date",
    "发生日期": "effective_date",
    "异动原因": "change_reason",
    "原因": "change_reason",
    "记录状态": "record_status",
}

TARGETS: Dict[str, Dict[str, object]] = {
    "students": {
        "fields": STUDENT_FIELDS,
        "labels": STUDENT_LABELS,
        "aliases": STUDENT_ALIASES,
        "required": ["student_no", "student_name"],
    },
    "student_changes": {
        "fields": CHANGE_FIELDS,
        "labels": CHANGE_LABELS,
        "aliases": CHANGE_ALIASES,
        "required": ["student_no", "change_type", "effective_date"],
    },
}

# ---------------------------------------------------------------- 受控枚举
STUDENT_STATUS_MAP: Dict[str, str] = {
    "在校": "enrolled",
    "休学": "suspended",
    "退学": "withdrawn",
    "毕业": "graduated",
    "其他": "other",
    "enrolled": "enrolled",
    "suspended": "suspended",
    "withdrawn": "withdrawn",
    "graduated": "graduated",
    "other": "other",
}

CHANGE_TYPE_MAP: Dict[str, str] = {
    "休学": "suspend",
    "复学": "resume",
    "退学": "withdraw",
    "转专业": "transfer_major",
    "转学": "transfer_school",
    "保留学籍": "retain",
    "其他": "other",
    "suspend": "suspend",
    "resume": "resume",
    "withdraw": "withdraw",
    "transfer_major": "transfer_major",
    "transfer_school": "transfer_school",
    "retain": "retain",
    "other": "other",
}

RECORD_STATUS_MAP: Dict[str, str] = {
    "草稿": "draft",
    "待复核": "pending_review",
    "已确认": "confirmed",
    "已退回": "returned",
    "draft": "draft",
    "pending_review": "pending_review",
    "confirmed": "confirmed",
    "returned": "returned",
}

STUDENT_STATUS_CODES = ["enrolled", "suspended", "withdrawn", "graduated", "other"]
CHANGE_TYPE_CODES = ["suspend", "resume", "withdraw", "transfer_major", "transfer_school", "retain", "other"]
RECORD_STATUS_CODES = ["draft", "pending_review", "confirmed", "returned"]

ENUM_FIELDS: Dict[str, tuple] = {
    "student_status": (STUDENT_STATUS_MAP, STUDENT_STATUS_CODES),
    "change_type": (CHANGE_TYPE_MAP, CHANGE_TYPE_CODES),
    "record_status": (RECORD_STATUS_MAP, RECORD_STATUS_CODES),
}
