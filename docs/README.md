# 文档索引

> **2026-10-22 文档治理完成**：`docs/` 现行 **14** 份 + `archive/` 历史 **26** 份 = 40 份；根目录 `PROJECT-ROADMAP.md` 单独计数，根 `README.md`/`CONTRIBUTING.md` 仅更新不计入。
>
> **唯一年有效认证方案**：RuoYi 登录会话 → Java 网关 `X-Internal-*` 签名 → FastAPI 二次验签。任何 pwdlib/PyCasbin 或"不迁移若依"的旧方案都只在 `archive/` 中作历史追溯，**不得作为实施依据**。

图例：✅ 已完成并生效 ｜ 🧪 仅隔离 POC 成立 ｜ 📐 方案/决策（未实施） ｜ 🗺️ 路线 ｜ ⚙️ 协议 ｜ 🔐 契约

---

## 一、现行规范（docs/ 14 份）

### 入口与路线

| 文档 | 状态 | 内容 |
|---|---|---|
| [README.md](README.md) | ✅ | 本索引 |
| [`../PROJECT-ROADMAP.md`](../PROJECT-ROADMAP.md) | ✅ | **唯一总路线图**（根目录，不计入 docs 14）：G/R/PR-B/C/D/E、变更边界、停止条件、自主执行边界 |
| [SECURITY-MIGRATION-EXECUTION-PLAN.md](SECURITY-MIGRATION-EXECUTION-PLAN.md) | 🗺️ | 安全迁移专项细化（阶段 0–5），冲突时以总路线图为准 |
| [EXECUTION-PROTOCOL.md](EXECUTION-PROTOCOL.md) | ⚙️ | 执行协议：两种任务模式、PR 流程、自主/批准边界、中断恢复 |
| [DOCUMENTATION-AUDIT.md](DOCUMENTATION-AUDIT.md) | 🗂️ | 文档分类、计数口径、归档方案与 POC 审查 |

### 架构、安全与契约

| 文档 | 状态 | 内容 |
|---|---|---|
| [ARCHITECTURE-AND-SECURITY-PLAN.md](ARCHITECTURE-AND-SECURITY-PLAN.md) | 🏛️ | 现状拓扑、可信身份链路、安全边界、数据库边界（基线 `d10946f`） |
| [INTERNAL-AUTH-SPEC.md](INTERNAL-AUTH-SPEC.md) | 🔐 | **内部认证唯一契约**：14 段 canonical、11 个头、金标向量 |
| [SECURITY-CHECKLIST.md](SECURITY-CHECKLIST.md) | 📐 | 安全检查项：数据、身份、权限、密钥、网络、备份、导入 |

### 接口、数据与测试

| 文档 | 状态 | 内容 |
|---|---|---|
| [IMPORT-API.md](IMPORT-API.md) | ✅ | 导入接口契约：请求、响应、状态机、幂等、双模式认证 |
| [DATA-DICTIONARY.md](DATA-DICTIONARY.md) | ✅ | 表结构、字段、枚举、约束 |
| [TEST-COVERAGE-MATRIX.md](TEST-COVERAGE-MATRIX.md) | 📐 | 覆盖矩阵与缺口分析（基线 `c28ec94`，待更新为 `d10946f`） |
| [ADR-001-import-mapping.md](ADR-001-import-mapping.md) | ✅ | 表头识别与字段映射采用规则而非大模型 |

### 盘点、部署与协作

| 文档 | 状态 | 内容 |
|---|---|---|
| [API-MIGRATION-INVENTORY.md](API-MIGRATION-INVENTORY.md) | ✅ | 12 个接口盘点与安全边界（历史基线 `5b5d0dc`，状态更新见 §5） |
| [DOCKER-ENV-AUDIT.md](DOCKER-ENV-AUDIT.md) | ✅ | Compose、Dockerfile、CI、远程/本机差异（POC 已独立仓库） |
| [GIT-WORKFLOW.md](GIT-WORKFLOW.md) | ✅ | 分支模型、提交信息、版本标签、回滚；`main` 只接受 PR |

---

## 二、`archive/` 历史归档（26 份，仅追溯）

> 归档不代表删除：全部保留 Git 历史与审计价值。归档文档中的方案、数字与环境快照可能已过时，**不得作为当前实施依据**。

### 一期 Appsmith 阶段（8）

[PRD.md](archive/PRD.md)、[APPSMITH-SETUP.md](archive/APPSMITH-SETUP.md)、[TEST-PLAN.md](archive/TEST-PLAN.md)、[BUILD-LOG.md](archive/BUILD-LOG.md)、[PHASE0-ENV-CHECK.md](archive/PHASE0-ENV-CHECK.md)、[REACT-MIGRATION-PLAN.md](archive/REACT-MIGRATION-PLAN.md)、[REACT-TEST-REPORT.md](archive/REACT-TEST-REPORT.md)、[DEPLOY-WEB-PLAN.md](archive/DEPLOY-WEB-PLAN.md)

### 一期验收（1）

[DEPLOY-ACCEPTANCE-1.3.md](archive/DEPLOY-ACCEPTANCE-1.3.md)

### 轻量认证路线（4）

[SECURITY-AUTH-ROADMAP.md](archive/SECURITY-AUTH-ROADMAP.md)、[SECURITY-AUTH-DESIGN.md](archive/SECURITY-AUTH-DESIGN.md)、[SECURITY-AUTH-DECISION.md](archive/SECURITY-AUTH-DECISION.md)、[RUOYI-PLUS-EVALUATION.md](archive/RUOYI-PLUS-EVALUATION.md)

### RuoYi 评估与 POC 方案（4）

[RUOYI-PLUS-MIGRATION-PLAN.md](archive/RUOYI-PLUS-MIGRATION-PLAN.md)、[POC-SHARING-PLAN.md](archive/POC-SHARING-PLAN.md)、[POC-FRESH-CLONE-REPORT.md](archive/POC-FRESH-CLONE-REPORT.md)、[RUOYI-POC-GO-NOGO.md](archive/RUOYI-POC-GO-NOGO.md)

### POC 执行记录（4）

[RUOYI-POC-AUTH-RESULTS.md](archive/RUOYI-POC-AUTH-RESULTS.md)、[RUOYI-POC-DATA-PERMISSION.md](archive/RUOYI-POC-DATA-PERMISSION.md)、[RUOYI-POC-STUDENT-SLICE.md](archive/RUOYI-POC-STUDENT-SLICE.md)、[POC-IMPORT-API-PR3-REVIEW.md](archive/POC-IMPORT-API-PR3-REVIEW.md)

### 被 PR #16 取代的计划（3）

[RUOYI-S1S3-MERGE-PLAN.md](archive/RUOYI-S1S3-MERGE-PLAN.md)、[IMPORT-API-SECURITY-PLAN.md](archive/IMPORT-API-SECURITY-PLAN.md)、[IMPORT-API-SECURITY-INVENTORY.md](archive/IMPORT-API-SECURITY-INVENTORY.md)

### 已合并 PR 的审查与实测（2）

[PR16-PRE-MERGE-REVIEW.md](archive/PR16-PRE-MERGE-REVIEW.md)、[IMPORT-MAPPING-TEST.md](archive/IMPORT-MAPPING-TEST.md)

---

## 阅读建议

| 你的目的 | 建议顺序 |
|---|---|
| 第一次接触项目 | [`../README.md`](../README.md) → [`../PROJECT-ROADMAP.md`](../PROJECT-ROADMAP.md) → DATA-DICTIONARY → IMPORT-API |
| 参与开发 | README → CONTRIBUTING → GIT-WORKFLOW → 当前阶段方案 |
| 评审安全改动 | ARCHITECTURE-AND-SECURITY-PLAN → INTERNAL-AUTH-SPEC → SECURITY-CHECKLIST |
| 评估 RuoYi 路线 | PROJECT-ROADMAP §5 → `archive/` 中的 POC 记录（仅历史） |
