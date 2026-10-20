"""结构校验规则（Pandera）。

职责边界（与业务校验严格区分）：
- 本文件只负责：必填、字段类型、长度、受控枚举、数值范围。
- 不负责：学号是否存在于数据库、跨批次重复、异动类型与学籍状态联动。
  这些属于业务规则，见 service.py 的 business_issues。
"""
from __future__ import annotations

import pandera.pandas as pa
from pandera import Check

from .mapping import CHANGE_TYPE_CODES, RECORD_STATUS_CODES, STUDENT_STATUS_CODES

_MAX_TEXT = 100


def _isin_or_null(codes: list[str]) -> Check:
    """允许为空，非空时必须命中受控值。"""
    return Check(lambda s: s.isna() | s.isin(codes), ignore_na=False)


STUDENT_SCHEMA = pa.DataFrameSchema(
    columns={
        "student_no": pa.Column(str, Check.str_length(1, 32), nullable=False),
        "student_name": pa.Column(str, Check.str_length(1, 100), nullable=False),
        "college_name": pa.Column(str, Check.str_length(max_value=_MAX_TEXT), nullable=True),
        "major_name": pa.Column(str, Check.str_length(max_value=_MAX_TEXT), nullable=True),
        "class_name": pa.Column(str, Check.str_length(max_value=_MAX_TEXT), nullable=True),
        "enrollment_year": pa.Column("Int16", Check.in_range(1990, 2100), nullable=True),
        "student_status": pa.Column(str, _isin_or_null(STUDENT_STATUS_CODES), nullable=True),
    },
    coerce=True,
    strict=False,
)

CHANGE_SCHEMA = pa.DataFrameSchema(
    columns={
        "student_no": pa.Column(str, Check.str_length(1, 32), nullable=False),
        "change_type": pa.Column(str, _isin_or_null(CHANGE_TYPE_CODES), nullable=True),
        "effective_date": pa.Column(pa.DateTime, nullable=True),
        "change_reason": pa.Column(str, Check.str_length(max_value=500), nullable=True),
        "record_status": pa.Column(str, _isin_or_null(RECORD_STATUS_CODES), nullable=True),
    },
    coerce=True,
    strict=False,
)

SCHEMAS = {"students": STUDENT_SCHEMA, "student_changes": CHANGE_SCHEMA}
