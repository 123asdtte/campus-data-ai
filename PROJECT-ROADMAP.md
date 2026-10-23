# PROJECT-ROADMAP — 校园数据 AI 项目总路线图

- **版本**：v2.0（2026-10-23 第八次更新：main 至 `65c7fda`；23 个 PR 全部落地，含告警投递 #47 与 CI 组合校验 #46）
- **地位**：本项目唯一总路线图。安全迁移细节见 `docs/SECURITY-MIGRATION-EXECUTION-PLAN.md`（专项细化，阶段定义以本文为准）。
- **审批状态**：23 个 PR 已合并，开放 PR 为 0；正式库迁移、正式开启认证、正式流量切换**仍未批准、未执行**。
- **本轮边界**：合并后只读验收 + 开发/隔离环境准备；未改正式库、未开启认证、未切换流量。

---

## 0. 既定决策（v1.1 固化，v1.2 仅更新执行状态）

| # | 决策 | 固化内容 | v1.2 状态 |
|---|---|---|---|
| D1 | **认证架构 = RuoYi 路线** | RuoYi 负责登录/身份/权限；Java 网关为 FastAPI 生成内部签名；FastAPI 复核身份与范围。PR-B **只**接入登录 + 学生域 3 端点；保留现有 React 前端；**plus-ui-react 许可未确认前不作为正式依赖** | 不变 |
| D2 | **Appsmith 风险处置先于 PR-B** | 确认无实际业务依赖 → 停服务并保留数据卷与配置；仍需使用 → 换独立只读账号 + 负向测试证明写操作被拒。**不得为迁就功能给只读账号加写权限** | **R2 已执行并合并（PR #19）**：容器已停、服务已移出 compose、卷与 `.env` 保留；**业务方确认无依赖仍未完成** |
| D3 | **文档治理原则** | 更新现行规范、归档历史决策、**不永久删除**有审计价值的材料；每份文件唯一分类，数量与路径一一对应 | 不变；计数口径见 v1.2 §1.3 |
| D4 | **审计匿名基线** | 明确统计时间范围、分母、匿名判定规则、历史/近期区分；**不导出学生个人信息或完整业务记录** | 不变 |
| D5 | **RuoYi 与业务库隔离** | 独立数据库 `campus_gateway` + 专用账号 `gw_app`；认证框架账号对 `campus` schema 零权限；学院清单由网关随签名下发 | 不变 |
| D6 | **阶段顺序** | G → R → PR-B → PR-C → PR-D → PR-E 主流程；G 与 R 为业务开发前独立任务，各自独立提交 | 不变；R 主体已提前完成，见 §2 |

---

## 1. 项目当前状态（事实基线，2026-10-23 合并后核对）

| 项 | 状态 | 证据 |
|---|---|---|
| 主分支 | `65c7fda`（23 个 PR 已合并）；开关 `INTERNAL_AUTH_ENABLED=false` | `git log` / 容器 env |
| 规划分支 | 全部堆叠分支已合并，保留未删除 | `gh pr list` |
| 开放 PR | **0** | `gh pr list --state open` |
| 合并方式 | 逐个 merge commit；#33 为单提交，使用 squash；#39 为同事分支 merge commit | GitHub |
| 未提交改动 | 无；本地 `main` 与 `origin/main` 一致（`65c7fda`） | `git status` |
| 认证基础设施 | 已合入并验证（`internal_auth.py`、11 个 `X-Internal-*` 头、14 段 canonical、`sql/004`）；**正式库是否执行 004：未核验** | 代码 + 测试 |
| 业务路由 | 关闭态 11 业务路由 + 2 健康端点（`PUT /students` 不注册）；开启态 12 个 | `routes/*.py` |
| 正式库角色 | **未核验**（无正式库访问）；开发/测试库含 `campus_app`/`campus_ro` | 未验证 |
| 审计 | 开发库 `operation_logs` = 555+ 条（含本轮冒烟导入）；正式库计数**未核验** | 恢复演练 / 日常测试 |
| Appsmith | 已下线：服务移出 compose、容器不启动、卷 `campus_appsmith_stacks` 保留 | `docker compose config` |
| 前端 | React（`web/`），nginx 仅 `/gw/*` 反代网关；旧 `/api/*` 直连已移除 | `web/nginx.conf` |
| POC 远程 | `origin` = `campus-ruoyi-poc`；工作分支 `feat/import-api-security` @ `563e400`，工作树干净，无开放 PR | `git status` / `gh pr list` |
| 测试 | 关闭态 **195 passed / 102 skipped / 1 xfailed**；开启态 **120 passed**；权限 **11/11 PASS** | 本轮实测 |
| 上线预检 | `scripts/preflight.py` 16 项中 **2 FAIL**：TLS 入口（模板已就绪、默认入口仍为 HTTP）、默认 dev 构建的镜像配置卫生（监控已 PASS） | `python scripts/preflight.py` |
| SQL 脚本 | `001`–`006` 齐全；开发/测试库已应用 004/006，`up-main.ps1` 会在 003 后自动重放；**正式库未执行 004/006（未核验）** | `sql/` / 迁移演练 |

**核心判断**：代码与安全控制已全部合并，主线可复现验收。当前风险集中在正式环境准备：正式库迁移与恢复流程、认证开启、TLS/密钥、正式告警渠道、RuoYi 裁剪与许可审计；不再是代码合并风险。开发脚本已与统一入口对齐，监控与 TLS 模板已验证，AI 只读原型在隔离环境通过权限/审计/注入测试；新同事可按 `docs/DEVELOPMENT-ENVIRONMENT.md` 从零启动并冒烟。

### 1.1 审计匿名基线（D4 固化，历史基线）

> 下表为一期 Appsmith 阶段的历史快照；当前开发库 `operation_logs` 已增至 555 条（含后续测试与演练），不再逐项回填历史口径。

| 指标 | 值 | 说明 |
|---|---|---|
| 统计时间范围 | 2026-10-20 单日（`min(created_at)=max(created_at)=2026-10-20`） | 一期 Appsmith 阶段的验收操作 |
| 分母 | **544** 条 `operation_logs` 记录 | 全部记录，无抽样 |
| 匿名判定 | `actor_user_id IS NULL OR btrim(actor_user_id)=''` | 与一期写入路径一致（未设置会话变量） |
| 匿名 / 有主 | **504 / 40**（92.6% / 7.4%） | 有主的 40 条为手工带 `X-Actor` 的操作 |
| 按对象类型 | `student_changes` 305（匿名 300）、`students` 239（匿名 204） | 均为写入/更新路径 |
| 历史 vs 近期 | **全部为历史记录；2026-10-21 起新增 0 条** | 92.6% 反映"一期从未接入可信身份"，**不等于当前活跃缺陷比例** |

**验收指标（后续阶段引用）**：PR-B 完成后，任何**新增**业务操作必须有非空 `actor_user_id`；PR-E 验收要求"近期窗口内匿名新增 = 0"。存量历史不回填（回填属伪造审计，禁止）。

### 1.2 v1.2 核对记录（历史，已被 §1 的 v1.3 事实表取代）

1. **测试数字更正**：v1.1 写的"关闭态 130 / 开启态 97"中，开启态实际为 **88 passed**（collected 88）；`TEST-COVERAGE-MATRIX` 的"112 用例"基线是 `c28ec94`，已过时。
2. **SQL 编号冲突**：v1.1 同时把 PR-B 与 PR-C 的脚本写成 `005`。v1.2 统一为：**005 = 网关引导（PR-B）、006 = 导入范围与审计（PR-C）**。
3. **`ry_*` 残留**：`ARCHITECTURE-AND-SECURITY-PLAN.md` §4 仍写 `ry_*`，与 D1/D5 的 `sys_*` 冲突，已在本轮修正。
4. **文档计数口径**：`docs/` 实际有 **40** 份 Markdown（37 旧 + 3 新增），根目录另 1 份总路线图；治理后 `docs/` 现行 **14** 份（A5+B6+新增3）、归档 **26** 份，合计 40；全项目合计 41。v1.1 的"15/41"把根路线图算进了 `docs/`，已更正。
5. **Appsmith 卷名**：v1.1 写 `appsmith_pgdata`，实际是 `campus_appsmith_stacks`；回退命令也需先恢复服务定义再 `up`。
6. **R2 未收尾**：容器与 compose 已处理，但改动未提交、README/文档仍描述 Appsmith 在运行、"业务方确认无依赖"未核实。
7. **POC 本地滞后**：静态审读基于 `origin/main f1c2856`（正确），但本地 `main` 落后 10 个提交，后续操作前需 `git fetch`。

### 1.3 v1.4/v1.5 核对记录（2026-10-22 二次、三次合并）

本轮在原 7 个 PR 之后又合并 8 个（均经 diff 审查、CI 全绿、合并后复验）：

| PR | 内容 | 合并提交 |
|---|---|---|
| #32 | 建立 `docs/DECISION-LOG.md`（D-001~D-006） | `33df853` |
| #34 | `restore.sh` 固定重放 003→004→006，防权限回退 | `cbcc64b` |
| #33 | 孤儿 `.mapping.json` 清理脚本（同事，squash） | `f7b322d` |
| #35 | 移除 RuoYi demo 模块与示例路由 | `9ca6c1f` |
| #36 | 网关加固：JWT 外部化、Actuator 收口、非 root、`/healthz` | `4281e31` |
| #38 | `scripts/preflight.py` 只读 16 项上线预检 | `aa5ebe6` |
| #37 | `-Pprod` 排除本地配置 + 渲染/挂载生产配置 | `63ccc4d` |
| #39 | 同事：开发脚本适配 R2/PR-D、`.env` 漂移与 GBK 吞行（D-008） | `146548d` |
| #40 | 开发脚本叠加：统一入口冒烟、双模式、决策留痕（D-007/D-008） | `2263aee` |
| #41 | 前端 nginx 动态解析网关，网关重建后不再 502（D-009） | `cfeec7a` |
| #42 | 监控最小集：Prometheus + blackbox + Alertmanager（D-010） | `a1144f7` |
| #43 | TLS 入口模板与开发验证（D-011） | `c6d03d3` |
| #44 | AI 校园助手只读原型（D-012） | `762b433` |

本轮发现的真实问题与处理：

1. **恢复后权限回退**：恢复只重放 003 会让 `campus_app` 重新获得 `import_issues` 的 DELETE；改为重放 004/006 并断言 `DELETE=f`、函数数 2。
2. **JWT 密钥并非“未使用”**：移除后登录 500（`SaJwtException`），证明其参与签发；改为 `JWT_SECRET_KEY` 必填并由 compose fail-closed。
3. **prod 构建丢过滤**：自定义 `<resources>` 覆盖根 pom 后 `@profiles.active@` 未被替换；补齐 `filtering=true` 并清理增量产物后 `active: prod`。
4. **开发脚本与统一入口脱节**：`scripts/dev/*` 仍指向 Appsmith/8010，且只跑 003；已在本轮分支 `chore/dev-env-align` 全部对齐（见 D-007）。
5. **预检剩余 3 FAIL**：监控组件、TLS 入口、默认 dev 构建的镜像配置卫生；前两项属环境/运维待办，第三项用 `-Pprod` 构建可转 PASS。

---

## 2. 总览表（含状态、变更边界与依赖）

| 阶段 | 状态 | 解决的问题 | 最终成果 | 变更边界（只允许改这些） | 验收标准 | 前置依赖 | 主要风险 |
|---|---|---|---|---|---|---|---|
| **G 文档治理** | ✅ 已合并（PR #18 @ `90c34f3`） | 两套互斥认证方案并存、索引缺失、计数口径不一 | `docs/` 现行 14 + `archive/` 26；索引两节；非 archive 零废弃引用 | `docs/**`、`README.md`、`CONTRIBUTING.md`；**禁止**改代码/compose/SQL | 分类唯一且数量自洽（40=14+26）；`grep` 零命中废弃路线；链接无死链 | PR #17 批准 | `git mv` 破坏相对链接（8 处需同步） |
| **R Appsmith 处置** | ✅ 已合并（PR #19 @ `d11059a`） | `campus_app` 可写账号经 Appsmith 暴露 | R2：停服务 + 移出 compose + 保留卷/配置 | 仅 `docker-compose.yml` + 文档同步；**禁止**改数据库授权 | 容器无、端口无监听、compose 无服务、卷在；业务方确认无依赖 | 无（已完成主体） | Appsmith 账号仍在；业务方确认未完成 |
| **PR-B 学生域（含网关最小切片）** | ✅ 已合并（PR #21 @ `8ae372f`） | 无网关则签名无从产生；学生域仍是旧行为 | `auth-gateway` 服务 + `campus_gateway` 库 + 登录 + 学生 3 端点签名代理；前端学生页切登录 | 新增 `backend/`（或独立网关目录）、`sql/005`、`web/src/api/client.ts`、compose 新增服务；**禁止**触碰导入域、禁止关 8010 | 登录→网关→验签→DB→审计端到端；跨学院 403；审计 actor=登录用户；关闭态 195 项回归全绿；`gw_app` 对 `campus` 零权限 | G、R 收尾 | RuoYi 精简未实测；JVM + `sys_*` 表重量；引导凭据管理 |
| **PR-C 导入域** | ✅ 已合并（PR #22 @ `fd6e59f`） | 导入无批次范围/逐行校验/批次审计 | `created_dept_id` + 逐行学院校验 + 语句级审计触发器；解除管理员硬限制 | `sql/006`、`import-api/app/service.py`/`queries.py`、导入测试；**禁止**改网关端点/前端入口 | 跨学院导入被拒且不落库；越权读取被拒；重复提交 409；失败整体回滚；审计计数与 POC 一致 | PR-B | 正式库需执行 006（先备份）；POC 审计串设计脆弱 |
| **PR-D 正式入口** | ✅ 已合并（PR #25 @ `e45dd35`） | 8010 宿主可直连；前端多入口 | 网关补导入 7 端点；前端导入页切登录；**关闭宿主 8010 发布** | 网关 `InternalProxyController`、`web/nginx.conf`/前端、compose 端口；**禁止**改业务 SQL | ①前端经网关访问全部必需接口（学生3+聚合2+导入7）均 200；②宿主 `curl 8010` 被拒；③容器内 `campus-web`→`import-api:8000` 不受影响；④网关→内网链路正常 | PR-C | multipart 过网关内存峰值；误关容器内链路 |
| **PR-E 整体验收** | ✅ 已合并（PR #26 @ `122a0ba`） | 四项未验证项 + 正式库迁移不可逆 | 四项专项测试 + 004/005/006 迁移与回退演练 + Go/No-Go | 测试/脚本/演练报告；另附带修复验收发现的审计 actor 缺失与 nonce 周期清理两处缺口 | 无 P0/P1；回退 ≤5 分钟；近期匿名新增=0；迁移前后数据一致 | B/C/D | 演练环境与正式环境差异 |
| **H 上线准备与开发体验（阶段 5）** | 🚧 进行中 | 备份恢复、密钥、预检、生产构建、开发脚本与真实拓扑脱节、缺少可用性监控、TLS 未落地 | `restore.sh` 重放修复、JWT 外部化、Actuator 收口、非 root、预检 16 项、`-Pprod` 配置卫生、开发脚本对齐、nginx 动态 DNS、监控最小集、TLS 模板与开发验证 | `scripts/**`、`gateway/**`（仅加固）、`docker-compose*.yml`、`monitoring/**`、`web/**`（仅入口配置）、`.env.example`、`docs/**`；**禁止**正式库迁移/认证开启/流量切换 | 恢复后 `DELETE=f`；缺失 JWT 即失败；预检除环境项外全 PASS；新同事按文档可启动并冒烟；监控目标全 up 且告警可触发/解除；TLS 链路 `FAIL=0` | PR-E | 正式库与演练环境差异；正式证书/告警渠道未就绪 |
| **I AI 校园助手原型（阶段 7）** | ✅ 已合并（#44 @ `762b433`） | 需要验证 AI 问答的权限、只读、脱敏、审计与注入边界 | 独立库/网络 + 虚构数据 + 固定意图 + 双角色最小权限 + fail-closed 审计 + 可选 LLM planner | `ai-assistant/**`、`docker-compose.ai-poc.yml`、`.env.example`、`docs/AI-ASSISTANT-POC.md`；**禁止**连接主业务库、禁止真实数据、禁止默认外发模型 | 跨学院 403；只读账号无法写入；检索不含联系方式；审计含认证失败/拒绝记录；注入不导出明细；15 项自动化测试通过 | 无（独立于主栈） | POC token 非正式认证；规则意图有限；真实数据/外部模型未接入 |

> **对原 PR-B/C/D/E 的调整声明**（不静默扩范围）：
> 1. **PR-B 吸收"网关最小切片"**：无网关则签名无从产生，只能停在测试桩；因此网关**提前并缩小**（仅登录 + 学生 3 端点），原 PR-D 剩余部分（导入接入 + 前端导入页 + 关 8010）保持为 PR-D。
> 2. **G 与 R 为业务开发前的独立任务**；R 主体已执行，文档同步并入 G，避免同一文件双改。
> 3. **PR-C 内容不变**；**PR-E 增加**四项专项测试（并发写、审计差异、大文件内存、nonce 增长）。

---

## 3. 阶段详解

### 3.1 G — 文档治理

**目标**：把 26 份历史文档移入 `docs/archive/`，更新 6 份 B 类和根 2 份，重建索引，使活跃文档与 `d10946f` 一致。

**为什么**：两套互斥认证方案（pwdlib+PyCasbin vs 现行网关签名）同时存在；`004_auth.sql` 与 `004_internal_auth.sql` 编号撞车；README 仍指向已废弃路线。后续 AI/新人从旧文档出发会做错实现。

**具体实现**：
1. `git mv` 26 份 C 类 → `docs/archive/`（文件名不变）；
2. 3 份加"已被取代"头注（`SECURITY-AUTH-ROADMAP`、`SECURITY-AUTH-DECISION`、`RUOYI-PLUS-EVALUATION`）；
3. 更新 6 份 B 类 + `README.md` 7 处 + `CONTRIBUTING.md` 2 处；
4. 重建 `docs/README.md` 两节索引；
5. 修复 8 处相对链接。

**变更边界**：仅文档文件；禁止改代码、compose、SQL、数据库。

**测试命令**：
```bash
grep -rn "SECURITY-AUTH-ROADMAP\|poc_auth.py\|004_internal_nonce\|ry_\*" docs README.md \
  --exclude-dir=archive   # 必须零命中
```
**验收**：`docs/` 40 = 现行 14 + archive 26；每份文件唯一分类；索引覆盖 100%；无死链。

**回退**：`git revert` 整个治理提交；`archive/` 移回原位。

**风险**：`git mv` 破坏外部链接；需在 PR 描述列重定向说明。

### 3.2 R — Appsmith 风险处置（R2 已执行）

**目标**：消除"低代码平台持可写账号直连业务库"这一攻击面。

**为什么**：`campus_app` 可写账号经 Appsmith 暴露，是绕过 FastAPI 校验与审计的最短路径。

**已完成（2026-10-22）**：
- `docker compose stop appsmith` → 容器 `campus-appsmith` Exited (137)；
- 从 `docker-compose.yml` 移除 `appsmith` 服务（-33 行），保留顶层 `appsmith_stacks` 卷声明并注释；
- 8081/8443 已无监听；卷 `campus_appsmith_stacks` 仍在；`.env` 中 `APPSMITH_*` 配置未删；
- `docker compose config` 校验通过，主栈仅 `campus-db`、`campus-import-api`，均 healthy。

**待收尾**：
1. 提交 compose 改动（建议独立提交 `chore(infra): 下线 Appsmith（R2）`）；
2. 业务方确认无 Appsmith 页面依赖（验收项，未完成）；
3. README/docs 中 Appsmith 运行描述并入 G 统一更新；
4. 数据库侧 `campus_app` 账号仍存在——停服务已阻断暴露路径，但账号收敛留待 PR-B 的 `gw_app`/最小账号治理，不在 R 阶段扩大范围。

**变更边界**：仅 `docker-compose.yml` 与文档；**禁止**改数据库授权、删除数据卷。

**验收**：`docker ps -a` 无运行中的 appsmith；`Get-NetTCPConnection -LocalPort 8081,8443` 无监听；卷存在；业务方书面确认。

**回退**：把已删除的服务定义原样加回 `docker-compose.yml`，再 `docker compose up -d appsmith`（卷 `campus_appsmith_stacks` 与 `.env` 未动，数据不丢）。

**风险**：若存在未识别的页面依赖，停服务会破坏使用（须先确认）；账号仍可被其他进程使用（属 PR-B 账号治理）。

### 3.3 PR-B — 学生域（含网关最小切片）

**目标**：让"登录会话 → 网关签名 → FastAPI 验签 → 数据范围 → 审计"在**主项目**跑通，且只覆盖学生域。

**为什么**：PR-A 只提供验签能力，没有签名产生者；学生域要可信必须有登录、权限点与学院声明。

**具体实现**：
- 独立数据库 `campus_gateway` + 专用账号 `gw_app`（仅 `sys_*` 表读写；对 `campus` schema 零权限）；
- `sql/005_gateway_bootstrap.sql`：`sys_*` 必要子集（PG 方言，取自 POC `sql/01_ruoyi.sql`）、管理员、`student:list/write` 权限点、学院角色；
- 网关端点：`POST /auth/login`、`GET /poc-proxy/students`、`GET /poc-proxy/students/{no}`、`PUT /poc-proxy/students/{no}`；
- 前端学生页改登录会话，移除 `X-Actor`；
- 移植 POC `PocProxyController` 的 14 段 canonical（零改动）、头名 `X-Poc-*`→`X-Internal-*`（11 个）、权限点 `poc:student:*`→`student:*`、配置键 `poc.hmac-secret`→`INTERNAL_HMAC_SECRET`、nonce 沿用主项目 `internal_nonce`。

**变更边界**：新增网关代码/服务、`sql/005`、`web/src/api/client.ts`、compose 新增服务；**禁止**改导入域、禁止关闭 8010、禁止改正式库。

**测试命令**：
```bash
mvn -pl ruoyi-admin test -Dtest=InternalAuthGoldenVectorTest   # 必须复现金标向量
curl -X POST <gw>/auth/login ... && curl -H "Authorization: Bearer <token>" <gw>/poc-proxy/students
INTERNAL_AUTH_ENABLED=true pytest tests/test_internal_auth.py tests/test_route_matrix.py
```
**验收**：① 登录取 token；② 网关签名被 FastAPI 验签通过；③ 跨学院详情/修改 403；④ 审计 `actor_user_id` = 登录用户且新增匿名=0；⑤ 关闭态 195 项回归全绿；⑥ `gw_app` 对 `campus` schema 零权限（DB 断言）。

**回退**：compose 移除 `auth-gateway`；前端回到 `/api` 直连（改动集中在 `web/src/api/client.ts`）。

**风险**：RuoYi 精简裁剪未实测（PR-B 第一周验证项）；POC 用 `sys_dept` 直查学院清单，在独立库下不可达 → **网关随签名下发学院集合**（必须改）。

### 3.4 PR-C — 导入域

**目标**：导入具备批次归属、逐行学院校验、批次/异常表审计，解除管理员硬限制。

**为什么**：导入是唯一批量写学生数据的入口，当前 `IMPORT_ADMIN_ONLY=True` 只是临时措施。

**具体实现**：
- `sql/006_import_scope.sql`：`import_batches.created_dept_id` + 索引；`import_batches` 行级审计触发器（每次状态跃迁一行）；`import_issues` 采用 **方案 C**——不逐行审计，改由 `clear_import_issues()` / `record_import_issues()` 写 JSON 摘要，并收回 `campus_app` 的 DELETE（删除只能经受控函数）；
- `service.create_batch(created_dept_id=)`、`commit_batch(allowed_colleges=)`、`list_batches(dept_id=)`、`_assert_batch_scope()`；
- 批次范围：详情 / 字段映射 / 校验 / 提交均校验批次归属部门；历史 `created_dept_id IS NULL` 的批次仅管理员可见；
- `commit` 逐行学院校验：**任一有效行学院不在授权范围内即整批拒绝（403），不写入任何学生数据**；
- 解除 `IMPORT_ADMIN_ONLY`，改为权限点 + 批次范围 + 逐行校验；
- 相关安全用例：`tests/test_import_scope.py`（8 项）+ `tests/test_import_audit_summary.py`（3 项审计摘要/删除收口）。

**变更边界**：`sql/006`、`import-api/app/service.py`/`routes/imports.py`/`internal_auth.py`、导入测试；**禁止**改网关端点、前端入口、关闭 8010。

**测试命令**：
```bash
INTERNAL_AUTH_ENABLED=true pytest tests/test_import_scope.py tests/test_import_audit_summary.py tests/test_db_privileges.py
python -m pytest                                               # 关闭态全量
```
**验收**：跨学院导入被拒且不落库；越权读取被拒；重复提交 409；失败整体回滚；异常明细每次重写只写摘要、无逐行噪声；直接 DELETE 被拒绝；历史 NULL 批次仅管理员可见。

**实施结果（2026-10-22）**：代码与测试完成；关闭态全量为新增用例后的全量通过；开启态专项 `120 passed`；006 仅在测试库与演练库执行，正式库未执行。审计方案已按同事 Issue #10 设计（`docs/IMPORT-AUDIT-DESIGN.md`）收敛为方案 C。

**回退**：开关关闭 + `git revert`；正式库迁移前必须 `pg_dump`。

**风险**：POC `import_audit_trail` 用逗号串 + 正则匹配，设计脆弱 → 移植改为关联表或精确 `bigint[]`；006 需在正式库执行（人工审批）。

### 3.5 PR-D — 正式入口

**目标**：前端所有业务流量统一经网关，关闭宿主 8010 直连，形成正式网络边界。

**为什么**：只要 8010 对宿主发布且前端直连，导入路径就有绕网关的口子。

**具体实现（已完成）**：
- 网关补 **导入 7 端点 + 聚合 2 端点**：`/internal/proxy/imports*`、`/meta/filters`、`/stats/overview`；multipart 签名覆盖文件 SHA-256 + 非文件字段规范化串；
- 前端 `students.ts`/`imports.ts`/`home.ts` 全部改走 `requestGateway`；新增登录守卫（未登录跳 `/login`）；
- 移除 nginx `/api/` 反代与 Vite `/api` 代理，浏览器只保留 `/gw/` 入口；
- 移除 compose 中 `127.0.0.1:8010:8000` 发布；`import-api` 仅容器内网；
- `sql/005` 增加导入域 6 个权限点并授予 `college_scope` 角色（仅网关库）。

**变更边界**：网关控制器、`web/` 前端与 nginx、compose 端口、`sql/005` 权限种子；**禁止**改业务 SQL/数据范围模型。

**验收（D5 前置条件，顺序不可颠倒）**：
1. **先证明**：前端经网关访问**全部必需接口**（学生 3 + 聚合 2 + 导入 7）均 200；
2. 再移除宿主 8010 发布；
3. 关闭后 `curl 127.0.0.1:8010` **连接被拒**；
4. **容器内通信未受影响**：`campus-web` → `import-api:8000` 仍 200，healthcheck healthy；
5. 网关 → import-api 内网签名链路正常。

**实施结果（2026-10-22）**：
- 开启态（`INTERNAL_AUTH_ENABLED=true`）真实登录 + 网关签名 E2E：**26 项全部 PASS**（含 multipart 预览、validate、commit、跨学院 403、混合学院整批拒绝零写入、审计 actor=`ry:college_a`、未签名/伪造头 401）；
- 浏览器 UI：登录 → 学生列表（236 条）→ 导入页 → 按批次号恢复 → 退出，7 步全 PASS，控制台无错误；
- 关闭宿主 8010 后：`127.0.0.1:8010` 连接失败 `000`；容器内 `import-api:8000/health`=200；网关学生/导入/总览均 200；`docker compose config -q` 通过；
- 验证后开发栈已恢复 `INTERNAL_AUTH_ENABLED=false`。

**测试命令**：
```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/health    # 期望 000（连接失败）
docker exec campus-web curl -s -o /dev/null -w "%{http_code}" http://import-api:8000/health  # 期望 200
```
**回退**：恢复 compose 端口发布 + 前端切回直连（需同时恢复 nginx `/api` 与 `X-Actor` 路径）。

**风险**：multipart 经网关内存峰值（`getBytes()` 全量读入）→ PR-E 压测项。**已知未验证**：网关进程在超大文件（接近 10MB）下的堆占用。

### 3.6 PR-E — 整体验收

**目标**：把四项未验证项与正式库迁移做成可复现证据，给出 Go/No-Go。

**为什么**：正式库迁移不可逆，必须有演练证据。

**具体实现（已完成）**：① PUT 并发写竞态；② 审计多写不丢失；③ 大文件（接近 10MB）内存与耗时；④ nonce 增长、周期清理与回退；⑤ 004/005/006 在一次性隔离库执行升级与回退演练（正式库未执行）；⑥ 开关开启/关闭全量回归；⑦ Go/No-Go 报告。

**变更边界**：测试脚本、演练报告、迁移/回退脚本；**附带修复**验收中发现的审计 actor 缺失与 nonce 周期清理缺口。

**验收（v1.3 在 main @ `122a0ba` 复测）**：
- 关闭态 **195 passed / 102 skipped / 1 xfailed**；开启态安全用例 **120 passed**；PR-E 专项 11 项 PASS；
- 迁移/回退演练 **12 步全 PASS，5.34s**（PR-E 首次为 1.99s）；
- 近期匿名审计新增：修复后 **0**（修复前 1 条清理事务记录，未回填历史）；
- 9MB 预览 0.30–0.44s；1000 行提交 2.08–2.64s；网关 +12.7MiB、Import API +61MiB 峰值；
- 详细证据见 `docs/PR-E-ACCEPTANCE-REPORT.md`。

**回退**：DDL 回退脚本（004/005/006 均附）；开关关闭；镜像回退到演练通过的 tag。

**风险**：演练环境与正式环境差异 → 用同镜像同 compose。

---

## 4. 串行 / 并行安排（v1.2 按实际状态调整）

| 工作 | 关系 | 说明 |
|---|---|---|
| G 文档治理 | 串行在 PR-B 之前 | 避免后续 PR 基于旧文档；同时承接 R 的 README/文档同步 |
| R 收尾 | 与 G **可并行**（不同文件：R 只提交 compose，G 改文档） | R 主体已完成；**不与业务 PR 混在一个提交** |
| PR-B → PR-C → PR-D | **严格串行** | 权限点、范围模型、入口逐层依赖 |
| 同事线（Issue #3 Docker / #8 测试覆盖） | 与 PR-B 可并行 | 边界：不改同一 compose 段、不改 `sql/` 授权脚本 |
| PR-E 专项测试 | 依赖 B/C/D 全部完成 | 不可提前 |

**阶段停止条件（v1.2 明确）**：
1. 某阶段验收不过 → 停留在该阶段修复，**不进入下一阶段**；
2. 同一阶段连续两次修复仍不过 → 回到前一阶段重新评估依赖；
3. 涉及授权模型、正式库、密钥、正式入口 → **立即停止并汇报**（见 §7）；
4. 发现影响数据安全的根本设计问题 → 停止，不"带病推进"；
5. 任何"顺手改动"超出本阶段变更边界 → 拆出独立任务，不混入当前 PR。

---

## 5. POC 仓库审查结论（动用 POC 代码前必读）

来源：只读审查 `campus-ruoyi-poc` **origin/main `f1c2856`**（PR #3 合并）；明细见 `docs/DOCUMENTATION-AUDIT.md` §6。注意：本地 `main` 落后 origin 10 个提交，操作前先 `git fetch`。

| 分类 | 内容 |
|---|---|
| **零改动可复制** | 14 段 canonical 构造与段序、`pct`/`normalize`、`sha256`/`hmacHex`、multipart 签名策略、`Who`/`require_perm`/`require_college` 骨架、RestClient 转发与错误透传、`LoginHelper` API（v6.0.0 确认存在） |
| **必须改写** | 头名 `X-Poc-*`→`X-Internal-*`（11 个）；权限点 `poc:student:*`→`student:*`；配置键 `poc.hmac-secret`→`INTERNAL_HMAC_SECRET`；nonce 沿用主项目 `internal_nonce`+`cleanup_internal_nonce()`；admin 严格布尔；补 nonce/ts/dept 格式与长度校验、密钥 ≥32 校验 |
| **禁止移植** | `sql/06` 的 `campus.poc_nonce`（含 `GRANT DELETE`）；`sql/07:196` 的 `GRANT SELECT ON sys_dept TO campus_app`；`sql/08` 复制 admin 密码建用户；`poc-api` 服务与 `--poc.api-base`；`.env.poc`（磁盘含明文密钥） |
| **POC 文档已过时** | `VERSIONS.md` 的"5 处/3 处定制"与 PR #3 实际 diff 不符；POC `README.md` 写"sql/01–06"实为 01–08，测试脚本清单漏 `test_import_security.sh` |

**口径更正（重要）**：POC 的 `test_slice.sh` / `test_datascope.sh` **没有 PASS/FAIL 计数器**（打印式脚本）——"POC 学生 12/12"指 **T1–T12 段落数**，不是断言通过数；只有 `test_import_security.sh` 有计数器，其"48"为运行时计数，无法从静态文件复算。

**许可结论（THIRD-PARTY-NOTICES 实查）**：
- RuoYi-Vue-Plus v6.0.0：**MIT 已核实**（`backend/LICENSE` 保留上游原文）；
- plus-ui `6.X-React` @ `25e69f1`：分支根目录**无 LICENSE**、`package.json` **无 license 字段** → **许可未确认**（Issue #11），**不作为正式依赖**；
- npm/Maven/Python 间接依赖**未逐包审计**。

---

## 6. 未验证项、依赖与风险（v1.3 合并后更新）

### 6.1 未验证（不得当作已成立）
1. **Appsmith 的“业务方确认无依赖”仍未完成**；容器/端口/compose/卷已按 R2 处理并合并。
2. **正式库是否执行 004/006 未核验**（无正式库访问）；开发/测试库已执行并通过演练。
3. **RuoYi 精简裁剪可行性未实测**：当前 `ruoyi-admin` 仍包含 demo、job、ai、workflow、mail/social、mcp、admin-client 等模块。
4. **真实规模备份恢复未验证**：已完成开发规模（0.03MB）恢复演练；生产数据量与备份频率/保留策略未定。
5. **TLS/域名/监控告警未就绪**；生产拓扑未确定。
6. plus-ui 许可未确认（不作为本仓库生产依赖）；npm/Maven/Python **间接依赖未逐包审计**。
7. POC 仓库仅做状态核验（分支/工作树/开放 PR），其构建与 SQL 可执行性未在本次复验。
8. 负载结论仅覆盖开发环境 180s/3rps 只读基线，**不能外推生产容量**。

### 6.2 外部依赖
- GitHub（仓库/PR/CI）可用；`gh` 已认证；
- Docker Desktop、PostgreSQL 16.15、JDK 21、Node/pnpm（仅 POC 构建）；
- 正式库迁移与认证开关依赖人工审批窗口。

### 6.3 风险清单
| 风险 | 影响 | 缓解 |
|---|---|---|
| Appsmith 页面仍被业务使用 | 停服务破坏流程 | 收尾前完成业务方确认；保留卷可快速恢复 |
| `campus_app` 账号仍可写 | 其他进程仍可绕过 | PR-B 账号治理；不在 R 阶段扩大授权 |
| 网关引入 JVM + `sys_*` 表 | 资源与运维复杂度 | 独立库 + 专用账号 + 仅必要端点；PR-B 首周裁剪验证 |
| 导入 005/006 在正式库执行 | 不可逆 | 先 `pg_dump`；附回退脚本；PR-E 演练 |
| multipart 过网关内存峰值 | OOM | PR-E 压测；必要时流式转发 |
| 文档双轨 | 新人/AI 从废弃路线出发 | G 一次性治理；grep 验收 |

---

## 7. 自主执行 vs 人工审批（承接 `docs/EXECUTION-PROTOCOL.md` §6）

### 7.1 AI 可自主连续完成
- 代码实现、测试编写与修复、规划/文档同步；
- 测试库/隔离环境建库、迁移演练、重建容器（**开关保持关闭**）；
- PR 创建与推送、Issue 评论、依赖安装；
- 规划文档修订（本 Goal 已执行）。

### 7.2 必须人工批准（不可自动）
- 合并任何 PR（含文档 PR）；
- 对**正式库**执行任何 SQL（004/005/006）；
- 开启 `INTERNAL_AUTH_ENABLED` 或修改正式 compose 的开关/密钥；
- 切换正式入口（关 8010、改 nginx 上游）；
- 扩大授权（新增角色/权限点/跨学院名单）；
- 采用第三方组件为生产依赖（如 plus-ui，许可未决）；
- 删除数据库卷、业务数据、测试数据或验收证据；
- 接入真实学生数据。

### 7.3 必须暂停并汇报
- 发现影响数据安全的根本设计问题；
- 回退演练失败；
- 外部系统（GitHub/POC 仓库）不可达导致验证缺口；
- 需要越出已批准的文件范围。

> **Goal 1 特别约束**：本轮只核对规划；不执行 G、R 收尾或 PR-B；不提交、不合并；不改业务代码/部署配置/数据库。

---

## 8. PR #17 最终修改清单（v1.2 核对结果）

PR #17 当前 head `3a2efda`，包含 6 个文件。以下是**需要追加到 PR #17** 的修改（本 Goal 只改规划文档，不提交）：

| 文件 | 必改点 |
|---|---|
| `PROJECT-ROADMAP.md` | 本文件 v1.2 全文：事实基线、R 状态、测试 130/88、SQL 005/006、文档计数、停止条件、自主执行边界、PR #17 清单 |
| `docs/ARCHITECTURE-AND-SECURITY-PLAN.md` | 拓扑/组件表更新 Appsmith 已停；安全边界 #8/#12 去重；§4 `ry_*`→`sys_*`、005 网关 / 006 导入；§5 测试数字改 CI 实查（130/88）；§7 未验证声明 |
| `docs/DOCUMENTATION-AUDIT.md` | §1.2 计数口径改为 docs 40 = 14 + 26、全项目 41；补充 PR #17 已含 4 份新增；README 的 Appsmith 7 处纳入 G 更新范围 |
| `docs/SECURITY-MIGRATION-EXECUTION-PLAN.md` | 阶段 1 验收数字 112→130/88；阶段 2 补"网关最小切片 + 005"；阶段 4 范围改为"导入 7 端点 + 前端 + 关 8010" |
| `README.md`（后续 G 阶段，不在本 PR） | 行 39/99/123/151/179/308/322 的 Appsmith 描述；行 173/182 重复的 6.3 编号；行 222 测试表补双模式与实际数字；行 77/86 废弃路线引用 |
| `CONTRIBUTING.md`（后续 G 阶段） | 行 82-84"没有单元测试目录"过时；分支前缀统一 `feat/` |

**PR #17 本轮不改代码的原因**：它只交付阶段 0 规划；compose 的 R2 改动应作为**另一个独立提交**，避免规划 PR 混入部署变更。

---

## 9. 本轮核对证据索引

| 事实 | 证据位置 |
|---|---|
| Git 状态与未提交改动 | `git status`（合并后工作树干净，`main @ 122a0ba`） |
| PR 合并与 CI | GitHub PR #17/#18/#19/#21/#22/#25/#26；main CI success（122a0ba） |
| 测试实际数字（v1.3 实测） | 关闭态 195 passed / 102 skipped / 1 xfailed；开启态 120 passed |
| Appsmith 下线 | `docker ps -a`（Exited 137）、端口无监听、`docker volume ls`、compose 无服务 |
| 认证契约 | `import-api/app/internal_auth.py`（14 段 canonical、11 头） |
| 路由数量 | `import-api/app/routes/*.py` 装饰器（11 业务 + 2 健康，开启态 +PUT） |
| SQL 现状 | `sql/` 001–006 齐全；004/006 幂等与回退演练 12 步 PASS |
| 备份恢复演练 | 隔离实例恢复 0.41s；表计数一致；恢复库测试 9 passed / 1 skipped |
| POC 审查基线 | `campus-ruoyi-poc` 工作树干净，`feat/import-api-security @ 563e400`，无开放 PR |
| 文档计数 | `docs/` 现行 17 + archive 26 = 43 |
