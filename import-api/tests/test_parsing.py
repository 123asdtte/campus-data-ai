"""工作簿结构识别与载入：多工作表、表头定位、重名列、空行剔除。

对应用例来源：docs/IMPORT-MAPPING-TEST.md §一 的场景 1–8，
夹具全部来自 samples/ 下的虚构数据（学号形如 SMPL/DEMO/G2026 等）。
"""
from __future__ import annotations

import io

import openpyxl

from app.parsing import analyze_workbook, load_frame


def build_xlsx(sheets: dict[str, list[list]]) -> bytes:
    """在内存里拼一个多工作表 xlsx，用于造仓库中没有的夹具。"""
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        worksheet = workbook.create_sheet(name)
        for row in rows:
            worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestAnalyzeWorkbook:
    def test_标准表头在第1行(self, load_sample) -> None:
        """场景 1：students_clean.xlsx → Sheet1 / 第 1 行 / 7 列全中。"""
        analysis = analyze_workbook(load_sample("students_clean.xlsx"), "students_clean.xlsx", "students")
        best = analysis["best"]

        assert best is not None
        assert best["name"] == "Sheet1"
        assert best["header_row"] == 1
        assert best["matched"] == 7
        assert best["matched_required"] == 2
        assert best["data_rows"] == 10
        assert analysis["needs_sheet_choice"] is False

    def test_标题行在前时自动下移表头(self, load_sample) -> None:
        """场景 3：test_title_rows.csv 表头在第 4 行，数据 2 行。"""
        analysis = analyze_workbook(load_sample("test_title_rows.csv"), "test_title_rows.csv", "students")
        best = analysis["best"]

        assert best["header_row"] == 4
        assert best["matched"] == 4
        assert best["data_rows"] == 2

    def test_行号偏移夹具同样定位到第4行(self, load_sample) -> None:
        """场景 11 的前置条件：表头第 4 行、3 行数据。"""
        analysis = analyze_workbook(load_sample("test_title_rows_bad.csv"), "test_title_rows_bad.csv", "students")
        best = analysis["best"]

        assert best["header_row"] == 4
        assert best["data_rows"] == 3

    def test_缺必填字段的夹具仍能识别表头(self, load_sample) -> None:
        """场景 6：表头识别成功，缺的是字段而不是表头。"""
        analysis = analyze_workbook(
            load_sample("test_missing_required.csv"), "test_missing_required.csv", "students"
        )
        best = analysis["best"]

        assert best["matched"] == 3
        assert best["matched_required"] == 1  # 只命中「学号」这一个必需字段

    def test_未知列不影响识别(self, load_sample) -> None:
        """场景 5：学号+姓名命中，备注/辅导员/宿舍号不参与计分。"""
        analysis = analyze_workbook(
            load_sample("test_unknown_columns.csv"), "test_unknown_columns.csv", "students"
        )

        assert analysis["best"]["matched"] == 2
        assert analysis["best"]["matched_required"] == 2

    def test_乱序列不影响识别(self, load_sample) -> None:
        """场景 8：班级/姓名/学号/学院乱序。"""
        analysis = analyze_workbook(load_sample("test_reordered.csv"), "test_reordered.csv", "students")

        assert analysis["best"]["matched"] == 4
        assert analysis["best"]["header_row"] == 1

    def test_异动表按自身别名表识别(self, load_sample) -> None:
        analysis = analyze_workbook(
            load_sample("student_changes_demo.xlsx"), "student_changes_demo.xlsx", "student_changes"
        )
        best = analysis["best"]

        assert best["header_row"] == 1
        assert best["matched"] == 5
        assert best["matched_required"] == 3
        assert best["data_rows"] == 9

    def test_多个工作表都可用时要求用户确认(self) -> None:
        """两个表都含必需字段且都有数据行 → 不静默选择。"""
        data = build_xlsx(
            {
                "人工智能学院": [["学号", "姓名", "班级"], ["S001", "甲", "1班"], ["S002", "乙", "1班"]],
                "康养护理学院": [["学号", "姓名", "班级"], ["S003", "丙", "2班"]],
            }
        )
        analysis = analyze_workbook(data, "汇总表.xlsx", "students")

        assert analysis["needs_sheet_choice"] is True
        assert len(analysis["sheets"]) == 2
        # 数据行更多的工作表排在最前
        assert analysis["best"]["data_rows"] == 2

    def test_单个可用工作表时无需确认(self) -> None:
        data = build_xlsx(
            {
                "说明": [["本表由教务处提供"], ["请勿修改"]],
                "学生": [["学号", "姓名"], ["S001", "甲"], ["S002", "乙"]],
            }
        )
        analysis = analyze_workbook(data, "名单.xlsx", "students")

        assert analysis["needs_sheet_choice"] is False
        assert analysis["best"]["name"] == "学生"

    def test_没有可用表头时返回空(self) -> None:
        data = build_xlsx({"Sheet1": [["甲", "乙"], ["1", "2"]]})
        analysis = analyze_workbook(data, "无效.xlsx", "students")

        assert analysis["best"] is None
        assert analysis["sheets"] == []


class TestLoadFrame:
    def test_按识别出的表头载入(self, load_sample) -> None:
        frame, info = load_frame(load_sample("test_title_rows.csv"), "test_title_rows.csv", "students")

        assert info["header_row"] == 4
        assert info["data_rows"] == 2
        assert list(frame.columns) == ["学生学号", "姓名", "班级", "学院"]

    def test_剔除表头下方的空行(self, load_sample) -> None:
        """标题区里的空行不能算作数据行。"""
        _frame, info = load_frame(load_sample("test_title_rows.csv"), "test_title_rows.csv", "students")
        assert info["data_rows"] == 2

    def test_手动指定表头行覆盖自动识别(self, load_sample) -> None:
        """显式给 header_row=1，就应该按第 1 行取列，而不是自动识别出的第 4 行。"""
        frame, info = load_frame(
            load_sample("test_title_rows.csv"), "test_title_rows.csv", "students", header_row=1
        )

        assert info["header_row"] == 1
        assert frame.columns[0] == "2026级新生信息汇总表"
        assert len(frame) == 5  # 表头以下的 5 行都被当作数据

    def test_重名列仍然可区分(self) -> None:
        """两个「备注」列必须能各自取值，不能返回 DataFrame。

        注意实际后缀：pandas 在 read_csv/read_excel 阶段已把重名列改名为
        `备注.1`，load_frame 里的 `_1` 补偿逻辑走不到（README 写的 `_1` 与实现不符）。
        这里只断言「可区分且值正确」，不锁死后缀写法。
        """
        raw = "学号,姓名,备注,备注\nS001,甲,x,y\n".encode("utf-8")
        frame, _info = load_frame(raw, "dup.csv", "students")

        assert len(set(frame.columns)) == 4
        assert frame.columns[2].startswith("备注")
        assert frame.columns[3].startswith("备注")
        assert frame.at[0, frame.columns[2]] == "x"
        assert frame.at[0, frame.columns[3]] == "y"

    def test_丢弃无表头的尾随空列(self) -> None:
        raw = "学号,姓名,\nS001,甲,\n".encode("utf-8")
        frame, _info = load_frame(raw, "tail.csv", "students")

        assert "Unnamed: 2" not in frame.columns
        assert list(frame.columns) == ["学号", "姓名"]

    def test_gbk编码的csv可读(self) -> None:
        """学校导出的 CSV 常见 GBK 编码，不能只支持 UTF-8。"""
        raw = "学号,姓名\nS001,张三\n".encode("gbk")
        frame, _info = load_frame(raw, "gbk.csv", "students")

        assert frame.at[0, "姓名"] == "张三"

    def test_工作表名可显式指定(self) -> None:
        data = build_xlsx(
            {
                "表一": [["学号", "姓名"], ["S001", "甲"]],
                "表二": [["学号", "姓名"], ["S002", "乙"], ["S003", "丙"]],
            }
        )
        frame, info = load_frame(data, "多表.xlsx", "students", sheet_name="表一")

        assert info["sheet_name"] == "表一"
        assert frame.at[0, "学号"] == "S001"
