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
from app.service import (
    ServiceError,
    _read_sidecar,
    _remove_staged,
    _require_supported_extension,
    _sidecar_path,
    _write_sidecar,
)

CSV_BYTES = "学号,姓名\nS001,甲\n".encode("utf-8")


class TestExtensionHandling:
    def test_未知后缀在服务层被拒绝(self) -> None:
        """矩阵 §10-2 已修复：白名单在 `create_batch` 入口生效。

        解析层仍按内容识别（`load_frame` 不看后缀），但服务层先拦一道。
        这样「格式不对」与「内容为空」能给出不同提示——旧实现里两者都是
        「文件没有可导入的数据行」，用户不知道该去换格式。
        """
        assert parsing._is_xlsx("名单.txt") is False

        with pytest.raises(ServiceError) as excinfo:
            _require_supported_extension("名单.txt")

        assert "仅支持" in excinfo.value.message
        assert ".txt" in excinfo.value.message

    def test_无扩展名同样被拒绝(self) -> None:
        with pytest.raises(ServiceError) as excinfo:
            _require_supported_extension("名单")

        assert "没有扩展名" in excinfo.value.message

    def test_白名单内的后缀放行(self) -> None:
        for name in ("名单.xlsx", "名单.XLSM", "名单.csv"):
            _require_supported_extension(name)

    def test_xlsm按Excel解析(self) -> None:
        assert parsing._is_xlsx("名单.xlsm") is True
        assert parsing._is_xlsx("名单.XLSX") is True


class TestEncodingFallback:
    def test_非法字节直接报错(self) -> None:
        """矩阵 §10-3 已修复：不再静默替换成 `U+FFFD`。

        旧实现先用 `utf-8-sig, errors="replace"` 拿一份结果，再用 `gbk` 严格解码
        去覆盖它：只要字节流恰好能被 GBK 解出来（GBK 相当宽容），UTF-8 文件就会
        被改成乱码；而替换已发生，`S\\ufffd001` 能通过长度与非空校验直接入库。
        """
        broken = b"\x80\x81\xe5\xa7\x93\xe5\x90\x8d\nS001\xfe\xfe\n"

        with pytest.raises(parsing.WorkbookError):
            parsing.load_frame(broken, "broken.csv", "students")

    def test_中文表头加ASCII数据不被GBK覆盖(self) -> None:
        """旧实现的解码顺序会把整份 UTF-8 文件读成乱码。

        旧代码：先 `utf-8-sig, errors="replace"` 解一份，再 `data.decode("gbk")`
        严格解一次并**覆盖**前者。`学号,姓名\\n2026001,\\n` 整份字节恰好能被 GBK
        解出来，于是表头变成「瀛﹀彿,濮撳悕」，映射全部失配，用户拿到
        「200 + status=failed / 缺少必需列」——看起来像文件写错了表头。

        这不是罕见个例：常见中文表头里 `学号`/`姓名`/`学院`/`专业`/`备注` 等
        单独拿出来都算得出 GBK 可解的字节序列（实测 24 个常用表头词中 13 个），
        能否触发取决于整份文件的字节对齐。
        """
        data = "学号,姓名\n2026001,\n".encode("utf-8")

        frame, _info = parsing.load_frame(data, "utf8.csv", "students")

        assert list(frame.columns) == ["学号", "姓名"]

    def test_GBK编码文件仍能正常读取(self) -> None:
        """严格解码不能把正常文件误杀：UTF-8 失败后应回落到 GBK。"""
        data = "学号,姓名\nS001,甲\n".encode("gbk")

        frame, _info = parsing.load_frame(data, "gbk.csv", "students")

        assert list(frame.columns) == ["学号", "姓名"]
        assert len(frame) == 1

    def test_带BOM的UTF8仍能正常读取(self) -> None:
        data = "\ufeff学号,姓名\nS001,甲\n".encode("utf-8")

        frame, _info = parsing.load_frame(data, "bom.csv", "students")

        assert list(frame.columns) == ["学号", "姓名"]

    def test_UTF16报编码错误而不是500(self) -> None:
        """UTF-16 字节流此前会绕过解码、在 pandas 里抛 ParserError，冒成 500。"""
        data = "学号,姓名\nS001,甲\n".encode("utf-16")

        with pytest.raises(parsing.WorkbookError):
            parsing.load_frame(data, "utf16.csv", "students")


class TestCorruptedWorkbook:
    def test_损坏的xlsx应转为WorkbookError(self) -> None:
        """矩阵 §10-4 已修复：解析层把 openpyxl 的异常收成 `WorkbookError`，
        service 再转 `ServiceError`，用户拿到 400 而不是 500。"""
        with pytest.raises(parsing.WorkbookError):
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


class TestStagedCleanup:
    """矩阵 §10-1：提交后只删暂存文件、不删 sidecar，导致 `.mapping.json` 永久残留。"""

    def test_删除暂存时一并删除sidecar(self, tmp_path) -> None:
        staged = tmp_path / "IMP-1.csv"
        staged.write_bytes(CSV_BYTES)
        _write_sidecar(str(staged), {"mapping": {"学号": "student_no"}})
        assert (tmp_path / "IMP-1.mapping.json").exists()

        _remove_staged(str(staged))

        assert not staged.exists()
        assert not (tmp_path / "IMP-1.mapping.json").exists()

    def test_暂存文件已缺失时删除不报错(self, tmp_path) -> None:
        """文件被运维手工清掉、只剩 sidecar 时，仍然要能把残留清干净。"""
        staged = tmp_path / "IMP-2.csv"
        _write_sidecar(str(staged), {"mapping": {}})

        _remove_staged(str(staged))

        assert not (tmp_path / "IMP-2.mapping.json").exists()

    def test_只删自己的sidecar不影响同目录其他批次(self, tmp_path) -> None:
        first = tmp_path / "IMP-3.csv"
        second = tmp_path / "IMP-4.csv"
        _write_sidecar(str(first), {"mapping": {}})
        _write_sidecar(str(second), {"mapping": {}})

        _remove_staged(str(first))

        assert not (tmp_path / "IMP-3.mapping.json").exists()
        assert (tmp_path / "IMP-4.mapping.json").exists()
