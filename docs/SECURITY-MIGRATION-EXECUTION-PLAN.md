# 安全迁移总执行计划（阶段 0–5）

- **状态**：阶段 1（PR-A）实施中；正式开关保持关闭
- **关联**：`INTERNAL-AUTH-SPEC.md`、`IMPORT-API-SECURITY-PLAN.md`、`RUOYI-S1S3-MERGE-PLAN.md`

---

## 阶段 0：基线与规划（已完成）

- 主项目现状：11 个业务路由无认证；无 nonce 表；CI 只跑 001。
- POC 已验证实现：`campus-ruoyi-poc` PR #3（`f1c2856`），导入 48/48、学生 12/12。
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
| 验收 | 关闭态 112 项全绿；开启态专项全绿；11×5 矩阵全绿；权限正负向全绿 |

**未覆盖（明确）**：导入批次范围（`created_dept_id`）、逐行学院校验、批次/异常表审计触发器。

---

## 阶段 2（PR-B）：学生域真实链路

- 前端与调用方切换为签名请求；删除 `X-Actor` 依赖。
- 审计核对：`operation_logs.actor_user_id` 必须等于验签用户。
- 补范围边界用例（`college_name` 为 NULL 的学生对非管理员不可见）。
- **验收**：学生列表/详情/修改全部走签名；跨学院 403 无回归。

---

## 阶段 3（PR-C）：导入链路范围与审计

- `sql/005_import_scope.sql`：`import_batches.created_dept_id` + 索引 + 审计触发器（语句级）。
- `service.create_batch(created_dept_id=)`、`commit_batch(allowed_colleges=)`、`list_batches(dept_id=)`、`batch_scope_info()`。
- 解除 `IMPORT_ADMIN_ONLY`，改为权限点 + 批次范围 + 逐行校验。
- **验收**：越权批次不可见/不可提交；历史 NULL 批次仅管理员；审计与 POC 一致；48 项导入安全用例在主项目复跑。

---

## 阶段 4（PR-D）：Java 网关与前端

- 按 `INTERNAL-AUTH-SPEC.md` 实现 `InternalProxyController`（`X-Internal-*`）。
- 权限点映射到 RuoYi 菜单；前端统一走 `/api`，不再直连 8010。
- 关闭 8010 的宿主端口发布（或以 nginx 独占）。
- **验收**：Java 复现金标向量；端到端（登录→网关→验签→DB→审计）可重复。

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
