"""校验层：类型预转换、Pandera 结构校验、行号偏移。

这些函数不访问数据库，属于「改一行就可能悄悄放宽数据质量」的地方，
是本轮自动化测试的重点覆盖对象。

行号约定（与 service.py 保持一致）：Excel 行号 = DataFrame 索引 + 2 + 表头偏移。
索引 0 是第一条数据，+1 是表头，+1 让行号从 1 起算。
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.service import (
    _code_for_failure,
    _encode_enums,
    _normalize_frame,
    _pre_coerce,
    _structural_issues,
)


def students_frame(**overrides) -> pd.DataFrame:
    """一份合法的学生数据，按需覆盖某一列以构造异常。"""
    base = {
        "student_no": ["S001", "S002"],
        "student_name": ["甲", "乙"],
        "college_name": ["计算机学院", "计算机学院"],
        "major_name": ["软件技术", "软件技术"],
        "class_name": ["软件2601", "软件2601"],
        "enrollment_year": pd.array([2026, 2026], dtype="Int64"),
        "student_status": ["enrolled", "enrolled"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def codes(issues) -> list[tuple[int, str]]:
    return [(item.row_number, item.issue_code) for item in issues]


class TestNormalizeFrame:
    def test_空白字符串视为缺失(self) -> None:
        frame = _normalize_frame(pd.DataFrame({"姓名": ["  ", "甲"]}))
        assert frame.at[0, "姓名"] is None
        assert frame.at[1, "姓名"] == "甲"

    def test_去除全角空格并strip列名(self) -> None:
        frame = _normalize_frame(pd.DataFrame({" 学\u3000号 ": ["S1"]}))
        assert list(frame.columns) == ["学 号"]


class TestEncodeEnums:
    def test_中文标签转内部代码(self) -> None:
        frame = _encode_enums(pd.DataFrame({"student_status": ["在校", "休学", "退学"]}))
        assert frame["student_status"].tolist() == ["enrolled", "suspended", "withdrawn"]

    def test_已是代码时保持不变(self) -> None:
        frame = _encode_enums(pd.DataFrame({"student_status": ["enrolled"]}))
        assert frame["student_status"].tolist() == ["enrolled"]

    def test_无法识别时保留原值交给校验报错(self) -> None:
        """这里不吞掉非法值，否则用户看不到问题。"""
        frame = _encode_enums(pd.DataFrame({"student_status": ["在读"]}))
        assert frame["student_status"].tolist() == ["在读"]

    def test_空值保持为空(self) -> None:
        frame = _encode_enums(pd.DataFrame({"change_type": [None]}))
        assert frame["change_type"].tolist() == [None]


class TestPreCoerceStudents:
    def test_入学年份转为整数(self) -> None:
        frame, issues = _pre_coerce(students_frame(enrollment_year=["2026", "2025"]), "students")
        assert frame["enrollment_year"].tolist() == [2026, 2025]
        assert str(frame["enrollment_year"].dtype) == "Int64"
        assert issues == []

    def test_非数字年份报错并置空(self) -> None:
        frame, issues = _pre_coerce(students_frame(enrollment_year=["2026", "二〇二六"]), "students")

        assert codes(issues) == [(3, "INVALID_ENUM")]
        assert issues[0].field_name == "enrollment_year"
        assert "必须是数字" in issues[0].issue_message
        assert pd.isna(frame.at[1, "enrollment_year"])

    def test_小数年份报错(self) -> None:
        _frame, issues = _pre_coerce(students_frame(enrollment_year=["2026.5", "2025"]), "students")

        assert codes(issues) == [(2, "INVALID_ENUM")]
        assert "必须是整数" in issues[0].issue_message

    def test_空入学年份不报错(self) -> None:
        _frame, issues = _pre_coerce(students_frame(enrollment_year=[None, "2025"]), "students")
        assert issues == []

    def test_空的在校状态默认为在校(self) -> None:
        frame, _issues = _pre_coerce(students_frame(student_status=[None, "suspended"]), "students")
        assert frame["student_status"].tolist() == ["enrolled", "suspended"]

    def test_行号随表头偏移(self) -> None:
        """表头在第 4 行时，第一条数据是 Excel 第 5 行。"""
        _frame, issues = _pre_coerce(
            students_frame(enrollment_year=["坏值", "2025"]), "students", row_offset=3
        )
        assert codes(issues) == [(5, "INVALID_ENUM")]


class TestPreCoerceChanges:
    def changes(self, effective_date) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "student_no": ["S001", "S002"],
                "change_type": ["suspend", "resume"],
                "effective_date": effective_date,
                "change_reason": [None, "转专业"],
                "record_status": [None, None],
            }
        )

    def test_合法日期被解析(self) -> None:
        frame, issues = _pre_coerce(self.changes(["2026-03-01", "2026/04/02"]), "student_changes")

        assert issues == []
        assert str(frame.at[0, "effective_date"].date()) == "2026-03-01"
        assert str(frame.at[1, "effective_date"].date()) == "2026-04-02"

    def test_无法识别的日期报INVALID_DATE(self) -> None:
        _frame, issues = _pre_coerce(self.changes(["2026-03-01", "下周一"]), "student_changes")

        assert codes(issues) == [(3, "INVALID_DATE")]
        assert issues[0].field_name == "effective_date"

    def test_空的生效日期报缺失(self) -> None:
        _frame, issues = _pre_coerce(self.changes(["2026-03-01", None]), "student_changes")

        assert codes(issues) == [(3, "MISSING_REQUIRED")]
        assert issues[0].field_name == "effective_date"

    def test_记录状态空值默认为草稿(self) -> None:
        frame, _issues = _pre_coerce(self.changes(["2026-03-01", "2026-03-02"]), "student_changes")
        assert frame["record_status"].tolist() == ["draft", "draft"]


class TestStructuralIssues:
    def test_合法数据无异常(self) -> None:
        assert _structural_issues(students_frame(), "students") == []

    def test_缺姓名报缺失并定位到行(self) -> None:
        frame = students_frame(student_name=["甲", None])
        issues = _structural_issues(frame, "students")

        assert (3, "MISSING_REQUIRED") in codes(issues)
        assert issues[0].field_name == "student_name"
        assert issues[0].severity == "error"

    def test_缺姓名时行号带表头偏移(self) -> None:
        """场景 11：表头第 4 行、第 2 条数据缺姓名 → Excel 第 6 行。"""
        frame = students_frame(student_name=["甲", None])
        issues = _structural_issues(frame, "students", row_offset=3)

        assert codes(issues) == [(6, "MISSING_REQUIRED")]

    def test_学号超长报VALUE_TOO_LONG(self) -> None:
        frame = students_frame(student_no=["S" * 33, "S002"])
        issues = _structural_issues(frame, "students")

        assert codes(issues) == [(2, "VALUE_TOO_LONG")]
        assert issues[0].field_name == "student_no"

    def test_学号为空报缺失(self) -> None:
        frame = students_frame(student_no=[None, "S002"])
        issues = _structural_issues(frame, "students")

        assert codes(issues) == [(2, "MISSING_REQUIRED")]

    def test_入学年份超范围报错(self) -> None:
        frame = students_frame(enrollment_year=pd.array([1800, 2026], dtype="Int64"))
        issues = _structural_issues(frame, "students")

        assert codes(issues) == [(2, "INVALID_ENUM")]
        assert issues[0].field_name == "enrollment_year"

    def test_非法在校状态报错(self) -> None:
        frame = students_frame(student_status=["在读", "enrolled"])
        issues = _structural_issues(frame, "students")

        assert codes(issues) == [(2, "INVALID_ENUM")]
        assert issues[0].field_name == "student_status"

    def test_同一行同一列的重复异常只报一次(self) -> None:
        frame = students_frame(student_name=[None, None])
        issues = _structural_issues(frame, "students")

        assert len(issues) == len(set(codes(issues)))

    def test_异动表缺学号报缺失(self) -> None:
        frame = pd.DataFrame(
            {
                "student_no": [None],
                "change_type": ["suspend"],
                "effective_date": [pd.Timestamp("2026-03-01")],
                "change_reason": [None],
                "record_status": ["draft"],
            }
        )
        issues = _structural_issues(frame, "student_changes")

        assert codes(issues) == [(2, "MISSING_REQUIRED")]


class TestIssueCodeMapping:
    @pytest.mark.parametrize(
        "check, column, is_missing, expected",
        [
            ("any_check", "student_no", True, "MISSING_REQUIRED"),
            ("str_length(1, 32)", "student_no", False, "VALUE_TOO_LONG"),
            ("in_range(1990, 2100)", "effective_date", False, "INVALID_DATE"),
            ("isin(['a'])", "student_status", False, "INVALID_ENUM"),
        ],
    )
    def test_异常码映射(self, check, column, is_missing, expected) -> None:
        assert _code_for_failure(check, column, is_missing) == expected
