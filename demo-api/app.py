#!/usr/bin/env python
"""本地演示数据只读服务：按网关身份返回授权范围内的数据。

- 学生：本人档案 + 本人班级课表 + 本人异动；
- 辅导员：本人所带班级/学生/异动；
- 学工处、管理员：全校演示数据；
- 四件套 Excel 仅学工处/管理员可下载。

数据文件只存在于服务端镜像，不再由 web/public 公开提供。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "demo-data.json"
FOUR_SHEET_PATH = BASE_DIR / "data" / "four-sheet.xlsx"
GATEWAY_BASE = os.environ.get("GATEWAY_BASE", "http://gateway:9180").rstrip("/")
CLIENT_ID = os.environ.get(
    "GATEWAY_CLIENT_ID", "e5cd7e4891bf95d1d19206ce24a7b32e"
)
STAFF_ROLES = {"xgb", "superadmin"}

# Docker Desktop 会注入 127.0.0.1:8080 代理；容器内没有该代理。
# 网关调用必须直连，不能被环境代理劫持。
NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

try:
    DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    print(f"demo-api: 无法加载 {DATA_PATH}: {exc}", file=sys.stderr)
    raise SystemExit(1)


def counts(items: list[str]) -> list[dict]:
    return [
        {"name": name, "count": value}
        for name, value in Counter(item for item in items if item).most_common()
    ]


def scope_metrics(students: list[dict], changes: list[dict], classes: list[dict]) -> dict:
    base = DATA.get("metrics") or {}
    return {
        "disclaimer": base.get("disclaimer", ""),
        "generated_at": base.get("generated_at", ""),
        "source": base.get("source", ""),
        "total_students": len(students),
        "total_classes": len(classes),
        "roster_class_names": len(classes),
        "total_colleges": len({s.get("college") for s in students if s.get("college")}),
        "total_majors": len({s.get("major") for s in students if s.get("major")}),
        "total_counselors": len({s.get("counselor") for s in students if s.get("counselor")}),
        "status_counts": counts([s.get("status", "") for s in students]),
        "college_counts": counts([s.get("college", "") for s in students]),
        "grade_counts": counts([s.get("grade", "") for s in students]),
        "top_majors": [],
        "change_total": len(changes),
        "change_type_counts": counts([c.get("type", "") for c in changes]),
        "change_status_counts": counts([c.get("status", "") for c in changes]),
        "orphan_changes": 0,
        "registration": {},
        "data_quality": {},
        "affairs": [],
        "source_files": [],
        "schedule_meta": base.get("schedule_meta") or {},
    }


def scoped_payload(user: dict, roles: set[str]) -> dict | None:
    """返回该身份可见的数据；无权限返回 None。"""
    if roles & STAFF_ROLES:
        return DATA

    students_all = DATA.get("students") or []
    if "student_portal" in roles:
        uid = (user.get("userName") or "").strip()
        student = next((s for s in students_all if s.get("uid") == uid), None)
        if not student:
            return None
        class_keys = {student.get("class_name"), student.get("class_short")} - {None, ""}
        schedule = [
            row for row in (DATA.get("schedule") or [])
            if row.get("class_name") in class_keys or row.get("class_short") in class_keys
        ]
        changes = [c for c in (DATA.get("changes") or []) if c.get("uid") == uid]
        classes = [
            c for c in (DATA.get("class_summary") or [])
            if c.get("class_name") in class_keys or c.get("class_short") in class_keys
        ]
        return {
            "meta": DATA.get("meta") or {},
            "metrics": scope_metrics([student], changes, classes),
            "students": [student],
            "schedule": schedule,
            "changes": changes,
            "class_summary": classes,
            "anomalies": [],
        }

    if "counselor" in roles:
        counselor = (user.get("nickName") or user.get("userName") or "").strip()
        username = (user.get("userName") or "").strip()
        students = [
            s for s in students_all
            if s.get("counselor") in {counselor, username}
        ]
        uids = {s.get("uid") for s in students}
        class_keys = {
            key
            for s in students
            for key in (s.get("class_name"), s.get("class_short"))
            if key
        }
        schedule = [
            row for row in (DATA.get("schedule") or [])
            if row.get("class_name") in class_keys or row.get("class_short") in class_keys
        ]
        changes = [c for c in (DATA.get("changes") or []) if c.get("uid") in uids]
        classes = [
            c for c in (DATA.get("class_summary") or [])
            if c.get("counselor") in {counselor, username}
        ]
        return {
            "meta": DATA.get("meta") or {},
            "metrics": scope_metrics(students, changes, classes),
            "students": students,
            "schedule": schedule,
            "changes": changes,
            "class_summary": classes,
            "anomalies": [],
        }

    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "campus-demo-api"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        print("[demo-api] " + (fmt % args), file=sys.stderr)

    def _send(self, status: int, body: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _identify(self) -> dict | None:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._json(401, {"error": "未登录"})
            return None
        request = urllib.request.Request(
            GATEWAY_BASE + "/system/user/getInfo",
            headers={
                "Authorization": auth,
                "clientid": CLIENT_ID,
                "Accept": "application/json",
            },
        )
        try:
            with NO_PROXY_OPENER.open(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self._json(401 if exc.code == 401 else 503, {"error": "身份校验失败"})
            return None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            print(f"demo-api: 网关不可用: {exc}", file=sys.stderr)
            self._json(503, {"error": "身份服务暂不可用"})
            return None
        if payload.get("code") != 200 or not payload.get("data"):
            self._json(401, {"error": "身份校验失败"})
            return None
        data = payload["data"]
        return {
            "user": data.get("user") or {},
            "roles": set(data.get("roles") or []),
        }

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return
        if path not in ("/data", "/four-sheet"):
            self._json(404, {"error": "not found"})
            return

        identity = self._identify()
        if identity is None:
            return
        roles = identity["roles"]
        if path == "/four-sheet":
            if not (roles & STAFF_ROLES):
                self._json(403, {"error": "当前角色无权下载全校四件套"})
                return
            try:
                body = FOUR_SHEET_PATH.read_bytes()
            except OSError:
                self._json(503, {"error": "四件套文件不可用"})
                return
            self._send(
                200, body,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "four-sheet.xlsx",
            )
            return

        payload = scoped_payload(identity["user"], roles)
        if payload is None:
            self._json(403, {"error": "当前角色没有可用的数据范围"})
            return
        self._json(200, payload)


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"demo-api listening on :{port}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
