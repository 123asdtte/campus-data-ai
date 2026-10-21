# 导入 API 安全边界盘点（Issue #9）

- **日期**：2026-10-21
- **范围**：`/imports/**` 共 7 个接口（只读盘点）
- **代码基线**：`main @ 37ed9df`，`import-api/app/{main.py,service.py}`
- **结论**：**7 个接口全部无认证、无角色、无数据范围**；其中 `POST /imports/{id}/commit` 直接写 `students` 与 `student_changes`，是迁移上线前**必须**保护的最后一条写入路径

> 证据分级：**✅ 已确认**（代码/实测）｜**🔶 推断**（读代码得出，未实测）｜**⏳ 未验证**

---

## 1. 结论摘要

| 问题 | 结论 | 级别 |
|---|---|---|
| 认证 | 7 个接口**全部无认证**（无 Depends、无中间件、无 API Key） | ✅ |
| 角色权限 | 无 | ✅ |
| 操作人身份 | `X-Actor` 头，缺失时回落 `settings.actor_fallback`（默认 `import-api`），**任何调用方可任意填写** | ✅ |
| 学院/数据范围 | 无任何强制过滤 | ✅ |
| 绕过 Java 网关 | **可以**：`8010` 绑定在宿主机 `127.0.0.1`，本机任意进程可直连 | ✅ |
| 学生数据写入 | `commit` 写 `students` + `student_changes`，**完全绕过 S1–S3 的签名与学院范围** | ✅ |
| 批次/异常表审计 | **无触发器、无应用层审计** | ✅ |

---

## 2. 逐接口证据

### 2.1 `POST /imports/preview`（main.py:81）

| 项 | 事实 | 证据 |
|---|---|---|
| 业务函数 | `service.create_batch`（service.py:361） | ✅ |
| 认证 | 无 | ✅ |
| 身份 | `x_actor` 头 → `_actor()` 截断 150 字符（main.py:48-49、97） | ✅ |
| 数据范围 | 无 | ✅ |
| 文件 | 读全文 → 大小校验（service.py:374，`max_upload_bytes`）→ 行数上限（:385）→ **先写盘**（:390-393）→ 写 sidecar（:395）| ✅ |
| 落盘路径 | `{upload_dir}/{batch_code}{ext}`，`upload_dir` 默认 `/data/uploads`，容器挂 `campus_uploads` 卷 | ✅ |
| 写入表 | `import_batches` INSERT（:434）；缺必填列时 `import_issues` INSERT（:281） | ✅ |
| 审计 | 无（两张表均无触发器） | ✅ |
| 事务 | 单连接（:418）；**但文件在事务前已落盘** | ✅ |
| 异常/重试 | 同文件重复上传：查 `file_sha256 + imported`（:422），命中则复用；**但落盘发生在查重之前，重复上传会留下孤儿文件** | ✅ |
| 审计追溯 | 只能靠 `created_by`（可伪造） | ✅ |

### 2.2 `POST /imports/preview-base64`（main.py:138）

与 2.1 完全同一条 `create_batch` 链路，仅入参为 base64 字符串（`_decode_base64`，main.py:145）。**攻击面相同**。

### 2.3 `POST /imports/{id}/remap`（main.py:163 → service.py:539）

| 项 | 事实 |
|---|---|
| 认证 | 无 ✅ |
| 写入 | `import_batches` 重置为 `uploaded`（:586）、`import_issues` **DELETE**（:593）、重写 sidecar ✅ |
| 事务 | 单连接（:547）+ `SELECT ... FOR UPDATE` 防并发 ✅ |
| 风险 | 任何人可把已校验批次打回 `uploaded`，清空其异常明细；**无审计留痕** ✅ |
| 文件 | 只重写 sidecar，不动数据文件 ✅ |

### 2.4 `POST /imports/{id}/validate`（main.py:181 → service.py:642）

| 项 | 事实 |
|---|---|
| 认证 | 无 ✅ |
| 状态机 | `imported` 拒绝（:650，409）；其余状态可重复校验 ✅ |
| 写入 | `import_issues` **DELETE 后重插**（:655）、`import_batches` 更新计数（:665） ✅ |
| 审计 | 无 ✅ |
| 事务 | 单连接 + `FOR UPDATE`（:646） ✅ |
| 风险 | 每次校验抹掉上次结论，**历史校验不可追溯**；`campus_app` 拥有 `import_issues` 的 DELETE 是库内唯一物理删授权 ✅ |

### 2.5 `POST /imports/{id}/commit`（main.py:189 → service.py:697）⭐ 关键

| 项 | 事实 |
|---|---|
| 认证 | **无** ✅ |
| 身份 | `X-Actor`（main.py:193）→ `_set_actor`（service.py:703） ✅ |
| 数据范围 | **无**；不检查调用者属于哪个学院 ✅ |
| 写入表 | `students` INSERT（:736，`ON CONFLICT (student_no) DO NOTHING`）<br>`import_issues` INSERT（:758，学号冲突 warning）<br>`student_changes` INSERT（:767，target=student_changes 时）<br>`import_batches` UPDATE ×2（:790 状态/计数、:804 清空 staged_path） ✅ |
| 审计 | `students`/`student_changes` 触发器生效，**操作人 = X-Actor**（可伪造） ✅ |
| 事务 | **两段**：主循环单事务（:701-793）；清理与 `staged_path=NULL` 在**第二个连接**（:801-806） ✅ |
| 幂等 | 靠 `create_batch` 的 sha 查重；`commit` 本身对已导入批次直接 409（:717-724） ✅ |
| 失败行为 | 单行失败记入 `skipped`（学号已存在）或提前进 `import_issues`（校验失败行），**不中断整批** ✅ |
| 真实风险 | **任何人可提交任意批次，写入/更新任意学院的学生数据**；审计只能记录伪造的 `X-Actor` ✅ |

**写入时序（已确认）**

```
1. UPDATE import_batches SET status='importing'（:708）
2. for row in mapped:                       ← 同一事务
     INSERT students ... ON CONFLICT DO NOTHING
       └ 冲突 → INSERT import_issues(warning)
     [target=student_changes] INSERT student_changes ...
3. UPDATE import_batches SET status='imported', valid_rows=...（:790）
4. ── commit ──
5. 新事务：删除暂存文件 → UPDATE staged_path=NULL（:801）
```

### 2.6 `GET /imports/{id}`（main.py:203 → service.py:817）

| 项 | 事实 |
|---|---|
| 认证 | 无 ✅ |
| 返回 | 批次元信息 + 最多 500 条异常明细，**含 `source_filename`（原始文件名）** ✅ |
| 数据范围 | 无，可枚举任意 `id` ✅ |
| 风险 | 文件名叫"XX学院2026级花名册.xlsx"即泄露组织结构与生源信息 ✅ |

### 2.7 `GET /imports`（main.py:211 → service.py:859）

| 项 | 事实 |
|---|---|
| 认证 | 无 ✅ |
| 返回 | 最近 50 个批次（`batch_code`、文件名、行数、状态、`created_by`、时间） ✅ |
| 风险 | 可遍历全部导入历史与操作人（`created_by` 本身可伪造） ✅ |

---

## 3. 绕过路径分析（✅ 已确认）

| 路径 | 是否可达 | 说明 |
|---|---|---|
| 宿主机 → `127.0.0.1:8010` | ✅ 可达 | compose 显式发布端口（`docker-compose.yml:94`） |
| 前端 nginx → `/api/*` | ✅ 可达 | `web/nginx.conf:20-21` `proxy_pass http://import-api:8000/`，**不注入任何身份头、不做鉴权** |
| 局域网/公网 → 8010 | ❌ 不可达 | 只绑 `127.0.0.1`；但**本机任何进程**都算"内网" |
| Java 网关 → FastAPI | ✅ 仅 POC 副本，主项目**无此链路** | 主项目 FastAPI 不经 Java |

**结论**：只要攻击者能在该机器上执行任意进程（含脚本、浏览器扩展、其他容器），即可完整调用导入接口。**Java 网关不是主项目的入口，起不到任何保护作用。**

---

## 4. 审计覆盖矩阵

| 表 | 写入来源 | 触发器 | 操作人可信 | 可追溯状态变更 |
|---|---|---|---|---|
| `students` | commit | ✅ | ❌ `X-Actor` | ✅ 仅 insert |
| `student_changes` | commit | ✅ | ❌ `X-Actor` | ✅ 仅 insert |
| `import_batches` | preview/remap/validate/commit | ❌ | — | **❌ 完全不可追溯** |
| `import_issues` | preview/remap/validate/commit | ❌ | — | **❌ 每次校验被覆盖** |

---

## 5. 必须在正式迁移前修复（按优先级）

| # | 问题 | 建议措施 | 级别 |
|---|---|---|---|
| 1 | `commit` 无认证即可写学生数据 | 纳入统一链路：Java 授权 + FastAPI 验签 + 可信操作人；或先用「提交闸门」默认拒绝 | **P0** |
| 2 | 全部导入接口无认证 | 与 #1 同批处理；preview/validate 至少要求已登录会话 | **P0** |
| 3 | `X-Actor` 可伪造 | 改为签名声明（与 S1–S3 同一套 `require_internal`） | **P0** |
| 4 | 宿主机可直连 8010 | 迁移后取消宿主端口发布，仅容器网络可达 | P1 |
| 5 | 无学院范围 | 与 `/students` 一致的 `forced_college` 过滤（批次按创建者学院限定） | P1 |
| 6 | 批次/异常无审计 | 方案见 Issue #10 | P1 |
| 7 | 重复上传产生孤儿文件 | 查重前移（先算 sha → 查重 → 再落盘） | P2 |
| 8 | `import_issues` 的 DELETE 授权过宽 | 收窄为软删除或仅触发器写入 | P2 |

---

## 6. 与迁移计划的关系（上线门槛）

`RUOYI-S1S3-MERGE-PLAN.md` §3.1 已定义硬门槛，本盘点为其提供证据：

> **只要 `POST /imports/{id}/commit` 未受同等保护，系统就不能宣称"完成权限迁移"，不得切换正式入口。**

S1–S3 保护的是「查询 + 单条修改」；导入提交是**第二条完整写入路径**，两者必须同批或先后完成保护，否则"学生数据写入"仍存在无认证入口。

---

## 7. 未验证 / 推断项

| # | 项 | 状态 |
|---|---|---|
| 1 | 并发 `commit` 同一批次的行为 | 🔶 仅靠 `FOR UPDATE` 与状态判断，未做压力测试 |
| 2 | `staged_path` 清理失败（文件被占用）时的残留 | 🔶 代码 `except OSError: pass`，未实测 |
| 3 | 超大文件（接近 10MB）的内存占用 | 🔶 `file.file.read()` 全量读入，未压测 |
| 4 | `source_filename` 是否含个人信息 | ⏳ 未逐条检查存量数据（禁止接触真实数据） |
| 5 | 跨学院越权写入的实际影响面 | ⏳ 未在虚构数据上执行越权 commit（本轮只读） |

---

## 8. 建议的整改顺序

1. **止血**：给 `commit` 加开关，默认拒绝（仅内网批处理可开）；
2. **对齐身份**：引入 `require_internal`，覆盖 7 个接口；
3. **数据范围**：按调用者学院限制批次可见性与提交目标；
4. **审计补齐**：按 Issue #10 方案落地；
5. **收口**：取消 8010 宿主端口发布，前端统一走网关。

本轮仅盘点，**未修改任何代码、数据库或配置**。
