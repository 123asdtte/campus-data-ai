#!/usr/bin/env python
"""本地演示栈冒烟测试（只读，不改数据）。

检查：
  1. 8083 健康探针与登录页可访问；
  2. 四个演示账号能通过网关登录并拿到预期角色；
  3. 缺 token / 伪造 token 不能读取身份。

用法：
    python scripts/demo/smoke-demo.py
    DEMO_BASE_URL=http://127.0.0.1:8083 python scripts/demo/smoke-demo.py

演示口令仅用于本机虚构数据环境，禁止用于正式环境。
"""
from __future__ import annotations

import sys as _sys

if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:8083").rstrip("/")
CLIENT_ID = "e5cd7e4891bf95d1d19206ce24a7b32e"
TIMEOUT = 10

ACCOUNTS = [
    ("SK-2026-000001", "Demo@2026", "student_portal", "学生"),
    ("counselor01", "Demo@2026", "counselor", "辅导员"),
    ("xgb01", "Demo@2026", "xgb", "学工处"),
    ("admin", "admin123", "superadmin", "管理员"),
]

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def request(method: str, path: str, payload: dict | None = None, token: str | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["clientid"] = CLIENT_ID
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except OSError as exc:
        raise RuntimeError(f"{method} {path} 不可达：{exc}") from exc


def get_json(method: str, path: str, payload: dict | None = None, token: str | None = None):
    status, raw = request(method, path, payload, token)
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, {}


def response_headers(path: str) -> dict[str, str]:
    req = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return {key.lower(): value for key, value in resp.headers.items()}
    except OSError as exc:
        raise RuntimeError(f"GET {path} 不可达：{exc}") from exc


def main() -> None:
    try:
        status, _ = request("GET", "/healthz")
        check("演示站 healthz", status == 200, f"HTTP {status}")

        status, raw = request("GET", "/login")
        html = raw.decode("utf-8", errors="ignore")
        check("登录页可访问", status == 200 and 'id="root"' in html, f"HTTP {status}")

        headers = response_headers("/login")
        check(
            "基础安全响应头",
            headers.get("x-content-type-options") == "nosniff" and headers.get("x-frame-options") == "DENY",
        )
        csp = headers.get("content-security-policy", "")
        check(
            "CSP 已启用",
            "script-src 'self'" in csp and "object-src 'none'" in csp,
            csp[:80] + ("…" if len(csp) > 80 else ""),
        )

        for username, password, expected_role, label in ACCOUNTS:
            status, payload = get_json(
                "POST",
                "/gw/auth/login",
                {
                    "clientId": CLIENT_ID,
                    "grantType": "password",
                    "username": username,
                    "password": password,
                    "tenantId": "000000",
                },
            )
            data = payload.get("data") or {}
            token = data.get("access_token")
            check(f"{label} 登录", status == 200 and payload.get("code") == 200 and bool(token), f"{username}")
            if not token:
                continue

            status, info = get_json("GET", "/gw/system/user/getInfo", token=token)
            info_data = info.get("data") or {}
            roles = info_data.get("roles") or []
            user = (info_data.get("user") or {}).get("userName")
            check(
                f"{label} 角色",
                status == 200 and info.get("code") == 200 and expected_role in roles,
                f"{username} -> {roles}",
            )
            check(f"{label} 身份一致", user == username, f"{user!r}")

            if expected_role == "student_portal":
                check("学生无员工角色", not ({"counselor", "xgb", "superadmin"} & set(roles)), str(roles))

            data_status, data = get_json("GET", "/demo-api/data", token=token)
            students = data.get("students") or []
            if expected_role == "student_portal":
                check(
                    "学生数据范围",
                    data_status == 200 and len(students) == 1
                    and students[0].get("uid") == username
                    and len(data.get("schedule") or []) > 0,
                    f"{len(students)} 学生 / {len(data.get('schedule') or [])} 排课",
                )
            elif expected_role == "counselor":
                nickname = (info_data.get("user") or {}).get("nickName")
                scoped = bool(students) and len(students) < 5000 and all(
                    item.get("counselor") == nickname for item in students
                )
                check(
                    "辅导员数据范围",
                    data_status == 200 and scoped,
                    f"{len(students)} 学生 / {len(data.get('class_summary') or [])} 班级",
                )
            else:
                check(
                    "全校角色数据范围",
                    data_status == 200 and len(students) > 5000,
                    f"{len(students)} 学生",
                )

            sheet_status, _ = request("GET", "/demo-api/four-sheet", token=token)
            expected_sheet = 200 if expected_role in {"xgb", "superadmin"} else 403
            check(f"{label} 四件套权限", sheet_status == expected_sheet, f"HTTP {sheet_status}")

            if expected_role == "student_portal":
                change_status, _ = get_json(
                    "POST",
                    "/demo-api/changes",
                    {
                        "uid": username,
                        "type": "休学",
                        "date": "2026-10-24",
                        "reason": "冒烟：学生不应能登记",
                    },
                    token=token,
                )
                check("学生不能登记异动", change_status == 403, f"HTTP {change_status}")

        status, payload = get_json("GET", "/gw/system/user/getInfo")
        check("缺 token 拒绝读身份", not (status == 200 and payload.get("code") == 200), f"HTTP {status}")

        status, payload = get_json("GET", "/gw/system/user/getInfo", token="invalid-token")
        check("伪 token 拒绝读身份", not (status == 200 and payload.get("code") == 200), f"HTTP {status}")

        status, payload = get_json(
            "POST",
            "/gw/auth/login",
            {
                "clientId": CLIENT_ID,
                "grantType": "password",
                "username": "__smoke_nonexistent__",
                "password": "not-a-real-password",
                "tenantId": "000000",
            },
        )
        check("不存在账号登录失败", not (status == 200 and payload.get("code") == 200), f"HTTP {status}")

        status, _ = request("GET", "/demo-api/data")
        check("数据接口拒绝匿名请求", status == 401, f"HTTP {status}")

        status, _ = request(
            "POST",
            "/demo-api/changes",
            {"uid": "SK-2026-000001", "type": "休学", "date": "2026-10-24", "reason": "匿名"},
        )
        check("异动接口拒绝匿名请求", status == 401, f"HTTP {status}")

        status, _ = request("GET", "/demo/demo-data.json")
        check("旧公开数据入口已关闭", status == 404, f"HTTP {status}")
    except RuntimeError as exc:
        print(f"[FAIL] {exc}")
        failures.append(str(exc))

    print()
    if failures:
        print(f"冒烟失败：{len(failures)} 项")
        sys.exit(1)
    print(f"冒烟通过：{BASE}")


if __name__ == "__main__":
    main()
