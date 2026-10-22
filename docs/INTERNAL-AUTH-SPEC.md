# 内部请求认证规范（v1）

- **状态**：PR-A 实施中；`INTERNAL_AUTH_ENABLED` 默认关闭
- **适用**：`import-api` 的 11 个业务路由
- **公开端点（有意豁免）**：`GET /health`（liveness）、`GET /health/ready`（readiness）

---

## 1. 信任链

```
浏览器 → Java 网关（会话 + 权限点） → X-Internal-* 签名 → FastAPI（验签 + 范围复核） → PG
```

FastAPI **不信任**任何客户端提交的身份头；只认签名覆盖的声明。密钥仅存在于网关与业务服务的环境变量中。

---

## 2. 请求头（11 个）

| 头 | 含义 | 约束 |
|---|---|---|
| `X-Internal-User` | 可信用户，形如 `ry:<username>` | 1..150 字符 |
| `X-Internal-Role` | 主角色 key | 1..50 |
| `X-Internal-College` | 所属学院（percent-encoded） | ≤200；普通用户必填 |
| `X-Internal-Colleges` | 授权学院集合（逗号分隔，percent-encoded） | ≤400 |
| `X-Internal-Dept` | 部门 ID | `^\d{1,19}$` 或空 |
| `X-Internal-Admin` | 管理员声明 | 仅 `true` / `false` / 空；**严格小写** |
| `X-Internal-Perms` | 权限点，空格分隔 | ≤1024，**ASCII 升序** |
| `X-Internal-Timestamp` | Unix 秒 | `^\d{10,13}$`，±60s |
| `X-Internal-Nonce` | 一次性随机串 | `^[A-Za-z0-9._~-]{16,64}$` |
| `X-Internal-Payload-Sha256` | 载荷摘要（见 §4） | 小写 hex |
| `X-Internal-Signature` | HMAC-SHA256 hex | 小写 hex |

---

## 3. Canonical（14 段，`\n` 连接，UTF-8）

```
1  METHOD      大写
2  PATH        后端可见路径，不含 query（例：/students）
3  QUERY       规范化查询串；无参数为空串（不是 "?"）
4  TS          Unix 秒字符串
5  NONCE
6  PAYLOAD_SHA 见 §4，小写 hex
7  META        见 §4；JSON 请求为空串
8  USER
9  ROLE
10 COLLEGE    percent-encoding 后的学院名（原样参与签名）
11 COLLEGES   percent-encoding 后的逗号列表
12 DEPT       部门 ID 字符串
13 ADMIN      "true" | "false"
14 PERMS      空格分隔、ASCII 升序、去重
```

**percent-encoding 规则**：仅 `A-Za-z0-9-._~` 保留，其余按 UTF-8 逐字节 `%XX`（大写）。

**规范化规则**：
- query：`parse_qsl(keep_blank_values=True)` 后按 key 排序，`k=v` 用 `&` 连接；
- 同一 key 只允许出现一次（重复 key 的排序语义不保证跨语言一致）。

---

## 4. PAYLOAD_SHA 与 META

| 请求类型 | PAYLOAD_SHA | META |
|---|---|---|
| JSON / 无 body | 原始 body 字节的 SHA-256 | 空串 |
| `multipart/form-data` | **文件内容**（`file` 字段字节）的 SHA-256 | 除 `file` 外全部表单字段，键排序后规范化 |

不签 multipart 原始 body：boundary 每次不同，无法跨语言稳定复现。

---

## 5. 校验顺序（不可调换）

1. 密钥存在（缺失 → 500，fail-closed）
2. 读取 body/文件，计算摘要与 meta
3. `X-Internal-Payload-Sha256` 与实算值比对（不一致 → 401）
4. 头完整性、格式与长度校验（401）
5. 时间窗（±60s，401）
6. HMAC 验签（401）
7. **消费 nonce**（重放 → 409）
8. 普通用户必须有学院声明（403）

先验签后消费 nonce：避免攻击者用错误签名消耗他人 nonce。

---

## 6. 错误码

| 码 | 场景 |
|---|---|
| 401 | 缺头、格式非法、摘要不符、时间戳越界、签名错误 |
| 403 | 权限点不足、缺少学院声明、导入接口非管理员（PR-C 前） |
| 409 | nonce 重放 |
| 413 | 文件/行数超限（业务层） |
| 500 | 密钥/配置缺失（部署错误，不是客户端问题） |

---

## 7. 权限点

| 路由 | 权限点 |
|---|---|
| `GET /students`、`GET /students/{no}` | `student:list` |
| `PUT /students/{no}` | `student:write`（仅开启态注册） |
| `GET /meta/filters`、`GET /stats/overview` | `student:list` + 学院范围 |
| `GET /imports` | `import:batch:list` |
| `GET /imports/{id}` | `import:batch:detail` |
| `POST /imports/preview`、`preview-base64` | `import:batch:upload` |
| `POST /imports/{id}/remap` | `import:batch:remap` |
| `POST /imports/{id}/validate` | `import:batch:validate` |
| `POST /imports/{id}/commit` | `import:batch:commit` |
| 跨学院（PR-C 使用） | `import:batch:cross_college` |

**PR-C 前的临时限制**：7 个导入接口仅允许 `admin=true`；非管理员即使持有全部 `import:batch:*` 也返回 403。

---

## 8. 金标向量（跨语言契约）

Java 实现必须复现该签名；测试 `test_internal_auth.py::test_金标向量` 同时校验测试助手与生产实现。

```
secret   = test-secret
METHOD   = GET
PATH     = /imports
QUERY    = limit=1
TS       = 1700000000
NONCE    = 0123456789abcdef
PAYLOAD_SHA = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
META     = (空)
USER     = ry:test
ROLE     = college
COLLEGE  = %E8%AE%A1%E7%AE%97%E6%9C%BA%E5%AD%A6%E9%99%A2   (计算机学院)
COLLEGES = 同上
DEPT     = 1762000000000000101
ADMIN    = false
PERMS    = import:batch:list

canonical = GET\n/imports\nlimit=1\n1700000000\n0123456789abcdef\n<PAYLOAD_SHA>\n\nry:test\ncollege\n%E8%AE%A1%E7%AE%97%E6%9C%BA%E5%AD%A6%E9%99%A2\n%E8%AE%A1%E7%AE%97%E6%9C%BA%E5%AD%A6%E9%99%A2\n1762000000000000101\nfalse\nimport:batch:list
signature = 9d934c4c8c41c5430d040f99bd142ba815b5b85bf738d7c309da80be4f42500a
```

---

## 9. 易错点（PR-D 联调必看）

1. 方法必须大写；`GET` 不能写成 `get`。
2. 空 query 是空串，不是 `"?"`。
3. multipart 只对**文件内容**做摘要，不对整个 body。
4. `+` 与 `%20` 必须统一为 `%20`（空格也按 `%20` 编码）。
5. `PERMS` 必须 ASCII 升序、空格分隔、去重。
6. 签名对象是**后端可见路径**：若 nginx 配置 `proxy_pass .../` 会剥掉 `/api`，网关签 `/api/students` 必定 401。
7. `X-Internal-Admin` 只接受小写 `true`；`TRUE`/`1` 直接 401。

---

## 10. 存储与清理

- `campus.internal_nonce(nonce PK, seen_at, expires_at)`；
- `campus_app` 只有 `SELECT/INSERT`，**不能删除**任何 nonce；
- 过期清理仅能调用 `campus.cleanup_internal_nonce()`（`SECURITY DEFINER`，属主 `campus_nonce_cleaner`，只删 `expires_at < now()`）；
- 应用启动时调用一次清理；失败只告警，不影响启动。
