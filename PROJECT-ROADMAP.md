# PROJECT-ROADMAP — 校园数据 AI 项目总路线图

- **版本**：v1.1（2026-10-22 修订，含六项既定决策、POC 仓库审查、审计基线）
- **地位**：本项目唯一总路线图。安全迁移细节见 `docs/SECURITY-MIGRATION-EXECUTION-PLAN.md`（专项细化，阶段定义以本文为准）。
- **审批状态**：PR #17 开放待整体审批；本轮不启动 PR-B、不治理文档、不动正式库。

---

## 0. 既定决策（v1.1 固化，后续不再逐项询问）

| # | 决策 | 固化内容 |
|---|---|---|
| D1 | **认证架构 = RuoYi 路线** | RuoYi 负责登录/身份/权限；Java 网关为 FastAPI 生成内部签名；FastAPI 复核身份与范围。PR-B **只**接入登录 + 学生域 3 端点；保留现有 React 前端；**plus-ui-react 许可未确认前不作为正式依赖** |
| D2 | **Appsmith 风险处置先于 PR-B** | 确认无实际业务依赖 → 停服务并保留数据卷与配置；仍需使用 → 换独立只读账号 + 负向测试证明写操作被拒。**不得为迁就功能给只读账号加写权限**；处置与验证在 PR-B 开发前完成（不在正式环境执行） |
| D3 | **文档治理原则** | 更新现行规范、归档历史决策、**不永久删除**有审计价值的材料；每份文件唯一分类，数量与路径一一对应 |
| D4 | **审计匿名基线** | 明确统计时间范围、分母、匿名判定规则、历史/近期区分；**不导出学生个人信息或完整业务记录**；基线成为后续验收指标 |
| D5 | **RuoYi 与业务库隔离** | 明确 `sys_*` 表位置、访问账号、能否触碰业务表；**优先独立数据库 + 专用账号**；认证框架账号不得获得业务表写权限。PR-D 关 8010 前须先证明前端经网关全接口可用，且关闭的是**宿主直连入口**而非容器内通信 |
| D6 | **阶段顺序** | 保留 PR-B → PR-C → PR-D → PR-E 主流程；文档治理（G）与 Appsmith 风险处置（R）作为**业务开发前的独立任务**，各自独立 PR |

---

## 1. 项目当前状态（事实基线，2026-10-22 实查）

| 项 | 状态 | 证据 |
|---|---|---|
| 主分支 | `d10946f`（PR #16 已合并）；主栈运行版本一致，`INTERNAL_AUTH_ENABLED=false` | git / 容器 env |
| 认证基础设施 | 已合入（`internal_auth.py`、11 路由验签、`sql/004`），**正式库未执行 004** | PR #16；`psql campus-db` |
| 正式库角色 | 仅 `campus_app`/`campus_ro`；**无** `campus_nonce_cleaner` | `pg_roles` 实查 |
| 审计 | 544 条，全部产生于 2026-10-20；匿名 504 条（**92.6%**）；对象类型仅 students/student_changes | `operation_logs` 聚合计数（无业务明细） |
| 近期审计 | 2026-10-21 起**无新增审计记录**（最新 2026-10-20） | 同上 |
| Appsmith | 在主栈运行，持 `campus_app` 可写账号 | compose + `SECURITY-AUTH-DESIGN` |
| 前端 | React（`web/`），nginx 反代 import-api，`X-Actor` 无签名 | `web/nginx.conf:28` |
| POC | `campus-ruoyi-poc` main=`f1c2856`；审查结论见 §5 | POC 仓库 |
| 测试 | 关闭态 130 / 开启态 97 / CI 四项全绿 | CI + 本地 |

**核心判断**：技术路线（RuoYi 网关 + `X-Internal-*`）成立且不需更换；POC 与 PR-A 双重验证。当前风险集中在三处：网关未进主项目、Appsmith 可写账号、文档双轨。

### 1.1 审计匿名基线（D4 固化）

| 指标 | 值 | 说明 |
|---|---|---|
| 统计时间范围 | 2026-10-20 单日（`min(created_at)=max(created_at)=2026-10-20`） | 一期 Appsmith 阶段的验收操作 |
| 分母 | **544** 条 `operation_logs` 记录 | 全部记录，无抽样 |
| 匿名判定 | `actor_user_id IS NULL OR btrim(actor_user_id)=''` | 与一期写入路径一致（未设置会话变量） |
| 匿名 / 有主 | **504 / 40**（92.6% / 7.4%） | 有主的 40 条为手工带 `X-Actor` 的操作 |
| 按对象类型 | `student_changes` 305（匿名 300）、`students` 239（匿名 204） | 均为写入/更新路径 |
| 历史 vs 近期 | **全部为历史记录；2026-10-21 起新增 0 条** | 因此 92.6% 反映"一期从未接入可信身份"，**不等于当前存在同等强度的活跃缺陷** |

**验收指标（后续阶段引用）**：PR-B 完成后，任何**新增**业务操作必须有非空 `actor_user_id`；PR-E 验收要求"近期窗口内匿名新增 = 0"。存量历史不回填（回填属伪造审计，禁止）。

---

## 2. 总览表（按既定决策调整后）

| 阶段 | 解决的问题 | 最终成果 | 核心实现 | 验收标准 | 前置依赖 | 主要风险 |
|---|---|---|---|---|---|---|
| **G 文档治理** | 37 份文档 26 份属历史，两套互斥认证方案并存 | 现行 15 份 + `archive/` 26 份，索引分两节 | `git mv` 归档 + 修 6 份 B 类 + 索引重建 | 分类唯一且数量自洽；非 archive 文件中零处指向已废弃路线；链接无死链 | 本方案批准 | 移动破坏相对链接（8 处需同步） |
| **R Appsmith 风险处置** | `campus_app` 可写账号是最短攻击路径 | 二选一：停服务（保留卷/配置）**或** 只读化 + 负向测试 | 独立只读账号；数据源切换或 compose 下线 | 写操作被实测拒绝；必要功能经回归验证；不新增任何写授权 | G（避免混 PR） | 存在未识别的写入依赖 → 先核实再决策 |
| **PR-B 学生域（含网关最小切片）** | 无网关则签名无从产生；学生域仍是旧行为 | `auth-gateway` 服务 + `sys_*` 引导 + 登录 + 学生端点签名代理；前端学生页切登录 | 移植 `PocProxyController` 为 `InternalProxyController`（14 段 canonical 零改动，头名/权限点改写） | 登录→网关→验签→DB→审计端到端可跑；跨学院 403；审计 actor=登录用户；Java 复现金标向量；**审计新增匿名=0** | G、R | 网关引入 JVM + `sys_*` 表的重量；账号引导凭据管理 |
| **PR-C 导入域** | 导入无批次范围/逐行校验/批次审计；管理员硬限制是临时措施 | `created_dept_id` + 逐行学院校验 + 语句级审计触发器；解除管理员硬限制 | 移植 POC `07_import_security.sql` 思路（**不照抄 nonce/授权部分**） | 跨学院导入被拒且不落库；越权读取被拒；重复提交 409；失败整体回滚；审计计数与 POC 一致 | PR-B | 正式库需执行 005（先备份） |
| **PR-D 正式入口** | 8010 宿主可直连；前端多入口 | 导入 7 端点接入网关；前端导入页切登录；**关闭宿主 8010 发布** | 网关补 7 个代理端点（multipart 签名） | ①前端经网关访问**全部必需接口**均 200；②宿主 `curl 127.0.0.1:8010` 连接被拒；③**容器内 `campus-web`→`import-api:8000` 通信不受影响**；④网关→import-api 内网正常 | PR-C | multipart 过网关内存峰值；误关容器内链路 |
| **PR-E 整体验收** | 未验证项收口；上线决策 | 四项专项测试报告 + 正式库 004/005 迁移与回退演练 + Go/No-Go 报告 | 压测/演练脚本 | 无未解决 P0/P1；回退 ≤5 分钟；近期窗口审计匿名新增=0；正式库迁移前后数据一致 | B/C/D | 演练环境与正式环境差异导致"演练通过、实际失败" |

> **对原 PR-B/C/D/E 的调整声明**（不静默扩范围）：
> 1. **PR-B 吸收原 PR-D 的"网关最小切片"**：原 PR-B（学生域真实链路）硬依赖网关，无网关则签名无从产生，只能停在测试桩；因此把网关**提前并缩小**（仅登录 + 学生 3 端点），原 PR-D 剩余部分（导入接入 + 前端导入页 + 关 8010）保持为 PR-D。
> 2. **新增 G（文档治理）与 R（Appsmith 风险处置）**，二者为业务开发前的独立任务，各自独立 PR。
> 3. **PR-C 内容不变**；**PR-E 增加**此前承诺的四项专项测试（并发写、审计差异、大文件内存、nonce 增长）。
> 4. **更正既有描述**：RuoYi-Vue-Plus 6.0.0 的表前缀是 `sys_*`（以 POC `sql/01_ruoyi.sql` 为准），**不是** v1.0 写的 `ry_*`；POC 的 `sys_*` 与业务 `campus` schema 同库不同 schema，主项目按 D5 改为**独立数据库 + 专用账号**。

---

## 3. 阶段详解

### 3.1 G — 文档治理

**为什么**：两套互斥认证方案（`SECURITY-AUTH-ROADMAP` 的 pwdlib+Casbin vs 现行网关签名）同时存在于正文；`004_auth.sql` 编号与实际 `004_internal_auth.sql` 撞车；根 README 仍指向已废弃路线。后续任何 AI/新人从旧文档出发都会做错实现。

**做到什么程度**：见 `docs/DOCUMENTATION-AUDIT.md` §5。验收：非 archive 文件中 `grep -rn "SECURITY-AUTH-ROADMAP\|poc_auth.py\|004_internal_nonce\|ry_\*"` 零命中；索引覆盖 100% 现存文件；每份活跃文档与 `d10946f` 一致。

**怎么做**：一个 PR（`docs/governance-stage0`）：`git mv` 26 份 C 类 → `docs/archive/`；3 份加"已被取代"头注；修 6 份 B 类；重建 `docs/README.md` 两节索引；修根 README 7 处 + CONTRIBUTING 2 处；同步 8 处相对链接。

**测试命令**：无代码测试；验收靠 `grep` 校验 + 链接检查。
**回退**：`git revert` 整个 PR。
**未解决风险**：`git mv` 后外部引用（GitHub 链接、其他仓库）会失效，需在 PR 描述列出重定向说明。

### 3.2 R — Appsmith 风险处置

**为什么**：`campus_app` 可写账号经 Appsmith 暴露，是当前最短攻击路径；10-20 文档已标高风险但始终无归属阶段。

**做到什么程度**：二选一（先核实使用情况：近 7 日访问/查询记录、页面是否被业务方使用）：
- **R1 只读化**：新建 `appsmith_ro`（仅 `campus` schema SELECT），切换 Appsmith 数据源；**不新增任何写授权**；
- **R2 停服务**：`docker compose stop appsmith`（保留 `appsmith_pgdata` 卷与 `.env` 配置），从 compose 移除服务但**不删卷**。

**验收**：R1 → 用 `appsmith_ro` 执行 INSERT/UPDATE/DELETE 全部被拒（错误码 42501），只读页面仍可用；R2 → `docker ps` 无 appsmith，业务方确认无依赖。
**测试命令**：`psql` 以 `appsmith_ro` 身份尝试写入 → 必须 permission denied。
**回退**：R1 改回数据源连接串；R2 `docker compose up -d appsmith`（配置与卷未动）。
**未解决风险**：若存在未识别的写入依赖，R1 会破坏功能——先核实再决策，不允许"先加权限再谈"。

### 3.3 PR-B — 学生域（含网关最小切片）

**为什么**：PR-A 只提供了"验签能力"，没有"签名的产生者"；学生域要真正可信，必须有登录会话与权限点发放。

**做到什么程度**：
- 独立数据库 `campus_gateway` + 专用账号 `gw_app`（**仅** `sys_*` 表读写；**对 `campus` schema 零权限**）；
- `sql/005_gateway_bootstrap.sql`：`sys_*` 表（PG 方言，取自 POC `sql/01_ruoyi.sql` 的必要子集）、管理员账号、`student:list/write` 权限点、学院角色；
- 网关端点：`POST /auth/login`、`GET /poc-proxy/students`、`GET /poc-proxy/students/{no}`、`PUT /poc-proxy/students/{no}`；
- 前端学生页改走登录会话，`X-Actor` 移除。

**怎么做**（方案对比）：
- **A 移植 POC 的 RuoYi 后端（推荐）**：14 段 canonical、`pct`、`multipart` 签名策略、RestClient 转发可**零改动复制**；头名 `X-Poc-*`→`X-Internal-*`、权限点 `poc:student:*`→`student:*`、配置键 `poc.hmac-secret`→`INTERNAL_HMAC_SECRET`、nonce 沿用主项目 `internal_nonce`+`cleanup_internal_nonce()`。
- B Python 轻量签名边缘：需自建会话/权限/菜单三件事 → 等于重做已被否决的路线，排除；
- C 前端直连 + 应用内登录：第三套方案，排除。
- 选 A：复用已验证资产，权限模型与 `INTERNAL-AUTH-SPEC` 对齐；重量通过"独立数据库 + 独立账号 + 仅必要端点"控制。

**测试命令**：
```bash
# Java 侧金标向量（必须复现 9d934c4c…500a）
mvn -pl ruoyi-admin test -Dtest=InternalAuthGoldenVectorTest
# 网关链路
curl -X POST <gw>/auth/login … && curl -H "Authorization: Bearer <token>" <gw>/poc-proxy/students
# Python 侧（开启态）
INTERNAL_AUTH_ENABLED=true pytest tests/test_internal_auth.py tests/test_route_matrix.py
```
**验收**：① 登录取 token；② 网关签名被 FastAPI 验签通过；③ 跨学院详情/修改 403；④ 审计 `actor_user_id` = 登录用户且新增匿名=0；⑤ 关闭态 130 项回归全绿；⑥ `gw_app` 对 `campus` schema 零权限（DB 断言）。
**回退**：compose 移除 `auth-gateway`；前端回到 `/api` 直连（改动集中在 `web/src/api/client.ts`）。
**未解决风险**：RuoYi 精简裁剪可行性未实测（PR-B 第一周验证项）；POC 用 `sys_dept` 直查学院清单，在**独立库**下 `campus_app` 不可达 → 学院白名单改为网关随签名下发（**移植时必须改**）。

### 3.4 PR-C — 导入域

**为什么**：导入是唯一批量写学生数据的入口，缺批次归属与逐行校验；管理员硬限制是临时措施。

**做到什么程度**：`created_dept_id`（服务端身份写入、客户端不可指定）+ 索引；`create_batch` 写快照；`commit` 逐行学院校验（越权行记 `COLLEGE_OUT_OF_SCOPE` 并不落库）；7 路由批次范围检查；`import_batches`/`import_issues` 语句级审计触发器（SECURITY DEFINER + 专用属主）；解除 `IMPORT_ADMIN_ONLY`；POC 48 项导入安全用例移植到主项目（**按主项目表名/角色重写，不照抄 POC 脚本**）。

**怎么做**：新增 `sql/005_import_scope.sql`（`created_dept_id`、约束扩展、审计函数与触发器、专用属主与授权）；`service.py`/`queries.py` 移植 POC 对应逻辑（POC `service.py:740-815`、`sql/07:37-134`）。
**测试命令**：`INTERNAL_AUTH_ENABLED=true pytest tests/test_import_security_main.py`（POC 48 项重写版）+ 关闭态全量。
**验收**：跨学院导入被拒且不落库；越权读取被拒；重复提交 409；失败整体回滚；审计计数与 POC 一致；历史 NULL 批次仅管理员可见。
**回退**：开关关闭 + `git revert`；正式库迁移前必须 `pg_dump`。
**未解决风险**：POC `import_audit_trail` 用逗号串 id + 正则匹配，设计脆弱 → 移植时改为关联表或精确 `bigint[]`。

### 3.5 PR-D — 正式入口

**为什么**：只要 8010 对宿主发布且前端直连，导入路径就有绕网关的口子。

**做到什么程度**：网关补 7 个导入代理端点（multipart：文件 SHA-256 + 规范化字段签名）；前端导入页切登录；**移除 compose 中 `127.0.0.1:8010:8000` 发布**。

**怎么做**：移植 POC `PocProxyController` 的导入 7 端点并改写命名；nginx 不变（仍按服务名 `import-api:8000` 访问）。

**验收（D5 明确的前置条件）**：
1. **先证明**：前端经网关访问**全部必需接口**（学生 3 + 聚合 2 + 导入 7）均 200；
2. 再关闭宿主发布；
3. 关闭后：`curl 127.0.0.1:8010` **连接被拒**；
4. **容器内通信未受影响**：`campus-web` → `import-api:8000`（服务名，非 8010）仍 200；`campus-web` healthcheck 仍 healthy；
5. 网关 → import-api 内网签名链路正常。

**回退**：恢复 compose 端口发布 + 前端切回。
**未解决风险**：multipart 经网关内存峰值（`file.getBytes()` 全量读入）→ PR-E 压测项。

### 3.6 PR-E — 整体验收

**为什么**：四项未验证项 + 正式库迁移是不可逆动作，必须有演练证据。

**做到什么程度**：① PUT 并发写竞态测试；② 审计 `changed_fields` 新旧值差异完整性验证；③ 大文件（接近 10MB）内存与耗时基准；④ nonce 表增长率与清理效果；⑤ 正式库执行 004/005（先 `pg_dump`）；⑥ 开关开启演练 + 回退演练各一次；⑦ Go/No-Go 报告。

**验收**：无未解决 P0/P1；回退 ≤5 分钟；正式库迁移前后业务数据一致；近期窗口审计匿名新增=0。
**回退**：DDL 回退脚本（004/005 均附）；开关关闭；镜像回退到演练通过的 tag。
**未解决风险**：演练环境与正式环境配置差异导致"演练通过、实际失败"——缓解：演练用与正式同镜像同 compose。

---

## 4. 串行 / 并行安排

| 工作 | 关系 | 说明 |
|---|---|---|
| G 文档治理 | 串行在 R、PR-B 之前 | 避免后续 PR 基于旧文档 |
| R Appsmith 处置 | 与 G 串行；与 PR-B **可并行**（不同服务、不同文件） | 但**不与业务 PR 混在一个 PR** |
| PR-B → PR-C → PR-D | **严格串行** | 权限点、范围模型、入口逐层依赖 |
| 同事线（Issue #3 Docker / #8 测试覆盖） | 与 PR-B 可并行 | 边界：不改同一 compose 段、不改 `sql/` 授权脚本 |
| PR-E 专项测试 | 依赖 B/C/D 全部完成 | 不可提前 |

**失败回退规则**：某阶段验收不过 → 回到该阶段修复；连续两次修复仍不过 → 回到前一阶段重新评估依赖；涉及授权/密钥/正式库 → 停止并汇报（见 `docs/EXECUTION-PROTOCOL.md` §6）。

---

## 5. POC 仓库审查结论（动用 POC 代码前必读）

来源：只读审查 `campus-ruoyi-poc`（main `f1c2856`），明细见 `docs/DOCUMENTATION-AUDIT.md` §6。

| 分类 | 内容 |
|---|---|
| **零改动可复制** | 14 段 canonical 构造与段序、`pct`/`normalize` percent-encoding、`sha256`/`hmacHex`、multipart 签名策略（文件内容摘要 + 非文件字段 meta）、`Who`/`require_perm`/`require_college` 骨架、RestClient 转发与错误透传、`LoginHelper` 相关 API（v6.0.0 确认存在） |
| **必须改写** | 头名 `X-Poc-*`→`X-Internal-*`（11 个）；权限点 `poc:student:*`→`student:*`；配置键 `poc.hmac-secret`→`INTERNAL_HMAC_SECRET`；nonce **沿用主项目** `internal_nonce`+`cleanup_internal_nonce()`（**不移植** POC 的 `poc_nonce` 与应用级 DELETE）；admin 判定改严格布尔；补 POC 缺失的 nonce/ts/dept 格式与长度校验、密钥 ≥32 校验 |
| **禁止移植** | `sql/06` 的 `campus.poc_nonce`（含 `GRANT DELETE`）；`sql/07:196` 的 `GRANT SELECT ON sys_dept TO campus_app`（独立库下不成立，且泄漏框架表）；`sql/08` 复制 admin 密码建用户的做法；`poc-api` 服务与 `--poc.api-base`（键名与代码不匹配，参数实际未生效）；`.env.poc`（磁盘含明文密钥） |
| **POC 文档已过时** | `VERSIONS.md` 的"backend 5 处/import-api-poc 3 处定制"与 PR #3 实际 diff 不符；POC `README.md` 仍写"sql/01–06"（实为 01–08）且测试脚本清单漏 `test_import_security.sh` |

**口径更正（重要）**：POC 的 `test_slice.sh` / `test_datascope.sh` **没有 PASS/FAIL 计数器**，是打印式脚本——此前"POC 学生 12/12"指的是 **T1–T12 段落数**，不是断言通过数；只有 `test_import_security.sh` 有计数器（其"48"为运行时计数，无法从静态文件复算）。POC 文档已归档，引用时按此口径表述。

---

## 6. 未验证项声明

- POC 仓库本轮为**静态审读**：未运行容器、未构建 Maven/前端、未复算 48 项计数；SQL 可执行性未验证；
- RuoYi 精简裁剪可行性基于 POC 经验推断，未实测；
- plus-ui 许可（Issue #11）只影响"是否采用其管理界面"，不阻塞网关后端；
- 审计基线仅覆盖 2026-10-20 一期数据，2026-10-21 起无新增记录，**不能据此推断当前活跃路径的缺陷比例**。
