"""demo-api 纯函数回归测试：身份范围、异动校验与台账合并。

不启动 HTTP 服务、不写台账；用演示数据构造四类身份。
运行：python -m unittest discover -s demo-api/tests -v
"""
from __future__ import annotations

import re
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as demo  # noqa: E402


STUDENT_UID = "SK-2026-000001"
STAFF = {"superadmin"}
COUNSELOR_ROLE = {"counselor"}
STUDENT_ROLE = {"student_portal"}


def student_user(uid: str = STUDENT_UID) -> dict:
    return {"userName": uid, "nickName": ""}


def counselor_user() -> dict:
    student = next(s for s in demo.DATA["students"] if s["uid"] == STUDENT_UID)
    return {"userName": "counselor01", "nickName": student["counselor"]}


def staff_user() -> dict:
    return {"userName": "admin", "nickName": "管理员"}


def out_of_scope_uid() -> str:
    counselor = counselor_user()["nickName"]
    return next(s["uid"] for s in demo.DATA["students"] if s["counselor"] != counselor)


class VisibleUidsTest(unittest.TestCase):
    def test_student_sees_only_self(self):
        self.assertEqual(demo.visible_uids(student_user(), STUDENT_ROLE), {STUDENT_UID})

    def test_counselor_sees_own_students(self):
        user = counselor_user()
        uids = demo.visible_uids(user, COUNSELOR_ROLE)
        self.assertIn(STUDENT_UID, uids)
        self.assertNotIn(out_of_scope_uid(), uids)
        self.assertLess(len(uids), len(demo.DATA["students"]))

    def test_staff_sees_all(self):
        self.assertIsNone(demo.visible_uids(staff_user(), STAFF))


class ValidateChangeTest(unittest.TestCase):
    def body(self, **overrides) -> dict:
        payload = {
            "uid": STUDENT_UID,
            "type": "休学",
            "date": "2026-10-05",
            "reason": "单元测试",
        }
        payload.update(overrides)
        return payload

    def test_accepts_valid_row(self):
        fields, status, error = demo.validate_change(self.body(), counselor_user(), COUNSELOR_ROLE)
        self.assertEqual(status, 0, error)
        self.assertEqual(fields["target"], "—")
        self.assertEqual(fields["uid"], STUDENT_UID)

    def test_rejects_invalid_calendar_date(self):
        fields, status, error = demo.validate_change(
            self.body(date="2026-02-30"), counselor_user(), COUNSELOR_ROLE
        )
        self.assertIsNone(fields)
        self.assertEqual(status, 400)
        self.assertIn("有效日期", error)

    def test_rejects_bad_date_format(self):
        _, status, error = demo.validate_change(
            self.body(date="2026/2/3"), counselor_user(), COUNSELOR_ROLE
        )
        self.assertEqual(status, 400)
        self.assertIn("YYYY-MM-DD", error)

    def test_rejects_unknown_type(self):
        _, status, _ = demo.validate_change(
            self.body(type="转学"), counselor_user(), COUNSELOR_ROLE
        )
        self.assertEqual(status, 400)

    def test_rejects_empty_reason(self):
        _, status, _ = demo.validate_change(
            self.body(reason="  "), counselor_user(), COUNSELOR_ROLE
        )
        self.assertEqual(status, 400)

    def test_rejects_unknown_student(self):
        _, status, _ = demo.validate_change(
            self.body(uid="SK-NOT-EXISTS"), staff_user(), STAFF
        )
        self.assertEqual(status, 404)

    def test_counselor_cannot_write_out_of_scope(self):
        _, status, error = demo.validate_change(
            self.body(uid=out_of_scope_uid()), counselor_user(), COUNSELOR_ROLE
        )
        self.assertEqual(status, 403)
        self.assertIn("数据范围", error)

    def test_staff_scope_overrides_counselor_scope(self):
        _, status, _ = demo.validate_change(
            self.body(uid=out_of_scope_uid()), counselor_user(), COUNSELOR_ROLE | STAFF
        )
        self.assertEqual(status, 0)

    def test_staff_can_write_any_student(self):
        _, status, error = demo.validate_change(
            self.body(uid=out_of_scope_uid()), staff_user(), STAFF
        )
        self.assertEqual(status, 0, error)


class MergeLedgerTest(unittest.TestCase):
    def test_counselor_changes_are_scoped_and_checked_pruned(self):
        user = counselor_user()
        in_scope = STUDENT_UID
        outside = out_of_scope_uid()
        state = {
            "changes": [
                {"change_no": "T-IN", "uid": in_scope},
                {"change_no": "T-OUT", "uid": outside},
            ],
            "checked": {"T-IN": {"by": "x"}, "T-OUT": {"by": "x"}},
        }
        changes, checked = demo.merge_ledger(user, COUNSELOR_ROLE, state)
        numbers = {c["change_no"] for c in changes}
        self.assertIn("T-IN", numbers)
        self.assertNotIn("T-OUT", numbers)
        self.assertEqual(checked, ["T-IN"])

    def test_staff_gets_all_changes(self):
        state = {"changes": [{"change_no": "T1", "uid": out_of_scope_uid()}], "checked": {"T1": {}}}
        changes, checked = demo.merge_ledger(staff_user(), STAFF, state)
        self.assertEqual(len(changes), len(demo.DATA.get("changes") or []) + 1)
        self.assertEqual(checked, ["T1"])


class NextChangeNoTest(unittest.TestCase):
    def test_avoids_existing_number(self):
        existing = {"YD-LOCAL-20260101000000-0000"}
        number = demo.next_change_no(existing)
        self.assertNotIn(number, existing)
        self.assertTrue(number.startswith("YD-LOCAL-"))


class ScopedPayloadTest(unittest.TestCase):
    def test_student_payload_contains_only_self(self):
        payload = demo.scoped_payload(student_user(), STUDENT_ROLE)
        self.assertIsNotNone(payload)
        self.assertEqual([s["uid"] for s in payload["students"]], [STUDENT_UID])
        self.assertGreater(len(payload["schedule"]), 0)

    def test_counselor_payload_is_subset(self):
        payload = demo.scoped_payload(counselor_user(), COUNSELOR_ROLE)
        self.assertIsNotNone(payload)
        self.assertGreater(len(payload["students"]), 0)
        self.assertLess(len(payload["students"]), len(demo.DATA["students"]))

    def test_staff_payload_is_full(self):
        payload = demo.scoped_payload(staff_user(), STAFF)
        self.assertIsNotNone(payload)
        self.assertEqual(len(payload["students"]), len(demo.DATA["students"]))


class QuietServer(demo.Server):
    def handle_error(self, request, client_address) -> None:
        # 测试里主动断开半开连接，忽略由此产生的写回失败
        pass


class DataIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.students = demo.DATA["students"]
        self.uids = {student["uid"] for student in self.students}

    def test_students_have_unique_non_empty_uid(self):
        self.assertEqual(len(self.uids), len(self.students))
        self.assertTrue(all(student.get("uid") for student in self.students))
        self.assertTrue(all(student.get("name") for student in self.students))

    def test_contact_fields_are_masked(self):
        phone_pattern = re.compile(r"^(\d{3}\*{4}\d{4}|\*{4}\d{4})$")
        id_pattern = re.compile(r"^\*{4}\d{3}[\dX]$")
        for student in self.students:
            self.assertRegex(student["phone"], phone_pattern, student["uid"])
            self.assertRegex(student["id_card"], id_pattern, student["uid"])

    def test_changes_reference_existing_students_and_known_types(self):
        for change in demo.DATA["changes"]:
            self.assertIn(change["uid"], self.uids, change.get("change_no"))
            self.assertIn(change["type"], demo.CHANGE_TYPES, change.get("change_no"))

    def test_schedule_references_known_classes(self):
        class_keys = {
            key
            for student in self.students
            for key in (student.get("class_name"), student.get("class_short"))
            if key
        }
        for row in demo.DATA["schedule"]:
            self.assertTrue(
                row.get("class_name") in class_keys or row.get("class_short") in class_keys,
                row.get("class_name"),
            )
            self.assertTrue(row.get("course"), row.get("class_name"))

    def test_metrics_match_student_count(self):
        self.assertEqual(demo.DATA["metrics"]["total_students"], len(self.students))

    def test_four_sheet_file_is_present(self):
        self.assertTrue(demo.FOUR_SHEET_PATH.is_file())
        self.assertGreater(demo.FOUR_SHEET_PATH.stat().st_size, 100_000)


class ConcurrencyLimitTest(unittest.TestCase):
    def test_rejects_when_slots_exhausted_then_recovers(self):
        original = demo.MAX_CONCURRENT_REQUESTS
        demo.MAX_CONCURRENT_REQUESTS = 1
        server = QuietServer(("127.0.0.1", 0), demo.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        holder = None
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=3) as response:
                self.assertEqual(response.status, 200)

            holder = socket.create_connection(("127.0.0.1", port), timeout=3)
            holder.sendall(b"GET /healthz HTTP/1.1\r\nHost: x\r\n")
            deadline = time.time() + 3
            while server._slots._value > 0 and time.time() < deadline:
                time.sleep(0.02)
            self.assertEqual(server._slots._value, 0, "慢请求未占用唯一并发槽")

            with self.assertRaises(urllib.error.HTTPError) as context:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=3)
            self.assertEqual(context.exception.code, 503)

            holder.close()
            holder = None
            deadline = time.time() + 3
            while server._slots._value == 0 and time.time() < deadline:
                time.sleep(0.02)
            time.sleep(0.05)

            status = None
            for _ in range(50):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=3) as response:
                        status = response.status
                    break
                except (urllib.error.HTTPError, urllib.error.URLError):
                    time.sleep(0.02)
            self.assertEqual(status, 200)
        finally:
            if holder is not None:
                holder.close()
            server.shutdown()
            server.server_close()
            demo.MAX_CONCURRENT_REQUESTS = original


if __name__ == "__main__":
    unittest.main()
