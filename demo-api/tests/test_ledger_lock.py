"""台账写入的响应必须落在 STATE_LOCK 之外（S3）。

原来 _check_change 的 404/403 与 _create_change 的 409 都写在 `with STATE_LOCK:` 里。
socket 写一旦因为客户端不收数据而卡住（Handler.timeout = 10），这把全局锁就一直不放手，
别人的建单、导入、核销乃至 scoped_payload 的台账读全被串行拖住。
这里不起服务，只把 Handler._json 换成探针，直接断言「写响应的那一刻锁是空的」。
"""

import tempfile
import unittest
from pathlib import Path

import app as demo


class LedgerResponseOutsideLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._state_dir = demo.STATE_DIR
        demo.STATE_DIR = Path(self.tmp.name)
        self.responses = []

        def spy(self_handler, status, payload):
            self.responses.append((status, payload, demo.STATE_LOCK.locked()))

        self._json = demo.Handler._json
        demo.Handler._json = spy
        # 只借方法，不建 socket：这几个 handler 除了 self._json 不碰连接状态
        self.handler = object.__new__(demo.Handler)
        self.user = {"userName": "xgb01", "nickName": "学工处"}
        self.roles = {"xgb"}
        self.uid = next(student["uid"] for student in demo.DATA["students"] if student.get("uid"))

    def tearDown(self):
        demo.Handler._json = self._json
        demo.STATE_DIR = self._state_dir
        self.tmp.cleanup()

    def assert_unlocked(self, index=0):
        status, _payload, lock_held = self.responses[index]
        self.assertFalse(lock_held, f"写 {status} 响应时仍然持有 STATE_LOCK")
        return status

    def test_check_missing_record_releases_lock_before_responding(self):
        self.handler._check_change(self.user, self.roles, {"change_no": "BX-不存在"})
        self.assertEqual(404, self.assert_unlocked())

    def test_check_out_of_scope_releases_lock_before_responding(self):
        # 辅导员身份只看得见自己带的学生，越界核销要回 403，而且同样不能持锁写响应
        counselor = {"userName": "fls99", "nickName": "别人"}
        self.handler._check_change(counselor, {"counselor"}, {"change_no": "BX-0001"})
        self.assertIn(self.assert_unlocked(), (403, 404))

    def test_check_ok_persists_and_releases_lock(self):
        state = demo.load_ledger()
        state["changes"].append({
            "uid": self.uid, "type": "休学", "date": "2026-10-01", "reason": "演示测试",
            "status": "审批中", "change_no": "BX-LOCK-0001", "created_by": "xgb01",
        })
        demo.save_ledger(state)
        self.handler._check_change(self.user, self.roles, {"change_no": "BX-LOCK-0001"})
        self.assertEqual(200, self.assert_unlocked())
        self.assertIn("BX-LOCK-0001", demo.load_ledger()["checked"])

    def test_create_releases_lock_before_responding(self):
        self.handler._create_change(
            self.user, self.roles,
            {"uid": self.uid, "type": "休学", "date": "2026-10-01", "reason": "演示测试"},
        )
        self.assertEqual(201, self.assert_unlocked())
        self.assertEqual(1, len(demo.load_ledger()["changes"]))


if __name__ == "__main__":
    unittest.main()
