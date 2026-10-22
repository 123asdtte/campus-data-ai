"""解析与暂存的边界行为：扩展名、编码、损坏文件、sidecar。

不需要数据库，本地即可运行。这里的用例有两种性质，看标记区分：
- **现状固化**：断言当前行为，注释里写明「若改行为请同步更新本用例」；
- **xfail(strict)**：断言期望行为，当前不满足即标为已知缺陷，
  修复后会 XPASS 从而强制删除标记，避免缺陷修好了却没人更新测试。

对应 docs/TEST-COVERAGE-MATRIX.md §3 与 §10。
"""
from __future__ import annotations

import pytest

from app import parsing
from app.service import ServiceError, _read_sidecar, _sidecar_path, _write_sidecar

CSV_BYTES = "学号,姓名\nS001,甲\n".encode("utf-8")


class TestExtensionHandling:
    def test_未知后缀按内容识别为CSV(self) -> None:
        """现状固化（矩阵 §10-2）：扩展名白名单实际未生效。

        `.txt`、`.dat` 等后缀只要内容是 CSV 就会被正常解析，而
        `service._read_frame` 里那句「仅支持 .xlsx / .csv」是死代码。
        若后续改为「拒绝未知后缀」，本用例需要同步改成断言报错。
        """
        assert parsing._is_xlsx("名单.txt") is False

        frame, _info = parsing.load_frame(CSV_BYTES, "名单.txt", "students")

        assert list(frame.columns) == ["学号", "姓名"]
        assert len(frame) == 1

    def test_xlsm按Excel解析(self) -> None:
        assert parsing._is_xlsx("名单.xlsm") is True
        assert parsing._is_xlsx("名单.XLSX") is True


class TestEncodingFallback:
    def test_非法字节被替换为替换字符而不是报错(self) -> None:
        """现状固化（矩阵 §10-3）：非法字节静默替换，乱码学号可以一路走到入库。

        期望行为至少是给出 warning。改为报错或告警时，本用例需同步更新。

        注：这里固化的是 pandas 当前的 decode 策略（`errors="replace"`），
        pandas 大版本升级若改变该行为，本用例会无故失败，届时按需调整预期。
        """
        broken = b"\x80\x81\xe5\xa7\x93\xe5\x90\x8d\nS001\xfe\xfe\n"

        frame, _info = parsing.load_frame(broken, "broken.csv", "students")

        assert "\ufffd" in str(frame.columns[0])


class TestCorruptedWorkbook:
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "已知缺陷（矩阵 §10-4）：扩展名是 .xlsx 但内容不是 zip 包时，"
            "openpyxl 抛出 zipfile.BadZipFile，不是 ServiceError，"
            "因此会冒到 FastAPI 变成 500 而不是 400。"
            "修复时应在解析层包一层转 ServiceError，届时请移除本标记"
        ),
    )
    def test_损坏的xlsx应转为ServiceError(self) -> None:
        with pytest.raises(ServiceError):
            parsing.load_frame(b"not a zip file at all", "broken.xlsx", "students")


class TestSidecar:
    def test_写入后可原样读回(self, tmp_path) -> None:
        staged = str(tmp_path / "IMP-1.csv")

        _write_sidecar(staged, {"sheet_name": "Sheet1", "header_row": 3, "mapping": {"学号": "student_no"}})

        assert _read_sidecar(staged) == {
            "sheet_name": "Sheet1",
            "header_row": 3,
            "mapping": {"学号": "student_no"},
        }

    def test_sidecar不存在时读取为空(self, tmp_path) -> None:
        assert _read_sidecar(str(tmp_path / "IMP-1.csv")) == {}

    def test_sidecar损坏时读取为空且不阻断(self, tmp_path) -> None:
        """写坏了退回空映射，让批次走自动映射，而不是整个请求 500。"""
        staged = tmp_path / "IMP-1.csv"
        staged.write_bytes(CSV_BYTES)
        (tmp_path / "IMP-1.mapping.json").write_text("{坏掉的 json", encoding="utf-8")

        assert _read_sidecar(str(staged)) == {}

    def test_sidecar路径由暂存文件派生(self, tmp_path) -> None:
        assert _sidecar_path(str(tmp_path / "IMP-1.csv")) == str(tmp_path / "IMP-1.mapping.json")
