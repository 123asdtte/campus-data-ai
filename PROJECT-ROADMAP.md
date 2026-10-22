# PROJECT-ROADMAP — 校园数据 AI 项目总路线图

- **版本**：v1（2026-10-22，阶段 0 产出）
- **地位**：本项目唯一总路线图。安全迁移细节见 `docs/SECURITY-MIGRATION-EXECUTION-PLAN.md`（专项细化，阶段定义以本文为准）。
- **审批状态**：待项目负责人一次性确认；确认前不启动 PR-B。

---

## 1. 项目当前状态（事实基线，2026-10-22）

| 项 | 状态 | 证据 |
|---|---|---|
| 主分支 | `d10946f`（PR #16 已合并），工作区干净 | git |
| 主栈运行版本 | 与 main 一致（11:32 重建），`INTERNAL_AUTH_ENABLED=false` | `docker exec campus-import-api env` |
| 认证基础设施 | 已合入：`internal_auth.py`、11 路由验签依赖、`PUT /students` 条件注册、`sql/004`（**未在正式库执行**） | PR #16 |
| 正式库 | `campus.internal_nonce` 不存在；`campus_nonce_cleaner` 角色不存在；`campus_app` 仍为可写账号 | `psql campus-db` 实查 |
| 审计 | `operation_logs` 匿名占比 **93%** | 实查 |
| 前端 | React（`web/`），经 nginx 调 import-api，`X-Actor` 无签名 | `web/nginx.conf:28` |
| POC | `campus-ruoyi-poc` PR #3 已合并（`f1c2856`），导入 48/48、学生 12/12 | POC 仓库 |
| Appsmith | 仍在主栈运行，持 `campus_app` 可写账号（高风险，未处置） | compose + `SECURITY-AUTH-DESIGN` |
| plus-ui 许可 | 未确认（Issue #11，阻塞项：仅当采用 plus-ui 界面时相关） | Issue |
| 测试 | 关闭态 130 / 开启态 97 / CI 四项全绿（001→003→004 + campus_app） | CI + 本地 |

**核心判断**：技术路线（RuoYi 网关 + `X-Internal-*` 签名 + FastAPI 范围复核）已被 POC 与 PR-A 双重验证，**方向正确，不需要更换**。当前最大风险不是技术，而是：① 网关尚未进入主项目；② Appsmith 可写账号未处置；③ 文档新旧混杂（37 份中 26 份属历史）。

---

## 2. 总览表

| 阶段 | 解决的问题 | 最终成果 | 核心实现 | 验收标准 | 前置依赖 | 主要风险 |
|---|---|---|---|---|---|---|
| **G 文档治理**（新增，本次方案批准后执行） | 37 份文档 26 份属历史，新旧路线并存会误导开发 | docs/ 活跃文档 ≤11 份 + `archive/` 26 份；索引分"现行/归档"两节 | `git mv` 归档 + 修复 6 份 B 类 + 索引重建 | 归档链接无死链；每份活跃文档与代码一致；README 不再指向已废弃路线 | 本方案批准 | 移动文件破坏相对链接（需同步修 8 处引用） |
| **PR-B 网关落地（学生域）**（职责调整） | 学生域"真实链路"缺网关：无网关则签名无从产生 | compose 新增 `auth-gateway`（RuoYi 后端精简）；登录/权限点/3 个学生端点签名代理；前端学生页切登录会话 | POC 的 `PocProxyController` 模式移植为 `InternalProxyController`；RuoYi 表（`ry_*`）以 `sql/005_gateway_bootstrap.sql` 引导 | 登录→网关→验签→DB→审计全链路可重复；审计 actor=登录用户；跨学院 403 | PR-A；G | 网关引入 RuoYi 全套表与 JVM 服务的重量；管理员引导凭据管理 |
| **PR-C 导入范围与审计** | 导入接口缺批次范围/逐行校验/审计 | 解除管理员硬限制；`created_dept_id` + 逐行校验 + 语句级审计触发器；48 项导入安全用例在主项目复跑 | 移植 POC `07_import_security.sql` 与 `service` 改动（PR #3 已验证） | 越权批次不可见/不可提交；历史 NULL 批次仅管理员；审计计数与 POC 一致 | PR-B | 正式库需要执行 005/006 迁移（先备份） |
| **PR-D 导入接入网关 + 前端切换** | 导入仍可绕过网关直连 8010；前端多入口 | 导入 7 端点接入网关签名代理；前端导入页切登录；**关闭 8010 宿主端口** | 网关补 7 个代理端点（multipart 签名）；nginx 不再直连 | 无签名直连 8010 不可达；前端全站登录可用 | PR-C | 前端大文件上传经网关的内存峰值 |
| **PR-E 回归与发布评审** | 未验证项收口；上线 Go/No-Go | 并发写/审计差异/大文件/nonce 增长四项专项测试；Appsmith 只读化或下线；迁移+回退演练；Go/No-Go 报告 | 压测脚本 + 演练记录 | 无未解决 P0/P1；回退 5 分钟内可完成；Go/No-Go 有证据 | B/C/D | 演练发现回退不可用需要返工 |
| **Appsmith 处置**（独立任务，随 PR-E 收口） | 可写账号是最短攻击路径 | 只读化（新账号 campus_ro）或整体下线 | 新增只读账号 + Appsmith 数据源切换，或 `docker compose down appsmith` | Appsmith 无法再写任何业务表 | PR-A | 现有 Appsmith 页面失效（已降级为历史方案，影响可接受） |

> **对原路线的调整声明**（不静默扩范围）：
> 1. **PR-B 与 PR-D 职责对调**：原 PR-B 是"学生域真实链路"，但它硬依赖网关（签名无从产生）；原 PR-D 的"网关"被**提前、缩小**为"仅学生域切片"，并入 PR-B。原 PR-D 剩余部分（导入接入 + 前端导入页 + 关 8010）成为新 PR-D。理由：不做网关，PR-B 只能停留在测试桩，与"真实链路"目标矛盾。
> 2. **新增 G 阶段（文档治理）**：37 份文档中 26 份为历史方案，其中两套互斥认证方案并存，是后续 AI 开发误用的最大风险源。
> 3. **新增 Appsmith 处置任务**：可写账号问题在 10-20 的文档中已是"高风险"，但一直无所属阶段。
> 4. **PR-C 内容不变**，PR-E 增加四项此前承诺的专项测试（并发写、审计差异、大文件、nonce 增长）。

---

## 3. 阶段详解

### 3.1 G — 文档治理（新增，先行）

**为什么**：`SECURITY-AUTH-ROADMAP`（pwdlib+Casbin 路线）与 `INTERNAL-AUTH-SPEC`（网关签名路线）两套互斥方案并存；`RUOYI-S1S3-MERGE-PLAN` 写的文件名（`poc_auth.py`、`004_internal_nonce.sql`）与实际实现不同；`IMPORT-API.md` §3.7 的 `/health` 契约与实现矛盾。后续任何 AI 或新人从旧文档出发都会做出错误实现。

**做到什么程度**：见 `docs/DOCUMENTATION-AUDIT.md` §4 目标结构。验收：`grep -r "SECURITY-AUTH-ROADMAP" README.md docs/*.md` 仅出现在 archive 内部；docs/README 索引覆盖全部现存文件；无一份活跃文档描述已被取代的路线。

**怎么做**：一个 PR 完成——`git mv` 26 份到 `docs/archive/`；修复 6 份 B 类（API-MIGRATION-INVENTORY、DOCKER-ENV-AUDIT、GIT-WORKFLOW、IMPORT-API、TEST-COVERAGE-MATRIX、docs/README 索引）；README.md 修 7 处（§3.1、§4、§8、§13 行 278 等）；CONTRIBUTING 修 2 处（tests 已存在、分支前缀 feat/）。

**失败怎么办**：移动导致链接失效 → 归档 PR 内跑 `grep -rn "docs/XXX" README.md docs/*.md import-api web` 逐个修复；不删除任何文件，回退即 `git revert`。

### 3.2 PR-B — 网关落地（学生域切片）

**为什么**：这是"POC 验证成果进入主项目"的关键一步。没有网关，`X-Internal-*` 无处产生，学生接口只能停留在测试桩；且菜单权限点（`student:list/write`）需要 RuoYi 的 `sys_menu` 体系来承载。

**做到什么程度**：
- `docker-compose.yml` 新增服务 `auth-gateway`（RuoYi-Vue-Plus 后端，仅启用登录/用户/菜单/权限最小模块）；
- `sql/005_gateway_bootstrap.sql`：`ry_*` 表引导 + 管理员账号 + `student:list`/`student:write` 菜单权限点 + 学院角色；
- 网关暴露 3 个端点：`POST /auth/login`、`GET /poc-proxy/students`、`PUT /poc-proxy/students/{no}`（签名转发）；
- 前端学生页：登录 → 携 token 调网关；`X-Actor` 从前端删除；
- 导入接口保持现路径不变（PR-D 再切）。

**怎么做（方案对比）**：
- **A. 移植 RuoYi 后端（推荐）**：POC 已验证（12/12），权限模型现成；代价是引入 JVM 服务与 `ry_*` 表。
- B. Python 轻量签名边缘：无 Java 依赖，但需自建会话/权限/菜单三件事，等于重做一遍已被否决的 `SECURITY-AUTH-DECISION` 路线，且与 POC 验证物分叉。
- C. 不做网关，前端直连 FastAPI + 应用内登录：等于第三套方案，直接排除。
- 选 A 的理由：复用已验证资产、权限点模型与 `INTERNAL-AUTH-SPEC` 天然对齐；RuoYi 的重量通过"精简模块 + 独立 schema"控制。

**验收**：① 登录获取 token；② 网关生成签名可被 FastAPI 验签通过（金标向量在 Java 侧复现）；③ 跨学院 403；④ 越权写 403；⑤ 审计 actor=登录用户；⑥ 导入接口行为与 PR-A 完全一致（回归）；⑦ `INTERNAL_AUTH_ENABLED=false` 时一切照旧。

**失败怎么办**：RuoYi 精简失败（模块耦合过深）→ 降级为"完整 RuoYi 后端镜像"（更重但可行）；签名不一致 → 金标向量单测定位差异段。网关侧发现根本性问题 → 停止并汇报，回退 = compose 移除服务。

### 3.3 PR-C — 导入范围与审计

**为什么**：导入是唯一写学生数据的批量入口，目前只有认证与权限点，没有批次归属、逐行学院校验和批次审计；管理员硬限制是临时措施，不解除则导入功能对普通用户不可用。

**做到什么程度**：`created_dept_id` 快照列 + 索引；`create_batch` 写快照、`commit` 逐行学院校验（越权行记 `COLLEGE_OUT_OF_SCOPE` 不落库）、`list/get/remap/validate/commit` 批次范围检查；`import_batches/import_issues` 语句级审计触发器（SECURITY DEFINER + 专用属主，复刻 POC 已验证实现）；解除 `IMPORT_ADMIN_ONLY`；POC 48 项导入安全用例移植到主项目。

**怎么做**：直接移植 POC `07_import_security.sql` 与 `service.py` 对应改动（已在 POC 通过审查），新增 `sql/005_import_scope.sql`；POC 侧保持不变。替代方案（在网关层做批次过滤）否决：批次范围是数据语义，必须贴近数据层。

**依赖与验收**：依赖 PR-B（权限点经网关下发生效）；验收 = 48 项矩阵全绿 + 关闭态 130 项回归全绿 + 历史批次（NULL 快照）仅管理员可见。

**失败怎么办**：迁移在测试库先演练；正式库执行前 `pg_dump`；失败回退 = 开关关闭 + revert。

### 3.4 PR-D — 导入接入网关 + 前端切换

**为什么**：只要 8010 对宿主发布且前端直连 FastAPI，导入路径就存在绕过网关的口子；"部分接口走网关"的状态不能作为终态。

**做到什么程度**：网关补 7 个导入代理端点（含 multipart：文件 SHA-256 + 规范化字段签名）；前端导入页切登录会话；**`docker-compose.yml` 移除 `127.0.0.1:8010:8000` 端口发布**；`docs/IMPORT-API.md` 标注新入口。

**验收**：① 宿主机 `curl 127.0.0.1:8010` 连接拒绝；② 前端导入全流程（上传→校验→提交）走登录会话可用；③ 无签名直连 FastAPI 容器内网也不可达网关外路径；④ 导入审计 actor 全部为真实用户（匿名占比从 93% 下降到仅剩历史行）。

**失败怎么办**：multipart 经网关内存放大 → 网关侧限流/分块，或临时保留 8010 并加防火墙规则（记录为偏离项并汇报）。

### 3.5 PR-E — 回归与发布评审

**为什么**：PR-A 审查遗留四项未验证（PUT 并发写、审计差异完整性、大文件内存、nonce 增长）；且"开认证"是不可逆动作，必须有演练证据。

**做到什么程度**：四项专项测试各出报告；`sql/004` 在正式库执行（先 `pg_dump`）；Appsmith 只读化/下线；开关开启演练 + 回退演练各一次（回退 ≤5 分钟）；Go/No-Go 报告（含证据链接）。

**失败怎么办**：任何演练失败 → No-Go，保持关闭态，问题回对应阶段修复；报告与证据归档。

### 3.6 Appsmith 处置（独立任务）

**为什么**：`campus_app` 可写账号经 Appsmith 暴露，是当前系统最短攻击路径（10-20 已标记高风险，至今未动）。
**做到什么程度**：二选一——只读化（Appsmith 数据源切 `campus_ro`）或下线；验收 = Appsmith 无法执行任何写语句。
**怎么做**：只读化成本低（改数据源连接串）；下线影响历史页面（已降级为历史方案）。
**依赖**：无硬依赖，建议与 PR-C 并行或 PR-E 前完成。

---

## 4. 执行机制

见 `docs/EXECUTION-PROTOCOL.md`（自主执行白名单、批准清单、每阶段交付义务、中断恢复）。

## 5. 未验证项声明

- POC 仓库的文档与当前代码一致性本轮**未复核**（仅主仓库审计）；
- GitHub CI 的 AI 评审质量本轮未评估；
- RuoYi 后端"精简模块"的可行性基于 POC 经验推断，**未实际裁剪验证**（PR-B 第一周验证项）；
- plus-ui 许可影响仅限"是否采用其管理界面"，不阻塞网关后端（Issue #11 继续跟进）。
