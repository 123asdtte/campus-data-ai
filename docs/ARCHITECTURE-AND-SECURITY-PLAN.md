# 架构与安全边界（ARCHITECTURE & SECURITY PLAN）

- **版本**：v1.2（2026-10-22 最终核对：Appsmith 已停、SQL 编号统一、测试数字更正）
- **地位**：系统现状架构与安全边界的权威描述。实现细节以 `INTERNAL-AUTH-SPEC.md` 为准；迁移阶段以 `PROJECT-ROADMAP.md` 为准。
- **基线**：main `d10946f`（PR #16 已合并，开关关闭）；主栈容器 = 运行版本。

---

## 1. 组件拓扑（现状）

```
浏览器
  │ http
  ▼
campus-web (nginx:8082)  ──/api/*──►  import-api (uvicorn:8000，宿主 127.0.0.1:8010)
                                          │ psycopg (campus_app)
                                          ▼
                                      campus-db (PG16, schema campus)
~~campus-appsmith ── campus_app 可写账号 ──►~~  （已停止：R2，2026-10-22）
campus-gateway (PR-B 已实现) ── X-Internal-* ──► import-api
  │ Sa-Token 会话
  ├─ campus-gateway-db（RuoYi sys_*，独立库）
  └─ campus-gateway-redis（会话/缓存）
```

| 组件 | 说明 | 端口 |
|---|---|---|
| `campus-db` | PG16，schema `campus`，角色 `campus_dba`(super)/`campus_app`(业务读写)/`campus_ro`(只读) | 内部 5432 |
| `import-api` | FastAPI，11 业务路由 + 2 健康端点 | 127.0.0.1:8010 → 容器 8000 |
| `campus-web` | React 静态 + nginx 反代 `/api/` → `import-api:8000` | 127.0.0.1:8082 |
| `campus-appsmith` | 历史低代码平台，**已停止（R2，2026-10-22）**：容器 Exited、compose 服务已移除、8081/8443 无监听；数据卷 `campus_appsmith_stacks` 保留 | 不再发布 |
| `campus-gateway` | PR-B 已实现：RuoYi 最小切片 + `X-Internal-*` 签名代理（学生域 3 端点） | 127.0.0.1:9190 → 容器 9180 |
| `campus-gateway-db` | 独立认证库 `campus_gateway`（`sys_*`），账号 `gateway_dba` | 127.0.0.1:55434 |
| `campus-gateway-redis` | 网关会话缓存 | 127.0.0.1:6382 |

**注意**：`8010` 当前对宿主回环发布——任何本机进程可绕过 nginx 直连。PR-D 将移除该发布。

---

## 2. 可信身份链路（目标态已部分落地）

```
登录会话（网关/RuoYi Sa-Token）
  → 网关校验权限点（sys_menu.perms）
  → 网关生成 X-Internal-*（11 头，HMAC-SHA256，14 段 canonical，60s 窗口 + 一次性 nonce）
  → import-api require_internal：验签 → 消费 nonce → 构造 Who
  → require_perm（权限点）+ require_college/scope_colleges（数据范围）
  → SQL 层 WHERE 强制（WHERE college_name=%s）
  → 触发器审计（actor 来自 set_config('campus.actor_user_id')，与 DML 同事务）
```

**信任边界**：`X-Internal-Admin/Perms/College` 全部来自网关签名，FastAPI 不做二次鉴权查询（信任前提 = HMAC 密钥只存在于网关与服务端 env）。任何能访问密钥的进程 = 完全信任域，因此密钥不得进入前端、Git、日志。

### 2.1 两种模式（`INTERNAL_AUTH_ENABLED`，导入期定型，改后需重建容器）

| 模式 | 业务路由 | `PUT /students` | 操作人来源 | 状态 |
|---|---|---|---|---|
| 关闭（默认，现网） | 无认证，`X-Actor` 仅演示 | **不注册**（405） | `X-Actor`/回落值 | 当前运行态 |
| 开启 | 验签 + 权限点 + 范围 | 注册（401/403/200） | 签名声明 | 已验证（测试库），未在正式库启用 |

### 2.2 权限点与数据范围

| 路由 | 权限点 | 数据范围（SQL 强制） |
|---|---|---|
| `GET /students`、`/students/{no}` | `student:list` | `college_name = 签名学院`；越界筛选 → 空集；详情越界 → 403 |
| `PUT /students/{no}` | `student:write` | 同上（WHERE 内含范围） |
| `GET /meta/filters`、`/stats/overview` | `student:list` | 聚合按 `ANY(colleges)`；非管理员不返回批次字段 |
| 导入 7 路由 | `import:batch:list/detail/upload/remap/validate/commit` | **PR-C 已实施**：`created_dept_id` 批次范围 + 逐行学院校验 + 批次审计；管理员硬限制已解除 |

---

## 2.3 RuoYi 认证库与业务库的隔离（D5 固化）

| 项 | 决策 | 理由 |
|---|---|---|
| 库 | **独立数据库 `campus_gateway`**（RuoYi `sys_*` 表） | POC 做法是同库不同 schema；独立库让"网关账号碰不到业务表"成为**物理事实**而非授权约定 |
| 账号 | 专用 `gw_app`，仅 `sys_*` 表读写 | 认证框架账号不得获得业务数据写权限 |
| 业务库 | `campus` schema 仅 `campus_app` / `campus_ro` / `campus_nonce_cleaner` | `gw_app` 对 `campus` schema **零权限**（DB 断言负向测试） |
| 学院清单来源 | POC 用 `sys_dept` 直查（`sql/07:196` 给了 `campus_app` SELECT）→ **不可移植**：独立库下业务账号不可达 | 改为**网关在签名声明中下发学院集合**（`X-Internal-Colleges`），FastAPI 只用声明，不再查框架表 |
| 框架表泄漏面 | 主项目 `campus_app` **不授予** `sys_*` 任何权限 | POC 的 `GRANT SELECT ON sys_dept TO campus_app` 是需避免的反面样本 |

## 2.4 关闭 8010 的前置条件（D5 固化）

关闭顺序不可颠倒：

1. **先证明**：前端经网关访问**全部必需接口**（学生 3 + 聚合 2 + 导入 7）均 200；
2. 再移除 compose 中 `127.0.0.1:8010:8000` 发布；
3. 关闭后 `curl 127.0.0.1:8010` **连接被拒**；
4. **容器内通信不受影响**：`campus-web` → `import-api:8000`（按**服务名**解析，与 8010 无关）；`campus-web` healthcheck 仍 healthy；
5. 网关 → import-api 内网签名链路正常。

> 误关风险：若把 8010 当作容器间路径使用，关闭会切断 nginx→import-api。本项目 nginx 使用服务名，因此 8010 仅是"宿主直连入口"。

## 2.5 审计匿名基线（D4 固化）

| 指标 | 值 |
|---|---|
| 统计范围 | 2026-10-20 单日（`min=max=2026-10-20`） |
| 分母 | 544 条（全部 `operation_logs`，无抽样、无业务明细导出） |
| 匿名判定 | `actor_user_id IS NULL OR btrim(actor_user_id)=''` |
| 结果 | 匿名 504（92.6%）/ 有主 40（7.4%）；`student_changes` 305、`students` 239 |
| 历史/近期 | 全部为历史；2026-10-21 起新增 **0** 条 |
| 验收指标 | PR-B 后新增操作必须有非空 actor；PR-E 要求近期窗口匿名新增=0；**不回填历史**（回填=伪造审计） |

## 3. 安全边界清单（当前状态）

| # | 边界 | 状态 | 说明 |
|---|---|---|---|
| 1 | 网关会话 → 内部签名 | ✅ PR-B 已实现（待评审） | `campus-gateway` 登录后签发 14 段签名；规范见 `INTERNAL-AUTH-SPEC.md` |
| 2 | FastAPI 验签 + nonce 防重放 | ✅ 已实现（开启态生效） | 60s 窗口、nonce 主键原子消费 |
| 3 | 权限点 | ✅ 声明链路已实现 | 权限点的**发放**（sys_menu + 网关）在 PR-B |
| 4 | 学院数据范围 | ✅ 学生/聚合/导入均已强制（PR-C） | fail-closed：空声明 → 403；导入逐行校验 |
| 5 | 审计 | ✅ 批次行级审计 + 异常摘要；开启态 actor 可信 | 导入异常明细不再逐行审计；`campus_app` 无 `import_issues` DELETE，删除经受控函数 |
| 6 | nonce 表 | ✅ 代码已合入 | **正式库未执行 004**；`campus_app` 无 DELETE，清理走受控函数 |
| 7 | 网络边界 | 🔴 8010 宿主可直连 | PR-D 移除发布 |
| 8 | Appsmith 可写账号 | 🟢 已停服务（R2） | 容器停止、compose 移除、卷保留；账号仍存在，留待 PR-B 账号治理 |
| 9 | 密钥管理 | 🟡 仅 env，未接入 secrets | `INTERNAL_HMAC_SECRET` 不得入库/前端/日志 |
| 10 | 备份/迁移演练 | 🔴 未做 | PR-E |
| 11 | RuoYi 认证库隔离 | ✅ PR-B 已建（待评审） | 独立库 `campus_gateway` + `gw_app`/`gateway_dba`（对 `campus` schema 零权限） |
| 12 | 文档双轨 | 🔴 26 份历史文档在正文 | G：归档 + 索引两节 |

---

## 4. 数据库角色与迁移

| 脚本 | 内容 | 执行时机 | 回退 |
|---|---|---|---|
| 001/002 | 结构 / 演示数据（002 禁止用于测试与生产） | initdb / 手动 | 002 幂等可重跑 |
| 003 | `campus_app`/`campus_ro` 最小权限 | 一次性（手工） | DROP ROLE |
| **004** | `internal_nonce` + 受控清理函数 | **开关开启前必须执行** | DROP FUNCTION/TABLE/ROLE |
| 005（PR-B） | 网关 `sys_*` 引导 + 权限点（`sql/005_gateway_bootstrap.sql`） | PR-B | 脚本附回退段 |
| 006（PR-C） | `created_dept_id` + 审计触发器（`sql/006_import_scope.sql`） | PR-C | 脚本附回退段 |

测试库初始化：`python scripts/init-test-db.py --admin-dsn <DSN> --verify`（管理连接建库授权，业务测试用 `campus_app`，正负向权限 11 项断言）。

---

## 5. 测试与证据体系

> **2026-10-22 CI 实查**（run 39725491360）：关闭态 collected 213（**130 passed / 82 skipped / 1 xfailed**）；开启态 collected 88（**88 passed**）。下表分层数字为基线快照，最终以 CI 输出为准；`TEST-COVERAGE-MATRIX.md` 的 112 用例基线（`c28ec94`）已过时。

| 层 | 内容 | 证据 |
|---|---|---|
| 单元/契约 | 100 项（mapping/parsing/validation/business/api_contract） | `TEST-COVERAGE-MATRIX.md` |
| 真库集成 | 14 项（全链路/状态机/幂等/审计） | 同上 |
| 安全·关闭态 | OpenAPI 无 PUT、405 无副作用、旧行为回归 | `tests/test_auth_disabled.py` |
| 安全·开启态 | 无签名/缺头/篡改/过期/重放/并发 nonce/权限/范围 | `tests/test_internal_auth.py` |
| 逐路由矩阵 | 11×5（含副作用快照） | `tests/test_route_matrix.py` |
| 写接口专项 | PUT 9 项（401/403/范围/审计 actor/4xx） | `tests/test_student_write.py` |
| DB 权限 | campus_app 正负向 15 项 | `tests/test_db_privileges.py` |

运行方式与 CI 见 `docs/EXECUTION-PROTOCOL.md` §4。

---

## 6. 已知缺口（与 ROADMAP 对应）

| 缺口 | 归属 |
|---|---|
| 网关未进主项目（签名无从产生） | PR-B |
| 导入批次范围 / 逐行校验 / 批次审计 | PR-C |
| 导入未接网关、8010 未关闭 | PR-D |
| PUT 并发写、审计差异、大文件、nonce 增长四项专项 | PR-E |
| Appsmith 可写账号 | 独立任务 |
| plus-ui 许可（仅当采用其界面） | Issue #11 |

---

## 7. 未验证声明

- 本文档的运行态断言基于 2026-10-22 的容器与数据库实查；Appsmith 停止状态基于同日 `docker ps -a`、端口监听与 compose diff。
- `auth-gateway` 的 RuoYi 精简可行性未经裁剪验证（PR-B 首周验证项）。
- Appsmith 内部页面与数据源配置未逐项检查；**R2 的"业务方确认无依赖"尚未完成**，compose 改动未提交、未推送。
- POC 审查基于 `origin/main f1c2856` 的静态审读；本地 `main` 落后 origin 10 个提交。
- 测试数字以 CI 日志为准；`TEST-COVERAGE-MATRIX` 的 112 用例基线（`c28ec94`）已过时。
