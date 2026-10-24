"""demo-api 纯函数回归测试：身份范围、异动校验与台账合并。

不启动 HTTP 服务、不写台账；用演示数据构造四类身份。
运行：python -m unittest discover -s demo-api/tests -v
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as demo  # noqa: E402
import os
import io
import stat

REPO_ROOT = Path(__file__).resolve().parents[2]


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


class AssistantQueryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = demo.scoped_payload(student_user(), STUDENT_ROLE)
        cls.student = cls.payload["students"][0]
        cls.schedule = cls.payload["schedule"]
        cls.metrics = cls.payload["metrics"]
        cls.now = demo.datetime(2026, 10, 24, 15, 0)

    def answer(self, question: str) -> dict:
        return demo.schedule_answer(question, self.student, self.schedule, self.metrics, self.now)

    def test_all_schedule_weekdays_are_normalized(self):
        self.assertEqual(len(demo.DATA["schedule"]), self.metrics["schedule_meta"]["rows"])
        self.assertTrue(all(row["weekday"] in demo.WEEKDAYS for row in demo.DATA["schedule"]))
        self.assertEqual(demo.normalize_weekday("3"), "周三")
        self.assertEqual(demo.normalize_weekday("星期五"), "周五")

    def test_week_matches_parity_and_ranges(self):
        self.assertTrue(demo.week_matches("1-16周", 8))
        self.assertFalse(demo.week_matches("1-16周(单)", 8))
        self.assertTrue(demo.week_matches("1-16周(双)", 8))
        self.assertFalse(demo.week_matches("2-6周", 8))
        self.assertTrue(demo.week_matches("", 8))

    def test_explicit_weekday_first_period_returns_room(self):
        reply = self.answer("这周五第一节在哪？")
        self.assertEqual(reply["intent"], "schedule_day")
        self.assertEqual(reply["scope"]["weekday"], "周五")
        self.assertEqual(reply["scope"]["week"], 8)
        self.assertTrue(all(course["period"] == "1-2节" for course in reply["courses"]))
        self.assertTrue(all(course["room"] for course in reply["courses"]))

    def test_remaining_classes_only_returns_later_periods(self):
        thursday_1030 = demo.datetime(2026, 10, 22, 10, 30)
        reply = demo.schedule_answer(
            "今天还剩几节课？", self.student, self.schedule, self.metrics, thursday_1030,
        )
        self.assertEqual(reply["intent"], "schedule_remaining")
        self.assertTrue(reply["courses"])
        self.assertTrue(all(demo.period_numbers(course["period"]) >= {9} for course in reply["courses"]))
        self.assertIn("10:30", reply["answer"])

    def test_schedule_never_leaks_other_classes(self):
        keys = {self.student["class_name"], self.student["class_short"]}
        own_courses = {
            row["course"] for row in demo.DATA["schedule"]
            if row["class_name"] in keys or row["class_short"] in keys
        }
        reply = self.answer("下周有哪些课？")
        self.assertTrue(reply["courses"])
        self.assertTrue(all(course["course"] in own_courses for course in reply["courses"]))

    def test_sensitive_question_is_refused(self):
        reply = self.answer("我的成绩和别的同学电话是多少？")
        self.assertEqual(reply["intent"], "refused")
        self.assertEqual(reply["courses"], [])
        self.assertIn("只回答你自己的课表和本人学籍信息", reply["answer"])

    def test_other_student_questions_are_not_answered_as_own_schedule(self):
        # 曾被误答成学生本人课表（“今天没有课”），必须明确拒绝而不是误导。
        for question in ("张三的课表是什么？", "我室友明天有什么课？", "隔壁班的同学今天有什么课？"):
            reply = self.answer(question)
            self.assertEqual(reply["intent"], "refused", question)
            self.assertEqual(reply["courses"], [], question)
            self.assertIn("查不到其他学生", reply["answer"], question)

    def test_own_schedule_questions_are_not_blocked_by_other_guard(self):
        for question in ("我明天有什么课？", "我的课表", "本周的课表", "我们班的课表", "下周有哪些课？"):
            reply = self.answer(question)
            self.assertNotEqual(reply["intent"], "refused", question)

    def test_roster_student_names_are_refused_even_without_keewei(self):
        # 脱敏姓名含 * （如 朱**），不在 OTHER_STUDENT_PATTERN 的纯汉字类里；
        # 花名册兜底必须拦住“X今天有没有课？”这类不带“的课表”的问法。
        other = next(
            item["name"] for item in demo.DATA["students"]
            if item["name"] and item["name"] != self.student["name"]
        )
        for question in (f"{other}今天有没有课？", f"{other}的课表是什么？"):
            reply = self.answer(question)
            self.assertEqual(reply["intent"], "refused", question)
            self.assertEqual(reply["courses"], [], question)
            self.assertIn("查不到其他学生", reply["answer"], question)

        own = self.student["name"]
        if own:
            reply = self.answer(f"{own}今天有没有课？")
            self.assertNotEqual(reply["intent"], "refused", "本人姓名不应被花名册守卫误拦")

    def test_student_profile_question_uses_own_record(self):
        student = next(
            item for item in demo.DATA["students"]
            if item.get("counselor") and item.get("grade")
        )
        rows = [row for row in demo.DATA["schedule"] if row.get("class_name") == student["class_name"]]
        now = datetime.now().astimezone()
        for question, value in (
            ("我的学籍状态是什么？", student["status"]),
            ("我是哪个班的？", student["class_short"] or student["class_name"]),
            ("我的辅导员是谁？", student["counselor"]),
            ("我什么时候入学？", student["grade"]),
        ):
            # 空课表也要能答档案：以前这类问题会落到课表分支，回一句“今天没有课”
            for schedule in (rows, []):
                reply = demo.schedule_answer(question, student, schedule, demo.DATA["metrics"], now)
                self.assertEqual(reply["intent"], "profile", question)
                self.assertIn(value, reply["answer"], question)
                self.assertEqual(reply["scope"]["label"], "仅本人档案")
                self.assertEqual(reply["courses"], [])

    def test_student_profile_does_not_leak_identifiers(self):
        student = demo.DATA["students"][0]
        now = datetime.now().astimezone()
        for question in ("我的学号是多少？", "我的身份证号？", "别人电话？"):
            reply = demo.schedule_answer(question, student, [], demo.DATA["metrics"], now)
            self.assertEqual(reply["intent"], "refused", question)
            self.assertNotIn(student["uid"], reply["answer"])

    def test_timetable_question_still_wins_over_profile(self):
        student = next(
            item for item in demo.DATA["students"]
            if any(row.get("class_name") == item["class_name"] for row in demo.DATA["schedule"])
        )
        rows = [row for row in demo.DATA["schedule"] if row.get("class_name") == student["class_name"]]
        reply = demo.schedule_answer(
            "我们班明天有课吗？", student, rows, demo.DATA["metrics"], datetime.now().astimezone()
        )
        self.assertNotEqual(reply["intent"], "profile")
        self.assertIn("演示课表", reply["answer"])

    def test_status_question_answers_headcount_not_ledger_rows(self):
        staff_payload = demo.scoped_payload(staff_user(), STAFF)
        status_counts = {item["name"]: item["count"] for item in staff_payload["metrics"]["status_counts"]}
        ledger_rows = {
            name: sum(1 for change in staff_payload["changes"] if change.get("type") == name)
            for name in ("休学", "退学")
        }
        # 两条口径在演示数据里本来就不同，否则这条断言没有保护任何东西
        self.assertNotEqual(status_counts["休学"], ledger_rows["休学"])
        reply = demo.staff_answer("全校休学和退学各有多少人？", staff_payload, STAFF)
        self.assertEqual(reply["intent"], "count")
        for name in ("休学", "退学"):
            self.assertIn(f"{name} {status_counts[name]} 人", reply["answer"])
            self.assertNotIn(f"{name} {ledger_rows[name]} 条", reply["answer"])

    def test_college_status_count_stays_college_scoped(self):
        staff_payload = demo.scoped_payload(staff_user(), STAFF)
        expected = sum(
            1 for student in staff_payload["students"]
            if student.get("college") == "人工智能学院" and student.get("status") == "休学"
        )
        reply = demo.staff_answer("人工智能学院休学的有多少人？", staff_payload, STAFF)
        self.assertEqual(reply["intent"], "count")
        self.assertIn("人工智能学院", reply["answer"])
        self.assertIn(f"休学 {expected} 人", reply["answer"])

    def test_ledger_only_types_answer_as_rows_not_headcount(self):
        staff_payload = demo.scoped_payload(staff_user(), STAFF)
        # 留级/复学只存在于异动台账里，不是当前学籍状态；回答必须承认这一点而不是回一句全校人数。
        reply = demo.staff_answer("留级和复学各多少人？", staff_payload, STAFF)
        self.assertEqual(reply["intent"], "change_count")
        for name in ("留级", "复学"):
            rows = sum(1 for change in staff_payload["changes"] if change.get("type") == name)
            self.assertIn(f"{name} {rows} 条", reply["answer"])
        self.assertIn("不是当前学籍状态", reply["answer"])
        self.assertNotIn("名学生", reply["answer"])

    def test_natural_phrasing_of_quality_question_still_answers_quality(self):
        staff_payload = demo.scoped_payload(staff_user(), STAFF)
        counselor_payload = demo.scoped_payload(counselor_user(), COUNSELOR_ROLE)
        # “数据质量”四个字只是其中一种说法：用户更常说“今天数据有什么问题”。
        for question in ("数据质量怎么样？", "今天数据有什么问题？", "这批数据有啥问题没？"):
            reply = demo.staff_answer(question, staff_payload, STAFF)
            self.assertEqual(reply["intent"], "quality", question)
            self.assertIn("重复学号", reply["answer"], question)
            # 辅导员没有全校质量统计，必须说清范围而不是编一份数
            limited = demo.staff_answer(question, counselor_payload, COUNSELOR_ROLE)
            self.assertEqual(limited["intent"], "quality", question)
            self.assertIn("没有全校数据质量统计范围", limited["answer"], question)

    def test_question_about_other_objects_is_not_answered_with_headcount(self):
        staff_payload = demo.scoped_payload(staff_user(), STAFF)
        # “哪些”是提问词，不指向学生：收件箱资料不能拿学籍人数冒充答案，宁落回 unknown 的引导。
        for question in ("收件箱里有哪些资料？", "导入批次怎么提交？"):
            reply = demo.staff_answer(question, staff_payload, STAFF)
            self.assertEqual(reply["intent"], "unknown", question)
            self.assertNotIn("名学生", reply["answer"], question)
        for question in ("全校学生总数是多少？", "人工智能学院有多少学生？"):
            reply = demo.staff_answer(question, staff_payload, STAFF)
            self.assertEqual(reply["intent"], "count", question)

    def test_change_type_counts(self):
        staff_payload = demo.scoped_payload(staff_user(), STAFF)
        reply = demo.staff_answer("异动台账里休学和退学各有多少条？", staff_payload, STAFF)
        self.assertEqual(reply["intent"], "change_count")
        self.assertIn(str(len(staff_payload["changes"])), reply["answer"])
        for name in ("休学", "退学"):
            expected = sum(1 for change in staff_payload["changes"] if change.get("type") == name)
            self.assertIn(f"{name} {expected} 条", reply["answer"])

    def test_changes_answer_discloses_unmatched_rows(self):
        staff_payload = demo.scoped_payload(staff_user(), STAFF)
        reply = demo.staff_answer("最近的学籍异动情况", staff_payload, STAFF)
        self.assertEqual(reply["intent"], "changes")
        # 工作台 KPI 用的是整表条数，可核对清单只有学号匹配上的行：回答里要说清差额
        orphan = staff_payload["metrics"].get("orphan_changes") or 0
        self.assertIn(str(len(staff_payload["changes"])), reply["answer"])
        if orphan:
            self.assertIn(f"另有 {orphan} 条学号未匹配的异动", reply["answer"])

    def test_quality_answer_covers_every_flag(self):
        staff_payload = demo.scoped_payload(staff_user(), STAFF)
        quality = staff_payload["metrics"]["data_quality"]
        reply = demo.staff_answer("数据质量怎么样？", staff_payload, STAFF)
        self.assertEqual(reply["intent"], "quality")
        # AI 问数页迁到服务端后，这些口径必须一条不漏，否则前端旧文案会丢失
        for key in (
            "duplicate_rows", "same_name_groups", "id_invalid",
            "class_not_found", "transfer_conflicts", "same_name_all",
        ):
            self.assertIn(str((quality.get(key) or {}).get("count")), reply["answer"])

    def test_staff_scope_and_counselor_scope(self):
        staff_payload = demo.scoped_payload(staff_user(), STAFF)
        staff_reply = demo.staff_answer("人工智能学院有多少学生？", staff_payload, STAFF)
        self.assertEqual(staff_reply["intent"], "count")
        self.assertIn("人工智能学院", staff_reply["answer"])
        self.assertIn("全校范围", staff_reply["scope"]["label"])

        counselor_payload = demo.scoped_payload(counselor_user(), COUNSELOR_ROLE)
        counselor_reply = demo.staff_answer("我班有多少学生？", counselor_payload, COUNSELOR_ROLE)
        self.assertIn("本班范围", counselor_reply["scope"]["label"])
        self.assertIn(str(len(counselor_payload["students"])), counselor_reply["answer"])


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


class DatasetTrackingTest(unittest.TestCase):
    """`.gitignore` 里的 `data/` 曾经把整个演示数据集目录盖掉：新增的数据文件
    在 `git status` 里完全不出现，只有 CI 报缺文件时才被发现。"""

    @classmethod
    def setUpClass(cls):
        if not (REPO_ROOT / ".git").exists():
            raise unittest.SkipTest("不是 git 工作区，忽略规则无从校验")

    @staticmethod
    def is_ignored(relpath: str) -> bool:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", relpath],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        return result.returncode == 0

    def test_demo_dataset_is_not_hidden_by_the_data_rule(self):
        self.assertFalse(self.is_ignored("demo-api/data/demo-data.json"))
        # 还没入库的新数据集也必须能被 git status 看到，否则等于问题没修。
        self.assertFalse(self.is_ignored("demo-api/data/next-semester.xlsx"))

    def test_real_export_paths_stay_ignored(self):
        # 放行演示目录不能顺手把真实导出的个人信息变成可提交。
        self.assertTrue(self.is_ignored("data/real-students.csv"))
        self.assertTrue(self.is_ignored("import-api/data/real-students.csv"))
        self.assertTrue(self.is_ignored("demo-api/state/ledger.json"))


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
            # 槽位只有 1 个，预热请求的 serve 线程可能还没 release 就被测试线程抢，
            # 于是 acquire 偶发失败（从仓库根目录跑 verify 脚本时实测必现）。
            # 去掉预热请求：空闲槽位必然可占用，“能正常回答 200”由释放后的恢复断言覆盖。
            self.assertTrue(server._slots.acquire(timeout=3), "空闲槽位应能被测试线程占用")
            raw = socket.create_connection(("127.0.0.1", port), timeout=3)
            holder = raw
            raw.sendall(b"GET /healthz HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            drained = b""
            deadline = time.time() + 3
            while b"503" not in drained and time.time() < deadline:
                chunk = raw.recv(2048)
                if not chunk:
                    break
                drained += chunk
            self.assertIn(b"503 Service Unavailable", drained, "并发槽满时应返回 503")
            self.assertIn("服务繁忙".encode("utf-8"), drained, "503 应带中文提示体")
            raw.close()
            holder = None
            server._slots.release()

            status = None
            for _ in range(100):
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


class CollegeScopeAnswerTest(unittest.TestCase):
    """辅导员载荷里的 college_counts 只是本人带班口径，不能当成全院数字播报。"""

    def test_counselor_college_question_states_scope_limit(self):
        payload = demo.scoped_payload(counselor_user(), COUNSELOR_ROLE)
        college = payload["metrics"]["college_counts"][0]["name"]
        reply = demo.staff_answer(f"{college}有多少学生？", payload, COUNSELOR_ROLE)
        self.assertEqual(reply["intent"], "out_of_scope")
        self.assertIn("不在你的数据范围", reply["answer"])
        self.assertNotIn(f"{college}共有", reply["answer"])

    def test_counselor_status_count_still_answers(self):
        payload = demo.scoped_payload(counselor_user(), COUNSELOR_ROLE)
        status = next(
            item["name"] for item in payload["metrics"]["status_counts"]
            if item["name"] not in ("休学", "退学", "转专业")
        )
        reply = demo.staff_answer(f"{status}有多少人？", payload, COUNSELOR_ROLE)
        self.assertEqual(reply["intent"], "count")
        self.assertIn(status, reply["answer"])

    def test_staff_still_gets_college_total(self):
        payload = demo.scoped_payload(staff_user(), STAFF)
        entry = payload["metrics"]["college_counts"][0]
        reply = demo.staff_answer(f"{entry['name']}有多少学生？", payload, STAFF)
        self.assertEqual(reply["intent"], "count")
        self.assertIn(str(entry["count"]), reply["answer"])


class AssistantAuditTest(unittest.TestCase):
    """问数审计要落在服务端，且不得把问题原文写进审计文件。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._state_dir = demo.STATE_DIR
        demo.STATE_DIR = self.dir

    def tearDown(self):
        demo.STATE_DIR = self._state_dir
        self.tmp.cleanup()

    def test_records_identity_without_question_text(self):
        demo.record_assistant_audit(
            {"userName": "counselor01"}, COUNSELOR_ROLE,
            {"intent": "out_of_scope", "scope": {"label": "本班范围"}},
            "张三的身份证号是多少", "/counselor",
        )
        entry = json.loads(demo.assistant_log_path().read_text(encoding="utf-8").strip())
        self.assertEqual(entry["actor"], "counselor01")
        self.assertEqual(entry["roles"], ["counselor"])
        self.assertEqual(entry["intent"], "out_of_scope")
        self.assertEqual(entry["scope"], "本班范围")
        self.assertEqual(entry["page"], "/counselor")
        self.assertNotIn("张三", demo.assistant_log_path().read_text(encoding="utf-8"))
        self.assertEqual(entry["question_chars"], len("张三的身份证号是多少"))

    def test_log_stays_bounded(self):
        for index in range(demo.ASSISTANT_LOG_KEEP + 40):
            demo.record_assistant_audit(
                {"userName": f"u{index}"}, COUNSELOR_ROLE, {"intent": "count"}, "问", "")
        lines = demo.assistant_log_path().read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), demo.ASSISTANT_LOG_KEEP)
        self.assertEqual(json.loads(lines[-1])["actor"], f"u{demo.ASSISTANT_LOG_KEEP + 39}")


class LedgerPendingAnswerTest(unittest.TestCase):
    """助手要能回答“哪些异动还没我核对完”，口径与台账共用同一个判定函数。"""

    def test_pending_helper_matches_ledger_rule(self):
        changes = [
            {"change_no": "A1", "status": "已批", "type": "休学", "date": "2026-03-02"},
            {"change_no": "A2", "status": "审批中", "type": "退学"},
            {"change_no": "A3", "status": "已批", "type": "转专业"},
        ]
        self.assertEqual([c["change_no"] for c in demo.pending_check_rows(changes, ["A1"])], ["A3"])
        self.assertEqual(len(demo.pending_check_rows(changes, ["A1", "A3"])), 0)

    def test_counselor_gets_pending_list_within_scope(self):
        payload = demo.scoped_payload(counselor_user(), COUNSELOR_ROLE)
        expected = demo.pending_check_rows(payload["changes"], payload.get("platform_checked") or [])
        reply = demo.staff_answer("还有哪些异动没核对？", payload, COUNSELOR_ROLE)
        self.assertEqual(reply["intent"], "pending")
        self.assertIn(f"有 {len(expected)} 条异动已批但平台未核对", reply["answer"])
        for row in expected[:5]:
            self.assertIn(row["change_no"], reply["answer"])
        self.assertEqual(reply["action"]["to"], "/changes")

    def test_approving_branch_counts_review_in_progress(self):
        payload = demo.scoped_payload(staff_user(), STAFF)
        expected = [c for c in payload["changes"] if "审批中" in (c.get("status") or "")]
        reply = demo.staff_answer("审批中的异动有多少？", payload, STAFF)
        self.assertEqual(reply["intent"], "pending")
        self.assertIn(f"有 {len(expected)} 条异动仍在审批中", reply["answer"])


class LedgerIntegrityTest(unittest.TestCase):
    """台账读不出来时不能当成空表：照旧写回去就等于静默删掉已有异动记录。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._state_dir = demo.STATE_DIR
        demo.STATE_DIR = self.dir

    def tearDown(self):
        demo.STATE_DIR = self._state_dir
        self.tmp.cleanup()

    def quarantined(self) -> list[Path]:
        return sorted(p for p in self.dir.iterdir() if p.name.startswith("ledger.corrupt-"))

    def test_absent_file_reads_as_empty_ledger(self):
        self.assertEqual(demo.load_ledger(), {"changes": [], "checked": {}})

    def test_valid_ledger_round_trips(self):
        state = {"changes": [{"change_no": "BG-1", "type": "休学"}], "checked": {"BG-1": {"by": "admin"}}}
        demo.save_ledger(state)
        self.assertEqual(demo.load_ledger(), state)
        self.assertEqual(self.quarantined(), [])

    def test_truncated_file_is_refused_and_kept_recoverable(self):
        demo.save_ledger({"changes": [{"change_no": "BG-OLD", "type": "休学"}], "checked": {}})
        broken = '{"changes": [{"change_no": "BG-OLD", "type": "休学"}], "checked": '
        demo.state_path().write_text(broken, encoding="utf-8")
        with self.assertRaises(demo.LedgerUnavailable):
            demo.load_ledger()
        # 写链路唯一入口是 load_ledger，它抛错就说明这条写被拦在覆盖之前；原字节必须还在。
        self.assertEqual(demo.state_path().read_text(encoding="utf-8"), broken)
        copies = self.quarantined()
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_text(encoding="utf-8"), broken)

    def test_wrong_shape_is_not_silently_emptied(self):
        demo.state_path().write_text('{"changes": {"不是": "数组"}, "checked": {}}', encoding="utf-8")
        with self.assertRaises(demo.LedgerUnavailable):
            demo.load_ledger()
        self.assertEqual(len(self.quarantined()), 1)

    def test_display_path_degrades_instead_of_failing(self):
        demo.state_path().write_text("{{{", encoding="utf-8")
        state, warning = demo.read_ledger_for_display()
        self.assertEqual(state, {"changes": [], "checked": {}})
        # 退回了基础演示数据就必须把「台账没计入」说出来，否则用户会把缺数当成没发生异动。
        self.assertIn("台账", warning)
        payload = demo.scoped_payload(staff_user(), STAFF)
        self.assertIsNotNone(payload)
        self.assertEqual(len(payload["changes"]), len(demo.DATA["changes"]))
        self.assertIn("ledger_warning", payload["meta"])

    def test_healthy_ledger_carries_no_warning(self):
        self.assertIsNone(demo.read_ledger_for_display()[1])
        self.assertNotIn("ledger_warning", demo.scoped_payload(staff_user(), STAFF)["meta"])


SEED_ACCOUNTS = REPO_ROOT / "scripts" / "demo" / "seed-demo-accounts.sql"


class CounselorScopeIdentityTest(unittest.TestCase):
    """带生范围只能由不可自改的 userName 决定：网关允许本人改昵称，拿昵称定范围等于让辅导员自己换范围。"""

    def setUp(self):
        own_label = demo.COUNSELOR_LABELS["counselor01"]
        students = demo.DATA["students"]
        self.own = {s["uid"] for s in students if s["counselor"] == own_label}
        other = next(
            s["counselor"] for s in students
            if s["counselor"] != own_label
        )
        self.other_label = other
        self.others = {s["uid"] for s in students if s["counselor"] == other}

    def test_renaming_to_another_counselor_does_not_widen_scope(self):
        user = {"userName": "counselor01", "nickName": self.other_label}
        self.assertEqual(demo.visible_uids(user, COUNSELOR_ROLE), self.own)

    def test_unmapped_counselor_gets_no_scope(self):
        user = {"userName": "counselor99", "nickName": self.other_label}
        self.assertEqual(demo.visible_uids(user, COUNSELOR_ROLE), set())
        payload = demo.scoped_payload(user, COUNSELOR_ROLE)
        self.assertEqual(payload["students"], [])
        self.assertEqual(payload["class_summary"], [])

    def test_scope_label_matches_seeded_account_nickname(self):
        # 映射与演示账号种子必须一致，否则改种子会悄悄把辅导员的范围改成空。
        seed = SEED_ACCOUNTS.read_text(encoding="utf-8")
        labels = {s["counselor"] for s in demo.DATA["students"]}
        for username, label in demo.COUNSELOR_LABELS.items():
            self.assertRegex(
                seed,
                rf"'{username}',\s*'{re.escape(label)}'",
                f"{username} 的种子昵称与 COUNSELOR_LABELS 不一致",
            )
            self.assertIn(label, labels)

    def test_counselor_payload_only_exposes_own_classes(self):
        payload = demo.scoped_payload(
            {"userName": "counselor01", "nickName": self.other_label}, COUNSELOR_ROLE
        )
        self.assertEqual({s["uid"] for s in payload["students"]}, self.own)
        self.assertTrue(all(c["counselor"] != self.other_label for c in payload["class_summary"]))
        self.assertTrue(all(row["uid"] in self.own for row in payload["changes"]))

@unittest.skipUnless(os.name == "posix", "POSIX 才有可校验的文件权限位")
class AssistantAuditPermissionTest(unittest.TestCase):
    """问数审计记着「谁在哪个页面问了什么」，可读性不能高于同目录下的台账。

    追加写跟着 umask（演示容器里实测是 0644，台账却是 0600），所以要显式收紧一次。
    Windows 的权限位是模拟的，只在 POSIX 上断言，免得留一条永远验不出名堂的测试。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._state = demo.STATE_DIR
        demo.STATE_DIR = Path(self.tmp.name) / "state"
        os.umask(0o022)

    def tearDown(self):
        demo.STATE_DIR = self._state

    def _audit_mode(self):
        return stat.S_IMODE(os.stat(demo.assistant_log_path()).st_mode)

    def test_audit_file_is_not_group_or_world_readable(self):
        demo.record_assistant_audit(
            {"userName": "戴雅琴"}, {"counselor"},
            {"intent": "affairs", "scope": {"label": "本班"}}, "本班有谁申请休学？", "/changes",
        )
        self.assertEqual(self._audit_mode(), 0o600, f"审计文件权限为 {oct(self._audit_mode())}")

    def test_repeated_writes_keep_the_tightened_mode(self):
        for index in range(3):
            demo.record_assistant_audit(
                {"userName": f"辅导员{index}"}, {"counselor"}, {"intent": "affairs"}, "追问", "/changes",
            )
        self.assertEqual(len(demo.assistant_log_path().read_text(encoding="utf-8").splitlines()), 3)
        self.assertEqual(self._audit_mode(), 0o600)


class TruncatedBodyTest(unittest.TestCase):
    """请求体读不完时必须回一个明确状态码，不能把连接直接掐了。

    客户端声明了 Content-Length 却拖到 socket 超时，旧实现里 rfile.read 抛
    TimeoutError 且不在任何 try 内，连接被直接关闭：调用方拿到 0 字节，前端只能
    显示「未知错误」。这条断言在没有修复前会因异常外抛而失败。
    """

    class _BoomStream:
        def read(self, _size: int) -> bytes:
            raise TimeoutError("timed out")

    def _handler(self, rfile, responses: list) -> demo.Handler:
        handler = demo.Handler.__new__(demo.Handler)
        handler.headers = {"Content-Length": "64"}
        handler.rfile = rfile
        handler._json = lambda status, payload: responses.append((status, payload))
        return handler

    def test_read_timeout_answers_408(self):
        responses: list = []
        handler = self._handler(self._BoomStream(), responses)
        self.assertIsNone(handler._read_json())
        self.assertEqual([status for status, _ in responses], [408])
        self.assertIn("重试", responses[0][1]["error"])

    def test_incomplete_body_still_parses_as_bad_json(self):
        # 只发了半截 JSON（没超时）必须走 400 而不是 408：两种失败的处理方式不同。
        responses: list = []
        handler = self._handler(io.BytesIO(b'{"question":'), responses)
        self.assertIsNone(handler._read_json())
        self.assertEqual(responses[0][0], 400)


class ClassScopeCountTest(unittest.TestCase):
    """同一个班的两种写法（全称 + 简称）只能算一个班（D-065）。"""

    def test_alias_rows_count_as_one_class(self):
        rows = [
            {"class_code": "26010201", "class_name": "信息安全技术应用2601班",
             "class_short": "信息安全2601", "students": 44, "status": {}},
            {"class_code": "26010201", "class_name": "信息安全2601",
             "class_short": "信息安全2601", "students": 1, "status": {}},
        ]
        metrics = demo.scope_metrics([], [], rows)
        self.assertEqual(1, metrics["total_classes"])
        self.assertEqual(2, metrics["roster_class_names"])

    def test_different_classes_still_count_separately(self):
        rows = [
            {"class_code": "26010201", "class_name": "信息安全2601班", "class_short": "信息安全2601"},
            {"class_code": "26010301", "class_name": "数媒2601班", "class_short": "数媒2601"},
        ]
        self.assertEqual(2, demo.scope_metrics([], [], rows)["total_classes"])

    def test_missing_class_code_falls_back_to_normalized_name(self):
        rows = [
            {"class_code": "", "class_name": "数媒2601", "class_short": "数媒2601"},
            {"class_code": "", "class_name": "数字媒体技术2601班", "class_short": "数媒2601"},
        ]
        self.assertEqual(1, demo.scope_metrics([], [], rows)["total_classes"])

    def test_shipped_fixture_actually_contains_split_class_names(self):
        by_code = {}
        for row in demo.DATA["class_summary"]:
            by_code.setdefault(row.get("class_code"), []).append(row)
        split = next((rows for rows in by_code.values() if len(rows) > 1), None)
        self.assertIsNotNone(split, "演示数据里已查不到同名多写法班级，需重新确认班级数口径")

    def test_student_scope_reports_one_class_for_split_name(self):
        by_code = {}
        for row in demo.DATA["class_summary"]:
            by_code.setdefault(row.get("class_code"), []).append(row)
        rows = next(rows for rows in by_code.values() if len(rows) > 1)
        names = {row.get("class_name") for row in rows}
        student = next(
            s for s in demo.DATA["students"]
            if s.get("class_name") in names and s.get("uid")
        )
        payload = demo.scoped_payload({"userName": student["uid"]}, {"student_portal"})
        self.assertIsNotNone(payload)
        self.assertEqual(len(rows), len(payload["class_summary"]))
        self.assertEqual(1, payload["metrics"]["total_classes"])
        self.assertEqual(len(rows), payload["metrics"]["roster_class_names"])


class DateValidationTest(unittest.TestCase):
    """异动日期必须同时过「格式」与「真实日历日」两道校验（D-069 复测结论）。

    正则里的数字字符类也吃全角与阿拉伯-印度数字，但紧随其后的 strptime 会拒掉，
    最终仍是 400 而不是写进台账；这条把两道校验的分工钉住，防止以后有人把
    strptime 当成冗余删掉。
    """

    def setUp(self):
        self.uid = next(s["uid"] for s in demo.DATA["students"] if s.get("uid"))
        self.user = {"userName": "seed-xgb"}

    def status(self, date):
        body = {"uid": self.uid, "type": "休学", "date": date, "reason": "演示测试"}
        _, status, message = demo.validate_change(body, self.user, {"xgb"})
        return status, message

    def test_valid_date_passes(self):
        status, message = self.status("2026-10-24")
        self.assertEqual(0, status)
        self.assertEqual("", message)

    def test_fullwidth_digits_are_rejected_as_invalid_date(self):
        status, message = self.status("２０２６-１０-２４")
        self.assertEqual(400, status)
        self.assertEqual("异动日期不是有效日期", message)

    def test_other_unicode_digits_are_rejected_as_invalid_date(self):
        status, message = self.status("٢٠٢٦-١٠-٢٤")
        self.assertEqual(400, status)
        self.assertEqual("异动日期不是有效日期", message)

    def test_impossible_calendar_days_are_rejected(self):
        for date in ("2026-10-32", "2026-02-30"):
            status, message = self.status(date)
            self.assertEqual(400, status, date)
            self.assertEqual("异动日期不是有效日期", message, date)

    def test_unpadded_date_is_a_format_error(self):
        status, message = self.status("2026-1-4")
        self.assertEqual(400, status)
        self.assertEqual("异动日期格式应为 YYYY-MM-DD", message)
