# 工程决策日志（DECISION LOG）

- **地位**：本项目工程决策的唯一索引。影响架构、数据、权限、API 兼容性、迁移或发布策略的决定必须在此登记。
- **维护规则**：
  1. 先记录方案与预期结果，再实施；实施后补充实际结果、偏差与风险。
  2. 状态只使用 `Proposed / Accepted / Implemented / Verified / Superseded / Rejected`。
  3. 自主决策标记 `Decision owner: AI`；只有实际获得人工授权才标记 `Decision owner: User-approved`。
  4. 同一主题只保留一条主记录，更新时覆盖旧结论并注明日期，不并列互相矛盾的结论。
- **关联文档**：行为级决策见 [TEST-BEHAVIOR-DECISIONS.md](TEST-BEHAVIOR-DECISIONS.md)；审计设计见 [IMPORT-AUDIT-DESIGN.md](IMPORT-AUDIT-DESIGN.md)；上线准备见仓库根目录 `PRODUCTION-READINESS-REPORT.md`。

> 说明：D-001～D-005 的实施发生在建立本日志之前；本轮按新目标要求统一回溯登记，证据均来自实际构建、测试与演练输出，未使用推测。

## 索引

| 编号 | 日期 | 主题 | 状态 | 分支 | 影响 |
|---|---|---|---|---|---|
| D-001 | 2026-10-22 | 恢复流程重放 004/006，防止权限回退 | Verified（已合并 `cbcc64b`） | `fix/restore-replay-006` | 备份恢复、权限 |
| D-002 | 2026-10-22 | 移除 RuoYi demo 模块，缩小暴露面 | Verified（已合并 `9ca6c1f`） | `chore/gateway-drop-demo` | 网关路由/安全 |
| D-003 | 2026-10-22 | 网关生产加固（JWT、Actuator、非 root、探针） | Verified（已合并 `4281e31`） | `ops/gateway-hardening` | 认证、部署、监控 |
| D-004 | 2026-10-22 | 上线预检脚本（只读 16 项） | Verified（已合并 `aa5ebe6`） | `ops/production-preflight` | 发布流程 |
| D-005 | 2026-10-22 | 生产构建排除本地配置 + 配置渲染/挂载 | Verified（已合并 `63ccc4d`） | `ops/gateway-config-hygiene` | 构建、密钥、部署 |
| D-006 | 2026-10-22 | 上述分支的合并顺序与执行方式 | Verified（实际顺序见正文） | — | 发布流程 |
| D-007 | 2026-10-22 | 开发脚本对齐统一入口与全新建库流程 | Verified（本分支 `chore/dev-env-align`） | `chore/dev-env-align` | 新同事启动、冒烟、文档 |
| D-008 | 2026-10-22 | 整合同事 PR #39，并修正其“网关不可启动”前提 | Verified（#39 已合并 `146548d`；本分支叠加后实测通过） | `fix/env-sync-with-example` + `chore/dev-env-align` | PR 整合、开发体验 |

---

## D-001 恢复流程重放 004/006

- **状态**：Verified（已合并，合并 commit 见索引）
- **Decision owner**：AI
- **问题与背景**：`scripts/restore.sh` 在导入备份后只重放 `003_roles.sql`。003 是历史授权基线，包含 `GRANT DELETE ON campus.import_issues`；006 才收回该权限。
- **证据**：
  - 隔离实例按“恢复 + 003”执行后，`has_table_privilege('campus_app','campus.import_issues','DELETE')` 返回 `t`；
  - 006 第 166 行执行 `REVOKE DELETE ... FROM campus_app`；重放 006 后返回 `f`，受控函数数为 2；
  - 006 在缺少角色时于第 166 行失败，补齐 003 后重放成功（中断可收敛）。
- **可选方案**：
  1. 修改 003 删除历史 DELETE 授权——会改变历史基线，影响其他依赖该脚本的环境；
  2. 恢复后固定重放 004/006——脚本幂等，且与新建库流程一致；
  3. 从备份恢复 ACL——当前备份使用 `--no-acl`，不可行。
- **决定**：方案 2。恢复顺序固定为 `003 → 004 → 006`，并在脚本末尾断言 `DELETE=f`、审计函数数为 2，失败即非零退出。
- **理由**：保持 003 作为历史基线；006 作为权限收口的唯一权威；断言让错误在恢复时暴露，而不是等到业务 500。
- **影响与兼容性**：恢复耗时增加约 0.1s；备份格式不变；开发规模与合成规模（50k 学生 / 155k 审计）均验证通过。
- **安全风险与权衡**：避免恢复后权限回退；若 006 未来拆分，需同步更新恢复脚本。
- **涉及文件**：`scripts/restore.sh`、`README.md`、`PROJECT-ROADMAP.md`（v1.3）。
- **验证方法**：`bash -n`；隔离库恢复演练；恢复库上 `test_import_audit_summary.py` + `test_staging.py` = **9 passed / 1 skipped**。
- **回退**：回退该分支；恢复时手动执行 006，并在完成后跑一次权限断言。
- **授权**：无需人工授权（B 类）。

---

## D-002 移除 RuoYi demo 模块

- **状态**：Verified（已合并，合并 commit 见索引）
- **Decision owner**：AI
- **问题与背景**：`ruoyi-admin` 依赖 `ruoyi-demo`，会注册 `/demo/**` 示例接口，并包含示例密钥；校园平台不使用这些能力。
- **证据**：`ruoyi-admin/pom.xml` 存在 `ruoyi-demo` 依赖；`ruoyi-modules/pom.xml` 存在 module；`application.yml` Knife4j 分组扫描 `org.dromara.demo`；demo 控制器包含 `/demo/mail`、`/demo/cache`、`/demo/mqtt` 等。
- **可选方案**：
  1. 保留但通过配置禁用——仍需维护依赖与路由面；
  2. 移除依赖、module 声明与扫描分组——直接缩小攻击面；
  3. 删除整个模块源码——改动面大且丢失上游参考。
- **决定**：方案 2。保留模块源码但不参与构建。
- **理由**：最小改动、可逆、无校园功能依赖；保留源码便于对照上游。
- **影响与兼容性**：`/demo/**` 返回 `code=404`；登录、学生、导入、筛选项、总览均 200。
- **安全风险与权衡**：减少示例接口与示例密钥暴露；若未来需要 demo，可按注释恢复三处配置。
- **涉及文件**：`gateway/ruoyi-admin/pom.xml`、`gateway/ruoyi-modules/pom.xml`、`gateway/ruoyi-admin/src/main/resources/application.yml`。
- **验证方法**：`mvn -B -DskipTests -pl ruoyi-admin -am package` = BUILD SUCCESS；重建容器后登录 200、学生 200、`/gw/demo/cache/test1` 返回 `code=404`。
- **回退**：恢复依赖、module 与 Knife4j 分组，重新构建。
- **授权**：无需人工授权（B 类）。

---

## D-003 网关生产加固

- **状态**：Verified（已合并，合并 commit 见索引）
- **Decision owner**：AI
- **问题与背景**：仓库内写死 `jwt-secret-key`；Actuator 暴露 `*` 且展示细节；网关镜像以 root 运行；compose 无 healthcheck。
- **证据**：
  - `SaTokenConfig` 使用 `StpLogicJwtForSimple`；移除密钥后登录直接 500（`SaJwtException: 请配置jwt秘钥`），恢复外部密钥后 200，证明密钥实际参与签发；
  - `management.endpoints.web.exposure.include: '*'`、`show-details: ALWAYS`；
  - 加固前容器 `uid=0(root)`，加固后 `uid=999(ruoyi)`。
- **可选方案**：
  1. 保留默认值并仅在文档中提示——风险不可接受；
  2. 密钥外部化 + compose 缺失即 fail-closed；Actuator 仅 health/info；非 root；新增 `/healthz` 与 healthcheck；
  3. 切换为 uuid token——改变认证实现，兼容风险更高。
- **决定**：方案 2。
- **理由**：不改变认证协议，只移除固定密钥与扩大面；fail-closed 让缺失配置在启动/登录时暴露。
- **影响与兼容性**：所有部署必须提供 `JWT_SECRET_KEY`（≥32 字符）；更换密钥会使既有 token 失效；开发 `.env` 已生成本地密钥（未入库）。
- **安全风险与权衡**：消除“已知密钥可伪造 token”的风险；密钥轮换需配合会话失效窗口。
- **涉及文件**：`gateway/ruoyi-admin/src/main/resources/application.yml`、`docker-compose.yml`、`gateway/Dockerfile`、`.env.example`、`README.md`、`HealthController.java`。
- **验证方法**：缺失密钥登录 500；提供 64 字符密钥后登录 200、学生 200、`/gw/healthz` 200、容器 healthy、`uid=999(ruoyi)`；Actuator 未认证仍 401。
- **回退**：回退分支；但不得恢复固定密钥，若必须回退应改用其他外部化方式。
- **授权**：无需人工授权（B 类）；正式密钥更换仍需运维窗口。

---

## D-004 上线预检脚本

- **状态**：Verified（已合并，合并 commit 见索引）
- **Decision owner**：AI
- **问题与背景**：上线准备项分散在文档中，缺少可重复执行的只读门禁。
- **证据**：手工检查项包括端口、JWT、Actuator、恢复脚本、备份、数据库权限、健康探针、TLS、监控、构建产物。
- **可选方案**：
  1. 仅维护人工清单；
  2. 编写只读脚本，FAIL 非零退出，作为发布前门禁。
- **决定**：方案 2。`scripts/preflight.py` 共 16 项检查。
- **理由**：可重复、可审计、不修改环境；把“未验证”变成显式 FAIL。
- **影响与兼容性**：只读；依赖 Docker CLI 与 `.env`；不打印任何密钥值。
- **安全风险与权衡**：脚本本身不改变权限；需注意不要把输出中的敏感值写入日志（当前只输出键名/长度/状态）。
- **涉及文件**：`scripts/preflight.py`。
- **验证方法**：main 基线 16 项中 9 FAIL；叠加修复分支后 13/15 PASS（当时 15 项），仅 TLS/监控未过；新增镜像配置卫生检查后，默认 dev jar 命中 FAIL、`-Pprod` jar PASS。
- **回退**：删除脚本；不影响运行系统。
- **授权**：无需人工授权（A 类）。

---

## D-005 生产构建排除本地配置 + 配置渲染/挂载

- **状态**：Verified（已合并，合并 commit 见索引）
- **Decision owner**：AI
- **问题与背景**：`application-dev.yml` / `application-prod.yml` 被 `.gitignore` 排除，但默认 `mvn package` 会把它们打进 jar；生产镜像若在开发机构建，会携带本地/示例配置。
- **证据**：
  - 实测默认 jar 含 `BOOT-INF/classes/application-dev.yml` 与 `application-prod.yml`；
  - 两份文件的字面量与 `.env` 实际值重合数为 **0**（未泄漏本环境真实密钥），但包含上游示例配置；
  - 直接挂载源文件会因 `@monitor.username@` 等 Maven 占位符导致 YAML 解析失败；
  - 首次 `-Pprod` 构建因 resources 覆盖丢失 `filtering`，`application.yml` 仍保留 `@profiles.active@`；补齐过滤后 `active: prod`。
- **可选方案**：
  1. 就地清理两份配置的敏感值——文件不入库，无法保证其他环境；
  2. `-Pprod` 构建排除 + 渲染脚本 + 外部挂载——构建与配置解耦；
  3. 仅依赖“从干净检出构建”——依赖人工纪律，无强制。
- **决定**：方案 2，并要求生产从干净检出使用 `-Pprod` 构建；运行时用 `scripts/render-gateway-config.py` 生成 `runtime-config/application-prod.yml` 并通过 `docker-compose.prod.yml` 挂载。
- **理由**：镜像不含环境配置；渲染脚本强制解决占位符；挂载方式不覆盖基础 compose 的 DB/Redis 参数。
- **影响与兼容性**：生产构建命令变为 `mvn -Pprod ... package`；默认 dev 构建不变；`runtime-config/` 已加入 `.gitignore`。
- **安全风险与权衡**：减少镜像携带配置的风险；渲染后的配置文件仍需 600 权限与受控分发；密钥轮换流程未定。
- **涉及文件**：`gateway/ruoyi-admin/pom.xml`、`scripts/render-gateway-config.py`、`docker-compose.prod.yml`、`.gitignore`。
- **验证方法**：
  - `-Pprod` jar 仅含 `application.yml` 且 `active: prod`；
  - 渲染输出残留占位符 0；
  - `-Pprod` 镜像 + 渲染配置启动后登录 200、学生接口 200；
  - 默认 dev 构建/运行不受影响。
- **回退**：回退分支，恢复默认构建；生产不得回退到“镜像内置配置”。
- **授权**：无需人工授权（B 类）；生产配置存放方式仍待运维确定（但机制已可用）。

---

## D-006 分支合并顺序与执行方式

- **状态**：Verified
- **Decision owner**：AI
- **问题与背景**：五个独立修复分支均基于 `main @ 122a0ba`，需要确定合并顺序、验证方式与冲突处理。
- **证据**：五个分支的净差异互不重叠（README 有两处不同段落）；此前已将 restore/demo/hardening/preflight 联合合并并构建成功，`application.yml` 自动合并。
- **可选方案**：
  1. 一次性全部合并——难以定位失败；
  2. 逐个合并，每次合并前同步最新 main 并等待 CI，合并后跑主线验收；
  3. 继续等待人工逐项批准——新目标已授权常规代码 PR 自主合并。
- **决定**：方案 2，并按下述**实际执行顺序**完成：
  1. `docs/decision-log`（治理基线）→ `33df853`
  2. `fix/restore-replay-006`（恢复正确性）→ `cbcc64b`
  3. 同事 `#33` 孤儿 sidecar 清理（独立变更，squash）→ `f7b322d`
  4. `chore/gateway-drop-demo`（缩小暴露面）→ `9ca6c1f`
  5. `ops/gateway-hardening`（认证/部署加固）→ `4281e31`
  6. `ops/production-preflight`（验证工具）→ `aa5ebe6`
  7. `ops/gateway-config-hygiene`（生产构建与配置）→ `63ccc4d`（最终 main）
- **偏差说明**：计划中预检排在配置卫生之后，实际先合入预检。原因：两者无代码依赖，且预检本身能对配置卫生做门禁；先合入时镜像配置卫生项如实 FAIL，再合入 D-005 后转 PASS，等于用预检验证了 D-005。
- **执行规则**：
  - 每个分支合并前：同步 main、复核 diff、CI 全绿、无 P0；
  - 使用 merge commit，不删除分支（#33 使用 squash，因其为单一提交）；
  - 每次合并后 fetch main，检查下一个 PR 的 base/head/diff；
  - 若出现冲突或未预期差异，暂停该次合并并记录；
  - 合并完成后在 main 上重跑全量测试、迁移演练与预检，并更新本日志状态。
- **理由**：先治理后执行；先正确性后暴露面；最后合入构建/配置卫生，使预检从 FAIL 收敛到只剩环境项。
- **影响与兼容性**：七个变更互不重叠；合并后 main `63ccc4d`，网关镜像已重建并复验登录/学生/导入。
- **安全风险与权衡**：合并改变了 main 的认证配置（JWT 外部化）与生产构建方式；开发 `.env` 已具备密钥；生产部署必须按 D-005 执行。
- **验证方法**：
  - 合并后主线：关闭态 **195 passed / 102 skipped / 1 xfailed**，开启态 **120 passed**，权限断言 **11/11 PASS**，迁移演练 **12 步 / 6.83s**；
  - 运行态：登录 200、学生 200、`/healthz` 200、`/gw/demo/cache/test1` 返回 `code=404`、容器 uid=999、8010 无监听、Actuator env 401；
  - 预检：16 项中 **3 FAIL**（监控组件、TLS 入口、默认 dev 构建的镜像配置卫生）。
- **回退**：按合并逆序 revert 对应 merge commit；不得回退到固定 JWT 密钥或镜像内置生产配置。
- **授权**：常规代码/文档 PR 合并，属新目标 A/B 类；不涉及正式库迁移、认证开启或流量切换（C 类）。

---

## D-007 开发脚本对齐统一入口与全新建库流程

- **状态**：Verified（本分支，待合并）
- **Decision owner**：AI
- **问题与背景**：同事 PR #31 引入的 `scripts/dev/*` 与 `docs/DEVELOPMENT-ENVIRONMENT.md` 基于 PR-D 之前的拓扑（Appsmith + 宿主 8010）。合并 #33/#35/#36/#38/#37 后，这些脚本既无法反映真实入口，也无法在全新数据库上完成初始化。
- **证据（逐项实测）**：
  1. `check-prereqs.ps1` 仍检查 8081/8443 并要求 `APPSMITH_ENCRYPTION_*`，而 Appsmith 已下线、compose 不再读取该密钥；
  2. `up-main.ps1` 仍生成 Appsmith 密钥、等待 `campus-appsmith`，且不生成 `JWT_SECRET_KEY`/`GATEWAY_DB_PASSWORD`/`GATEWAY_REDIS_PASSWORD`/`INTERNAL_HMAC_SECRET`——compose 对这些变量使用 `${VAR:?}`，缺失时直接拒绝启动；
  3. `smoke-test.ps1` 直接访问 `http://127.0.0.1:8010`，而 PR-D 已移除宿主发布，实测 `curl 8010` 连接失败；
  4. `_common.ps1` 只执行 003，不重放 004/006；全新库将缺少 `internal_nonce`、导入范围列与审计函数，与 `scripts/restore.sh` 的恢复流程也不一致；
  5. 五个脚本均为无 BOM 的 UTF-8，Windows PowerShell 5.1 按 GBK 解码：中文注释变成乱码并吞掉换行，`004_internal_auth.sql` 被 psql 判为 `syntax error at or near "campus_nonce_cleaner"`（实测复现，字节数 2839 → 2609，行数 71 → 66）；
  6. `smoke-test.ps1` 固定使用 `samples/students_clean.xlsx`，第二次运行全部命中 `DUPLICATE_STUDENT_NO`（实测 batch 41：10 行全部无效），冒烟结果不再可信。
- **可选方案**：
  1. 保留旧脚本，仅在文档中列出人工步骤——新人仍会踩 003/004/006 与 8010 的坑；
  2. 把脚本改到统一入口：端口/密钥/健康检查/冒烟全部走网关，补齐 004/006，脚本统一带 UTF-8 BOM；
  3. 删除开发脚本，只保留 compose 命令——放弃可重复的启动与冒烟能力。
- **决定**：方案 2，并额外做两处提高可重复性的修正：
  1. `_common.ps1` 新增 `Invoke-PsqlFile`：显式 `-Encoding UTF8` 读取 SQL、设置 `$OutputEncoding=UTF8`、失败时打印 psql 最后 10 行输出；
  2. `smoke-test.ps1` 每次生成唯一学号的临时 CSV（`SMK<MMddHHmmss><001..003>`），提交后按学号检索验证，跑完即删。
- **理由**：脚本是新人唯一入口，必须与真实拓扑一致；显式编码与唯一学号让失败可诊断、结果可重复，而不是把环境问题伪装成业务错误。
- **影响与兼容性**：
  - 端口检查改为 55432/55434/6382/9190/8082；8010/8081/8443 不再属于本栈，不再检查；
  - `.env` 必填 7 个密钥；`up-main.ps1` 自动补齐；
  - `.env.example` 移除已下线的 `APPSMITH_ENCRYPTION_*`；
  - 不改变任何业务代码、API 契约、数据库迁移或运行配置。
- **安全风险与权衡**：随机密钥仅写入本地 `.env`，不打印、不入库；冒烟测试仍使用虚构数据，不接触真实学生信息。新增的“无 token 被拒”“8010 不可达”两项断言把安全边界纳入日常检查。
- **涉及文件**：`scripts/dev/_common.ps1`、`check-prereqs.ps1`、`up-main.ps1`、`smoke-test.ps1`、`down-main.ps1`、`.env.example`、`docs/DEVELOPMENT-ENVIRONMENT.md`、`docs/README.md`、`PROJECT-ROADMAP.md`。
- **验证方法（Windows PowerShell 5.1 实测）**：
  - `check-prereqs.ps1`：栈运行时 `FAIL=0 / WARN=5`（5 个端口被本栈占用属预期）；
  - `up-main.ps1 -NoBuild`：`campus-db`/`campus-import-api`/`campus-gateway-db`/`campus-gateway-redis`/`campus-gateway` 全部 healthy，`003+004+006` 重放成功，退出码 0；
  - `smoke-test.ps1` 连续运行 3 次全部 `FAIL=0`（batch 42/43/44），每次均完成 预览→校验→提交→按学号检索；
  - `down-main.ps1` 后数据卷全部保留；再次 `up-main.ps1 -NoBuild` 后 `SMK1022214253%` 仍为 3 行。
- **回退**：回退本分支即可；脚本不参与容器启动，回退不影响运行中的栈。
- **授权**：无需人工授权（A 类：开发脚本与文档）。

---

## D-008 整合同事 PR #39，并修正其“网关不可启动”前提

- **状态**：Verified（#39 已合并；本分支叠加后双模式实测通过）
- **Decision owner**：AI
- **问题与背景**：PR #39（`fix/env-sync-with-example`，同事）与本分支 `chore/dev-env-align` 修改同一组 5 个文件，且都针对“#31 的脚本未跟上 R2/PR-D”。两边不能各自合并，必须先确定整合顺序与取舍。
- **证据**：
  - `gh pr view 39`：base `main`、head `fix/env-sync-with-example`，mergeable，7 项检查全部 SUCCESS（CI / 网关构建 / 后端测试 / 脚本自检 / AI 评审）；
  - 净差异仅 `scripts/dev/*` 与 `docs/DEVELOPMENT-ENVIRONMENT.md`，不触碰业务代码、SQL、compose；
  - #39 的 `Sync-EnvFile` 以 `.env.example` 为唯一来源，能自动跟上后续新增变量——优于本分支写死 7 个键的清单；
  - #39 判断“网关镜像要 `ruoyi-admin/target/ruoyi-admin.jar`，源码未入库（issue #1），宿主机通常构建不出来”，**在当前 main 上只对一半**：网关源码已在仓库，`gateway/Dockerfile` 确实只 `COPY` 宿主构建产物，且 `target/` 被忽略。本机已执行 `mvn package`，网关镜像可构建并运行；全新检出则必须先构建 jar；
  - #39 的冒烟测试改在 `import-api` 容器内直连 `127.0.0.1:8000`，不经过网关，因此不覆盖登录、HMAC 签名、“无 token 被拒”三条真实入口行为；开启 `INTERNAL_AUTH_ENABLED=true` 后该路径会失败。
- **可选方案**：
  1. 关闭 #39，只合并本分支——丢弃同事已验证的 `Sync-EnvFile` 与容器内兜底能力；
  2. 只合并 #39，放弃本分支——失去决策日志、网关路径冒烟、端口全集检查与文档一致性修正；
  3. **先合并 #39，再把本分支 rebase 到新 main 并按能力合并**。
- **决定**：方案 3。合并后在冲突处采用以下组合规则：
  1. `.env` 对齐保留 #39 的 `Sync-EnvFile`（以 `.env.example` 为准），删除本分支的写死键清单；
  2. `up-main.ps1`：默认启动 `campus-db` + `import-api`；**若 `gateway/ruoyi-admin/target/ruoyi-admin.jar` 存在，则一并启动 `gateway-db`/`gateway-redis`/`gateway` 并等待健康**；不存在时给出明确 WARN 与 `mvn -B -DskipTests -pl ruoyi-admin -am package` 提示，不再把“网关不启动”当成默认正确状态；
  3. `smoke-test.ps1`：网关 `9190/healthz` 可达时走真实入口（登录 → `/internal/proxy/*`，含无 token 拒绝与 8010 关闭断言）；不可达时退回 #39 的容器内直连模式，并明确 WARN“未覆盖统一入口”；
  4. 端口表取并集：55432 / 55434 / 6382 / 9190 / 8082；
  5. 脚本继续保留 UTF-8 BOM（#39 只修了 `Get-Content -Encoding UTF8` 的读取侧，未修 PS 5.1 读取脚本源码本身的 BOM 问题）；
  6. `.env.example` 删除已下线的 `APPSMITH_ENCRYPTION_*`。
- **理由**：#39 的环境同步与容器内兜底是实测有效的；本分支的网关路径冒烟与决策留痕是架构真实入口。两者互补，合并后既不重复开发，也不把“跳过网关”固化为长期设计。
- **影响与兼容性**：对全新检出，`up-main` 仍可在无 JDK/Maven 时启动核心栈；具备 jar 时自动恢复完整栈与真实入口测试。对已有环境，行为不变。
- **安全风险与权衡**：内嵌直连模式只用于“网关未构建”的降级路径，且会显式提示未覆盖统一入口，避免把降级测试误当成安全边界验证。
- **涉及文件**：`scripts/dev/_common.ps1`、`check-prereqs.ps1`、`up-main.ps1`、`smoke-test.ps1`、`docs/DEVELOPMENT-ENVIRONMENT.md`、`.env.example`、`docs/DECISION-LOG.md`。
- **验证方法**：合并 #39 后在其 main 上复跑一次脚本；叠加本分支后再跑完整流程（check / up / smoke / down / up），并分别在“有 jar（网关路径）”与“无 jar（降级路径）”两种状态下验证。
- **实施结果（2026-10-22）**：
  - #39 已合并为 `146548d`；本分支把该 main 合入，5 个文件各有一处冲突，按上述规则全部解决；
  - `Sync-EnvFile` 保留，并增加 `Test-SecretKey` / `Get-FillValue`：只有密钥类键在空值或占位符时才随机化，普通开关（如 `KEEP_UPLOAD_FILES`）沿用 `.env.example` 默认值；引号清洗与 `Read-EnvFile` 统一（回应 #39 AI 评审的建议 1、2）；
  - `up-main.ps1`：jar 存在 → 启动 5 个容器；临时移走 jar → 只启动核心栈并提示 Maven 命令，退出码 0；
  - `smoke-test.ps1`：网关模式连续 3 次 `FAIL=0`；`-ForceContainer` 降级模式 `FAIL=0`（10 行导入，按唯一学号检索）；
  - `check-prereqs.ps1`：`FAIL=0 / WARN=5`（栈运行中），并新增网关 jar 状态检查。
- **回退**：先 revert 本分支的叠加提交可回到 #39 行为；再 revert #39 的 merge commit 可回到 #31 脚本。
- **授权**：PR 整合顺序属 B 类；#39 本身只改脚本与文档，不涉及正式库、认证开关或流量切换（C 类）。
