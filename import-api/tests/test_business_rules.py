"""业务规则校验：学号文件内重复、库内已存在、异动引用的学生是否存在。

这部分刻意放在 Pandera 之外（schemas.py 只管结构），
所以没有测试就会完全裸奔。
"""
from __future__ import annotations

import pandas as pd

from app.service import _business_issues


def frame(student_no: list) -> pd.DataFrame:
    return pd.DataFrame({"student_no": student_no, "student_name": ["甲"] * len(student_no)})


class TestStudentsTarget:
    def test_文件内学号重复只标后出现的行(self) -> None:
        issues = _business_issues(frame(["S1", "S1"]), "students", known_students=set())

        assert [(i.row_number, i.issue_code) for i in issues] == [(3, "DUPLICATE_STUDENT_NO")]
        assert "文件内重复" in issues[0].issue_message

    def test_学号已存在于数据库(self) -> None:
        issues = _business_issues(frame(["S1", "S2"]), "students", known_students={"S2"})

        assert [(i.row_number, i.issue_code) for i in issues] == [(3, "DUPLICATE_STUDENT_NO")]
        assert "已存在" in issues[0].issue_message

    def test_文件内重复与库内已存在分别报出(self) -> None:
        """文件内重复且库里也有：两条规则各自成立，不去重。"""
        issues = _business_issues(frame(["S1", "S1"]), "students", known_students={"S1"})

        assert len(issues) == 3
        assert {i.row_number for i in issues} == {2, 3}

    def test_空学号不参与业务判断(self) -> None:
        """空值属于结构校验的 MISSING_REQUIRED，这里不重复报。"""
        issues = _business_issues(frame([None, "S2"]), "students", known_students=set())

        assert issues == []

    def test_行号带表头偏移(self) -> None:
        issues = _business_issues(frame(["S1", "S1"]), "students", known_students=set(), row_offset=3)

        assert [i.row_number for i in issues] == [6]


class TestChangesTarget:
    def test_引用不存在的学号报UNKNOWN_STUDENT(self) -> None:
        issues = _business_issues(frame(["S1", "S2"]), "student_changes", known_students={"S2"})

        assert [(i.row_number, i.issue_code) for i in issues] == [(2, "UNKNOWN_STUDENT")]
        assert "不存在" in issues[0].issue_message

    def test_同一学生在一次异动导入中重复出现是合法的(self) -> None:
        """一次休学+复学是正常业务场景，不能按学号重复处理。"""
        issues = _business_issues(frame(["S1", "S1"]), "student_changes", known_students={"S1"})

        assert issues == []

    def test_每个引用不存在的学号都会报(self) -> None:
        issues = _business_issues(frame(["X1", "X1"]), "student_changes", known_students=set())

        assert len(issues) == 2
        assert all(i.issue_code == "UNKNOWN_STUDENT" for i in issues)


class TestEdgeCases:
    def test_没有学号列时直接返回空(self) -> None:
        issues = _business_issues(pd.DataFrame({"student_name": ["甲"]}), "students", set())
        assert issues == []

    def test_空数据表返回空(self) -> None:
        issues = _business_issues(pd.DataFrame({"student_no": []}), "students", set())
        assert issues == []
