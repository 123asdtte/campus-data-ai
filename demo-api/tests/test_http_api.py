"""问数端点的 HTTP 层回归：走真实 socket 与真实路由，只把网关身份那一跳换成桩。

单元测试直接调函数，测不到路径分发、请求体上限、JSON 解析失败、身份缺失时的
状态码，以及健康检查与并发槽的耦合（D-066）。这些只有真发一次 HTTP 请求才看得见。

故意把连接搞坏的用例（超大请求体、裸 socket 分两次写）单独一个类、单独一个服务：
它们会让 Winsock 在同一个进程里留下半发送/未读的数据，跟正常契约用例混跑时会互相干扰
（实测表现为下一个用例 ConnectionAbortedError WinError 10053）。分开跑，断言一条都不减。
"""

import http.client
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import app as demo

CRLF = bytes([13, 10])


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


class HttpBase(unittest.TestCase):
    """自己起一台 Server，身份那一跳按需换成桩。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        demo.STATE_DIR = Path(cls.tmp.name)
        cls.server = demo.Server(("127.0.0.1", 0), demo.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        # 名字必须和被替换的 Handler._identify 不同：同名时 self.xxx 会绑成测试实例的方法，
        # handler 线程里 self 就变成 TestCase，直接 AttributeError 断开连接（D-068 的真实成因）
        cls.original_identify = demo.Handler._identify

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        demo.Handler._identify = cls.original_identify
        cls.tmp.cleanup()

    def setUp(self):
        demo.Handler._identify = type(self).original_identify

    def stub_identity(self, user: dict, roles: set) -> None:
        demo.Handler._identify = lambda self, _u=user, _r=roles: {"user": _u, "roles": _r}

    def student(self) -> dict:
        student = next(s for s in demo.DATA["students"] if s.get("uid"))
        return {"userName": student["uid"], "nickName": student["name"], "userId": "1"}

    def send_raw(self, head: bytes, body: bytes, gap: float = 0.05) -> bytes:
        """先写请求头、停 gap 秒再写请求体，然后读到 EOF。用于复现「服务端读完体才回」的时序。"""
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        collected = b""
        try:
            sock.sendall(head)
            time.sleep(gap)
            sock.sendall(body)
            while True:
                try:
                    chunk = sock.recv(4096)
                except OSError as exc:
                    self.fail(
                        f"响应被 RST 丢弃：{type(exc).__name__}，已收到 {len(collected)} 字节"
                    )
                if not chunk:
                    break
                collected += chunk
        finally:
            sock.close()
        return collected


class HttpContractTest(HttpBase):
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

    def test_missing_token_is_401_not_a_dropped_connection(self):
        status, data = _post(self.port, "/assistant/query", {"question": "明天有什么课"}, token=None)
        self.assertEqual(401, status)
        self.assertEqual("未登录", json.loads(data.decode("utf-8"))["error"])

    def test_role_denied_post_keeps_the_response(self):
        # /changes 的 403 也发生在读请求体之前，同样要让客户端拿到明确拒绝而不是网络错误
        self.stub_identity(self.student(), {"student_portal"})
        status, data = _post(self.port, "/changes", {"uid": "X", "type": "休学"})
        self.assertEqual(403, status)
        self.assertIn("学籍异动", json.loads(data.decode("utf-8"))["error"])

    def test_unknown_path_is_404_before_identity(self):
        # 路径白名单在身份校验之前（app.py 的 do_POST 开头），所以这里不需要任何身份
        status, _data = _post(self.port, "/assistant/nope", {"question": "x"}, token=None)
        self.assertEqual(404, status)

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


class HttpAbusiveClientTest(HttpBase):
    def audit_lines(self) -> int:
        path = demo.assistant_log_path()
        return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0

    def test_body_far_over_limit_is_never_parsed(self):
        # 请求体比排空上限（DRAIN_MAX_BYTES）还大时，服务端读不干净，关闭就是 RST，
        # 413 不保证送达——这是 D-074 明说的取舍：为了「让错误码一定送到」去替攻击者
        # 吞几十 GB，等于把上限本身变成消耗战。所以这里断言真正的契约：这么大的请求体
        # 绝不被解析、绝不留问数痕迹；连接要是还能读，读到的必须是 413。
        # 「刚超限、落在排空窗口内」的送达性由 test_over_limit_body_still_delivers_the_413 钉。
        self.stub_identity(self.student(), {"student_portal"})
        # 请求体要是被读了、被解析了，这条真问题就会 answered 并留下一行审计，
        # 所以「行数不变」是可证伪的断言，不是一句空话。
        body = json.dumps(
            {"question": "明天有什么课" + "啊" * (demo.DRAIN_MAX_BYTES + 10)},
            ensure_ascii=False,
        ).encode("utf-8")
        self.assertGreater(len(body), demo.DRAIN_MAX_BYTES, "示例请求体必须落在排空上限之外")
        before = self.audit_lines()
        status = None
        try:
            status, data = _post(self.port, "/assistant/query", None, raw=body)
        except OSError as exc:
            # RST 是本用例接受的失败方式：连接被中止，但请求绝不能已经被服务端处理
            print(f"[test] 超限请求体被 RST 中止：{type(exc).__name__}", file=sys.stderr)
        if status is not None:
            self.assertEqual(413, status)
            self.assertIn("error", json.loads(data.decode("utf-8")))
        self.assertEqual(before, self.audit_lines(), "超限请求体被解析了：问数审计多了一条")

    def test_deferred_request_body_does_not_lose_the_401(self):
        # D-068：分两次写（先请求头、隔一会儿再请求体）时，服务端若没把请求体读掉就关闭，
        # 内核回的是 RST 而不是 FIN，客户端已收到的 401 会被一起丢弃。真实浏览器和 curl
        # 都可能这样发，所以「未登录」必须稳定送达，不能变成网络错误。
        body = json.dumps({"question": "明天有什么课"}, ensure_ascii=False).encode("utf-8")
        head = (
            b"POST /assistant/query HTTP/1.1\r\nHost: demo\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
        )
        collected = self.send_raw(head, body)
        self.assertIn(b"401", collected.split(CRLF, 1)[0])
        self.assertIn("未登录", collected.decode("utf-8", "replace"))

    def test_over_limit_body_still_delivers_the_413(self):
        # D-074：请求体超限时服务端确实不该解析它，但那些字节已经躺在接收缓冲区里。
        # 不排空就关闭，内核发的是 RST，客户端连已经收到的 413 都会一起丢——实测整轮
        # 测试 10 次里 4 次就是这样红的，前端只会看到「网络错误」而不是「请求体过大」。
        # 这个失败是时序相关的，一次通过证明不了什么，所以连打三次；
        # 任何一次被 RST 吞掉，send_raw 就会红。
        self.stub_identity(self.student(), {"student_portal"})
        body = json.dumps({"question": "啊" * (demo.MAX_BODY_BYTES + 10)}, ensure_ascii=False).encode("utf-8")
        self.assertLessEqual(len(body), demo.DRAIN_MAX_BYTES, "示例请求体必须落在排空上限之内")
        head = (
            b"POST /assistant/query HTTP/1.1\r\nHost: demo\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
        )
        for attempt in range(3):
            collected = self.send_raw(head, body)
            status_line = collected.split(CRLF, 1)[0]
            self.assertIn(b"413", status_line, f"第 {attempt + 1} 次没拿到 413：{status_line!r}")
            self.assertIn("请求体过大", collected.decode("utf-8", "replace"))


class HttpHealthSlotTest(unittest.TestCase):
    """D-066 的既有特征：健康检查与业务抢同一个并发槽，满槽时一起 503。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        demo.STATE_DIR = Path(self.tmp.name)
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
