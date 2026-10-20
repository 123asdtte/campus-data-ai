"""列名映射与受控枚举。

约定：
- 别名表是唯一可维护入口：新增表头写法只需在此追加，不必改解析代码。
- 别名按“规范化后完全相等”命中为 1.0；包含关系与模糊匹配由 parsing.py 处理。
- 枚举同时接受中文标签与内部代码；无法识别时保留原值，交由校验环节报 INVALID_ENUM。
"""
from __future__ import annotations

import re
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
    # 学号
    "学号": "student_no",
    "学生学号": "student_no",
    "学生编号": "student_no",
    "学籍号": "student_no",
    "学号编号": "student_no",
    # 姓名
    "姓名": "student_name",
    "学生姓名": "student_name",
    "学生名称": "student_name",
    "名字": "student_name",
    # 学院
    "学院": "college_name",
    "所属学院": "college_name",
    "学院名称": "college_name",
    "二级学院": "college_name",
    "院系": "college_name",
    "系部": "college_name",
    "所在学院": "college_name",
    # 专业
    "专业": "major_name",
    "专业名称": "major_name",
    "所学专业": "major_name",
    "专业方向": "major_name",
    # 班级
    "班级": "class_name",
    "行政班": "class_name",
    "行政班级": "class_name",
    "班级名称": "class_name",
    "所在班级": "class_name",
    "就读班级": "class_name",
    # 入学年份
    "入学年份": "enrollment_year",
    "年级": "enrollment_year",
    "入学年": "enrollment_year",
    "入学时间": "enrollment_year",
    # 状态
    "在校状态": "student_status",
    "学籍状态": "student_status",
    "学生状态": "student_status",
    "状态": "student_status",
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
    "学生编号": "student_no",
    "学籍号": "student_no",
    "异动类型": "change_type",
    "学籍异动类型": "change_type",
    "异动类别": "change_type",
    "异动种类": "change_type",
    "生效日期": "effective_date",
    "异动日期": "effective_date",
    "发生日期": "effective_date",
    "异动时间": "effective_date",
    "日期": "effective_date",
    "异动原因": "change_reason",
    "原因": "change_reason",
    "说明": "change_reason",
    "备注": "change_reason",
    "记录状态": "record_status",
    "处理状态": "record_status",
    "状态": "record_status",
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


# ---------------------------------------------------------------- 规范化
def normalize_header(value: object) -> str:
    """去换行、全角空格、括号注释与标点，统一小写。

    例：「学号（必填）」→「学号」；「 学生 姓名 」→「学生姓名」。
    """
    text = "" if value is None else str(value)
    text = text.replace("\u3000", " ").replace("\r", "").replace("\n", "")
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    text = re.sub(r"[*＊:：\s]", "", text)
    return text.strip().lower()


def build_alias_index(target: str) -> Dict[str, str]:
    """规范化别名 → 字段名。同时把字段代码本身作为别名，兼容英文表头。"""
    aliases: Dict[str, str] = TARGETS[target]["aliases"]  # type: ignore[assignment]
    index: Dict[str, str] = {}
    for alias, field in aliases.items():
        index[normalize_header(alias)] = field
    for field in TARGETS[target]["fields"]:  # type: ignore[union-attr]
        index.setdefault(normalize_header(field), field)
    return index
