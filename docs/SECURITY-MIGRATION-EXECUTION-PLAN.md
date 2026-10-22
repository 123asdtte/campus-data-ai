# 安全迁移总执行计划（阶段 0–5）

- **版本**：v1.2（2026-10-22 最终核对：阶段 1 测试数字更正、阶段 2 补网关最小切片、阶段 4 对齐 PR-D 剩余范围）
- **状态**：阶段 1（PR-A）**已完成**——合并于 PR #16（merge `d10946f`），开关保持关闭；阶段 2（PR-B）**分支已实现、待评审**（`feat/student-gateway-pr-b`）
- **地位**：安全迁移**专项细化**；总路线图与阶段定义以根目录 `PROJECT-ROADMAP.md` 为准（含 PR-B/D 职责调整与文档治理阶段），冲突时以 PROJECT-ROADMAP 为准
- **关联**：`INTERNAL-AUTH-SPEC.md`、`PROJECT-ROADMAP.md`、`docs/ARCHITECTURE-AND-SECURITY-PLAN.md`

---

## 阶段 0：基线与规划（已完成）

- 主项目现状：11 个业务路由无认证；无 nonce 表；CI 只跑 001。
- POC 已验证实现：`campus-ruoyi-poc` PR #3（`f1c2856`），导入 48/48、学生 12/12。
  - 口径：48 为 `test_import_security.sh` 的**运行时计数**（静态无法复算）；12 为 `test_slice.sh` 的 **T1–T12 段落数**，该脚本无 PASS/FAIL 计数器。
- 结论：先补基础设施，再按域接入，最后统一发布。

---

## 阶段 1（PR-A）：认证基础设施 + 全路由认证

| 项 | 内容 |
|---|---|
| 代码 | `internal_auth.py`、`routes/*`、`config.py` 开关、`queries.py` 范围过滤 |
| DDL | `sql/004_internal_auth.sql`（nonce 表 + 受控清理函数） |
| CI | 001→003→004；管理连接初始化；`campus_app` 跑业务测试；正负权限断言 |
| 默认 | `INTERNAL_AUTH_ENABLED=false`；`PUT /students/{no}` 不注册（405） |
| 导入接口 | 认证 + 权限点 + **管理员硬限制**（PR-C 前） |
| 验收 | 关闭态 130 passed / 82 skipped / 1 xfailed（collected 213）；开启态 88 passed（collected 88）；11×5 矩阵全绿；权限正负向全绿（CI run 39725491360 实查） |

**未覆盖（明确）**：导入批次范围（`created_dept_id`）、逐行学院校验、批次/异常表审计触发器。

---

## 阶段 2（PR-B）：学生域真实链路（含网关最小切片）

**状态**：🟡 分支已实现、待评审（`feat/student-gateway-pr-b`）。

**为什么包含网关**：PR-A 只提供"验签能力"，没有"签名产生者"。没有网关，学生域只能停在测试桩，无法产生真实 `X-Internal-*`。因此把网关**提前并缩小**到"登录 + 学生 3 端点"，原 PR-D 的其余部分（导入接入 + 前端导入页 + 关 8010）保持为 PR-D。

- 独立数据库 `campus_gateway` + 专用账号 `gw_app`（仅 `sys_*` 读写，对 `campus` schema 零权限）；
- `sql/005_gateway_bootstrap.sql`：`sys_*` 必要子集（PG 方言，取自 POC `sql/01_ruoyi.sql`）、管理员、`student:list/write` 权限点、学院角色；
- 网关端点：`POST /auth/login`、学生列表/详情/修改 3 个代理端点；
- 前端学生页切换为签名请求；删除 `X-Actor` 依赖；
- 学院清单由网关随签名下发（`X-Internal-Colleges`），**不查 `sys_dept`**；
- 审计核对：`operation_logs.actor_user_id` 必须等于验签用户；
- 补范围边界用例（`college_name` 为 NULL 的学生对非管理员不可见）。
- **验收**：学生列表/详情/修改全部走签名；跨学院 403 无回归；审计新增匿名=0；关闭态 130 项回归全绿；`gw_app` 对 `campus` schema 零权限（DB 断言）。

---

## 阶段 3（PR-C）：导入链路范围与审计 —— 已实施（独立 PR 待评审）

- `sql/006_import_scope.sql`：`import_batches.created_dept_id` + 索引 + 审计触发器（语句级，`SECURITY DEFINER`）。
- `service.create_batch(created_dept_id=)`、`commit_batch(allowed_colleges=)`、`list_batches(dept_id=)`、`_assert_batch_scope()`。
- 解除 `IMPORT_ADMIN_ONLY`，改为权限点 + 批次范围 + 逐行校验；批次内任一有效行越权即整批 403 且不落库。
- **验收（实测）**：`test_import_scope.py` 8 passed；关闭态全量 130 passed；开启态专项 105 passed；历史 NULL 批次仅管理员可见；006 仅在测试库执行。
- **与计划的差异**：POC 的 48 项导入安全用例未逐条 1:1 移植，按主项目语义重写为 8 项批次范围用例 + 既有导入安全用例（`test_import_security` 系列）；该差异在 PR 说明中披露。

---

## 阶段 4（PR-D）：正式入口（网关剩余范围）—— 已实施（独立 PR 待评审）

PR-B 已完成登录与学生 3 端点；本阶段只做剩余部分，不重复实现 canonical 与登录：

- 网关补 **导入 7 个代理端点 + 聚合 2 个端点**（multipart：文件 SHA-256 + 非文件字段签名）；
- 前端业务请求全部切登录会话，统一走网关 `/gw`；移除 nginx `/api` 与 Vite `/api` 代理；
- 先证明前端经网关访问全部必需接口（学生 3 + 聚合 2 + 导入 7）均 200，再移除 compose 中 `127.0.0.1:8010:8000` 发布；
- **验收（实测）**：开启态 26 项 E2E 全 PASS；宿主 `curl 127.0.0.1:8010` 连接失败；容器内 `campus-web` → `import-api:8000` 仍 200；网关→import-api 内网签名链路正常；浏览器 UI 7 步 PASS。
- **附带变更**：`sql/005` 增加导入域 6 个权限点并授予 `college_scope` 角色（仅网关库，可重复执行）。

---

## 阶段 5（PR-E）：全量回归与发布评审 —— 已实施（独立 PR 待评审）

- 全量：关闭态 **130 passed** + 开启态 **116 passed** + 网关 26 项 E2E + 浏览器 7 步。
- 性能：9MB 预览 0.30–0.44s；1000 行提交 2.08–2.64s；网关 +12.7MiB / Import API +61MiB 峰值；nonce 1000 行 216KiB。
- 迁移/回退：004/005/006 在一次性隔离库演练 **12 步全 PASS，1.99s**；正式库未执行。
- 验收中修复两处缺口：提交后暂存清理事务未注入 actor（产生匿名审计）、nonce 仅启动清理（改为 3600s 周期清理）。
- 产出 `PR-E-ACCEPTANCE-REPORT.md`；**只有通过且人工批准后才允许**开启正式认证、执行正式库迁移、切换入口。

---

## 回退约定（每阶段通用）

| 层 | 操作 |
|---|---|
| 配置 | `INTERNAL_AUTH_ENABLED=false` + `--force-recreate import-api` |
| 代码 | `git revert <merge sha>` |
| DDL | 各阶段脚本附独立回退语句；004 为 `DROP FUNCTION/TABLE/ROLE` |

## 不可自动执行

- 真实业务库迁移；开启正式开关；切换入口；扩大授权；删除数据卷或验收证据。
