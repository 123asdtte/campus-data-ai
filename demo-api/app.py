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
import re
import secrets
import sys
import threading
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "demo-data.json"
FOUR_SHEET_PATH = BASE_DIR / "data" / "four-sheet.xlsx"
STATE_DIR = Path(os.environ.get("STATE_DIR", str(BASE_DIR / "state")))
STATE_PATH = STATE_DIR / "ledger.json"
GATEWAY_BASE = os.environ.get("GATEWAY_BASE", "http://gateway:9180").rstrip("/")
CLIENT_ID = os.environ.get(
    "GATEWAY_CLIENT_ID", "e5cd7e4891bf95d1d19206ce24a7b32e"
)
STAFF_ROLES = {"xgb", "superadmin"}
CHANGE_TYPES = {"休学", "复学", "退学", "转专业", "保留学籍", "跟读生转正式", "预科生转正", "留级"}
MAX_LOCAL_CHANGES = 500
MAX_BODY_BYTES = 8 * 1024
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATE_LOCK = threading.Lock()

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


def load_ledger() -> dict:
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"changes": [], "checked": {}}
    if not isinstance(payload, dict):
        return {"changes": [], "checked": {}}
    changes = payload.get("changes")
    checked = payload.get("checked")
    return {
        "changes": changes if isinstance(changes, list) else [],
        "checked": checked if isinstance(checked, dict) else {},
    }


def save_ledger(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, STATE_PATH)


def counselor_keys(user: dict) -> tuple[set[str], set[str]]:
    counselor = (user.get("nickName") or user.get("userName") or "").strip()
    username = (user.get("userName") or "").strip()
    students = [
        s for s in (DATA.get("students") or [])
        if s.get("counselor") in {counselor, username}
    ]
    uids = {s.get("uid") for s in students if s.get("uid")}
    class_keys = {
        key
        for s in students
        for key in (s.get("class_name"), s.get("class_short"))
        if key
    }
    return uids, class_keys


def visible_uids(user: dict, roles: set[str]) -> set[str] | None:
    """None 表示全校；空集合表示无可见范围。"""
    if roles & STAFF_ROLES:
        return None
    if "counselor" in roles:
        return counselor_keys(user)[0]
    uid = (user.get("userName") or "").strip()
    return {uid} if uid else set()


def merge_ledger(user: dict, roles: set[str], state: dict) -> tuple[list[dict], list[str]]:
    uids = visible_uids(user, roles)
    all_changes = list(DATA.get("changes") or []) + list(state["changes"])
    if uids is not None:
        all_changes = [c for c in all_changes if c.get("uid") in uids]
    numbers = {c.get("change_no") for c in all_changes}
    checked = [no for no in state["checked"] if no in numbers]
    return all_changes, checked


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
    with STATE_LOCK:
        state = load_ledger()

    if roles & STAFF_ROLES:
        changes, checked = merge_ledger(user, roles, state)
        metrics = dict(DATA.get("metrics") or {})
        metrics.update({
            "change_total": len(changes),
            "change_type_counts": counts([c.get("type", "") for c in changes]),
            "change_status_counts": counts([c.get("status", "") for c in changes]),
        })
        return {**DATA, "metrics": metrics, "changes": changes, "platform_checked": checked}

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
        changes, checked = merge_ledger(user, roles, state)
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
            "platform_checked": checked,
        }

    if "counselor" in roles:
        counselor = (user.get("nickName") or user.get("userName") or "").strip()
        username = (user.get("userName") or "").strip()
        uids, class_keys = counselor_keys(user)
        students = [s for s in students_all if s.get("uid") in uids]
        schedule = [
            row for row in (DATA.get("schedule") or [])
            if row.get("class_name") in class_keys or row.get("class_short") in class_keys
        ]
        changes, checked = merge_ledger(user, roles, state)
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
            "platform_checked": checked,
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

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            self._json(400, {"error": "请求体为空"})
            return None
        if length > MAX_BODY_BYTES:
            self._json(413, {"error": "请求体过大"})
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "请求体不是合法 JSON"})
            return None
        if not isinstance(payload, dict):
            self._json(400, {"error": "请求体必须是对象"})
            return None
        return payload

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in ("/changes", "/changes/check"):
            self._json(404, {"error": "not found"})
            return
        identity = self._identify()
        if identity is None:
            return
        user = identity["user"]
        roles = identity["roles"]
        if not (roles & STAFF_ROLES or "counselor" in roles):
            self._json(403, {"error": "当前角色不能管理学籍异动"})
            return
        body = self._read_json()
        if body is None:
            return
        if path == "/changes":
            self._create_change(user, roles, body)
        else:
            self._check_change(user, roles, body)

    def _create_change(self, user: dict, roles: set[str], body: dict) -> None:
        uid = str(body.get("uid") or "").strip()
        change_type = str(body.get("type") or "").strip()
        date = str(body.get("date") or "").strip()
        reason = str(body.get("reason") or "").strip()
        target = str(body.get("target") or "").strip() or "—"
        if not uid:
            self._json(400, {"error": "缺少学生 UID"})
            return
        if change_type not in CHANGE_TYPES:
            self._json(400, {"error": "异动类型不在允许范围"})
            return
        if not DATE_PATTERN.match(date):
            self._json(400, {"error": "异动日期格式应为 YYYY-MM-DD"})
            return
        if not 1 <= len(reason) <= 200 or len(target) > 200:
            self._json(400, {"error": "原因需为 1-200 字，去向不超过 200 字"})
            return
        if not any(s.get("uid") == uid for s in (DATA.get("students") or [])):
            self._json(404, {"error": "学生不存在"})
            return
        scope = visible_uids(user, roles)
        if scope is not None and uid not in scope:
            self._json(403, {"error": "该学生不在当前账号的数据范围内"})
            return

        username = (user.get("userName") or "").strip()
        with STATE_LOCK:
            state = load_ledger()
            if len(state["changes"]) >= MAX_LOCAL_CHANGES:
                self._json(409, {"error": "本地演示台账已达上限，请清理 state/ledger.json"})
                return
            existing = {c.get("change_no") for c in (DATA.get("changes") or [])}
            existing.update(c.get("change_no") for c in state["changes"])
            while True:
                change_no = f"YD-LOCAL-{datetime.now():%Y%m%d%H%M%S}-{secrets.token_hex(2)}"
                if change_no not in existing:
                    break
            change = {
                "uid": uid,
                "change_no": change_no,
                "type": change_type,
                "date": date,
                "reason": reason,
                "target": target,
                "status": "审批中",
                "created_by": username,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            state["changes"].insert(0, change)
            save_ledger(state)
        print(f"[demo-api] change created by {username}: {change_no} {uid} {change_type}", file=sys.stderr)
        self._json(201, {"change": change})

    def _check_change(self, user: dict, roles: set[str], body: dict) -> None:
        change_no = str(body.get("change_no") or "").strip()
        if not change_no:
            self._json(400, {"error": "缺少异动编号"})
            return
        with STATE_LOCK:
            state = load_ledger()
            change = next(
                (c for c in state["changes"] if c.get("change_no") == change_no),
                None,
            ) or next(
                (c for c in (DATA.get("changes") or []) if c.get("change_no") == change_no),
                None,
            )
            if not change:
                self._json(404, {"error": "异动记录不存在"})
                return
            scope = visible_uids(user, roles)
            if scope is not None and change.get("uid") not in scope:
                self._json(403, {"error": "该异动不在当前账号的数据范围内"})
                return
            username = (user.get("userName") or "").strip()
            state["checked"][change_no] = {
                "by": username,
                "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            save_ledger(state)
        print(f"[demo-api] change checked by {username}: {change_no}", file=sys.stderr)
        self._json(200, {"change_no": change_no, "checked": True})


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"demo-api listening on :{port}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
