"""内部请求认证：HMAC 验签、可信身份、权限点与数据范围。

设计约束（与 docs/INTERNAL-AUTH-SPEC.md 一致）：
1. 只信任服务端签名；浏览器提交的 X-Actor / X-Internal-* 一律不可信。
2. 开关关闭时不启用验签，仅为兼容旧行为；新增写接口在关闭态**不注册**。
3. 密钥缺失或过短时 fail-closed；开启开关但缺少 nonce 表时启动即失败。
4. 签名覆盖：方法、路径、规范化 query、时间戳、nonce、请求体/文件摘要、
   multipart 非文件字段、用户、角色、学院、学院集合、部门、管理员标记、权限点。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import Dict, Iterable, Optional, Set, Tuple
from urllib.parse import parse_qsl, quote, unquote

from fastapi import Header, HTTPException, Request

from .config import settings
from .db import pool

# 关闭态与开启态在导入期二选一；切换开关必须重启进程。
AUTH_ENABLED: bool = settings.internal_auth_enabled

MAX_SKEW_SECONDS: int = settings.internal_auth_max_skew_seconds
NONCE_TTL_HOURS: int = settings.internal_nonce_ttl_hours

_DEPT_RE = re.compile(r"^\d{1,19}$")
_TS_RE = re.compile(r"^\d{10,13}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9._~-]{16,64}$")

# PR-C（批次范围 + 逐行校验）完成前，导入接口只允许服务端认定的管理员。
# 常量而非环境变量：避免被部署配置意外关闭。
IMPORT_ADMIN_ONLY = True


class Who(Dict[str, str]):
    """验签通过后的可信身份。

    注意：admin 使用严格字符串比较，不接受 "TRUE"/"1" 等宽松写法。
    """

    @property
    def user(self) -> str:
        return self.get("user", "")

    @property
    def role(self) -> str:
        return self.get("role", "")

    @property
    def college(self) -> Optional[str]:
        return None if self.is_admin else (self.get("college") or None)

    @property
    def colleges(self) -> Set[str]:
        raw = self.get("colleges") or ""
        return {c for c in (x.strip() for x in raw.split(",")) if c}

    @property
    def dept_id(self) -> Optional[int]:
        value = (self.get("dept_id") or "").strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @property
    def perms(self) -> Set[str]:
        raw = self.get("perms") or ""
        return {p for p in (x.strip() for x in raw.split(" ")) if p}

    @property
    def is_admin(self) -> bool:
        return self.get("admin") == "true"

    def has(self, perm: str) -> bool:
        return self.is_admin or perm in self.perms

    def can_cross_college(self) -> bool:
        return self.has("import:batch:cross_college")


# --------------------------------------------------------------------- 规范化


def _pct(value: object) -> str:
    """逐字节 percent-encoding，仅保留 A-Za-z0-9-._~（与网关实现对齐）。"""
    return quote(str(value), safe="-._~")


def _norm_pairs(pairs: Iterable[Tuple[str, str]]) -> str:
    """按键排序后拼接 k=v；用于 query 与 multipart 字段。"""
    return "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(pairs, key=lambda kv: kv[0]))


def _norm_query(raw: str) -> str:
    return _norm_pairs(parse_qsl(raw, keep_blank_values=True))


def _canonical(method: str, path: str, query: str, ts: str, nonce: str, payload_sha: str,
               meta: str, user: str, role: str, college: str, colleges: str,
               dept: str, admin: str, perms: str) -> bytes:
    return "\n".join([method.upper(), path, query, ts, nonce, payload_sha, meta,
                      user, role, college, colleges, dept, admin, perms]).encode()


async def _payload_and_meta(request: Request) -> Tuple[str, str]:
    """multipart 用文件内容摘要 + 非文件字段；其它用原始 body 摘要。"""
    ctype = (request.headers.get("content-type") or "").lower()
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(status_code=400, detail="缺少上传文件")
        data = await upload.read()
        await upload.seek(0)  # 交还给路由继续读取
        meta_pairs = [(str(k), str(v)) for k, v in form.multi_items() if k != "file"]
        return hashlib.sha256(data).hexdigest(), _norm_pairs(meta_pairs)
    body = await request.body()
    return hashlib.sha256(body).hexdigest(), ""


# --------------------------------------------------------------------- nonce


def _consume_nonce(nonce: str) -> bool:
    """原子消费 nonce；返回 False 表示重放。"""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO campus.internal_nonce (nonce) VALUES (%s) "
                "ON CONFLICT (nonce) DO NOTHING RETURNING nonce",
                (nonce,),
            )
            return cur.fetchone() is not None


def cleanup_nonce() -> int:
    """删除过期 nonce。只经由受控函数执行，应用账号无表级 DELETE。"""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT campus.cleanup_internal_nonce() AS removed")
            row = cur.fetchone()
            return int(row["removed"]) if row else 0


def assert_nonce_ready() -> None:
    """开启认证但未执行 sql/004 时，启动阶段直接失败。"""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('campus.internal_nonce') AS oid")
            row = cur.fetchone()
    if not row or row["oid"] is None:
        raise RuntimeError("internal_nonce 表不存在：请先执行 sql/004_internal_auth.sql")


# --------------------------------------------------------------------- 依赖


async def _anonymous() -> None:
    """关闭态身份：显式返回 None，不代表任何权限。"""
    return None


async def require_internal(
    request: Request,
    x_internal_user: Optional[str] = Header(default=None),
    x_internal_role: Optional[str] = Header(default=None),
    x_internal_college: Optional[str] = Header(default=None),
    x_internal_colleges: Optional[str] = Header(default=None),
    x_internal_dept: Optional[str] = Header(default=None),
    x_internal_admin: Optional[str] = Header(default=None),
    x_internal_perms: Optional[str] = Header(default=None),
    x_internal_timestamp: Optional[str] = Header(default=None),
    x_internal_nonce: Optional[str] = Header(default=None),
    x_internal_payload_sha256: Optional[str] = Header(default=None),
    x_internal_signature: Optional[str] = Header(default=None),
) -> Who:
    if not settings.internal_hmac_secret:
        raise HTTPException(status_code=500, detail="内部签名配置缺失")

    computed_sha, payload_meta = await _payload_and_meta(request)
    norm_query = _norm_query(request.url.query or "")

    if not x_internal_payload_sha256 or not hmac.compare_digest(x_internal_payload_sha256, computed_sha):
        raise HTTPException(status_code=401, detail="请求体或文件被篡改")

    user = x_internal_user or ""
    role = x_internal_role or ""
    college = x_internal_college or ""
    colleges = x_internal_colleges or ""
    dept = (x_internal_dept or "").strip()
    admin = x_internal_admin or ""
    perms = x_internal_perms or ""
    ts = (x_internal_timestamp or "").strip()
    nonce = (x_internal_nonce or "").strip()
    signature = x_internal_signature or ""

    if not all([user, role, ts, nonce, signature]):
        raise HTTPException(status_code=401, detail="缺少内部签名头")

    if admin not in ("true", "false"):
        # 必须显式声明，避免"删掉该头"与"声明 false"产生同一签名
        raise HTTPException(status_code=401, detail="管理员声明缺失或非法")

    if len(user) > 150 or len(role) > 50 or len(college) > 200 or len(colleges) > 400 \
            or len(perms) > 1024:
        raise HTTPException(status_code=401, detail="身份声明超长")
    if dept and not _DEPT_RE.match(dept):
        raise HTTPException(status_code=401, detail="部门声明非法")
    if not _TS_RE.match(ts):
        raise HTTPException(status_code=401, detail="时间戳非法")
    if not _NONCE_RE.match(nonce):
        raise HTTPException(status_code=401, detail="nonce 非法")

    try:
        skew = abs(time.time() - int(ts))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="时间戳非法") from exc
    if skew > MAX_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="请求已过期")

    admin_flag = "true" if admin == "true" else "false"
    expected = hmac.new(
        settings.internal_hmac_secret.encode(),
        _canonical(request.method, request.url.path, norm_query, ts, nonce,
                   computed_sha, payload_meta,
                   user, role, college, colleges, dept, admin_flag, perms),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="签名校验失败")

    if not _consume_nonce(nonce):
        raise HTTPException(status_code=409, detail="重放请求：nonce 已被使用")

    if admin_flag == "true":
        return Who(user=user, role=role, college=unquote(college) or None,
                   colleges=unquote(colleges), dept_id=dept, admin="true", perms=perms)

    college_decoded = unquote(college)
    if not college_decoded:
        raise HTTPException(status_code=403, detail="缺少学院数据范围声明")

    return Who(user=user, role=role, college=college_decoded,
               colleges=unquote(colleges), dept_id=dept, admin="", perms=perms)


identity = require_internal if AUTH_ENABLED else _anonymous


# --------------------------------------------------------------------- 授权


def require_perm(who: Optional[Who], perm: str) -> None:
    """权限点校验。who 为 None 只可能出现在关闭态（identity 为 _anonymous）。"""
    if who is None:
        return
    if not who.has(perm):
        raise HTTPException(status_code=403, detail=f"缺少权限：{perm}")


def require_college(who: Optional[Who]) -> str:
    """返回强制学院；空串表示全范围（关闭态或管理员）。"""
    if who is None or who.is_admin:
        return ""
    if not who.college:
        raise HTTPException(status_code=403, detail="缺少学院数据范围声明")
    return who.college


def scope_colleges(who: Optional[Who]) -> Optional[list[str]]:
    """返回 SQL 过滤用的学院列表；None 表示全范围。

    与 POC 的差异：非管理员且学院集合为空时 fail-closed（403），
    不允许空列表退化成“全量可见”。
    """
    if who is None or who.is_admin or who.can_cross_college():
        return None
    colleges = sorted(who.colleges)
    if not colleges:
        raise HTTPException(status_code=403, detail="缺少学院数据范围声明")
    return colleges


def require_import_admin(who: Optional[Who]) -> None:
    """PR-C 前导入接口只允许管理员；关闭态保持旧行为。"""
    if who is None or not IMPORT_ADMIN_ONLY:
        return
    if not who.is_admin:
        raise HTTPException(status_code=403, detail="导入接口在数据范围改造完成前仅限管理员（PR-C）")


def resolve_actor(who: Optional[Who], x_actor: Optional[str]) -> str:
    """可信身份优先；关闭态沿用 X-Actor/回落值（现行为）。"""
    if who is not None and who.user:
        return who.user[:150]
    return (x_actor or settings.actor_fallback).strip()[:150]
