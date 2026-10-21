"""表头规范化与列名映射（纯函数，不触碰数据库）。

对应用例来源：docs/IMPORT-MAPPING-TEST.md §一 的场景 1、2、5、7、8，
以及 §2.3「手动映射优先级」。
"""
from __future__ import annotations

import pytest

from app.mapping import STUDENT_FIELDS, build_alias_index, normalize_header
from app.parsing import apply_overrides, auto_map, mapping_to_dict, required_missing


class TestNormalizeHeader:
    """表头规范化是别名匹配的前提，规则变动会连带影响全部映射结果。"""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("学号（必填）", "学号"),
            ("学号(必填)", "学号"),
            (" 学生\u3000姓名 ", "学生姓名"),
            ("学号\n", "学号"),
            ("学号：", "学号"),
            ("学号*", "学号"),
            ("Student_No", "student_no"),
        ],
    )
    def test_剥离注释与空白(self, raw: str, expected: str) -> None:
        assert normalize_header(raw) == expected

    def test_空值返回空串(self) -> None:
        assert normalize_header(None) == ""


class TestAliasIndex:
    def test_别名命中字段(self) -> None:
        index = build_alias_index("students")
        assert index["学号"] == "student_no"
        assert index["学生编号"] == "student_no"
        assert index["二级学院"] == "college_name"

    def test_字段代码本身也是别名(self) -> None:
        """兼容英文表头：直接写 student_no 也能识别。"""
        index = build_alias_index("students")
        for field in STUDENT_FIELDS:
            assert index[field] == field


class TestAutoMap:
    def test_标准表头全部精确匹配(self) -> None:
        columns = ["学号", "姓名", "学院", "专业", "班级", "入学年份", "在校状态"]
        matches = auto_map(columns, "students")

        assert [m.target for m in matches] == STUDENT_FIELDS
        assert all(m.method == "exact" for m in matches)
        assert all(m.confidence == 1.0 for m in matches)
        assert all(m.status == "matched" for m in matches)

    def test_中文别名变体(self) -> None:
        """场景 2：学生编号/学生名称/所属学院/专业名称/行政班级/学籍状态。"""
        columns = ["学生编号", "学生名称", "所属学院", "专业名称", "行政班级", "入学年份", "学籍状态"]
        matched = mapping_to_dict(auto_map(columns, "students"))

        assert matched == {
            "学生编号": "student_no",
            "学生名称": "student_name",
            "所属学院": "college_name",
            "专业名称": "major_name",
            "行政班级": "class_name",
            "入学年份": "enrollment_year",
            "学籍状态": "student_status",
        }

    def test_列顺序变化不影响映射(self) -> None:
        """场景 8：班级/姓名/学号/学院乱序。"""
        matched = mapping_to_dict(auto_map(["班级", "姓名", "学号", "学院"], "students"))
        assert matched == {
            "班级": "class_name",
            "姓名": "student_name",
            "学号": "student_no",
            "学院": "college_name",
        }

    def test_未知列不强行分配(self) -> None:
        """场景 5：备注/辅导员/宿舍号必须保持未匹配。"""
        columns = ["学号", "姓名", "备注", "辅导员", "宿舍号"]
        matches = auto_map(columns, "students")
        unmatched = [m.source for m in matches if m.target is None]

        assert unmatched == ["备注", "辅导员", "宿舍号"]
        assert all(m.status == "unmatched" for m in matches if m.source in unmatched)

    def test_包含关系命中并标注方法(self) -> None:
        """「录取专业」不含于别名表，靠包含关系命中「专业」。"""
        match = next(m for m in auto_map(["录取专业"], "students") if m.source == "录取专业")

        assert match.target == "major_name"
        assert match.method == "contains"
        assert match.confidence == 0.78

    def test_同一字段被多列命中时后者标为冲突(self) -> None:
        """场景 7：学号与学生学号同时命中，只保留置信度最高的一列。"""
        matches = auto_map(["学号", "学生学号", "姓名", "班级"], "students")
        by_source = {m.source: m for m in matches}

        assert by_source["学号"].target == "student_no"
        assert by_source["学号"].status == "matched"
        assert by_source["学生学号"].target is None
        assert by_source["学生学号"].status == "conflict"

    def test_空列名不产生匹配(self) -> None:
        assert auto_map([""], "students")[0].target is None


class TestApplyOverrides:
    """手动调整的优先级必须高于自动匹配，否则用户改了映射却不生效。"""

    def test_手动指定接管已被占用的字段(self) -> None:
        matches = auto_map(["学号", "学生学号", "姓名", "班级"], "students")
        updated = {m.source: m for m in apply_overrides(matches, {"学生学号": "student_no"})}

        assert updated["学生学号"].target == "student_no"
        assert updated["学生学号"].method == "manual"
        assert updated["学生学号"].confidence == 1.0
        assert updated["学生学号"].status == "matched"
        # 原「学号」列被解除占用，而不是继续静默写入
        assert updated["学号"].target is None
        assert updated["学号"].status == "conflict"

    def test_置空表示忽略该列(self) -> None:
        matches = auto_map(["学号", "姓名"], "students")
        updated = {m.source: m for m in apply_overrides(matches, {"学号": None})}

        assert updated["学号"].target is None
        assert updated["学号"].status == "unmatched"

    def test_未知来源被忽略(self) -> None:
        matches = auto_map(["学号", "姓名"], "students")
        result = apply_overrides(matches, {"不存在的列": "student_no"})

        assert [m.target for m in result] == ["student_no", "student_name"]


class TestRequiredMissing:
    def test_缺姓名(self) -> None:
        """场景 6：只有学号/学院/专业时，缺 student_name。"""
        matches = auto_map(["学号", "学院", "专业"], "students")
        assert required_missing(matches, "students") == ["student_name"]

    def test_必需字段齐全时为空(self) -> None:
        matches = auto_map(["学号", "姓名"], "students")
        assert required_missing(matches, "students") == []

    def test_异动表的必需字段是三个(self) -> None:
        matches = auto_map(["学号"], "student_changes")
        assert set(required_missing(matches, "student_changes")) == {"change_type", "effective_date"}
