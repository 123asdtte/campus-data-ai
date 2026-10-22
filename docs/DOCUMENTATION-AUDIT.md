# 文档审计与治理方案（DOCUMENTATION AUDIT）

- **版本**：v1（2026-10-22，阶段 0 产出）
- **方法**：逐文件阅读 + 交叉引用 grep + 与 main `d10946f` 代码/CI/部署现状比对；不按文件名或日期判断。
- **边界**：本轮**不执行**归档/删除；获批后按 §5 一次性实施。
- **范围**：`docs/` 37 份 + 根 `README.md`/`CONTRIBUTING.md` + 未跟踪 `.tmp/`。POC 仓库文档未审计（未验证项）。

---

## 1. 统计

| 类别 | 数量 | 含义 |
|---|---|---|
| A 当前权威 | 4 | 后续开发必须遵循 |
| B 需更新 | 7 | 主体有效，存在与现状不符的具体段落 |
| C 归档 | 26 | 已完成/被取代阶段的历史证据 → `docs/archive/` |
| D 删除 | 0 | 无；全部历史文档有审计或决策价值 |
| 未跟踪 `.tmp/` | 10 | 本地临时产物 → 核对后清空 |

新增 4 份（本次产出）：`PROJECT-ROADMAP.md`（根）、`docs/ARCHITECTURE-AND-SECURITY-PLAN.md`、`docs/EXECUTION-PROTOCOL.md`、本文件。

---

## 2. 逐文件判定

### A 类（保留原样，4）

| 文件 | 主题 | 理由 |
|---|---|---|
| `ADR-001-import-mapping.md` | 表头映射采用规则而非大模型的决策记录 | 决策对象未被 PR #16 改动，仍是约束依据 |
| `DATA-DICTIONARY.md` | 业务表字段/枚举/审计字段字典 | 表结构未变，PR-B/C 开发现行依据 |
| `INTERNAL-AUTH-SPEC.md` | 内部认证规范（14 段、11 头、金标向量） | PR-D 唯一权威契约；仅状态行"实施中"过时 → 改"已随 PR #16 合并" |
| `TEST-COVERAGE-MATRIX.md` | 112 用例覆盖矩阵与缺口清单 | 缺口分析仍有效；需更新基线并补"安全/权限"覆盖层（见 B 类动作） |

### B 类（更新，7）

| 文件 | 需更新的要点 |
|---|---|
| `API-MIGRATION-INVENTORY.md` | 头部注明基线 5b5d0dc；标记 §5 已由 PR-A 完成的项；§8 环境快照标失效 |
| `DOCKER-ENV-AUDIT.md` | §3 "CI 无 pytest" 已过时；§4.2 POC 已升独立仓库；P0 建议标完成；补入索引 |
| `GIT-WORKFLOW.md` | 删"允许直接提交 main"；分支前缀统一 `feat/`；type 表补 perf（与 CONTRIBUTING 对齐） |
| `IMPORT-API.md` | §3.7 `/health` 旧响应与新契约矛盾 → 更新为 `{status}` 并补 `/health/ready`；§2 身份说明改双模式 |
| `SECURITY-CHECKLIST.md` | §2/§3 补关闭态/开启态两种语境；登记 Appsmith 可写账号为未解决风险 |
| `docs/README.md`（索引） | 补收 4 个未收录文件；"认证尚未实施"改为"基础设施已合并、业务接入未开始"；归档后重建两节结构 |
| 根 `README.md` | 7 处：行 77"未实现"、行 86 指向已废弃 ROADMAP、行 127 缺 004、行 173/182 编号重复、行 222 测试表缺 5 文件与双模式、行 278 X-Actor 表述、POC 措辞（行 48/53）；行 322 Appsmith 风险保留 |

### C 类（移入 `docs/archive/`，26）

> 全部有历史/审计/决策价值，**不删除**。归档时同步修正引用（§4）。

| 组 | 文件 |
|---|---|
| 一期 Appsmith 阶段（8） | `PRD.md`、`APPSMITH-SETUP.md`、`TEST-PLAN.md`、`BUILD-LOG.md`、`PHASE0-ENV-CHECK.md`、`REACT-MIGRATION-PLAN.md`、`REACT-TEST-REPORT.md`、`DEPLOY-WEB-PLAN.md` |
| 一期验收（1） | `DEPLOY-ACCEPTANCE-1.3.md` |
| 轻量认证路线（被取代，4） | `SECURITY-AUTH-ROADMAP.md`、`SECURITY-AUTH-DESIGN.md`、`SECURITY-AUTH-DECISION.md`、`SECURITY-AUTH-ROADMAP` 相关的 `RUOYI-PLUS-EVALUATION.md` |
| RuoYi 评估与 POC 方案（4） | `RUOYI-PLUS-MIGRATION-PLAN.md`、`POC-SHARING-PLAN.md`、`POC-FRESH-CLONE-REPORT.md`、`RUOYI-POC-GO-NOGO.md` |
| POC 执行记录（4） | `RUOYI-POC-AUTH-RESULTS.md`、`RUOYI-POC-DATA-PERMISSION.md`、`RUOYI-POC-STUDENT-SLICE.md`、`POC-IMPORT-API-PR3-REVIEW.md` |
| 已被 PR #16 取代的计划（3） | `RUOYI-S1S3-MERGE-PLAN.md`、`IMPORT-API-SECURITY-PLAN.md`、`IMPORT-API-SECURITY-INVENTORY.md` |
| 已合并 PR 的审查（1） | `PR16-PRE-MERGE-REVIEW.md` |
| 实测记录（1） | `IMPORT-MAPPING-TEST.md` |

关键归档理由（抽查）：
- `SECURITY-AUTH-ROADMAP`：其 `sql/004_auth.sql` 编号与实际 `004_internal_auth.sql` 撞车、内容完全不同，且 README §3.1 仍把当"实施路线"引用——**是最危险的失效引用**；
- `SECURITY-AUTH-DECISION`：核心结论（不迁移若依）已被条件性 Go 推翻，仅作"为什么改向"档案，归档时头部加一行取代说明；
- `RUOYI-PLUS-EVALUATION`：其"plus-ui MIT 没问题"的结论早于 Issue #11，归档后不得再作许可背书引用；
- `RUOYI-S1S3-MERGE-PLAN`：文件名（`poc_auth.py`、`004_internal_nonce.sql`）与实际实现（`internal_auth.py`、`004_internal_auth.sql`）不一致，保留正文会双轨。

### D 类（删除，0）

docs/ 内无。未跟踪 `.tmp/` 见 §6。

---

## 3. 跨文档矛盾（10 条，归档后 1–4、6–10 自动消除，5 由 B 类更新消除）

| # | 冲突 | 处置 |
|---|---|---|
| 1 | GIT-WORKFLOW"允许直接提交 main" vs CONTRIBUTING"main 只接受 PR" | B 类更新统一 |
| 2 | 分支前缀 `feat/` vs `feature/` | 统一 `feat/` |
| 3 | ROADMAP(P0-P5 pwdlib+Casbin) vs INTERNAL-AUTH-SPEC（网关签名） | ROADMAP 归档 |
| 4 | SECURITY-AUTH-DECISION"不迁移若依" vs 条件性 Go | 归档 + 取代说明 |
| 5 | IMPORT-API.md §3.7 vs §9 的 /health 契约 | B 类更新 |
| 6 | S1S3 计划文件名 vs 实际实现名 | S1S3 归档 |
| 7 | "12/7 接口全部无认证" vs "11 路由开启态已验签" | 旧文档标基线 |
| 8 | DOCKER-ENV-AUDIT"CI 无 pytest" vs 现状 | B 类更新 |
| 9 | 7 段 canonical（旧）vs 14 段（现行） | 旧文档归档 + SPEC 声明唯一性 |
| 10 | RUOYI-PLUS-EVALUATION 许可背书 vs Issue #11 | 归档 + 不得引用为背书 |

失效引用：`SECURITY-AUTH-ROADMAP` 引用不存在的 `sql/004_auth.sql`/`auth/*`/`LoginPage.tsx`；`S1S3-MERGE-PLAN` 引用不存在的 `poc_auth.py`/`004_internal_nonce.sql`；`IMPORT-API.md §3.7` 旧 `/health` 字段；`APPSMITH-SETUP` 的 `X-Actor` 注入在开启态无效。归档后仅存在于 archive 内部，不再被现行文档引用。

索引缺口：`TEST-COVERAGE-MATRIX`、`PR16-PRE-MERGE-REVIEW`、`DOCKER-ENV-AUDIT`、`POC-SHARING-PLAN` 未被 `docs/README.md` 收录 → 治理 PR 补齐（归档类移入 archive 节）。

---

## 4. `.tmp/`（未跟踪，10 个文件）

| 文件 | 处置 |
|---|---|
| `comment-1/3/9/12.md`（评论草稿，结论已入正式文档） | 删除 |
| `issues/*.md`（Issue 草稿） | 与线上 Issue 逐份比对：已发布即删；`issue-license.md` 确认无未发布内容后删 |
| `patch_test.py`、`prev.json`、`t2.json`、`u.txt`、`uploads.txt` | 删除 |

均为本地未跟踪文件，不涉及 Git 历史。

---

## 5. 治理实施方案（获批后一个 PR 完成）

**PR**：`docs/governance-stage0`，单 PR、多 commit：

1. `git mv` 26 份 C 类 → `docs/archive/`（保持文件名不变）；
2. C 类中 3 份加"已被取代"头注（`SECURITY-AUTH-ROADMAP`、`SECURITY-AUTH-DECISION`、`RUOYI-PLUS-EVALUATION`）；
3. 修复 7 份 B 类（§2 列表）；
4. 新增 4 份交付文档（本阶段产物）；
5. 重建 `docs/README.md`：两节结构（**现行规范** / `archive/`（历史，仅追溯）），收录全部现存文件；
6. 修复归档造成的相对链接（涉及 `README.md`、`docs/README.md`、`docs/SECURITY-AUTH-DESIGN.md` 等 8 处引用，逐一 `grep -rn "docs/<file>"` 核对）；
7. 校验：`grep -rn "SECURITY-AUTH-ROADMAP\|poc_auth.py\|004_internal_nonce" README.md docs/*.md import-api web` 在**非 archive 文件**中零命中。

**影响评估**：
- 移动 26 个文件会破坏其相对路径引用——已盘点 8 处外部引用需同步改（清单见 §2 各行 referenced 列）；
- 不删除任何文件，`git revert` 即可整体回退；
- 对 CI 无影响（CI 不读取 docs/）。

**治理后结构**：

```
PROJECT-ROADMAP.md            ← 总路线图（根）
README.md / CONTRIBUTING.md   ← 修正后
docs/
  README.md                   ← 索引：现行规范 / archive/
  ARCHITECTURE-AND-SECURITY-PLAN.md
  EXECUTION-PROTOCOL.md
  DOCUMENTATION-AUDIT.md（本文件，治理后转为"维护记录"）
  INTERNAL-AUTH-SPEC.md  IMPORT-API.md  DATA-DICTIONARY.md
  TEST-COVERAGE-MATRIX.md  SECURITY-CHECKLIST.md  ADR-001-import-mapping.md
  API-MIGRATION-INVENTORY.md  DOCKER-ENV-AUDIT.md  GIT-WORKFLOW.md
  archive/                    ← 26 份历史文档
```

**收益**：① 活跃文档从 37 → 11+4，且全部与 `d10946f` 现状一致；② 两套互斥认证方案不再并存于正文；③ 每个阶段的验收证据在 `archive/` 可查；④ 索引覆盖 100% 现存文件，AI 与新人不会再从废弃路线出发。

---

## 6. 未验证项

- POC 仓库（campus-ruoyi-poc）内的文档未纳入本轮审计；
- `.tmp/issues/` 是否已全部发布到 GitHub 需逐份比对后才可删除；
- 归档后相对链接需在 PR 内以 grep 复核，本文件列出的 8 处来自审计时点的引用扫描。
