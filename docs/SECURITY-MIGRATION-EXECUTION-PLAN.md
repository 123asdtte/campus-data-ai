# 安全迁移总执行计划（阶段 0–5）

- **版本**：v1.2（2026-10-22 最终核对：阶段 1 测试数字更正、阶段 2 补网关最小切片、阶段 4 对齐 PR-D 剩余范围）
- **状态**：阶段 1（PR-A）**已完成**——合并于 PR #16（merge `d10946f`），开关保持关闭；阶段 2（PR-B）待启动
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

## 阶段 3（PR-C）：导入链路范围与审计

- `sql/006_import_scope.sql`：`import_batches.created_dept_id` + 索引 + 审计触发器（语句级）。
- `service.create_batch(created_dept_id=)`、`commit_batch(allowed_colleges=)`、`list_batches(dept_id=)`、`batch_scope_info()`。
- 解除 `IMPORT_ADMIN_ONLY`，改为权限点 + 批次范围 + 逐行校验。
- **验收**：越权批次不可见/不可提交；历史 NULL 批次仅管理员；审计与 POC 一致；48 项导入安全用例在主项目复跑。

---

## 阶段 4（PR-D）：正式入口（网关剩余范围）

PR-B 已完成登录与学生 3 端点；本阶段只做剩余部分，不重复实现 canonical 与登录：

- 网关补 **导入 7 个代理端点**（multipart：文件 SHA-256 + 非文件字段签名，复用 POC `PocProxyController` 导入段）；
- 前端导入页切登录会话，统一走网关 `/api`；
- **先证明**前端经网关访问全部必需接口（学生 3 + 聚合 2 + 导入 7）均 200；
- 再移除 compose 中 `127.0.0.1:8010:8000` 发布；nginx 保持按服务名 `import-api:8000` 访问；
- **验收**：宿主 `curl 127.0.0.1:8010` 连接被拒；容器内 `campus-web` → `import-api:8000` 仍 200；网关→import-api 内网签名链路正常。

---

## 阶段 5（PR-E）：全量回归与发布评审

- 全量：关闭态 + 开启态 + 学生回归 + 导入安全 + 迁移/回退演练。
- 性能：大文件内存、nonce 写入、审计批量落库。
- 产出 Go/No-Go 报告；**只有通过后才允许**开启正式认证、执行正式库迁移、切换入口。

---

## 回退约定（每阶段通用）

| 层 | 操作 |
|---|---|
| 配置 | `INTERNAL_AUTH_ENABLED=false` + `--force-recreate import-api` |
| 代码 | `git revert <merge sha>` |
| DDL | 各阶段脚本附独立回退语句；004 为 `DROP FUNCTION/TABLE/ROLE` |

## 不可自动执行

- 真实业务库迁移；开启正式开关；切换入口；扩大授权；删除数据卷或验收证据。
