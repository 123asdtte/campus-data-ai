# POC 导入 API 安全整改 PR #3 代码审查报告

- **审查对象**：`campus-ruoyi-poc` PR #3 `feat/import-api-security` → `main`
- **Head**：`86b8825`（4 个提交，+934/−130，8 个文件）
- **审查方式**：独立临时目录全新克隆（`Z:/ai/本地部署/.tmp/pr3-review/review`），未触碰开发目录；只读代码 + 在 POC 数据库做**权限探针**与**签名探针**
- **结论**：**REQUEST CHANGES**（存在 5 项 P1，其中 2 项已用可复现请求证实）

> 本报告不认可「34/34 通过 ⇒ 可合并」。测试通过只说明已覆盖的路径正确，不说明签名与审计的完整性。

---

## 1. 结论摘要

| 级别 | 数量 | 是否阻断合并 |
|---|---|---|
| P0 | 0 项**可直接利用的越权写入** | — |
| **P1** | **5**（其中 2 项落在 P0 检查项下，见说明） | **阻断** |
| P2 | 9 | 不阻断，需记录 |

> 分级说明：P1-1（表单字段未签名）与 P1-4（query 未签名）属于审查清单中"P0 检查项"的范围，
> 但利用前提是**能篡改 Java→FastAPI 之间的明文流量**（同网被攻陷容器或中间人），
> 且不能直接提权或跨学院写入，因此按 **P1** 计。若未来该链路跨主机/跨网段，应立即升为 P0。

**P1 清单**

| # | 问题 | 证据类型 |
|---|---|---|
| P1-1 | multipart 表单字段（`target_type` 等）未纳入签名 | 实测 200 复现 |
| P1-2 | `import_audit_trail` 跨批次串号 + 无访问控制 + PUBLIC 可执行 | 实测 33 行 vs 精确 1 行 |
| P1-3 | 审计函数属主为超级用户 `ruoyi` | `pg_proc` 实测 |
| P1-4 | query 参数未纳入签名 | 实测 200 复现 |
| P1-5 | `/stats/overview`、`/meta/filters` 完全未鉴权且跨学院聚合 | 实测 200 + 全量数据 |

---

## 2. P0 检查项结果（逐项）

### 2.1 SECURITY DEFINER 审计函数

| 检查项 | 结果 | 证据 |
|---|---|---|
| 固定 `search_path` | ✅ 通过 | `sql/07_import_security.sql:40,79,121` 均为 `SET search_path = campus, pg_temp` |
| 对象显式 schema | ✅ 通过 | 函数体内全部 `campus.operation_logs` 限定 |
| 函数属主最小权限 | ❌ **不通过（P1-3）** | `pg_proc.proowner = ruoyi`（超级用户），三个函数均如此 |
| 撤销 PUBLIC EXECUTE | ❌ **不通过（P1-2）** | 两个触发器函数 `proacl = NULL`（默认 PUBLIC 可执行）；`import_audit_trail` ACL 含 `=X/ruoyi`（PUBLIC） |
| `campus_app` 不能写审计表 | ✅ **通过（实测）** | `INSERT/UPDATE campus.operation_logs` → `ERROR: permission denied for table operation_logs` |
| 应用用户能否伪造他人操作 | ✅ 未发现可用路径 | 触发器函数引用转换表 `new_rows/old_rows`，触发器外调用即报错；无法直接构造审计行 |
| `import_audit_trail` 访问控制 | ❌ **不通过（P1-2）** | `campus_app` 调用 `import_audit_trail(6)` 返回 6 行，未校验批次归属 |
| 语句级触发器处理三类事件 | ⚠️ 部分 | `AFTER INSERT/UPDATE`（批次）、`AFTER INSERT/DELETE`（异常）已定义；**无 DELETE 审计**（批次删除未覆盖，当前业务不允许删批次，P2） |
| 聚合摘要与实际变更一致 | ⚠️ 有缺陷 | 单批次场景正确；`jsonb_object_agg(severity, …)` 在多批次同语句时会覆盖计数（P2-8） |
| 业务与审计事务边界 | ✅ 通过 | 触发器与业务同事务；清理事务已补 `_set_actor`（`service.py:846+`） |

### 2.2 HMAC、身份声明与防重放

| 检查项 | 结果 | 证据 |
|---|---|---|
| 方法/路径绑定 | ✅ | `poc_auth.py:87` canonical 第 1–2 段 |
| **query 参数绑定** | ❌ **P1-4** | 签名 `path=/imports`，实际请求 `/imports?limit=1` → **HTTP 200** |
| 时间戳 + nonce | ✅ | `poc_auth.py:132+`，60s 窗口 |
| 用户/角色/学院/部门/admin/权限 | ✅ 全部入签名 | canonical 第 6–12 段；admin 由 Java 依 `superadmin` 判定 |
| JSON 请求体摘要 | ✅ | `_payload_sha` 对非 multipart 取 raw body |
| 上传文件 SHA-256 | ✅ | Java `payloadSha = sha256(file)`（`PocProxyController.java:181`），FastAPI 重算比对 |
| **multipart 表单字段绑定** | ❌ **P1-1** | 签名只含文件摘要；实测把 `target_type` 从 `students` 改成 `student_changes` 仍返回 200 且生效 |
| 客户端伪造身份头 | ✅ 无效 | 实测 `X-Actor/X-Poc-User/X-Poc-Admin` 被忽略，审计 actor 仍为 `ry:poc_college_a` |
| Java/Python 规范化一致 | ✅ | 逐段比对 `PocProxyController.java:185` 与 `poc_auth.py:87`，顺序与编码一致（学院 percent-encode、perms 字典序） |
| nonce 原子性 | ✅ | `INSERT … ON CONFLICT DO NOTHING RETURNING`（`poc_auth.py:100`）依赖主键，非应用层查后写 |
| 并发重放 | ⚠️ 未验证 | 代码原子，但无并发测试（P2-3） |
| 时间窗与 nonce 清理一致 | ✅ | 60s 窗口 << 24h TTL |
| 密钥泄露面 | ✅ | 仅环境变量；异常路径不打印 canonical/secret |
| Java 先鉴权再签名 | ✅ | 7 个端点均 `@SaCheckPermission`（`:88–145`），`call()` 内从会话重建声明 |
| FastAPI 全路径验签 | ⚠️ 7 个导入接口 + 学生 3 接口已挂依赖；**`/stats/overview`、`/meta/filters` 未挂（P1-5）** | `main.py:347,352` |
| 直连 FastAPI | ✅ 不可达 | 容器 `8000/tcp` 未发布宿主端口 |

### 2.3 七个导入接口的授权与数据范围

| 接口 | Java 权限点 | FastAPI 校验 | 批次范围 | 结论 |
|---|---|---|---|---|
| `GET /imports` | `import:batch:list` | `require_perm` + 非管理员按 `dept_id` 过滤 | ✅ | 通过 |
| `GET /imports/{id}` | `import:batch:detail` | `_scope_checked` | ✅ | 通过 |
| `POST /preview` | `import:batch:upload` | `require_perm` | 新建归属当前部门 | 通过（**字段未签名 P1-1**） |
| `POST /preview-base64` | 同上 | 同上（body 摘要已签） | 同上 | 通过 |
| `POST /{id}/remap` | `import:batch:remap` | `_scope_checked` | ✅ | 通过 |
| `POST /{id}/validate` | `import:batch:validate` | `_scope_checked` | ✅ | 通过 |
| `POST /{id}/commit` | `import:batch:commit` | `_scope_checked` + 逐行学院校验 | ✅ | 通过 |

补充核验：

- 缺少学院声明 → `require_internal` 直接 403，无全库回退 ✅（`poc_auth.py:175-180`）
- `created_dept_id` 取自已验签 `current.dept_id`，路由不接受客户端该字段 ✅（`main.py:118-160`）
- 历史 `created_dept_id IS NULL` → 非管理员 403 ✅（`main.py:_assert_batch_scope`），**但无测试用例**（P2-7）
- `import:batch:cross_college` 来自签名声明，客户端无法自封 ✅
- 逐行校验：`sys_dept` 为权威清单，越权行写 `COLLEGE_OUT_OF_SCOPE` 并跳过，`students`/`student_changes` 均零落库 ✅（`service.py:740-815`；实测 DB 复查 0 行）
- 混合学院文件的响应/计数/issues 一致 ✅（实测 inserted=1、skipped=1）

### 2.4 文件生命周期与事务

| 检查项 | 结果 |
|---|---|
| 删除失败保留 `staged_path` | ✅ `service.py:846+`（`cleanup_ok` 控制是否置空） |
| DB 成功 / 清理失败可重试 | ✅ `cleanup_staged_files()` 只处理 `imported AND staged_path IS NOT NULL` |
| 两事务间崩溃 | ✅ 批次状态已 `imported`，路径保留，启动重试 |
| 清理限定暂存目录 | ✅ `path.startswith(upload_dir + os.sep)` |
| 符号链接 | ⚠️ 未解析 realpath；删除的是链接本身，风险低（P2） |
| 不误删 validated/处理中 | ✅ 只选 `imported` |
| **mapping sidecar** | ❌ 仍残留（P2-1） |
| 幂等 | ✅ `file_sha256 + imported` + 提交态 409 |
| 大文件内存 | ⚠️ `file.file.read()` / `getBytes()` 全量读入（P2-2） |

---

## 3. 发现明细

### P1-1 multipart 表单字段未纳入签名

- **位置**：`import-api-poc/app/poc_auth.py:117`（`_payload_sha` 只取文件摘要）；`backend/.../PocProxyController.java:181,185`（canonical 无表单字段）
- **复现**：容器内构造 multipart，签名只按文件 SHA-256 计算，把 `target_type=students` 改为 `student_changes`
  → **HTTP 200，响应 `target_type` 为 `student_changes`**
- **影响**：能篡改 Java→FastAPI 流量的主体（同网络被攻陷容器、中间人）可在不破坏签名的情况下改变导入目标表语义；POC 内 Java→FastAPI 为明文 HTTP
- **测试覆盖**：无（现有测试只验"签名篡改"）
- **修复**：把会影响语义的表单字段按固定顺序规范化后并入 canonical（如 `target_type \n sheet_name \n header_row \n mapping`），或对整个 multipart 的规范元数据做摘要
- **验证**：改任一字段后重放 → 401；正常请求仍 200

### P1-2 审计轨迹函数跨批次串号 + 无访问控制

- **位置**：`sql/07_import_security.sql:127`（`object_id LIKE '%' || p_batch_id || '%'`）、`:132`（GRANT 未 REVOKE PUBLIC）
- **复现**：
  - `SELECT count(*) FROM campus.import_audit_trail(1)` → **33**；精确匹配批次 1 仅 **1**
  - 以 `campus_app` 调用 `import_audit_trail(6)` → 返回 6 行（无归属校验）
  - `pg_proc.proacl` 显示 `=X/ruoyi`（PUBLIC 可执行）
- **影响**：审计查询返回错误批次记录（取证结论失真）；任一数据库角色可读取任意批次的操作人/状态变迁
- **修复**：`object_id` 比较改为 `id = ANY(string_to_array(object_id, ',')::bigint[])`；`REVOKE ALL ON FUNCTION … FROM PUBLIC`；按批次范围在应用层校验后再调用（或改为带 `WHERE` 参数的视图 + RLS）
- **验证**：`trail(1)` 仅 1 行；非授权角色调用报权限错误；非归属批次返回 0 行

### P1-3 审计函数属主为超级用户

- **位置**：`sql/07_import_security.sql:39,78,120`（三个 `SECURITY DEFINER` 函数）
- **证据**：`pg_proc.proowner = ruoyi`，且 `pg_roles.rolsuper = true`（实测），
  即函数以超级用户身份执行
- **影响**：函数一旦出现注入/路径缺陷即为超级用户权限提升面；违反"最小权限"要求
- **修复**：建专用角色（仅 `INSERT ON campus.operation_logs` + 序列 USAGE），`ALTER FUNCTION … OWNER TO`；再 `REVOKE PUBLIC`
- **验证**：`\df+` 显示属主为专用角色；`campus_app` 仍无表写权限；审计仍可写入

### P1-4 query 参数未纳入签名

- **位置**：`poc_auth.py:87`（canonical 只用 `request.url.path`）、`PocProxyController.java:185`
- **复现**：用 `path=/imports` 的签名请求 `/imports?limit=1` → **200**
- **影响**：当前参数（`limit` 被夹紧 1–200、`keyword` 仅在本范围内过滤）无越权；但签名完整性不成立，未来新增 `college/dept` 之类参数会直接变成可利用点
- **修复**：canonical 引入规范化 query（键排序、percent-encode、空值忽略）
- **验证**：改任一 query 值 → 401

### P1-5 两个读接口未鉴权且跨学院聚合

- **位置**：`import-api-poc/app/main.py:347`（`/meta/filters`）、`:352`（`/stats/overview`）
- **复现**：不带任何签名头直连 → **200**；返回 `colleges: [电子信息学院, 研发部门, 计算机学院]`、全量班级与总数
- **影响**：与 PR 描述"7 个接口全部受保护"形成事实缺口；任何能访问 FastAPI 的进程可读跨学院统计
- **修复**：挂 `require_internal` + 按 `colleges` 过滤聚合；或暂时下线，待权限设计就绪
- **验证**：无签名 401；学院 A 用户只看到本学院统计

### P2 清单

| # | 问题 | 位置 |
|---|---|---|
| P2-1 | `.mapping.json` sidecar 提交后不删除，长期残留 | `service.py` commit 清理分支 |
| P2-2 | 文件全量读入内存，接近 10MB 未压测 | `main.py:file.file.read()`；Java `getBytes()` |
| P2-3 | 无并发 nonce 测试（仅串行重放） | `test_import_security.sh` |
| P2-4 | 无"文件内容被篡改"测试（只测签名篡改） | 同上 |
| P2-5 | 测试脚本硬编码容器名 `ruoyi-poc-db`、依赖本机 docker | 同上 |
| P2-6 | 07 只有 up 脚本，无回滚脚本（触发器/函数/列） | `sql/07` |
| P2-7 | 历史 `created_dept_id IS NULL` 仅管理员：有代码无测试 | `main.py:_assert_batch_scope` |
| P2-8 | 异常审计 `jsonb_object_agg` 重复键覆盖（实测 `{"error":2}`，不报错） | `sql/07:100-110` |
| P2-9 | 遗留 `_actor()` 死代码（易被误用回退） | `main.py:64` |

---

## 4. 测试质量审查

| 检查项 | 结论 |
|---|---|
| 34 项是否命中真实接口/状态码/业务结果 | ✅ 抽查 8 项，均为真实 HTTP + DB 复查 |
| 是否存在只看日志的假阳性 | ✅ 未发现；关键断言均查 DB（越权零落库、审计 actor、staged_path） |
| 401/403/404/409/413 语义 | ⚠️ 401/403 走 RuoYi 业务码（HTTP 200），上游错误走 HTTP 状态；**口径混用需在文档写明** |
| 越权零写入 | ✅ 已验（`IMP…2` 计数 0） |
| 伪造头后审计操作人 | ✅ 已验（`ry:poc_college_a`） |
| base64 / 文件摘要 / 篡改 | ⚠️ base64 与签名篡改有测；**文件内容篡改未测**（P2-4） |
| 并发 nonce | ❌ 未测（P2-3） |
| 启动失败仍返回成功 | ✅ 脚本 `set -u` + 计数汇总，失败会非零退出 |
| 依赖外部端口/硬编码 | ⚠️ 依赖 `127.0.0.1:9180`、容器名 `ruoyi-poc-db`（P2-5） |
| 学生 12 项回归 | ✅ 本机复跑仍通过（非脚本自动执行） |

---

## 5. 未验证项（不得写成通过）

1. 并发重放（同 nonce 同时到达）
2. 接近 10MB 文件的内存与耗时
3. 单批 2000 行异常时的审计写放大（仅量级推断）
4. 历史 NULL 批次的越权访问（无测试样本）
5. DDL 回滚演练（无 down 脚本）
6. `campus.import_audit_trail` 在大表上的性能

---

## 6. 合并门槛建议

**REQUEST CHANGES**：先修 P1-1 至 P1-5，再重跑 34 项 + 新增 4 类用例（multipart 字段篡改、query 篡改、文件篡改、并发 nonce），并在报告中给出修复后的实测输出。

P2 可随修复一并处理或登记为后续 Issue；但 P2-1（sidecar）、P2-5（测试可移植性）建议同批修掉，成本极低。

修复完成后，建议按以下顺序复验：
1. 单元级：签名 canonical 覆盖字段清单（含 query 与表单）
2. 接口级：五个 P1 各自的负向用例
3. 回归：34 项 + 学生 12 项
4. 权限探针：`campus_app` 写审计表仍 denied、`import_audit_trail` 非授权不可调用
5. DDL 回滚演练（在临时库执行，不碰正式库）

---

## 7. 修复状态与复审结论（v3，2026-10-22）

### 7.1 五项 P1 的修复与实测

| P1 | 修复提交 | 实现 | 复核实测 |
|---|---|---|---|
| P1-1 multipart 字段未签名 | `e946e65` | canonical 增加 META 段（除 file 外全部字段，键排序 + 统一 percent-encoding） | 正常 200；改 `target_type` → **401** |
| P1-2 审计轨迹串号 | `bd5c3cb` | `unnest(string_to_array(object_id))` 精确匹配 | `trail(1)` **33 → 1 行**；批量副本 trail=exact（6=6） |
| P1-3 属主为超级用户 | `bd5c3cb` | NOLOGIN `campus_audit_writer`，三函数 ALTER OWNER，撤销 PUBLIC | `pg_proc` 属主已变更；PUBLIC 条目移除；campus_app 仍无写表权限 |
| P1-4 query 未签名 | `e946e65` | canonical 增加 QUERY 段 | 改 `?limit=1` → **401**；正常签名 → 200 |
| P1-5 两个读接口未鉴权 | `74fbbcb` | 挂验签 + colleges/dept 过滤 | 未签名 → **401**；`meta/filters` 仅返回「计算机学院」 |

### 7.2 测试结果（2026-10-22 09:30 实跑）

| 套件 | 结果 |
|---|---|
| `test_import_security.sh`（v3） | **48 / 48 通过** |
| `test_slice.sh`（学生管理回归） | **12 / 12 通过** |

覆盖新增项：query 篡改、multipart 字段篡改、文件内容替换、**并发同 nonce（实测 200 + 409）**、历史 `created_dept_id IS NULL` 批次（学院用户 403 / 管理员 200）、stats/meta 未签名 401 与范围过滤、审计属主与 PUBLIC 权限、审计串号精确比对。

### 7.3 复审结论

**APPROVE（POC 合并）**

- 5 项 P1 全部修复并有实测证据，无新增 P0/P1；
- 48 项导入安全矩阵 + 12 项学生回归全绿；
- 剩余风险均为 P2（见 §3 P2 清单）：sidecar 残留、大文件全量读入未压测、DDL 无回滚脚本、测试脚本绑定容器名，已登记不影响 POC 合并。

**仍不适用的结论**：本结论仅针对 POC 合并；主项目合入需另开 PR，且 `INTERNAL_AUTH_ENABLED` 默认关闭、新增写接口不注册。
