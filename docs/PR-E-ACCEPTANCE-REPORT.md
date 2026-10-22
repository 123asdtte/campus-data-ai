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
| G 文档治理 | **PASS** | `docs/` 40 = 现行 14 + archive 26；根 `PROJECT-ROADMAP.md` 单独计数；链接检查通过；PR #18 |
| R Appsmith 下线 | **PASS**（含 1 项未验证） | 容器 `Exited (137)`、8081/8443 监听数 0、compose 无服务、卷 `campus_appsmith_stacks` 保留；PR #19 |
| PR-B 学生域 | **PASS** | 真实 RuoYi 登录 → 网关签名 → FastAPI 验签 → 学院范围 → 审计；PR #21 |
| PR-C 导入域 | **PASS** | 批次归属 + 逐行学院校验 + 批次/异常表审计；关闭态 130 passed、开启态 105 passed；PR #22 |
| PR-D 统一入口 | **PASS** | 12 端点经网关；26 项 E2E + 浏览器 7 步；宿主 8010 关闭；PR #25 |
| PR-E 全量验收 | **PASS** | 关闭态 130 passed；开启态 116 passed；迁移/回退演练通过；PR-E 专项 11 passed |

---

## 2. 测试证据

### 2.1 关闭态（`INTERNAL_AUTH_ENABLED=false`）

```text
python -m pytest -q
130 passed, 101 skipped, 1 xfailed
```

跳过项均为"仅开启态运行"的安全用例，属预期。

### 2.2 开启态安全专项（`INTERNAL_AUTH_ENABLED=true`）

```text
pytest -q tests/test_internal_auth.py tests/test_route_matrix.py tests/test_db_privileges.py \
          tests/test_import_scope.py tests/test_student_write.py tests/test_pr_e_hardening.py
116 passed
```

覆盖：11 业务路由 × 5 类身份的权限矩阵、篡改/重放/过期/并发 nonce、跨学院读写、审计 actor、DB 权限正负向、批次范围、逐行学院拒绝。

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

PR #21、#22、#25 的 CI 全部 SUCCESS（后端语法、接口测试、网关构建、前端构建、AI 评审）。

---

## 3. 迁移与回退演练

脚本：`scripts/rehearse_migrations.py`（隔离库 `campus_rehearsal` / `gateway_rehearsal`，演练后自动删除）。

```text
PASS 001 建库结构 0.13s
PASS 004 第 1 次执行（幂等） 0.02s
PASS 004 第 2 次执行（幂等） 0.01s
PASS 004 回退（删函数/表；保留集群级角色）
PASS 004 回退后重放 0.02s
PASS 006 第 1 次执行（幂等） 0.01s
PASS 006 第 2 次执行（幂等） 0.01s
PASS 006 回退（触发器/函数/索引/列）
PASS 006 回退后重放 0.01s
PASS 迁移未写入业务行 students=0
PASS 005 网关库初始化 0.36s users=6 menus=117 import_perms=6
PASS 清理演练数据库
=== 演练通过，总耗时 1.99s ===
```

说明：
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
| 7 | 本 PR | `feat/gateway-entry-pr-d` ← `test/pr-e-acceptance` | PR-E 验收、专项测试与演练脚本 |

按上表顺序合并；每个 PR 只包含相对其 base 的独立改动。

---

## 10. 回退手册（摘要）

- **PR-E 代码**：`git revert` 本 PR；不影响已部署功能。
- **PR-D**：恢复 compose `127.0.0.1:8010:8000`、nginx `/api` 与 Vite `/api`，前端恢复旧 `get/post`。
- **PR-C**：执行 `sql/006_import_scope.sql` 末尾回退语句；`git revert`。
- **PR-B**：停止并移除 gateway 服务；前端学生页恢复旧入口。
- **R**：将 Appsmith 服务定义加回 compose，复用 `campus_appsmith_stacks` 卷。
- **正式库**：任何迁移前必须 `pg_dump`；004/006 回退语句分别在文件头/尾注释中。
