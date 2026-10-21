# 导入 API 安全整改设计与任务规划

- **日期**：2026-10-21
- **依据**：[IMPORT-API-SECURITY-INVENTORY.md](IMPORT-API-SECURITY-INVENTORY.md)（Issue #9 取证）
- **状态**：**设计与任务规划，未实施**；本轮不改代码、不改库、不动 Compose
- **关联**：[RUOYI-S1S3-MERGE-PLAN.md](RUOYI-S1S3-MERGE-PLAN.md)（上线硬门槛）、Issue #10（审计方案）

> 前提澄清：**主项目当前没有任何 Java 网关**。本文所有"网关"描述都是**目标态**，实施前主系统仍是无认证的内网工具。

---

## 1. 架构原则：七个接口共用一条信任链，按操作分权限

不按"GET 就宽松、POST 就严格"划分，因为 `preview` 名为预览、实际创建批次并落盘写库。统一为：

```
浏览器 → Java 网关（会话 + 权限点 + 数据范围）→ 内部签名 → FastAPI（验签 + 范围复核）→ PG
```

| 层 | 职责 | 不做什么 |
|---|---|---|
| Java 网关 | 校验 Sa-Token 会话、权限点、计算并签名身份与范围声明 | 不直接读写业务表 |
| FastAPI | 验签、时间窗、nonce 防重放、**复核数据范围**、执行业务 | 不信任任何浏览器头（`X-Actor` 等） |
| 数据库 | 触发器写学生表审计 | 不承担授权判断 |

**双保险**：网关算范围，FastAPI 再复核。任一层被绕过，另一层仍能拒绝。

---

## 2. 权限矩阵（7 个接口）

| # | 接口 | 实际副作用 | 权限点 | 批次范围 | 学院范围 | 文件权限 | 签名 |
|---|---|---|---|---|---|---|---|
| 1 | `GET /imports` | 读批次列表 | `import:batch:list` | 仅可见范围内批次 | 按批次创建者学院过滤 | — | ✅ |
| 2 | `GET /imports/{id}` | 读批次 + ≤500 条异常明细（含原文件名） | `import:batch:detail` | 单批次校验 | 同上 | — | ✅ |
| 3 | `POST /imports/preview` | **建批次 + 落盘 + 写异常** | `import:batch:upload` | 新建，归属当前用户 | 落盘前校验文件大小/行数；学院在提交时校验 | 需 `upload` 权限 | ✅ |
| 4 | `POST /imports/preview-base64` | 同上（base64 解码） | 同上 | 同上 | 同上 | 同上 | ✅ |
| 5 | `POST /imports/{id}/remap` | **重置状态 + 删异常 + 重写 sidecar** | `import:batch:remap` | 单批次校验 | 同上 | — | ✅ |
| 6 | `POST /imports/{id}/validate` | **删异常重插 + 改统计** | `import:batch:validate` | 单批次校验 | 同上 | — | ✅ |
| 7 | `POST /imports/{id}/commit` | **写 students/changes/batches/issues** | `import:batch:commit` | 单批次 + 状态机 | **逐行校验**（见 §4） | — | ✅ |
| — | 跨学院批量导入 | 用于合并多学院来源的批次 | `import:batch:cross_college` | 需显式授权 | 允许跨学院，但逐行仍校验 | — | ✅ |

**新增环境变量**（与 S1–S3 共用）：
`INTERNAL_AUTH_ENABLED`（默认 false）、`INTERNAL_HMAC_SECRET`（≥32 字节）、`IMPORT_BATCH_SCOPE_ENABLED`（默认 false，用于先上读接口、后上写接口的灰度）。

---

## 3. 逐接口副作用核对（已取证）

| 接口 | 数据库 | 文件系统 | 事务 | 现有审计 |
|---|---|---|---|---|
| preview / preview-base64 | `import_batches` INSERT（service.py:434）、缺列时 `import_issues`（:281） | **先落盘**（:390）再查重（:422）→ 重复上传留孤儿文件 | 单事务（:418） | 无 |
| remap | `import_batches` 重置（:586）、`import_issues` DELETE（:593） | 重写 `.mapping.json` | 单事务 + `FOR UPDATE`（:547） | 无 |
| validate | `import_issues` DELETE+INSERT（:655）、`import_batches` 计数（:665） | 读暂存文件 | 单事务 + `FOR UPDATE`（:646） | 无 |
| commit | `students` INSERT（:736）、`import_issues`（:758）、`student_changes`（:767）、`import_batches` UPDATE ×2（:790/:804） | 删暂存文件 | **两段**：主事务（:701-793）+ 清理事务（:801-806） | 学生表有，批次无 |

---

## 4. 范围规则

### 4.1 批次可见性

```
可见 ⇐ 批次.created_by == 当前用户
     ∨ 当前用户具备 import:batch:cross_college
     ∨ 批次创建者所属学院 ∈ 当前用户可管学院集合
```

> 现状：`import_batches` **没有 `created_dept` 列**，只能通过 `created_by` 反查用户部门。
> **建议新增 `created_dept_id`**（迁移需审批），否则每次查询都要 join 用户表，且用户调岗后历史批次范围会漂移。

### 4.2 跨学院导入政策（需业务方确认）

| 选项 | 含义 | 影响 |
|---|---|---|
| A. 禁止跨学院 | 一个批次只能含单学院数据，混入即整批拒绝 | 最安全，但招生汇总类文件无法导入 |
| B. 显式授权 | 持 `import:batch:cross_college` 者可提交多学院批次 | 灵活，需维护授权名单 |
| C. 逐行过滤 | 只提交范围内行，其余记异常 | 体验差但不用授权 |

**建议 B + 逐行复核**：授权者仍对每行校验学院，防止"有跨学院权限就写入任意学院"。

### 4.3 逐行校验（commit）

```
for row in rows:
    row.college ∈ 调用者允许的学院集合
      否 → 该行记 import_issues(error) 并跳过，不写 students
    学号已存在 → ON CONFLICT DO NOTHING + warning（现状保留）
```

---

## 5. 审计与两段事务

### 5.1 审计（与 Issue #10 衔接）

| 事件 | 记录方式 | 是否需要 DDL |
|---|---|---|
| 批次创建 / 重置 / 校验 / 提交 | 应用层写 `operation_logs`（`object_type='import_batches'`, `action='update'`, `changed_fields` 含 from→to） | ❌ 复用现有表 |
| 异常明细重写 | 只记摘要（`deleted=n, inserted=m`），不逐行 | ❌ |
| 学生/异动写入 | 触发器（现状保留） | ❌ |

**前置条件**：`campus_app` 当前对 `operation_logs` **只有 SELECT**（003_roles.sql）。应用层写审计需补 `INSERT` 授权 → **需审批**，属权限变更。

### 5.2 两段事务问题（现状缺陷）

```python
# 现状（service.py:797-806）
try: os.remove(path)          # 文件删除失败被静默吞掉
except OSError: pass
UPDATE import_batches SET staged_path = NULL   # 无论删除是否成功都置空
```

后果：删除失败 → 文件残留但路径被清空 → **永久孤儿文件，无法定位**。

**建议**：
1. 只有 `os.remove` 成功才置 `staged_path=NULL`；
2. 失败时保留路径并写一条 warning 审计；
3. 增加幂等清理任务（扫描 `status='imported' AND staged_path IS NOT NULL`），每日重试；
4. 不做"把文件删除塞进数据库事务"——FS 与 DB 无分布式事务，硬凑只会让回滚更糟。

---

## 6. POC 验收矩阵（10 项，实施后必须逐项有证据）

| # | 场景 | 期望 |
|---|---|---|
| 1 | 未登录调任意接口 | 401（网关拦截，FastAPI 收不到） |
| 2 | 已登录但无 `import:batch:*` 权限 | 403 |
| 3 | 伪造 `X-Actor` / `X-Poc-User` / `X-Poc-College`（带有效签名外的自造头） | 服务端识别身份不变，审计记录真实用户 |
| 4 | 直连 FastAPI（无签名） | 401；生产态端口不发布，外部不可达 |
| 5 | 签名篡改 / 过期 / 重放 | 401 / 401 / 409 |
| 6 | 学院 A 用户读学院 B 批次 | 403 或列表不可见 |
| 7 | 学院 A 用户提交含学院 B 行的批次 | 越权行被拒并记异常，B 行零落库 |
| 8 | 无效/不存在批次 | 404；已 imported 批次再提交 | 409 |
| 9 | 重复提交同一批次 / 同文件重复上传 | 409 / warning 且不新增学生 |
| 10 | 校验失败行与异常回滚 | 失败行不写 students；审计与业务同事务；文件清理有状态记录 |

**明确**：这 10 项是**导入链路**的验收，不能沿用学生管理 POC 的 12 项结果；两者写的是不同接口。

---

## 7. PR 拆分与依赖

| PR | 内容 | 依赖 | 回退 |
|---|---|---|---|
| PR-1 | `require_internal` 依赖 + 配置开关 + `internal_nonce` 表（与 S1–S3 共用） | 无 | 开关关闭即回退 |
| PR-2 | `GET /imports`、`GET /imports/{id}` 接入（登录 + 权限 + 批次范围） | PR-1 | 开关回退 |
| PR-3 | `preview` / `preview-base64`（上传权限、落盘前查重、创建审计） | PR-2 | 同上 |
| PR-4 | `remap` / `validate`（状态机加固 + 审计） | PR-3 | 同上 |
| PR-5 | `commit`（逐行范围校验 + 两段事务修复 + 审计） | PR-4 | 同上 |
| PR-6 | Java 网关代理导入接口（含 multipart 签名） | POC 验证 | 网关侧开关 |
| PR-7 | 关闭 `8010` 宿主端口、前端只走网关 | PR-6 | 恢复端口映射 |

**顺序原则**：先读后写、先 POC 后主项目；每个 PR 独立可回退，不合并"顺手重构"。

---

## 8. 剩余风险与待决事项

| # | 事项 | 需要谁决定 |
|---|---|---|
| 1 | 跨学院导入政策选 A/B/C | **用户/业务方** |
| 2 | 是否新增 `import_batches.created_dept_id`（DDL） | 用户 |
| 3 | 是否给 `campus_app` 补 `operation_logs` INSERT | 用户（权限变更） |
| 4 | multipart 文件签名的实现方式（整文件哈希 vs 分块） | 技术评审 |
| 5 | Appsmith 仍持可写账号，需只读化或下线 | 用户 |
| 6 | `import_issues` 的 DELETE 授权是否收窄 | 与 #10 一并评审 |

---

## 9. 与上线门槛的关系

`RUOYI-S1S3-MERGE-PLAN.md` §3.1 的门槛在本计划完成后才可解除：

> 七条写入路径（学生单条修改 + 导入提交）全部受保护，且验收矩阵有证据，才能宣称"权限迁移完成"。

在此之前：**不上真实数据、不切正式入口、不打开认证开关**。
