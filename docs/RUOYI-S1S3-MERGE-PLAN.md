# S1–S3 合入主项目：迁移评审计划（修订版 v2，未执行）

- **日期**：2026-10-21（v1 同日，本版根据安全评审意见修订）
- **状态**：**计划，未合入**；本轮不改主项目业务代码
- **前置条件**：POC 后端已可从全新克隆复现（[POC-FRESH-CLONE-REPORT.md](POC-FRESH-CLONE-REPORT.md)）

> **v2 修订要点**（针对评审意见）
> 1. 修正「5 个文件」与配置章节不一致 —— 实际 **6 个文件**（新增 `config.py`、`sql/004`）；
> 2. 明确 `INTERNAL_AUTH_ENABLED=false` 时**新增的 `PUT /students/{no}` 不注册路由**（不是 `_noop`），杜绝无认证写入口；
> 3. 明确 `/imports/{id}/commit` 仍写学生业务表、**不在本次保护范围**，并给出上线硬门槛；
> 4. 补充导入接口权限改造的后续任务（本轮不启动）。

---

## 1. 要合入什么（6 个文件）

| # | 文件 | 变更 | 规模（估） |
|---|---|---|---|
| 1 | `import-api/app/poc_auth.py` | **新增**：HMAC 验签依赖（方法/路径/时间戳/nonce/请求体摘要/身份/admin 声明 + 重放防护） | ~130 行 |
| 2 | `import-api/app/config.py` | 新增 `internal_auth_enabled: bool = False`、`internal_hmac_secret: str = ""` | +3 行 |
| 3 | `import-api/app/main.py` | 学生三接口按开关挂依赖；**`PUT` 仅在开关开启时注册路由** | +55 行 |
| 4 | `import-api/app/queries.py` | `list_students` 增 `forced_college`；新增 `update_student`（白名单 + 范围 WHERE + 同事务审计） | +110 行 |
| 5 | `import-api/requirements.txt` | **无变更**（`hmac`/`hashlib` 标准库，`psycopg` 已有） | 0 |
| 6 | `sql/004_internal_nonce.sql` | **新增**：`campus.internal_nonce` 表 + `campus_app` 的 INSERT/SELECT 授权 | +12 行 |

> v1 只列了 5 个文件却要求改 `config.py`，属清单遗漏；本版已补齐并加入 nonce 表脚本。

---

## 2. 特性开关语义（修订）

```python
# config.py
internal_auth_enabled: bool = False   # 环境变量 INTERNAL_AUTH_ENABLED
internal_hmac_secret: str = ""        # 环境变量 INTERNAL_HMAC_SECRET（≥32 字节）

# main.py —— 关键：新增写接口不共享旧接口的「兼容」待遇
if settings.internal_auth_enabled:
    app.include_router(student_write_router)   # PUT /students/{no} 只在此分支注册
```

| 接口 | 开关 = false（默认） | 开关 = true |
|---|---|---|
| `GET /students`、`GET /students/{no}`（**既有**） | 行为与现在完全一致（无鉴权，`X-Actor` 作为审计操作人） | 必须携带合法签名；缺签名 401；普通用户缺学院声明 403 |
| `PUT /students/{no}`（**新增**） | **路由不注册 → 404**；OpenAPI 中不出现 | 签名 + 写权限点 + 学院范围，三者缺一即拒绝 |
| `/imports/**`（既有） | 不变 | **不在本次范围，仍无签名校验**（见 §3） |

**红线**：不得为了「向后兼容」让任何**新增写接口**在无认证状态下可用。开关关闭时它的正确状态是「不存在」，不是「不校验」。

---

## 3. 未覆盖的写入路径（安全边界，必须先承认）

| 路径 | 写什么 | 本次是否保护 | 说明 |
|---|---|---|---|
| `PUT /students/{no}` | `students` | ✅ 是 | 本计划新增并保护 |
| `POST /imports/{id}/commit` | **`students` + `student_changes` + `import_issues`** | ❌ **否** | 既可导入新生，也可更新已有学生（触发器同样写审计） |
| `POST /imports/{id}/validate` / `remap` | `import_batches`、`import_issues` | ❌ 否 | 只写批次与异常表，不碰学生主数据 |

**结论**：S1–S3 只保护了「查询 + 单条修改」这一条链路；**导入提交是另一条完整的学生写入路径**，当前无认证、无签名、操作人可伪造。

### 3.1 上线硬门槛（写死在验收里）

1. 在 `POST /imports/{id}/commit` 完成**同等级**保护（Java 授权 + FastAPI 签名 + 可信操作人）之前：
   - **不得**对外宣称「主系统认证与权限迁移完成」；
   - **不得**切换正式入口或开放公网访问；
   - 主系统仍按现状作为「内网/单机工具」使用。
2. 开关语义只描述「学生接口」这一层，**不代表整系统安全等级**，文档与汇报中必须显式区分。

### 3.2 导入接口的两条可选路线（后续立项，不在本轮）

| 路线 | 做法 | 代价 | 风险 |
|---|---|---|---|
| A. 复用同一签名链路 | `/imports/**` 全部挂 `require_internal`，Java 网关代理文件上传（multipart + 签名覆盖请求体摘要） | 需处理大文件签名与流式上传，网关复杂度上升 | 签名对 10MB 文件的计算开销、超时 |
| B. 提交闸门 | 先给 `commit` 加独立开关（默认拒绝），仅在可信内网/批处理环境开启；后续再补签名 | 改动小、可立即止血 | 属于「禁用」而非「保护」，业务方需接受 |

**建议**：先 B 止血、再 A 根治；B 的实施必须与业务方确认「谁能提交」。

---

## 4. 风险清单（更新）

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| 1 | Java 网关未上线就开开关 | 学生查询/修改全部 401 | 只在代理联调通过后开启，灰度单实例 |
| 2 | 新增 `PUT` 在开关关闭时被误注册 | **无认证写入口** | 用 `include_router` 控制注册；测试断言「开关关闭时 PUT 返回 404」 |
| 3 | 导入提交绕过权限 | 越权写入学生数据 | 见 §3.1 硬门槛；不得宣称完成 |
| 4 | 双身份并存 | 审计出现 `ry:` 与旧值混杂 | 审计报表兼容两种前缀；迁移完成后统一 |
| 5 | `X-Actor` 移除影响 Appsmith | Appsmith 直连 8010 无法写 | 开关开启前完成 Appsmith 只读化或下线 |
| 6 | nonce 表膨胀 | 表持续增长 | 上线后加 TTL 清理（>24h 删除），本次不做 |
| 7 | 部门名 ≠ `college_name` | 查空或越权判断失真 | 上线前对齐命名（POC 已验证「部门名=学院名」可行） |

---

## 5. 验收标准（合入前必须全绿）

| 层次 | 要求 |
|---|---|
| 单测 | `pytest` 全绿；新增 5 类负向用例：缺签名 / 篡改 / 过期 / 重放 / 伪造头 |
| 开关语义 | 断言：`INTERNAL_AUTH_ENABLED=false` 时 `PUT /students/{no}` **返回 404**（不是 200/403） |
| 集成 | POC 12 项切片在主项目测试库复跑通过（虚构数据） |
| 负向 | 跨学院查/改 403 且 DB 无变更；无 token 401；低权限 403 |
| 审计 | `actor_user_id` 为真实登录名；`changed_fields` 与实际变更一致 |
| 回退 | 关闭开关 → 学生接口行为恢复；重启后前端无感 |
| 声明 | 文档与汇报中明确「导入提交尚未保护」 |

---

## 6. 回退方法

| 场景 | 操作 | 影响 |
|---|---|---|
| 开关开启后异常 | `INTERNAL_AUTH_ENABLED=false` 重启 import-api | 秒级；PUT 自动消失（404） |
| 撤回代码 | `git revert <merge commit>` | 单 PR 可逆；无 schema 变更 |
| 数据侧 | `campus.internal_nonce` 可保留（不读即无影响），或按 004 的反向语句删除 | 无业务数据影响 |

---

## 7. 实施顺序（建议）

1. **PR-A**：`config.py` + `poc_auth.py` + `sql/004`（默认关闭，纯增量，不含路由）；
2. **PR-B**：既有两个 GET 按开关挂依赖（关闭时行为不变）；
3. **PR-C**：`PUT /students/{no}`（**仅开关开启时注册**，含 404 断言测试）；
4. **PR-D**：Java 网关对接（先 POC 验证，再单独评估进主项目）；
5. 每步合并后跑 CI + pytest，观察一周再考虑开启开关。

**不在本计划内**：导入接口保护（另立项）、前端页面迁移、Appsmith 下线。

---

## 8. 后续任务（本轮不启动）

| 任务 | 内容 | 启动条件 |
|---|---|---|
| 导入接口权限改造 | 见 §3.2 的 A/B 路线，需业务方确认「谁能提交」 | S1–S3 合入后 |
| Appsmith 只读化/下线 | 回收可写账号 | 开关开启前 |
| nonce TTL 清理 | 定时任务 | 开关开启后一周 |

---

## 9. 与 Issue 的关系

- 依赖 Issue #2（自动化测试）已关闭 ✅
- 与 Issue #3（Docker 标准化）**不同分支**，避免同时改 Compose
- 本计划通过评审后再开新 Issue 跟踪 S1–S3 实施与导入接口改造
