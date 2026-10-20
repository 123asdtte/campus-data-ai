# 认证与权限实施路线图

- **日期**：2026-10-20
- **状态**：待批准，**尚未实施任何一步**
- **关联**：`docs/SECURITY-AUTH-DECISION.md`（选型）、`docs/SECURITY-AUTH-DESIGN.md`（现状与风险）
- **原则**：先写测试再实现；每阶段独立可回滚；不改动导入闭环

---

## P0：Appsmith 只读化

### 现状核实（2026-10-20 22:56）

**未执行。** 证据：

```
campus_app | Appsmith JDBC Driver | 172.20.0.4 | idle   ← 仍是可写账号
campus_ro  | 连接数 0
```

`campus_ro` 的能力已验证（读 235 行成功，`UPDATE` 返回 `permission denied for table students`），凭据在 `.env` 的 `RO_DB_PASSWORD` 中可用。

### 最小操作方案（待批准）

| 步骤 | 操作 | 执行者 |
|---|---|---|
| 1 | Appsmith 后台 → Data Sources → 现有 PostgreSQL 数据源 → 用户名改为 `campus_ro`、密码改为 `RO_DB_PASSWORD` | **你**（或授权我用浏览器自动化操作，需提供 Appsmith 管理员账号） |
| 2 | 保存后点「Test connection」 | 你 |
| 3 | 打开现有查询页，确认只读查询正常 | 你 |
| 4 | 我执行验证（见下） | 我 |

### 验收标准

| 项 | 期望 |
|---|---|
| Appsmith 只读查询 | 正常返回数据 |
| Appsmith 执行 `UPDATE campus.students ...` | 报 `permission denied` |
| `pg_stat_activity` | Appsmith 连接用户变为 `campus_ro` |
| Import API 导入链路 | 不受影响（仍用 `campus_app`） |
| 五张表记录数 | 与操作前一致 |

### 回滚

数据源改回 `campus_app` + `APP_DB_PASSWORD`，无需重启任何容器。

### 风险

- 若 Appsmith 中存在写入型查询，会立即失效——**这是预期效果**，但需先确认这些查询不是业务正在用的。
- 不涉及数据库结构、容器与代码。

---

## P1：认证基础（登录 / 会话 / 账号生命周期）

| 项 | 内容 |
|---|---|
| **目标** | 未登录不可访问任何业务接口；可登录、登出、过期、停用 |
| **新增文件** | `import-api/app/auth/__init__.py`、`passwords.py`（pwdlib 封装）、`sessions.py`（签发/校验/撤销）、`deps.py`（`current_user` 依赖）、`routes.py`（login/logout/me） |
| **修改文件** | `import-api/app/main.py`（挂载路由、全局依赖）、`import-api/requirements.txt`（+`pwdlib[argon2]`）、`web/src/api/client.ts`（`credentials:'include'`、401 跳转）、`web/src/App.tsx`（路由守卫）、`web/src/pages/LoginPage.tsx`（新增） |
| **数据库** | **需要迁移** `sql/004_auth.sql`：`campus.auth_user`（工号、姓名、角色、学院、状态、password_hash、失败次数、锁定至）、`campus.auth_session`（token_hash 唯一索引、user_id、expires_at、revoked_at、ip、ua） |
| **接口** | `POST /auth/login`、`POST /auth/logout`、`GET /auth/me` |
| **兼容性** | 现有 12 个接口若直接加 `Depends(current_user)`，所有 curl 脚本与验收脚本会 401。对策：引入 `AUTH_ENABLED` 开关，先开发后开启；开启前把自动化脚本改为先登录拿 Cookie |
| **回滚** | 关闭 `AUTH_ENABLED` 重启 API；`004` 只新增表，回滚可保留空表或 `DROP TABLE`（数据无依赖） |
| **测试（先写）** | ① 未登录访问 `/students` → 401；② 正确密码登录 → 200 且 Set-Cookie 含 HttpOnly；③ 错误密码 5 次 → 第 6 次 423/429；④ 登出后旧 Cookie → 401；⑤ 过期会话 → 401；⑥ 停用账号 → 403；⑦ 密码字段在响应中永不出现 |
| **验收** | 上述 7 条自动化用例全绿；浏览器手动登录一次成功 |
| **与导入闭环关系** | 只加前置门，不改任何导入逻辑；导入页所有请求自动带 Cookie |

**初始管理员**：`python -m app.auth.bootstrap --employee-no admin --name 系统管理员`，随机生成一次性密码打印到终端，**不设默认密码**。

---

## P2：角色授权（Casbin）

| 项 | 内容 |
|---|---|
| **目标** | 四类角色按最小权限放行；未明确授权默认拒绝 |
| **新增文件** | `import-api/app/authz/{model.conf,enforcer.py,adapter.py}`；`sql/005_policy.sql`（或并入 004）建 `campus.auth_policy` |
| **模型** | `p = sub, obj, act`；`g = _, _`；角色：`admin` / `student_affairs` / `academic` / `auditor` |
| **资源命名** | `students`、`changes`、`import_preview`、`import_commit`、`audit_log`、`stats` |
| **动作** | `read` / `write` / `commit` |
| **权限矩阵** | 见 `SECURITY-AUTH-DESIGN.md` §3；补充实现细节：`auditor` 对 `import_*` 全部拒绝，`admin` 不获得物理删除能力（本就无接口） |
| **策略存储** | 自写只读适配器从 `auth_policy` 载入（不引入 SQLAlchemy）；策略变更后 `enforcer.load_policy()` |
| **接口改造** | 每个路由加 `Depends(require("students","read"))` 形式；`/imports/{id}/commit` 用 `("import_commit","commit")` |
| **数据库** | 新增策略表；不涉及业务表 |
| **兼容性** | 策略为空时全部拒绝，需在迁移中初始化四条角色策略，否则上线即全站 403 |
| **回滚** | 删除 `require` 依赖或 `AUTHZ_ENABLED=false` 切换为「仅认证不授权」 |
| **测试（先写）** | ① 四角色 × 六资源的 24 组期望值表驱动测试；② `auditor` 调 `commit` → 403；③ 伪造角色字段无效（角色取自 DB，不信请求体）；④ 未登录 → 401 优先于 403 |
| **验收** | 24 组全部符合预期；越权用例全部 403 |
| **与导入闭环关系** | 只限制「谁能提交」，不改提交本身的事务与幂等逻辑 |

---

## P3：可信操作人

| 项 | 内容 |
|---|---|
| **目标** | 审计中的操作人 = 登录用户，客户端无法伪造 |
| **删除** | `import-api/app/main.py` 的 `X-Actor` 参数与 `_actor()`；`web/src/api/client.ts` 的 `X-Actor` 头；`web/.env.example` 的 `VITE_ACTOR` |
| **改造** | `service.py` 的 `create_batch/validate_batch/commit_batch/remap_batch` 签名由 `actor: str` 改为 `user: CurrentUser`；`_set_actor` 用 `user.employee_no` |
| **数据库** | 可选迁移：审计触发器增加 `IF v_actor_user_id IS NULL THEN RAISE EXCEPTION`（仅对 students / student_changes 的写入），避免再次出现匿名写入 |
| **测试（先写）** | ① 带 `X-Actor: 校长` 提交 → 审计记录的是登录工号；② 不登录 → 401；③ 事务回滚 → 审计同步回滚（同一事务）；④ 历史匿名记录保持原样（只影响新写入） |
| **回滚** | 保留 `X-Actor` 兼容期（读但忽略并告警），确认无脚本依赖后删除 |
| **验收** | 任取一次导入提交，`operation_logs.actor_user_id` 与登录工号一致；伪造头无效 |

---

## P4：用户与角色管理页面

| 项 | 内容 |
|---|---|
| **目标** | 管理员可增删用户、重置密码、停用、调整角色 |
| **接口** | `GET/POST/PATCH /admin/users`、`POST /admin/users/{id}/reset-password`、`GET/PUT /admin/roles/{role}/policies` |
| **前端** | `web/src/pages/AdminUsers.tsx`、`AdminRoles.tsx`，仅 `admin` 可见（后端同样校验） |
| **数据库** | 复用 004/005 表，无新迁移 |
| **测试** | ① 非管理员访问 `/admin/users` → 403；② 停用用户后其会话立即失效；③ 角色变更后下一次请求即生效（`load_policy`） |
| **回滚** | 隐藏菜单 + 路由下线，表结构保留 |
| **与导入闭环关系** | 无直接影响 |

---

## P5：学校 SSO 对接评估

| 项 | 内容 |
|---|---|
| **前置** | 学校信息中心确认协议（CAS / OAuth2 / OIDC / LDAP）与接入审批 |
| **改造点** | 仅替换 `authenticate()` 的实现：SSO 回调拿到工号后，匹配 `auth_user`，签发同样的会话 |
| **不改** | 角色、策略、审计、导入闭环均不变 |
| **回退** | 保留本地账号登录入口，SSO 故障时可切回 |
| **验收** | SSO 登录后 `current_user` 与本地登录一致；角色与审计行为不变 |

---

## 依赖与工程变更

| 变更 | 说明 |
|---|---|
| `requirements.txt` 新增 | `pwdlib[argon2]`、`casbin`；测试再加 `pytest`、`httpx` |
| 容器构建 | 新增依赖需 `scripts/fetch-wheels.sh` 重新下载 wheel（容器无外网） |
| CI | 增加 `pytest` 步骤；现有 `tsc + build` 保持不变 |
| 迁移 | `004_auth.sql`、`005_policy.sql`（或合并），由 `docker-entrypoint-initdb.d` 只在**首次初始化**执行——**已运行的库需要手工执行或写迁移脚本**，这点必须在实施时处理 |

---

## 顺序与依赖

```
P0（无代码，关掉最大绕过面）
  └─> P1（认证） ─> P2（授权） ─> P3（可信操作人） ─> P4（管理页）
                                              └─> P5（SSO，需外部条件）
```

P0 必须先做：它不依赖任何代码，却能立刻消除「Appsmith 可改学生数据」这一最高风险。

---

## 全局风险

| # | 风险 | 缓解 |
|---|---|---|
| 1 | 开启认证后，所有现有脚本（含验收脚本）失效 | 先在测试环境改脚本，再开开关 |
| 2 | `004` 脚本对已初始化库不生效 | 实施时用幂等 SQL + 手工执行，不依赖 initdb |
| 3 | 策略表为空导致全站 403 | 迁移内初始化四条角色策略，并有启动自检 |
| 4 | 学院级数据范围规则未定 | 先按「全部可见 + 明确标注待确认」，不做业务假设 |
| 5 | 会话表无索引拖慢鉴权 | `token_hash` 建唯一索引 |
| 6 | 无 HTTPS 时 Cookie 无法加 `Secure` | 本机阶段接受，上线前必须上 TLS |

---

## 下一步唯一最优先任务

**执行 P0：把 Appsmith 数据源从 `campus_app` 换成 `campus_ro`。**

理由：不需要写一行代码，就能消除当前最高的绕过风险；且它的验收结果会直接影响 P1 之后是否还需要保留 Appsmith。
