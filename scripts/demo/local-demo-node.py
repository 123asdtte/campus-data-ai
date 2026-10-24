"""无 Docker 本地演示栈：stub 网关 + demo-api 子进程 + 静态入口。

用途：Docker Desktop 不可用时，在 127.0.0.1:8083 复刻 docker-compose.demo.yml
的对外行为（web 静态资源 + /gw 代理网关 + /demo-api 代理 demo-api），
供浏览器人工验证与 Playwright E2E 使用。

启动：
  python scripts/demo/local-demo-node.py                # 前台运行，Ctrl-C 退出
  DEMO_ENTRY_PORT=8083 DEMO_API_PORT=9181 DEMO_GW_PORT=9180 python scripts/demo/local-demo-node.py

前提：web/dist 已构建（cd web && npm run build）；demo-api 仅用标准库。

边界：stub 网关只实现 RuoYi /auth/login 与 /system/user/getInfo 两个端点，
账号表与 scripts/demo/seed-demo-accounts.sql 保持一致。它不是真实网关：
缺少登录锁定、租户、clientid 校验、JWT 签名等行为，经此栈验证的结论
不能替代 Docker 演示栈或 CI 的 E2E 结果，只用于界面与交互的人工检查。
"""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIST = REPO_ROOT / "web" / "dist"
DEMO_API_DIR = REPO_ROOT / "demo-api"

GW_PORT = int(os.environ.get("DEMO_GW_PORT", "9180"))
API_PORT = int(os.environ.get("DEMO_API_PORT", "9181"))
ENTRY_PORT = int(os.environ.get("DEMO_ENTRY_PORT", "8083"))

# 与 seed-demo-accounts.sql 对齐；密码为本地演示共享口令（见该文件注释）。
ACCOUNTS = {
    "admin": {"password": "admin123", "roles": ["superadmin"], "nick": "系统管理员"},
    "SK-2026-000001": {"password": "Demo@2026", "roles": ["student_portal"], "nick": "万*"},
    "xgb01": {"password": "Demo@2026", "roles": ["xgb"], "nick": "张老师"},
    "counselor01": {"password": "Demo@2026", "roles": ["counselor"], "nick": "戴雅琴"},
}

TOKENS: dict[str, dict] = {}


def json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class StubGatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass

    def _send(self, status: int, payload: dict) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/auth/login":
            self._send(404, {"code": 404, "msg": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"code": 400, "msg": "bad request"})
            return
        username = str(body.get("username", ""))
        password = str(body.get("password", ""))
        account = ACCOUNTS.get(username)
        if account is None:
            # 与真实网关的英文报错保持可被前端 translateLoginError 识别的形态。
            self._send(401, {"code": 401, "msg": f"Your account: {username} does not exist"})
            return
        if password != account["password"]:
            self._send(401, {"code": 401, "msg": "username does not exist/password error"})
            return
        token = secrets.token_urlsafe(32)
        TOKENS[token] = {"userName": username, "roles": list(account["roles"]), "nick": account["nick"]}
        self._send(200, {"code": 200, "msg": "操作成功", "data": {"access_token": token, "expires_in": 72000}})

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/system/user/getInfo":
            self._send(404, {"code": 404, "msg": "not found"})
            return
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        session = TOKENS.get(token)
        if session is None:
            self._send(401, {"code": 401, "msg": "认证失败，无法访问系统资源"})
            return
        self._send(
            200,
            {
                "code": 200,
                "msg": "操作成功",
                "data": {
                    "user": {"userName": session["userName"], "nickName": session["nick"], "dept": None},
                    "roles": session["roles"],
                },
            },
        )


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".map": "application/json; charset=utf-8",
}


class EntryHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # 本机回环上游必须绕开 http_proxy 等环境变量，否则转发会被系统代理吞掉。
    NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass

    def _proxy(self, target_port: int, strip_prefix: str) -> None:
        path = self.path
        if path == strip_prefix or path.startswith(strip_prefix + "/"):
            path = path[len(strip_prefix):] or "/"
        url = f"http://127.0.0.1:{target_port}{path}"
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else None
        headers = {}
        for name in ("Authorization", "Content-Type", "clientid", "Range"):
            value = self.headers.get(name)
            if value:
                headers[name] = value
        request = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        try:
            with EntryHandler.NO_PROXY_OPENER.open(request, timeout=60) as response:
                payload = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/octet-stream"))
                if response.headers.get("Content-Disposition"):
                    self.send_header("Content-Disposition", response.headers["Content-Disposition"])
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json; charset=utf-8"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (urllib.error.URLError, OSError) as exc:
            body = json_bytes({"error": f"upstream unavailable: {exc}"})
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _serve_static(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        candidate = (WEB_DIST / path.lstrip("/")).resolve()
        if not str(candidate).startswith(str(WEB_DIST.resolve())):
            self.send_error(403)
            return
        if not candidate.is_file():
            candidate = WEB_DIST / "index.html"  # SPA 路由回退
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(candidate.suffix, "application/octet-stream"))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _handle(self) -> None:
        if self.command not in ("GET", "HEAD", "POST"):
            self.send_error(405)
            return
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/gw" or path.startswith("/gw/"):
            self._proxy(GW_PORT, "/gw")
            return
        if path == "/demo-api" or path.startswith("/demo-api/"):
            self._proxy(API_PORT, "/demo-api")
            return
        if self.command != "GET":
            self.send_error(404)
            return
        self._serve_static()

    do_GET = _handle  # noqa: N815
    do_HEAD = _handle  # noqa: N815
    do_POST = _handle  # noqa: N802


def main() -> int:
    if not WEB_DIST.is_dir():
        print(f"缺少 {WEB_DIST}，请先 cd web && npm run build", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["GATEWAY_BASE"] = f"http://127.0.0.1:{GW_PORT}"
    env["PORT"] = str(API_PORT)
    env.setdefault("MAX_CONCURRENT_REQUESTS", "32")
    env.setdefault("PYTHONUTF8", "1")
    demo_api = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=DEMO_API_DIR,
        env=env,
    )

    def shutdown(signum, frame):  # noqa: ARG001
        demo_api.terminate()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    gateway = ThreadingHTTPServer(("127.0.0.1", GW_PORT), StubGatewayHandler)
    entry = ThreadingHTTPServer(("127.0.0.1", ENTRY_PORT), EntryHandler)
    print(
        f"本地演示栈：入口 http://127.0.0.1:{ENTRY_PORT}  "
        f"stub 网关 :{GW_PORT}  demo-api :{API_PORT}（state 目录 {env.get('STATE_DIR', DEMO_API_DIR / 'state')}）",
        file=sys.stderr,
    )
    print("演示账号与 seed-demo-accounts.sql 一致；仅限本机使用，不是真实网关。", file=sys.stderr)
    threading.Thread(target=gateway.serve_forever, daemon=True).start()
    try:
        entry.serve_forever()
    finally:
        gateway.shutdown()
        gateway.server_close()
        demo_api.terminate()
        try:
            demo_api.wait(timeout=5)
        except subprocess.TimeoutExpired:
            demo_api.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
