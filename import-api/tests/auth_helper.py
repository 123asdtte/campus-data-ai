"""测试用签名助手：独立实现 canonical，不 import 生产模块。

独立实现的目的：生产代码与测试同时写错时，金标向量（GOLDEN）仍然会失败。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

TEST_SECRET = os.environ.get(
    "INTERNAL_HMAC_SECRET", "campus-test-secret-0123456789abcdef0123"
)

# 金标向量：固定输入 → 固定签名，跨语言实现必须复现
GOLDEN_INPUT = {
    "method": "GET",
    "path": "/imports",
    "query": "limit=1",
    "ts": "1700000000",
    "nonce": "0123456789abcdef",
    "payload_sha": hashlib.sha256(b"").hexdigest(),
    "meta": "",
    "user": "ry:test",
    "role": "college",
    "college": quote("计算机学院", safe="-._~"),
    "colleges": quote("计算机学院", safe="-._~"),
    "dept": "1762000000000000101",
    "admin": "false",
    "perms": "import:batch:list",
}
GOLDEN_SECRET = "test-secret"
GOLDEN_SIGNATURE = "9d934c4c8c41c5430d040f99bd142ba815b5b85bf738d7c309da80be4f42500a"

COLLEGE_A = "计算机学院"
COLLEGE_B = "电子信息学院"

WHO_ADMIN: Dict[str, str] = {
    "user": "ry:admin",
    "role": "superadmin",
    "college": "",
    "colleges": "",
    "dept_id": "",
    "admin": "true",
    "perms": "",
}

WHO_COLLEGE: Dict[str, str] = {
    "user": "ry:college_a",
    "role": "college",
    "college": COLLEGE_A,
    "colleges": COLLEGE_A,
    "dept_id": "1762000000000000101",
    "admin": "false",
    "perms": "student:list student:write import:batch:list import:batch:detail "
             "import:batch:upload import:batch:remap import:batch:validate import:batch:commit",
}

WHO_NO_COLLEGE: Dict[str, str] = {
    "user": "ry:no_college",
    "role": "college",
    "college": "",
    "colleges": "",
    "dept_id": "",
    "admin": "false",
    "perms": "student:list",
}

WHO_READONLY: Dict[str, str] = {
    "user": "ry:viewer",
    "role": "viewer",
    "college": COLLEGE_A,
    "colleges": COLLEGE_A,
    "dept_id": "1762000000000000101",
    "admin": "false",
    "perms": "student:list import:batch:list import:batch:detail",
}


def pct(value: object) -> str:
    return quote(str(value), safe="-._~")


def norm_pairs(pairs: Iterable[Tuple[str, str]]) -> str:
    return "&".join(f"{pct(k)}={pct(v)}" for k, v in sorted(pairs, key=lambda kv: kv[0]))


def norm_query(query: Optional[Any]) -> str:
    if query is None:
        return ""
    if isinstance(query, str):
        return norm_pairs(item.split("=", 1) for item in query.split("&") if item)
    items = query.items() if isinstance(query, dict) else query
    return norm_pairs([(str(k), str(v)) for k, v in items])


def canonical(method: str, path: str, query: str, ts: str, nonce: str, payload_sha: str,
              meta: str, user: str, role: str, college: str, colleges: str,
              dept: str, admin: str, perms: str) -> str:
    return "\n".join([method.upper(), path, query, ts, nonce, payload_sha, meta,
                      user, role, college, colleges, dept, admin, perms])


def sign(
    method: str,
    path: str,
    *,
    query: Optional[Any] = None,
    body: bytes = b"",
    file_bytes: Optional[bytes] = None,
    form: Optional[Dict[str, str]] = None,
    who: Optional[Dict[str, str]] = None,
    ts: Optional[str] = None,
    nonce: Optional[str] = None,
    secret: str = TEST_SECRET,
    tamper: bool = False,
) -> Dict[str, str]:
    who = who or WHO_COLLEGE
    ts = ts or str(int(time.time()))
    nonce = nonce or uuid.uuid4().hex
    payload_sha = hashlib.sha256(file_bytes if file_bytes is not None else body).hexdigest()
    meta = norm_pairs((form or {}).items()) if file_bytes is not None else ""
    college = pct(who.get("college", ""))
    colleges = pct(who.get("colleges", ""))
    admin = "true" if who.get("admin") == "true" else "false"
    perms = " ".join(sorted((who.get("perms") or "").split()))

    sig = hmac.new(
        secret.encode(),
        canonical(method, path, norm_query(query), ts, nonce, payload_sha, meta,
                  who.get("user", ""), who.get("role", ""), college, colleges,
                  who.get("dept_id", ""), admin, perms).encode(),
        hashlib.sha256,
    ).hexdigest()
    if tamper:
        sig = "0" * 64

    return {
        "X-Internal-User": who.get("user", ""),
        "X-Internal-Role": who.get("role", ""),
        "X-Internal-College": college,
        "X-Internal-Colleges": colleges,
        "X-Internal-Dept": who.get("dept_id", ""),
        "X-Internal-Admin": admin,
        "X-Internal-Perms": perms,
        "X-Internal-Timestamp": ts,
        "X-Internal-Nonce": nonce,
        "X-Internal-Payload-Sha256": payload_sha,
        "X-Internal-Signature": sig,
    }


def request(
    client,
    method: str,
    path: str,
    *,
    query: Optional[Any] = None,
    json_body: Optional[Any] = None,
    file_bytes: Optional[bytes] = None,
    filename: str = "sample.csv",
    form: Optional[Dict[str, str]] = None,
    who: Optional[Dict[str, str]] = None,
    ts: Optional[str] = None,
    nonce: Optional[str] = None,
    tamper: bool = False,
    extra_headers: Optional[Dict[str, str]] = None,
):
    """发送带签名的请求。json 用 content= 发送，确保签名覆盖的就是实际字节。"""
    headers: Dict[str, str] = {}
    kwargs: Dict[str, Any] = {}

    if file_bytes is not None:
        body = b""
        kwargs["files"] = {"file": (filename, file_bytes, "text/csv")}
        kwargs["data"] = form or {}
    elif json_body is not None:
        body = json.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
        kwargs["content"] = body
    else:
        body = b""
        kwargs["content"] = b""

    headers.update(sign(method, path, query=query, body=body, file_bytes=file_bytes,
                        form=form, who=who, ts=ts, nonce=nonce, tamper=tamper))
    if extra_headers:
        headers.update(extra_headers)

    return client.request(method, path, headers=headers, params=query, **kwargs)
