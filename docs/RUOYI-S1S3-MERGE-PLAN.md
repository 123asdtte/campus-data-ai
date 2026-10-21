# S1–S3 合入主项目：迁移评审计划（未执行）

- **日期**：2026-10-21
- **状态**：**计划，未合入**；本轮不改主项目业务代码
- **前置条件**：POC 已可从全新克隆复现（见 [POC-FRESH-CLONE-REPORT.md](POC-FRESH-CLONE-REPORT.md)）

---

## 1. 要合入什么（增量，共 5 个文件）

| 文件 | 变更 | 行数（估） |
|---|---|---|
| `import-api/app/poc_auth.py` | **新增**：HMAC 验签依赖（签名覆盖方法/路径/时间戳/nonce/请求体摘要/身份/admin 声明，含重放防护） | ~130 |
| `import-api/app/main.py` | 三个学生接口挂依赖；新增 `PUT /students/{no}` | +60 |
| `import-api/app/queries.py` | `list_students` 增加 `forced_college`；新增 `update_student`（白名单 + 范围 WHERE + 同事务审计） | +110 |
| `import-api/requirements.txt` | **无新增依赖**（`hmac`/`hashlib` 标准库，`psycopg` 已有） | 0 |
| `sql/`（可选） | `campus.poc_nonce` 表（若走"网关签名"模式则必需） | +10 |

**不包含**：导入流程（`/imports/**`）、前端页面、任何表结构改造（审计触发器不动）。

---

## 2. 特性开关设计（默认关闭）

目标：开关关闭时，主系统行为与现在**逐字节一致**；开启后学生接口改走内部签名与强制学院范围。

```python
# import-api/app/config.py 新增
internal_auth_enabled: bool = False      # 环境变量 INTERNAL_AUTH_ENABLED
hmac_secret: str = ""                    # 环境变量 INTERNAL_HMAC_SECRET（≥32 字节）

# import-api/app/poc_auth.py
require_internal = Depends(_require_internal) if settings.internal_auth_enabled else Depends(_noop)
```

| 开关状态 | 学生接口行为 | 身份来源 |
|---|---|---|
| `false`（默认） | 与当前完全一致（无鉴权，`X-Actor` 作为审计操作人） | `X-Actor` |
| `true` | 必须携带合法内部签名；缺签名 401；普通用户缺学院声明 403；`X-Actor` 被忽略 | 签名声明 |

**关键约束**：开关为 false 时**不得**初始化 nonce 表、不得读取 `INTERNAL_HMAC_SECRET`，避免给未接入的部署制造额外依赖。

---

## 3. 风险清单

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| 1 | Java 网关未同步上线就开开关 | 所有学生查询/修改 401，前端白屏 | 开关只在 Java 代理联调通过后打开；灰度单实例 |
| 2 | 双身份并存期审计口径不一致 | `operation_logs.actor_user_id` 出现 `ry:` 前缀与旧值混杂 | 审计按前缀可区分；报表层兼容两种来源，迁移完成后再统一 |
| 3 | `X-Actor` 移除影响 Appsmith | Appsmith 直连 8010 时不再能写 | Appsmith 已定性为历史方案且待只读化，需在开关开启前完成 |
| 4 | nonce 表增长 | 长期膨胀 | 上线后加 TTL 清理（每日删除 >24h 记录），本次不做 |
| 5 | 学院声明依赖部门名 | 若依部门名与 `students.college_name` 不一致则越权/查空 | 上线前对齐部门命名（POC 已验证"部门名=学院名"可行） |
| 6 | 修改接口白名单不足 | 业务方要求改学号/学院 | 明确拒绝；如确需，走独立的学籍异动流程，不放开本接口 |

---

## 4. 验收标准（合入前必须全绿）

| 层次 | 要求 |
|---|---|
| 单测 | `pytest` 全绿；新增「签名缺失/篡改/过期/重放/伪造头」5 类用例 |
| 集成 | POC 的 12 项切片测试在主项目测试库复跑通过（虚构数据） |
| 负向 | 跨学院查/改 403 且 DB 无变更；无 token 401；低权限 403 |
| 审计 | `actor_user_id` 为真实登录名；`changed_fields` 与实际变更一致 |
| 回退演练 | 关闭开关 → 行为恢复；重启后前端无感 |

---

## 5. 回退方法

| 场景 | 操作 | 影响 |
|---|---|---|
| 开关开启后异常 | 置 `INTERNAL_AUTH_ENABLED=false` 并重启 import-api | 秒级回退，无需回滚代码 |
| 需要撤回代码 | `git revert <merge commit>` | 单 PR 可逆；不涉及数据迁移 |
| 数据侧 | 无 schema 变更；`poc_nonce` 表可保留（不读即无影响） | 无 |

---

## 6. 实施顺序（建议）

1. **PR-A**：`poc_auth.py` + 配置开关（默认关闭，纯增量，不动路由）；
2. **PR-B**：三个学生接口挂依赖 + `forced_college`（开关关闭时行为不变）；
3. **PR-C**：`PUT /students/{no}`（新接口，开关关闭时不注册路由）；
4. **PR-D**：Java 网关对接（在 POC 仓库验证后，单独评估是否进主项目）；
5. 每步合并后跑一次 CI + pytest，观察一周再开开关。

**不在本计划内**：导入流程接入、前端页面迁移、Appsmith 下线。

---

## 7. 与 Issue 的关系

- 依赖 Issue #2（自动化测试）已关闭 ✅ —— 回归网已就位；
- 与 Issue #3（Docker 标准化）**不同分支**，避免同时改 Compose；
- 本计划通过评审后再开 Issue #4 跟踪实施。
