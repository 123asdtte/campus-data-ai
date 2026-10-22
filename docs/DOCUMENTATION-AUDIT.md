# 文档审计与治理方案（DOCUMENTATION AUDIT）

- **版本**：v1.2（2026-10-22 最终核对：计数口径修正、PR #17 状态、Appsmith 下线后的更新范围）
- **方法**：逐文件阅读 + 交叉引用 grep + 与 main `d10946f` 代码/CI/部署现状比对；不按文件名或日期判断。
- **边界**：本轮**不执行**归档/删除；获批后按 §5 一次性实施。
- **范围**：`docs/` 40 份 Markdown（含索引 README）+ 根 `PROJECT-ROADMAP.md` 1 份 + 根 `README.md`/`CONTRIBUTING.md`（仅更新，不计入）+ 未跟踪 `.tmp/`。

---

## 1. 计数（唯一分类，数量与路径一一对应）

### 1.1 分类演变说明（v1.0 → v1.1 更正）

| 版本 | A | B | C | D | 问题 |
|---|---|---|---|---|---|
| 初始审计（逐文件判定） | 4 | 7 | 26 | 0 | — |
| v1.0 文档 | 4 | 7 | 26 | 0 | **成员错误**：把 `TEST-COVERAGE-MATRIX` 由 B 提升为 A，却**漏列**了 A 类的 `SECURITY-MIGRATION-EXECUTION-PLAN`（总数偶然仍为 37，成员不唯一） |
| **v1.1（本次）** | **5** | **6** | **26** | **0** | 每份文件恰好一类；`TEST-COVERAGE-MATRIX` 提升为 A 的理由已写明 |

**`TEST-COVERAGE-MATRIX` 分类变更说明**：原判 B（需更新）——因基线 `c28ec94`/112 用例已过时、且未含 PR #16 新增的安全测试层。现提升为 **A（保留但需更新基线）**：其"59 场景缺口"仍是 PR-C/PR-E 补测的权威输入，比"待更新的现状快照"价值更高。更新动作保留在 §2 的 A 表中（**分类为 A，动作仍是更新**）。

### 1.2 数量总账（v1.2 修正）

| 口径 | 数量 |
|---|---|
| 治理前：`docs/` 现有文档（含索引 `README.md`） | **40** = 旧文档 37（A5+B6+C26）+ 本轮新增 3 |
| 治理前：根目录新增规划文件 | **1**（`PROJECT-ROADMAP.md`） |
| 治理前：全项目文档合计 | **41** = docs 40 + 根 1 |
| 根目录 `README.md`/`CONTRIBUTING.md` | 2（不计入 41，仅更新） |
| 治理后：`docs/` 现行文档 | **14** = A 5 + B 6（含索引 `README.md`）+ 新增 3 |
| 治理后：`docs/archive/` 历史文档 | **26** |
| 治理后：`docs/` 合计 | **40** = 14 + 26（数量守恒，无删除） |
| 治理后：全项目合计 | **41** = docs 40 + 根 `PROJECT-ROADMAP.md` 1 |
| 本次新增规划文件 | **4 份**：根 `PROJECT-ROADMAP.md`；`docs/ARCHITECTURE-AND-SECURITY-PLAN.md`、`docs/DOCUMENTATION-AUDIT.md`、`docs/EXECUTION-PROTOCOL.md` |

> **v1.1 口径更正**：v1.1 写"docs 现行 15 = A5+B6+新增4、合计 41"，把根目录 `PROJECT-ROADMAP.md` 算进了 `docs/`。按文件实际路径，`docs/` 内新增只有 3 份，现行 14 份；全项目（含根路线图）才是 15 份现行 / 41 份合计。v1.2 已按路径拆分，不再混用。

---

## 2. 逐文件判定（37 份，每份恰好一类）

### A 类 — 当前权威（5）

| 文件 | 主题 | 保留理由 / 需更新点 |
|---|---|---|
| `ADR-001-import-mapping.md` | 规则优先于大模型的映射决策 | 决策对象未被 PR #16 改动，仍是约束依据 |
| `DATA-DICTIONARY.md` | 业务表字段/枚举/审计字段字典 | 表结构未变，PR-B/C 开发现行依据 |
| `INTERNAL-AUTH-SPEC.md` | 内部认证规范（14 段、11 头、金标向量） | PR-D 唯一权威契约；**更新**：状态行"PR-A 实施中"→"已随 PR #16 合并" |
| `SECURITY-MIGRATION-EXECUTION-PLAN.md` | 安全迁移专项细化（阶段 0–5） | 现行有效；**更新**：阶段 1 标完成（`d10946f`），并声明与 `PROJECT-ROADMAP.md` 的主从关系 |
| `TEST-COVERAGE-MATRIX.md` | 112 用例覆盖矩阵 + 59 场景缺口 | 缺口分析是 PR-C/PR-E 补测权威输入（**由 B 提升**）；**更新**：基线→`d10946f`，补"安全/权限"覆盖层，复核 §10 疑似缺陷修否 |

### B 类 — 需更新（6）

| 文件 | 需更新要点 |
|---|---|
| `API-MIGRATION-INVENTORY.md` | 头部注明基线 `5b5d0dc`；标记 §5 已由 PR-A 完成的项；§8 环境快照标失效 |
| `DOCKER-ENV-AUDIT.md` | §3"CI 无 pytest"已过时；§4.2 POC 已升独立仓库；P0 建议标完成；补入索引 |
| `GIT-WORKFLOW.md` | 删"允许直接提交 main"；分支前缀统一 `feat/`；type 表补 perf（与 CONTRIBUTING 对齐） |
| `IMPORT-API.md` | §3.7 `/health` 旧响应与新契约矛盾 → 更新为 `{status}` 并补 `/health/ready`；§2 身份说明改双模式 |
| `SECURITY-CHECKLIST.md` | §2/§3 补关闭态/开启态两种语境；登记 Appsmith 可写账号为未解决风险（链接 R 任务） |
| `docs/README.md`（索引） | 重建为两节结构（**现行规范** / `archive/`），收录全部现存文件，标注治理过渡期 |

### C 类 — 归档到 `docs/archive/`（26）

> 全部有历史/审计/决策价值，**不删除**。归档时同步修正引用（§4）。

| 组 | 文件 |
|---|---|
| 一期 Appsmith 阶段（8） | `PRD.md`、`APPSMITH-SETUP.md`、`TEST-PLAN.md`、`BUILD-LOG.md`、`PHASE0-ENV-CHECK.md`、`REACT-MIGRATION-PLAN.md`、`REACT-TEST-REPORT.md`、`DEPLOY-WEB-PLAN.md` |
| 一期验收（1） | `DEPLOY-ACCEPTANCE-1.3.md` |
| 轻量认证路线（4） | `SECURITY-AUTH-ROADMAP.md`、`SECURITY-AUTH-DESIGN.md`、`SECURITY-AUTH-DECISION.md`、`RUOYI-PLUS-EVALUATION.md` |
| RuoYi 评估与 POC 方案（4） | `RUOYI-PLUS-MIGRATION-PLAN.md`、`POC-SHARING-PLAN.md`、`POC-FRESH-CLONE-REPORT.md`、`RUOYI-POC-GO-NOGO.md` |
| POC 执行记录（4） | `RUOYI-POC-AUTH-RESULTS.md`、`RUOYI-POC-DATA-PERMISSION.md`、`RUOYI-POC-STUDENT-SLICE.md`、`POC-IMPORT-API-PR3-REVIEW.md` |
| 被 PR #16 取代的计划（3） | `RUOYI-S1S3-MERGE-PLAN.md`、`IMPORT-API-SECURITY-PLAN.md`、`IMPORT-API-SECURITY-INVENTORY.md` |
| 已合并 PR 的审查与实测（2） | `PR16-PRE-MERGE-REVIEW.md`、`IMPORT-MAPPING-TEST.md` |

关键理由（抽查）：
- `SECURITY-AUTH-ROADMAP`：`sql/004_auth.sql` 编号与实际 `004_internal_auth.sql` 撞车且内容完全不同，README §3.1 仍引用它 → **最危险的失效引用**；
- `SECURITY-AUTH-DECISION`：核心结论（不迁移若依）已被条件性 Go 推翻，仅作"为什么改向"档案，归档时加取代说明；
- `RUOYI-PLUS-EVALUATION`：其"plus-ui MIT 没问题"早于 Issue #11，归档后**不得再作许可背书引用**；
- `RUOYI-S1S3-MERGE-PLAN`：文件名（`poc_auth.py`、`004_internal_nonce.sql`）与实际实现不一致，保留正文会双轨。

### D 类 — 删除（0）

`docs/` 内无。

### 根目录文档（2 份，不计入 37）

| 文件 | 更新要点 |
|---|---|
| `README.md` | 7 处：行 39/99/123/151/179/308/322 的 Appsmith 运行描述（**R2 已停服务，需改为"已下线"**）；行 77"未实现"、行 86 指向已废弃 ROADMAP、行 127 缺 004、行 173/182 编号重复、行 222 测试表缺双模式与实际数字（关闭态 130/开启态 88）、行 278 X-Actor 表述、POC 措辞（48/53） |
| `CONTRIBUTING.md` | 2 处：行 83-84"后端没有单元测试目录"已过时；分支前缀 `feature/`→`feat/`；补 CI 双连接要求 |

---

## 3. 跨文档矛盾（10 条）

| # | 冲突 | 处置 |
|---|---|---|
| 1 | GIT-WORKFLOW"允许直接提交 main" vs CONTRIBUTING"main 只接受 PR" | B 类统一 |
| 2 | 分支前缀 `feat/` vs `feature/` | 统一 `feat/` |
| 3 | ROADMAP(pwdlib+Casbin) vs INTERNAL-AUTH-SPEC（网关签名） | ROADMAP 归档 |
| 4 | SECURITY-AUTH-DECISION"不迁移若依" vs 条件性 Go | 归档 + 取代说明 |
| 5 | IMPORT-API.md §3.7 vs §9 的 `/health` 契约 | B 类更新 |
| 6 | S1S3 计划文件名 vs 实际实现名 | S1S3 归档 |
| 7 | "12/7 接口全部无认证" vs "11 路由开启态已验签" | 旧文档标基线 |
| 8 | DOCKER-ENV-AUDIT"CI 无 pytest" vs 现状 | B 类更新 |
| 9 | 7 段 canonical（旧）vs 14 段（现行） | 旧文档归档 + SPEC 声明唯一性 |
| 10 | RUOYI-PLUS-EVALUATION 许可背书 vs Issue #11 | 归档 + 不得引用为背书 |

**新增矛盾（v1.1 发现）**：PROJECT-ROADMAP v1.0 写"ry_* 表"，而 RuoYi-Vue-Plus 6.0.0 实际为 **`sys_*`**（以 POC `sql/01_ruoyi.sql` 为准）→ 已在 v1.1 更正。

失效引用：`SECURITY-AUTH-ROADMAP` 引用的 `sql/004_auth.sql`/`auth/*`/`LoginPage.tsx` 不存在；`S1S3-MERGE-PLAN` 引用的 `poc_auth.py`/`004_internal_nonce.sql` 不存在；`IMPORT-API.md §3.7` 旧 `/health` 字段；`APPSMITH-SETUP` 的 `X-Actor` 注入在开启态无效。归档后仅存在于 archive 内部。

索引缺口（治理 PR 修复）：`TEST-COVERAGE-MATRIX`、`PR16-PRE-MERGE-REVIEW`、`DOCKER-ENV-AUDIT`、`POC-SHARING-PLAN` 未被 `docs/README.md` 收录。

---

## 4. `.tmp/`（未跟踪，10 个文件）

| 文件 | 处置 |
|---|---|
| `comment-1/3/9/12.md`（评论草稿，结论已入正式文档） | 删除 |
| `issues/*.md`（Issue 草稿） | 与线上 Issue 逐份比对：已发布即删；`issue-license.md` 确认无未发布内容后删 |
| `patch_test.py`、`prev.json`、`t2.json`、`u.txt`、`uploads.txt` | 删除 |

均为本地未跟踪文件，不涉及 Git 历史。

---

## 5. 治理实施方案（获批后一个 PR）

> **状态（2026-10-22）**：PR #17 已开放待审批，本轮只交付规划，**尚未执行 `git mv`、未归档、未删除**。

**PR**：`docs/governance-stage0`，单 PR 多 commit：

0. **前置事实**：PR #17 已开放（head `3a2efda`），包含本轮 4 份新增规划文件 + `docs/README.md` + `SECURITY-MIGRATION-EXECUTION-PLAN.md` 修改；G 阶段应在 PR #17 合并后执行，避免重复改同一批文件。
1. `git mv` 26 份 C 类 → `docs/archive/`（文件名不变）；
2. C 类中 3 份加"已被取代"头注（`SECURITY-AUTH-ROADMAP`、`SECURITY-AUTH-DECISION`、`RUOYI-PLUS-EVALUATION`）；
3. 更新 6 份 B 类 + 根 2 份（§2 列表）；
4. 纳入 4 份新增规划文件（PR #17 已纳入，G 仅核对索引）；
5. 重建 `docs/README.md`：两节结构（**现行规范** / `archive/`（历史，仅追溯））；
6. 修复归档造成的相对链接（8 处外部引用，逐一 `grep -rn "docs/<file>"` 核对）；
7. **同步 Appsmith 下线**：README 7 处、`APPSMITH-SETUP.md`（随 C 类归档）、`DOCKER-ENV-AUDIT.md`、`SECURITY-CHECKLIST.md` 的状态描述；
8. 校验：非 archive 文件中 `grep -rn "SECURITY-AUTH-ROADMAP\|poc_auth.py\|004_internal_nonce\|ry_\*"` **零命中**。

**影响评估**：移动 26 个文件会破坏相对路径引用——已盘点 8 处需同步；不删除任何文件，`git revert` 可整体回退；对 CI 无影响。

**治理后结构**：

```
PROJECT-ROADMAP.md            ← 总路线图（根）
README.md / CONTRIBUTING.md   ← 修正后
docs/
  README.md                   ← 索引：现行规范 / archive/
  ARCHITECTURE-AND-SECURITY-PLAN.md  EXECUTION-PROTOCOL.md  DOCUMENTATION-AUDIT.md
  INTERNAL-AUTH-SPEC.md  IMPORT-API.md  DATA-DICTIONARY.md  TEST-COVERAGE-MATRIX.md
  SECURITY-CHECKLIST.md  ADR-001-import-mapping.md
  API-MIGRATION-INVENTORY.md  DOCKER-ENV-AUDIT.md  GIT-WORKFLOW.md
  archive/                    ← 26 份历史文档
```

**收益**：活跃文档 37 → 15（含 4 新增）且与 `d10946f` 一致；互斥方案不再并存于正文；阶段证据在 `archive/` 可查；索引覆盖 100%；AI 与新人不会再从废弃路线出发。

---

## 6. POC 仓库审查（新增，动用 POC 代码前必读）

对象：`campus-ruoyi-poc` **origin/main `f1c2856`**（PR #3 已合并）。方法：只读静态审读，**未运行容器、未构建、未复算计数**。
> 本地 `main` 实际为 `d5c45dc`，**落后 origin/main 10 个提交**；工作分支为 `feat/import-api-security` @ `563e400`。审查结论以 origin/main 为准，本地操作前先 `git fetch`。

### 6.1 可移植性

| 分类 | 内容 |
|---|---|
| 零改动可复制 | 14 段 canonical 构造与段序、`pct`/`normalize`、`sha256`/`hmacHex`、multipart 签名策略（文件内容摘要 + 非文件字段 meta）、`Who`/`require_perm`/`require_college` 骨架、RestClient 转发与错误透传；`LoginHelper.getLoginUser/getUsername/getDeptId/getDeptName` 在 v6.0.0 确认存在 |
| 必须改写 | 头名 `X-Poc-*`→`X-Internal-*`（11 个）；权限点 `poc:student:*`→`student:*`；`poc.hmac-secret`→`INTERNAL_HMAC_SECRET`；nonce **沿用主项目** `internal_nonce`+`cleanup_internal_nonce()`；admin 判定改严格布尔；补 POC 缺失的 nonce/ts/dept 格式与长度校验、密钥 ≥32 校验 |
| 禁止移植 | `sql/06` 的 `campus.poc_nonce`（含 `GRANT DELETE`）；`sql/07:196` 的 `GRANT SELECT ON sys_dept TO campus_app`；`sql/08` 复制 admin 密码建用户；`poc-api` 服务与 `--poc.api-base`（键名与代码不匹配，参数实际未生效）；`.env.poc`（磁盘含明文密钥） |
| POC 文档已过时 | `VERSIONS.md`（"5 处/3 处定制"与 PR #3 实际 diff 不符）；POC `README.md`（写"sql/01–06"实为 01–08；测试脚本清单漏 `test_import_security.sh`） |

### 6.2 角色模型差异（结构性）

| | POC | 主项目 | 移植规则 |
|---|---|---|---|
| 角色数 | 2（`campus_app`、`campus_audit_writer`） | 3（`campus_app`、`campus_ro`、`campus_nonce_cleaner`） | 沿用主项目，不回退 |
| nonce 表 | `campus.poc_nonce`，**无 `expires_at`**，应用账号直删 | `campus.internal_nonce`，有 `expires_at`，清理走受控函数 | 沿用主项目 |
| `campus_ro` / `campus_nonce_cleaner` | **POC 不存在** | 存在 | 不得从 POC 引入替代方案 |

### 6.3 依赖与许可

- RuoYi-Vue-Plus **6.0.0**（`org.dromara:ruoyi-vue-plus`，Spring Boot 4.1.0，Java 21，Sa-Token 1.45.0），vendored 入库，`backend/LICENSE` 为 MIT 原文 → **许可已核实**；
- 前端 plus-ui（`ui-react/`，`package.json` name=`plus-ui-react`）**无 LICENSE、无 `license` 字段** → 许可**未确认**（Issue #11），不作为正式依赖；
- 间接依赖（npm/Maven/Python）**未逐包审计**；
- POC `sql/01_ruoyi.sql` 为 **PostgreSQL 方言**（`int8`/`jsonb`/`comment on`/`gen_random_uuid`），主项目同为 PG 可用；若换 MySQL 需重写。

### 6.4 口径更正（重要）

POC 的 `test_slice.sh` / `test_datascope.sh` **没有 PASS/FAIL 计数器**（打印式）——此前"POC 学生 12/12"指的是 **T1–T12 段落数**，不是断言通过数；只有 `test_import_security.sh` 带计数器，其"48"为运行时计数，**无法从静态文件复算**。引用 POC 结论时按此口径表述。

---

## 7. 未验证项

- POC 仓库仅静态审读：SQL 实际可执行性、幂等性、Maven/前端构建均未验证；
- `.tmp/issues/` 是否已全部发布到 GitHub 需逐份比对后才可删除；
- 归档后相对链接需在治理 PR 内以 grep 复核（8 处来自审计时点扫描）；
- **R2 的"业务方确认无依赖"未完成**；Appsmith 的 compose 改动未提交，README 仍描述其运行中；
- 文档计数已按实际路径核对（docs 40 / 全项目 41），但归档执行后须再次以 `Get-ChildItem` 复核 14+26。
