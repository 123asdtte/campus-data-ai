# PR-E 整体验收报告（Go/No-Go）

- **日期**：2026-10-22
- **范围**：G 文档治理、R Appsmith 下线、PR-B 学生域网关、PR-C 导入域隔离、PR-D 统一入口、PR-E 全量验收
- **环境**：本机 Docker Desktop；业务栈 `campus-data-ai` + 前端栈 `campus-web`；隔离测试库 `campus-test-db:5433/campus_test`
- **结论**：**代码合并级 Go**；**正式切换级 Conditional Go**（需人工批准迁移与开关切换，见 §8）
- **未执行（明确）**：正式库迁移、正式环境开启 `INTERNAL_AUTH_ENABLED`、合并 PR、正式业务切换

---

## 1. 分阶段结论

| 阶段 | 结论 | 关键证据 |
|---|---|---|
| G 文档治理 | **PASS** | 治理基线 40 = 14 + 26；同事 PR #24 新增设计文档、PR-E 新增验收报告后为 16 + 26 = 42；链接与废弃路线检查通过；PR #18 |
| R Appsmith 下线 | **PASS**（含 1 项未验证） | 容器 `Exited (137)`、8081/8443 监听数 0、compose 无服务、卷 `campus_appsmith_stacks` 保留；PR #19 |
| PR-B 学生域 | **PASS** | 真实 RuoYi 登录 → 网关签名 → FastAPI 验签 → 学院范围 → 审计；PR #21 |
| PR-C 导入域 | **PASS** | 批次归属 + 逐行学院校验 + 方案 C 审计（批次行级 + 异常摘要）；关闭态 183 passed、开启态 120 passed；PR #22 |
| PR-D 统一入口 | **PASS** | 12 端点经网关；26 项 E2E + 浏览器 7 步；宿主 8010 关闭；PR #25 |
| PR-E 全量验收 | **PASS** | 关闭态 183 passed；开启态 120 passed；迁移/回退演练通过；PR-E 专项 11 passed |

---

## 2. 测试证据

### 2.1 关闭态（`INTERNAL_AUTH_ENABLED=false`）

```text
python -m pytest -q
183 passed, 102 skipped, 4 xfailed
```

包含同事 PR #20/#27 新增的 6 个测试文件（聚合、异常文件、remap、staging、冲突、覆盖矩阵第二步）；#23 的两处 strict xfail 已随 PR-C 修复转为正式断言。

### 2.2 开启态安全专项（`INTERNAL_AUTH_ENABLED=true`）

```text
pytest -q tests/test_internal_auth.py tests/test_route_matrix.py tests/test_db_privileges.py \
          tests/test_import_scope.py tests/test_student_write.py tests/test_pr_e_hardening.py \
          tests/test_import_audit_summary.py
120 passed
```

覆盖：11 业务路由 × 5 类身份的权限矩阵、篡改/重放/过期/并发 nonce、跨学院读写、审计 actor、DB 权限正负向、批次范围、逐行学院拒绝、审计摘要与删除收口。

### 2.3 PR-E 专项（`tests/test_pr_e_hardening.py`，11 passed）

| 用例 | 实测结果 |
|---|---|
| 并发学生更新 | 2 个并发 PUT 均 200；最终值属于两者之一；**2 条 update 审计、2 个不同 actor** |
| 并发导入提交 | 同一批次并发提交：**1×200 + 1×409**；学生行数 3、无重复；批次状态 `imported` |
| nonce 过期清理 | 过期行被删除、未过期保留；重复调用返回 0 |
| nonce 增长 | 1000 条 = **216 KiB**（`pg_total_relation_size`） |
| nonce 周期清理 | 后台循环在 0.06s 内被调用 ≥2 次（间隔改为 0.01s 的测试） |
| 大文件预览 | **8,658,061 bytes / 9000 行**，0.30–0.44s，200 |
| 超限文件 | >10MB 返回 **413**，提示包含"上限" |
| 1000 行批量提交 | **2.08–2.64s**；1000 条学生审计 actor=`ry:college_a`；批次审计无匿名 |
| 暂存文件清理 | 提交后 `staged_path IS NULL` |
| 配置 fail-closed | 密钥缺失/过短、时间窗越界均启动失败并给出明确错误 |

### 2.4 网关端到端（真实登录 + HMAC）

开启态下经 `http://127.0.0.1:8082/gw` 执行 **26 项，全部 PASS**：

- 学生/聚合：admin、college_a、college_b 的列表/筛选项/总览均 200；学院列表仅本学院（各 20 条）。
- 导入 multipart：college_a 预览 200 → 批次归属 `1762000000000000101` → remap 200 → validate 2 行 → commit 200 → 学生落库 → 审计 `ry:college_a`。
- 逐行范围：混合学院批次 commit **403 且零写入**。
- 越权：college_b 读/提交他人批次 403；readonly 权限不足；未登录 401；未签名/伪造内部头直连 FastAPI 401。
- 关闭 8010 前后：关闭前宿主 `8010/health`=200（基线）；关闭后 **000（连接失败）**；容器内 `import-api:8000/health`=200；网关学生/导入/总览仍 200。

### 2.5 浏览器 UI（真实 Chrome）

未登录跳转 `/login` → admin 登录 → 学生列表 **236 条** → 导入页步骤条 → 按批次号恢复 → 退出，**7 步全部 PASS**，控制台无 TypeError / Failed to fetch。

### 2.6 CI

PR #21、#22、#25、#26 的 CI 全部 SUCCESS（后端语法、接口测试、网关构建、前端构建、AI 评审）。其中 #26 的开启态步骤已纳入 PR-C/PR-E 安全用例（`test_import_scope`、`test_student_write`、`test_pr_e_hardening`、`test_import_audit_summary`）。

### 2.7 同事成果集成（PR #20 / #24 / #27）

三个 PR 均由同事 hjy-helloy 完成并已合并到 `main`（我方堆叠链原基于 `d10946f`，本次已同步）：

| PR | 内容 | 判定 | 集成处理 |
|---|---|---|---|
| #20 | 覆盖矩阵第二步：6 个测试文件（commit 冲突、parsing 边界、queries、remap、staging） | **A** | 全部保留；在本方分支复跑，48 项通过 |
| #24 | `IMPORT-AUDIT-DESIGN.md`：方案 C 设计（只读） | **B** | 设计成立；据此把 PR-C 的 006 从“逐行审计异常表”收敛为“批次行级 + 异常摘要 + 删除收口” |
| #27 | 覆盖矩阵第三步：`test_meta_and_files.py`（聚合/筛选/异常文件/冲突夹具） | **A**（含 2 处标记需调整） | 保留；其两处 `#23 strict xfail` 因 PR-C 修复而 XPASS，已改为正式断言 |
| #29（open） | D-4 删死代码 + D-1 sidecar 与暂存文件同删 | **B** | 质量与 CI 通过；但与 PR-C 同改 `service.py`，且覆盖 `test_staging.py`/`test_parsing_edge.py`。建议 #22 合并后由作者 rebase，暂不合并；合并后文档计数将变为 17+26=43 |

已合并三个 PR 的重叠面只有 `docs/TEST-COVERAGE-MATRIX.md`（已合并双方内容）；`#29` 另与 PR-C 在 `service.py` 及两个测试文件上重叠，按 B 类暂缓。同事成果没有依赖未合并的前置改动，也未触及认证、数据库权限或密钥。

---

## 3. 迁移与回退演练

脚本：`scripts/rehearse_migrations.py`（隔离库 `campus_rehearsal` / `gateway_rehearsal`，演练后自动删除）。

```text
PASS 001 建库结构 0.16s
PASS 004 第 1 次执行（幂等） 0.02s
PASS 004 第 2 次执行（幂等） 0.00s
PASS 004 回退（删函数/表；保留集群级角色）
PASS 004 回退后重放 0.01s
PASS 006 第 1 次执行（方案 C 幂等） 0.01s
PASS 006 第 2 次执行（方案 C 幂等） 0.01s
PASS 006 回退（触发器/函数/索引/列 + 恢复 DELETE）
PASS 006 回退后重放 0.01s
PASS 迁移未写入业务行 students=0
PASS 005 网关库初始化 0.39s users=6 menus=117 import_perms=6
PASS 清理演练数据库
=== 演练通过，总耗时 6.87s ===
```

说明：
- 006 演练同时验证 `clear_import_issues()` / `record_import_issues()` 存在、批次触发器唯一、`campus_app` 无 `import_issues` DELETE；回退时恢复该 DELETE 授权。
- 004 回退只删本库函数/表，**不删除集群级角色** `campus_nonce_cleaner`（其他库仍在使用）。
- 005 是初始化脚本，**非幂等**，只演练单次执行；重复执行不在设计目标内。
- 003 是集群级角色脚本（含 psql 元命令），不属于单库迁移，演练跳过。

---

## 4. 性能与内存

| 指标 | 实测 |
|---|---|
| 9MB 文件预览（解析） | 0.30–0.44s |
| 1000 行提交（含审计） | 2.08–2.64s |
| 网关内存（8.66MB multipart 上传） | 870.9 → **883.6 MiB**（+12.7 MiB） |
| Import API 内存（同一次上传） | 86.64 → **147.7 MiB**（+61 MiB），请求后回落 86.64 MiB |
| nonce 表 | 1000 行 216 KiB；周期清理 3600s + 启动时各一次 |
| 异常明细审计量 | 方案 C：每次重写 1~2 行摘要；按 #24 估算，2000 行异常的一次校验由约 4000 行审计降至 1~2 行 |

---

## 5. 安全边界核查

| 项 | 结果 |
|---|---|
| 正式库迁移 | **未执行**（004/005/006 只在开发栈与一次性演练库执行） |
| 认证开关 | 开发栈最终 **false**；未做正式切换 |
| 密钥 | 实际 HMAC 值不在 Git 跟踪文件与历史中（`git grep`/`git log -S` 均为空）；仓库只有脱敏 `.env.example` |
| Appsmith 数据卷 | `campus_appsmith_stacks` 存在且未删除 |
| `campus_app` 账号 | **保留**；import-api 的 `DATABASE_URL` 正在使用，不能删除 |
| 学生隐私 | 全部测试使用虚构样例与 E2E 前缀数据；未导出真实学生信息 |
| PR 状态 | #17/#18/#19/#21/#22/#25 全部未合并，堆叠依赖正确 |

---

## 6. 未验证事项（不得标记为通过）

1. Appsmith 停用后是否存在外部业务依赖：无日志/访问证据可证明"无人依赖"，维持 **未验证**。
2. RuoYi 精简裁剪：当前使用完整 RuoYi 构建，未做裁剪验证（体积/内存已实测可接受）。
3. 生产 TLS、反向代理 HTTPS、真实域名：未配置。
4. 多用户/持续负载压测：只做了单请求大文件与 2 并发，未做长时间压测。
5. 正式库迁移与回退：只在演练库与开发库执行，正式库需人工批准后按 §3 流程执行。
6. plus-ui 许可：未采用其界面，不构成依赖。

---

## 7. 残余风险

| 级别 | 风险 | 处理 |
|---|---|---|
| P2 | 网关 `MultipartFile.getBytes()` 全量读入内存 | 已实测 8.66MB 峰值 +12.7MiB；更大文件或高并发需限流/流式改造 |
| P2 | Appsmith 业务依赖未验证 | 恢复方式与卷保留已记录；建议下线观察期内保留 |
| P2 | nonce 清理为应用内定时任务，容器长期停机期间不清理 | 过期行不影响安全（仅占空间）；启动时会补一次清理 |
| P3 | 关闭态仍允许 `X-Actor` 演示身份 | 生产必须开启认证；文档已显著标注 |
| P3 | 中文操作人无法经 HTTP 头传递（xfail 固化） | 开启态 actor 来自登录用户，不受影响；关闭态仅演示 |
| P3 | 提交后 sidecar `.mapping.json` 残留（同事用例 xfail 固化，§10-1） | 不影响数据正确性；后续可随清理逻辑一并修复 |
| P3 | 损坏 xlsx 返回 500 而非 400（同事用例 xfail 固化，§10-4） | 用户侧错误码不友好；不影响数据安全 |

无 P0 / P1 未处理项。

---

## 8. Go / No-Go

- **代码合并：GO**。所有关键测试通过、回退演练成功、文档与代码一致、无未处理 P0/P1。
- **开发环境：GO**。当前栈 healthy，8010 已关闭，认证开关为 false。
- **正式环境切换：CONDITIONAL GO**。必须由项目负责人明确批准后，按顺序执行：
  1. 备份正式库（`pg_dump`）；
  2. 在正式库执行 004 → 006（先预演 §3，再执行）；
  3. 配置正式 HMAC 密钥与网关库 005 引导；
  4. 开启 `INTERNAL_AUTH_ENABLED=true` 并重建 import-api；
  5. 执行 §2.4 的回归命令与人工冒烟；
  6. 观察期后再合并 PR（当前全部保持未合并）。

---

## 9. PR 汇总与合并顺序

| 顺序 | PR | base ← head | 内容 |
|---|---|---|---|
| 1 | #17 | `main` ← `docs/stage0-planning` | 总规划与阶段 0 修订 |
| 2 | #18 | `docs/stage0-planning` ← `docs/governance-stage0` | G 文档治理 |
| 3 | #19 | `docs/governance-stage0` ← `chore/appsmith-r2` | R Appsmith 下线 |
| 4 | #21 | `chore/appsmith-r2` ← `feat/student-gateway-pr-b` | PR-B 学生域网关 |
| 5 | #22 | `feat/student-gateway-pr-b` ← `feat/import-scope-pr-c` | PR-C 导入域隔离 |
| 6 | #25 | `feat/import-scope-pr-c` ← `feat/gateway-entry-pr-d` | PR-D 统一入口 |
| 7 | #26 | `feat/gateway-entry-pr-d` ← `test/pr-e-acceptance` | PR-E 验收、专项测试与演练脚本 |

按上表顺序合并；每个 PR 只包含相对其 base 的独立改动。
**注**：`main` 已由同事合并 #20/#24/#27；本堆叠链已同步这些提交并解决 `TEST-COVERAGE-MATRIX.md` 冲突，合并顺序不变。

---

## 10. 回退手册（摘要）

- **PR-E 代码**：`git revert` 本 PR；不影响已部署功能。
- **PR-D**：恢复 compose `127.0.0.1:8010:8000`、nginx `/api` 与 Vite `/api`，前端恢复旧 `get/post`。
- **PR-C**：执行 `sql/006_import_scope.sql` 末尾回退语句；`git revert`。
- **PR-B**：停止并移除 gateway 服务；前端学生页恢复旧入口。
- **R**：将 Appsmith 服务定义加回 compose，复用 `campus_appsmith_stacks` 卷。
- **正式库**：任何迁移前必须 `pg_dump`；004/006 回退语句分别在文件头/尾注释中。
