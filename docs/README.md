# 文档索引

本目录存放全部设计、方案与验收记录。**先读状态标记，再看内容**——不同文档的结论适用范围不同。

图例：✅ 已完成并生效 ｜ 🧪 仅在隔离 POC 成立 ｜ 📐 方案/决策（未实施） ｜ 📜 历史记录

---

## 一、当前系统（主项目）

| 文档 | 状态 | 内容 |
|---|---|---|
| [PRD.md](PRD.md) | 📐 | 产品需求与阶段划分 |
| [DATA-DICTIONARY.md](DATA-DICTIONARY.md) | ✅ | 表结构、字段含义、枚举值、约束 |
| [IMPORT-API.md](IMPORT-API.md) | ✅ | 导入接口契约：请求、响应、状态机、幂等 |
| [IMPORT-MAPPING-TEST.md](IMPORT-MAPPING-TEST.md) | ✅ | 表头识别与字段映射的测试记录（11 项接口测试 + 20 项浏览器验收） |
| [SECURITY-CHECKLIST.md](SECURITY-CHECKLIST.md) | 📐 | 安全检查项清单 |
| [REACT-TEST-REPORT.md](REACT-TEST-REPORT.md) | ✅ | React 前端测试报告 |
| [REACT-MIGRATION-PLAN.md](REACT-MIGRATION-PLAN.md) | 📐 | 前端迁移计划 |
| [BUILD-LOG.md](BUILD-LOG.md) | 📜 | 构建与依赖变更记录 |
| [PHASE0-ENV-CHECK.md](PHASE0-ENV-CHECK.md) | 📜 | 阶段 0 环境核查 |

## 二、部署与运维

| 文档 | 状态 | 内容 |
|---|---|---|
| [DEPLOY-WEB-PLAN.md](DEPLOY-WEB-PLAN.md) | ✅ | 前端容器化方案与实施记录（含踩坑） |
| [DEPLOY-ACCEPTANCE-1.3.md](DEPLOY-ACCEPTANCE-1.3.md) | ✅ | 部署最终验收：重启、导入链路、独立回退 |
| [GIT-WORKFLOW.md](GIT-WORKFLOW.md) | ✅ | 分支模型、提交信息、版本标签、回滚 |
| [APPSMITH-SETUP.md](APPSMITH-SETUP.md) | 📜 | Appsmith 部署（历史方案，非主入口） |
| [TEST-PLAN.md](TEST-PLAN.md) | 📐 | 测试计划 |
| `.github/workflows/ai-review.yml` | ✅ | PR 自动评审机器人：diff 发给 LLM，结论以 PR 评论发布（需配置 AI_API_KEY 等 Secrets，未配置自动跳过） |

## 三、技术决策（ADR）

| 文档 | 状态 | 内容 |
|---|---|---|
| [ADR-001-import-mapping.md](ADR-001-import-mapping.md) | ✅ | 表头识别与字段映射采用规则而非大模型：取舍、局限、未来引入 AI 的边界 |
| [SECURITY-AUTH-DECISION.md](SECURITY-AUTH-DECISION.md) | 📐 | 认证选型：pwdlib + PyCasbin vs 若依；许可证与维护状态核查 |
| [RUOYI-PLUS-EVALUATION.md](RUOYI-PLUS-EVALUATION.md) | 🧪 | RuoYi-Vue-Plus 6.X 集成评估：事实核查、兼容性差异、no-go 门槛 |
| [RUOYI-PLUS-MIGRATION-PLAN.md](RUOYI-PLUS-MIGRATION-PLAN.md) | 📐 | 若依隔离验证与迁移方案（阶段 0–5） |

## 四、认证与权限（主系统，尚未实施）

| 文档 | 状态 | 内容 |
|---|---|---|
| [SECURITY-AUTH-DESIGN.md](SECURITY-AUTH-DESIGN.md) | 📐 | 现状取证：访问入口、数据库角色、审计契约、绕过路径 |
| [SECURITY-AUTH-ROADMAP.md](SECURITY-AUTH-ROADMAP.md) | 📐 | P0–P5 实施步骤、文件清单、测试与回退 |
| [API-MIGRATION-INVENTORY.md](API-MIGRATION-INVENTORY.md) | ✅ | 现有 12 个接口的完整盘点与安全边界（迁移依据） |
| [IMPORT-API-SECURITY-INVENTORY.md](IMPORT-API-SECURITY-INVENTORY.md) | ✅ | 导入 7 接口的逐条安全取证：全部无认证，commit 写学生表（Issue #9） |
| [IMPORT-API-SECURITY-PLAN.md](IMPORT-API-SECURITY-PLAN.md) | 📐 | 导入 7 接口的统一认证/权限/范围/审计整改设计（未实施） |
| [POC-IMPORT-API-PR3-REVIEW.md](POC-IMPORT-API-PR3-REVIEW.md) | 🔍 | POC PR #3 代码审查与复审：5 项 P1 修复证据、48/48 + 12/12 |
| [INTERNAL-AUTH-SPEC.md](INTERNAL-AUTH-SPEC.md) | 🔐 | 内部请求认证规范：14 段 canonical、11 个头、金标向量 |
| [SECURITY-MIGRATION-EXECUTION-PLAN.md](SECURITY-MIGRATION-EXECUTION-PLAN.md) | 🗺️ | 安全迁移总路线（阶段 0–5、依赖、验收、回退） |

## 五、RuoYi POC 验收记录（隔离环境，仓库之外）

> 以下结论**只在隔离 POC 成立**。主项目尚未合并任何认证/授权实现。

| 文档 | 状态 | 内容 |
|---|---|---|
| [RUOYI-POC-AUTH-RESULTS.md](RUOYI-POC-AUTH-RESULTS.md) | 🧪 | 登录 403 定位与修复、身份贯通、签名与重放防护、React 前端验收 |
| [RUOYI-POC-DATA-PERMISSION.md](RUOYI-POC-DATA-PERMISSION.md) | 🧪 | 数据权限：框架 Mapper 与实际业务路径**分别**取证，A1–A8 矩阵 |
| [RUOYI-POC-GO-NOGO.md](RUOYI-POC-GO-NOGO.md) | 🧪 | Go/No-Go 判定与成本对比（结论：条件性 Go） |
| [RUOYI-POC-STUDENT-SLICE.md](RUOYI-POC-STUDENT-SLICE.md) | 🧪 | 学生管理切片 S1–S3 验收：12 项测试全通过 |
| [POC-FRESH-CLONE-REPORT.md](POC-FRESH-CLONE-REPORT.md) | 🧪 | 全新克隆复现验证：修复 4 个阻塞后 12/12 通过 |
| [RUOYI-S1S3-MERGE-PLAN.md](RUOYI-S1S3-MERGE-PLAN.md) | 📐 | S1–S3 合入主项目的迁移评审计划（未执行） |

---

## 阅读建议

| 你的目的 | 建议顺序 |
|---|---|
| 第一次接触项目 | README → PRD → DATA-DICTIONARY → IMPORT-API |
| 参与开发 | README → CONTRIBUTING → GIT-WORKFLOW → 当前阶段对应的方案文档 |
| 评审安全相关改动 | SECURITY-AUTH-DESIGN → API-MIGRATION-INVENTORY → POC 三份验收记录 |
| 评估是否继续若依路线 | RUOYI-PLUS-EVALUATION → POC 三份验收记录 → SECURITY-AUTH-DECISION |
