"""状态文件路径必须跟着 STATE_DIR 走（D-073）。

台账/审计路径以前在模块导入期就拼成了常量，测试只 patch STATE_DIR 时写入仍落在仓库的
state/ 里，虚构的异动记录混进了本地真实台账。路径本身没坏，坏的是「换个目录就能隔离」
这个假设不成立，而它只有真的写一次才会暴露。这几条测试把假设钉死：只换 STATE_DIR 就必须
换掉全部状态文件，且原目录一个字节都不许动。
"""

import tempfile
import unittest
from pathlib import Path

import app as demo


class StatePathFollowsStateDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._state_dir = demo.STATE_DIR
        self.original = demo.STATE_DIR
        self.before = self.fingerprint(self.original)
        demo.STATE_DIR = self.dir

    def tearDown(self):
        try:
            demo.STATE_DIR = self._state_dir
            # 断言放在还原之后、清理临时目录之前：一旦哪天路径解析又绑回导入期，
            # 这条会直接指出「测试写进了真实 state/」，而不是留个没人发现的脏文件。
            self.assertEqual(self.fingerprint(self.original), self.before, "本次测试改动了真实 state/ 目录")
        finally:
            self.tmp.cleanup()

    def fingerprint(self, directory: Path):
        if not directory.is_dir():
            return None
        return sorted((entry.name, entry.stat().st_size) for entry in directory.iterdir())

    def test_save_and_load_ledger_use_the_current_state_dir(self):
        state = {"changes": [{"change_no": "BG-DIR-1", "type": "休学"}], "checked": {}}
        demo.save_ledger(state)
        self.assertEqual(self.dir / "ledger.json", demo.state_path())
        self.assertTrue((self.dir / "ledger.json").is_file(), "台账没写进当前 STATE_DIR")
        self.assertEqual(demo.load_ledger(), state)

    def test_audit_log_uses_the_current_state_dir(self):
        demo.record_assistant_audit(
            {"userName": "xgb01"}, {"xgb"}, {"intent": "count", "scope": {"label": "全部"}}, "有多少人休学", "/changes",
        )
        self.assertEqual(self.dir / "assistant-audit.jsonl", demo.assistant_log_path())
        self.assertEqual(len((self.dir / "assistant-audit.jsonl").read_text(encoding="utf-8").splitlines()), 1)

    def test_quarantine_copy_lands_in_the_current_state_dir(self):
        # 隔离副本原来用 STATE_PATH.with_name() 派生，路径一旦不再跟随 STATE_DIR，
        # 损坏备份就会跑到真实目录里去——排障的人按临时目录找，找不到。
        demo.state_path().write_text('{"changes": ', encoding="utf-8")
        with self.assertRaises(demo.LedgerUnavailable):
            demo.load_ledger()
        copies = [entry for entry in self.dir.iterdir() if entry.name.startswith("ledger.corrupt-")]
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_text(encoding="utf-8"), '{"changes": ')


if __name__ == "__main__":
    unittest.main()
