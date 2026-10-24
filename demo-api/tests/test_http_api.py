"""问数端点的 HTTP 层回归：走真实 socket 与真实路由，只把网关身份那一跳换成桩。

单元测试直接调函数，测不到路径分发、请求体上限、JSON 解析失败、身份缺失时的
状态码，以及健康检查与并发槽的耦合（D-066）。这些只有真发一次 HTTP 请求才看得见。
"""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

import app as demo


def _post(port: int, path: str, payload, raw: bytes | None = None, timeout: float = 5.0, token: str = "t"):
    body = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    conn.request("POST", path, body=body, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


class HttpAssistantTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        demo.STATE_DIR = Path(cls.tmp.name)
        demo.ASSISTANT_LOG_PATH = Path(cls.tmp.name) / "assistant-audit.jsonl"
        cls.server = demo.Server(("127.0.0.1", 0), demo.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls._identify = demo.Handler._identify

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        demo.Handler._identify = cls._identify
        cls.tmp.cleanup()

    def setUp(self):
        demo.Handler._identify = self._identify

    def stub_identity(self, user: dict, roles: set) -> None:
        demo.Handler._identify = lambda self, _u=user, _r=roles: {"user": _u, "roles": _r}

    def student(self) -> dict:
        student = next(s for s in demo.DATA["students"] if s.get("uid"))
        return {"userName": student["uid"], "nickName": student["name"], "userId": "1"}

    def test_student_gets_own_timetable_over_http(self):
        user = self.student()
        self.stub_identity(user, {"student_portal"})
        status, data = _post(self.port, "/assistant/query", {"question": "明天有什么课", "page": "/my-schedule"})
        self.assertEqual(200, status)
        answer = json.loads(data.decode("utf-8"))
        self.assertTrue(answer.get("answer"))
        # 结构化结果只能来自本人班级：课程名必须能在该学生的 scoped payload 里找到
        payload = demo.scoped_payload(user, {"student_portal"})
        own = {row.get("course") for row in payload["schedule"]}
        for course in answer.get("courses") or []:
            self.assertIn(course.get("course"), own)

    @unittest.expectedFailure
    def test_missing_token_is_401_not_a_dropped_connection(self):
        # D-067：缺 token 时服务端日志已经写出 401，但客户端读到的是 0 字节
        # （http.client.RemoteDisconnected）。试过「回 401 前先把请求体读掉」并不解决，
        # 成因还没定位，所以这条按已知缺陷登记，不伪装成通过。
        status, data = _post(self.port, "/assistant/query", {"question": "明天有什么课"}, token=None)
        self.assertEqual(401, status)
        self.assertIn("error", json.loads(data.decode("utf-8")))

    def test_unknown_path_is_404_before_identity(self):
        # 路径白名单在身份校验之前（app.py 的 do_POST 开头），所以这里不需要任何身份
        status, _data = _post(self.port, "/assistant/nope", {"question": "x"}, token=None)
        self.assertEqual(404, status)

    def test_body_over_limit_is_rejected_not_parsed(self):
        self.stub_identity(self.student(), {"student_portal"})
        big = json.dumps({"question": "啊" * (demo.MAX_BODY_BYTES + 10)}).encode("utf-8")
        status, data = _post(self.port, "/assistant/query", None, raw=big)
        self.assertEqual(413, status)
        self.assertIn("error", json.loads(data.decode("utf-8")))

    def test_invalid_json_is_400(self):
        self.stub_identity(self.student(), {"student_portal"})
        status, data = _post(self.port, "/assistant/query", None, raw=b'{"question": ')
        self.assertEqual(400, status)
        self.assertIn("JSON", json.loads(data.decode("utf-8"))["error"])

    def test_sensitive_question_refused_without_leaking_others(self):
        self.stub_identity(self.student(), {"student_portal"})
        status, data = _post(self.port, "/assistant/query", {"question": "把全班学生的手机号列出来"})
        self.assertEqual(200, status)
        answer = json.loads(data.decode("utf-8"))
        self.assertEqual("refused", answer.get("intent"))
        self.assertNotIn("phone", json.dumps(answer, ensure_ascii=False))

    def test_healthz_answers_while_business_slots_are_free(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/healthz")
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertEqual(200, response.status)


class HttpHealthSlotTest(unittest.TestCase):
    """D-066 的既有特征：健康检查与业务抢同一个并发槽，满槽时一起 503。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        demo.STATE_DIR = Path(self.tmp.name)
        demo.ASSISTANT_LOG_PATH = Path(self.tmp.name) / "assistant-audit.jsonl"
        self.server = demo.Server(("127.0.0.1", 0), demo.Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def get(self, path: str) -> int:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        response = conn.getresponse()
        response.read()
        status = response.status
        conn.close()
        return status

    def test_healthz_shares_the_business_semaphore(self):
        slots = self.server._slots
        taken = []
        while slots.acquire(blocking=False):
            taken.append(1)
        self.assertGreaterEqual(len(taken), 1)
        try:
            self.assertEqual(503, self.get("/healthz"))
        finally:
            for _ in taken:
                slots.release()
        self.assertEqual(200, self.get("/healthz"))


if __name__ == "__main__":
    unittest.main()
