# 导入批次与异常表的审计覆盖方案（设计）

> **实施状态（2026-10-22，PR-C）**：方案 C 已落地——`import_batches` 行级触发器；`import_issues` 由 `clear_import_issues()`（删前摘要）与 `record_import_issues()`（重写后摘要）各写一行 JSON 摘要；`campus_app` 的 `import_issues` DELETE 已收回。与本文的差异：保留了 `import_issues` INSERT（预览/提交仍由应用写入明细），未新增 `validate_seq` 软删除。

> Issue #10 交付物。**只做设计评估**：不创建触发器、不改表结构、不改权限、不迁移数据。
> 取证基线：`main` @ `d10946f`（PR #16 内部认证合并后）。

---

## 1. 现状取证

### 1.1 审计覆盖面

| 表 | 审计触发器 | 证据 |
|---|---|---|
| `campus.students` | 有（`insert`/`update`/`delete`） | `sql/001_schema.sql:245` `CREATE TRIGGER trg_students_audit` |
| `campus.student_changes` | 有 | `sql/001_schema.sql:253` `CREATE TRIGGER trg_changes_audit` |
| `campus.import_batches` | **无** | `001_schema.sql:241-255` 只有上述 4 个触发器 |
| `campus.import_issues` | **无** | 同上 |

即：业务数据的每一次写入都有审计，而**「谁发起了这次导入、谁改过映射、谁重复校验过」完全不可追溯**——只有 `import_batches.created_by`（`001_schema.sql` 中的普通列，由 `service.py:436` 在 INSERT 时写入一次），之后任何状态变化都不留痕。

### 1.2 可信操作人已经有了通路，但只挂在业务表上

- 触发器 `campus.audit_row()`（`001_schema.sql:45`）从事务级 GUC 取身份：
  `v_actor_user_id := nullif(current_setting('campus.actor_user_id', true), '')`（`:58`）。
- 应用层已经会注入它：`service.py:53` 的 `_set_actor()` 执行
  `SELECT set_config('campus.actor_user_id', %s, true)`，`true` 表示**事务局部**，
  每次 `validate`/`remap`/`commit` 都在自己的事务里设过。
- 身份来源：`internal_auth.py:299` `resolve_actor()`——开启内部认证时取签名头里的
  `who.user`（**可信**）；关闭态退回 `X-Actor` 或 `settings.actor_fallback`（**可伪造**）。

结论：机制是现成的，缺的只是把触发器挂到导入的两张表上。**但审计的可信度取决于认证开关**：
关闭态下 `X-Actor` 完全由客户端决定，审计里记的“操作人”可以被任意伪造。

### 1.3 `import_issues` 的删除与重写

- `campus_app` 是全库唯一持有物理删权限的角色：`sql/003_roles.sql:50` 先
  `REVOKE DELETE ... FROM campus_app`，紧接着 `:55` `GRANT DELETE ON campus.import_issues TO campus_app`。
- 实际使用点两处，都是**整批删后再整批写**：
  - `service.py:593`（`remap_batch`）
  - `service.py:655`（`validate_batch`）
- 后果：**历史校验结论不可回溯**。改一次映射再校验一次，上一次的异常明细就消失了，
  连“曾经报过什么”都查不到。
- 顺带一提，`campus_app` 对 `operation_logs` 只有 `SELECT`（`003_roles.sql:41`、`:51`），
  即应用层**无权自己写审计**——这是既有权限模型的硬约束，直接决定方案选型（见 §2 方案 B）。

### 1.4 审计表容量与形态

`campus.operation_logs`（`001_schema.sql`）：`actor_user_id`、`action`、`object_type`、
`object_id`、`changed_fields`、`before_data`/`after_data`（jsonb）、`result`、`details`。
`audit_row()` 对 UPDATE 会同时存 before/after 全行快照（`:64-66`），并在无实质变化时跳过（`:70`）。

---

## 2. 三方案对比

评估维度沿用 issue #10 给的七个。

| 维度 | A. 数据库触发器（两张表都挂 `audit_row`） | B. 应用层审计（service 层显式写） | C. 组合（批次用触发器 + 异常表用应用层摘要） |
|---|---|---|---|
| **事务一致性** | ✅ 与业务同事务，业务回滚则审计不残留；触发器漏不掉任何一条写入 | ⚠️ 靠代码自觉，新增写入点漏写无人发现；异常时可能业务成功、审计失败 | ✅ 状态跃迁同样由触发器保证；摘要写入与删除包在同一个函数里，删前必留痕 |
| **可信操作人** | ✅ 直接复用 `_set_actor` 已注入的事务 GUC | ✅ 同样能拿到 actor，但由应用拼字符串写库 | ✅ 同 A；开启内部认证后即端到端可信 |
| **状态变更历史** | ✅ `import_batches` 每次 UPDATE 留一行，含 before/after，可还原完整状态机跃迁 | ⚠️ 需要在每个状态跃迁点手写，共 4 处（create/remap/validate/commit），漏一处即断链 | ✅ 同 A（状态机部分） |
| **重复校验历史** | ❌ 逐行审计 `import_issues`：一次 validate = 删 N 行 + 写 N 行 = 最多 2N 条审计，全是噪声；且审计里存的是“某条异常记录被删了”，**没有业务语义** | ⚠️ 想保留历史得自己设计版本号/软删除，工作量转移到应用层 | ✅ 每次重写只写 **1 条摘要**（异常总数、按 code 分布、按 severity 分布），可比较历次校验结论 |
| **删除与重写** | ❌ 不解决：DELETE 授权仍在，删完照样没痕迹（审计里只有“删了 N 行”） | ⚠️ 应用层可以先写摘要再删，但没有强制力，绕过即可 | ✅ 删除改走 SECURITY DEFINER 函数，**函数内先写摘要再删**，数据库层面强制 |
| **存储成本** | ❌ 高：见 §3，单次校验最多约 1.8 MB 审计 | ✅ 低（只写摘要） | ✅ 低：批次侧约 6 KB/批次，异常侧约 400 B/次校验 |
| **保留策略** | ❌ 高频噪声会迅速撑大 `operation_logs`，分区/清理都被噪声绑架 | ✅ 干净 | ✅ 干净；`operation_logs` 可按月分区，审计语义清晰 |
| **与既有权限模型的冲突** | ✅ 无（触发器 `SECURITY DEFINER`，应用层不需要新权限） | ❌ **冲突**：应用层要写审计就得拿到 `operation_logs` 的 INSERT，而 `003_roles.sql:51` 明确禁止；一旦放开，`campus_app` 就具备了伪造审计的能力 | ✅ 无：应用层只 EXECUTE 一个 `SECURITY DEFINER` 函数，仍然拿不到 `operation_logs` 的 INSERT |

---

## 3. 存储成本估算

按 issue 给出的口径（单批次最多 2007 行异常）：

| 方案 | 单次操作产出 | 单批次累计 | 100 批次/天 |
|---|---|---|---|
| A：`import_issues` 逐行审计 | 一次 validate = 删除 2007 + 插入 2007 = **4014 行**，每行 before/after jsonb 约 450 B | 约 **1.8 MB**（若校验 1 次） | 约 **180 MB/天** |
| C：异常表只记摘要 | 一次 validate = **1 行**，约 400 B | 约 400 B | 约 40 KB/天 |
| C：`import_batches` 行级审计 | INSERT 1 + UPDATE 3~4（remap/validate/commit）≈ **5 行**，每行 before/after 约 1.2 KB | 约 **6 KB** | 约 600 KB/天 |

`import_batches` 状态跃迁次数天然稀少（每批次最多 4~5 次），逐行审计完全负担得起；
`import_issues` 是**数量级完全不同**的高频明细表，逐行审计的成本与价值严重倒挂。这是推荐 C 的核心理由。

---

## 4. 推荐：方案 C（组合）

**`import_batches` 挂触发器 + `import_issues` 用应用层摘要，删除走 SECURITY DEFINER 函数。**

### 4.1 三段设计

1. **`import_batches`：`AFTER INSERT OR UPDATE OR DELETE` 直接复用现有 `campus.audit_row()`。**
   零新代码——审计载荷函数 `audit_payload()`（`001_schema.sql:32`）已会剔除敏感列，
   `import_batches` 的字段（`batch_code`、`file_sha256`、`staged_path`、`batch_status`…）
   没有敏感数据，无需扩展剔除名单。
   注意：`import_batches` 没有 `updated_at` 列，`audit_row()` 里那段
   “无实质变化则不留痕”的去抖逻辑（`:70`）对它依然有效，空转 UPDATE 不会产生噪声。

2. **`import_issues`：不逐行审计，每次重写写一条摘要。**
   摘要落在 `operation_logs.details`（jsonb），`object_type='import_issues'`：

   ```json
   {
     "batch_id": 42,
     "trigger": "validate",
     "deleted": 12,
     "inserted": 9,
     "by_code": {"MISSING_REQUIRED": 3, "UNKNOWN_STUDENT": 6},
     "by_severity": {"error": 7, "warning": 2},
     "rows_affected": [3, 7, 11]
   }
   ```

   这样“上一次校验报了什么、这次改映射后少了哪几条”就能纵向比较，成本只有一行。

3. **删除收口：`campus.clear_import_issues(p_batch_id, p_trigger)`（`SECURITY DEFINER`）。**
   函数内**先写摘要、再 DELETE**，然后收回 `003_roles.sql:55` 授予的
   `GRANT DELETE ON campus.import_issues`。
   把“删之前必须留痕”从「应用层的君子协定」变成「数据库的硬性约束」——
   这是本方案相对 B 最实质的差别。

### 4.2 为什么不选 A

`import_issues` 逐行审计的成本（单次校验 ~1.8 MB）与它提供的信息（“某条异常行被删了”）
严重不匹配，还会把 `operation_logs` 撑成噪声表，让保留策略和分区都被绑架。
状态机部分 A 是对的，所以那半边被 C 保留了。

### 4.3 为什么不选 B

两条硬伤：

1. **与既有权限模型冲突**：应用层写审计必须获得 `operation_logs` 的 INSERT，
   而 `003_roles.sql:51` 明确 `REVOKE INSERT, UPDATE, DELETE ... ON campus.operation_logs FROM campus_app`
   （注释写得很清楚：`operation_logs 对 campus_app 仅授予 SELECT，禁止改写审计记录`）。
   放开这条等于让应用角色具备伪造/清理审计的能力，是安全性的净损失。
2. **一致性靠自觉**：4 个状态跃迁点 + 2 个删除点，任何一处漏写都不会报错，只会静默断链；
   而触发器漏不掉。

---

## 5. 实施步骤与风险

> 以下步骤供后续执行参考，**本设计文档不实施**。

**前置条件（必须，否则审计价值打折）**

- 内部认证开启（`INTERNAL_AUTH_ENABLED=true`，规范见 `docs/INTERNAL-AUTH-SPEC.md`，
  实现随 PR #16 已合并）。关闭态下操作人来自可伪造的 `X-Actor`（`internal_auth.py:299`），
  审计只能证明“有人做过”，不能证明“是谁做的”。

**步骤**

1. 新增迁移 `sql/005_import_audit.sql`：
   - `CREATE TRIGGER trg_import_batches_audit ... EXECUTE FUNCTION campus.audit_row()`
   - `CREATE FUNCTION campus.clear_import_issues(...)`（`SECURITY DEFINER` + `SET search_path = campus, pg_temp`，
     与 `audit_row()` 保持一致）
   - `REVOKE DELETE ON campus.import_issues FROM campus_app`
   - `GRANT EXECUTE ON FUNCTION campus.clear_import_issues(...) TO campus_app`
2. 应用层：把 `service.py:593`、`:655` 两处裸 DELETE 换成调用该函数，并传入 trigger 语义
   （`remap` / `validate`）。
3. 补测试（对应 issue #8 矩阵 §8 的延伸）：
   - 批次每次状态跃迁都留一条审计，且 `actor_user_id` 等于签名身份
   - 摘要里的计数与实际异常行数一致
   - **绕过函数直接 DELETE 会报权限不足**（这条最关键，证明收口真的生效）
   - 审计与业务同事务：业务回滚时审计不残留
4. 观察一周 `operation_logs` 增长量，再决定是否按月分区。

**风险**

| 风险 | 评估 | 缓解 |
|---|---|---|
| 审计与业务同事务，审计出错会连带回滚业务 | 与现有学生审计一致，属既定取舍（宁可业务失败也不能“改了数据没痕迹”） | 摘要字段做长度约束，`details` 只存计数与学号列表的截断版本 |
| `SECURITY DEFINER` 函数被滥用 | `clear_import_issues` 只接受 `batch_id`，没有“任意条件删除”的接口 | 函数内校验批次存在；不给 `campus_app` 任何 `operation_logs` 权限 |
| `import_batches` 触发器放大写入成本 | 每批次仅 4~5 次 UPDATE，6 KB/批次，可忽略 | 上线后按 §3 口径复核增长量 |
| 关闭认证时审计仍可伪造 | — | 文档里明确：审计可信度与认证开关绑定；迁移说明中把开启认证列为前置条件 |
| 收回 DELETE 后旧代码路径报错 | 只有 `service.py` 两处调用，收口面小 | 与代码改动同一次 PR 完成，避免中间态 |

**未采纳但有价值的备选（供讨论）**

- 给 `import_issues` 加 `validate_seq` 版本号 + `issue_status` 软删除，可完整保留历次明细。
  成本是表体积增长（每次校验 N 行）与查询复杂度上升；若将来“历次校验结论比对”成为硬需求，
  可以在方案 C 的摘要之上再加，属于增量演进，不冲突。

---

## 6. 边界声明

本文档只做设计评估：未创建任何触发器、未改表结构、未改权限、未迁移数据，也未触碰批次 27/37。
所有引用均为只读取证，行号基于 `main` @ `d10946f`。
