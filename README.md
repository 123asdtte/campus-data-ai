# 校园数据管理与 AI 助手平台

面向中职/高职校园的学生数据管理与学工服务系统。当前阶段：**把已有的 Excel 导入与查询能力做到可靠、可审计**，同时分阶段评估用成熟开源后台（RuoYi-Vue-Plus）承接认证、角色与数据权限。

第一阶段只使用**虚构数据**，不接触真实学生信息；Dify AI 助手排在认证与权限之后接入。

> **本仓库当前只有一套在跑的系统**：React 前端 + FastAPI + PostgreSQL（见 §2）。
> RuoYi-Vue-Plus 相关的一切内容都位于**仓库之外的隔离 POC 目录**，是迁移方案的验证环境，**不是**生产系统的一部分。

---

## 1. 项目要解决什么

- 把散落在 Excel 里的学生花名册、招生录取数据，变成**可校验、可追溯**的数据库；
- 导入过程不丢数据：表头自动识别 → 字段映射 → 逐行校验 → 异常带行号 → 人工确认后入库；
- 每次变更都留下**真实操作人**的审计记录；
- 后续在此基础上接入制度问答、统计分析与 AI 辅助。

---

## 2. 架构

### 2.1 主系统（当前在运行）

```
浏览器
  │  http://127.0.0.1:8082
  ▼
campus-web        nginx 1.29 + React 静态产物   （独立 Compose 栈）
  │  /gw/* 反向代理（登录 + 全部业务接口）
  ▼
campus-gateway    RuoYi-Vue-Plus（Sa-Token）     登录 / 权限点 / 学院范围 / HMAC 签名
  │  内网 X-Internal-*（14 段 canonical）
  ▼
campus-import-api FastAPI + pandas/openpyxl     验签 / 解析 / 校验 / 入库 / 审计上下文
  │  psycopg + 事务级 set_config('campus.actor_user_id')
  ▼
campus-db         PostgreSQL 16.15               业务表 + 审计触发器
                    │
                    └─ operation_logs（触发器写入，与业务同事务）

campus-gateway-db PostgreSQL 16.15               独立认证库 campus_gateway（sys_* 表）
campus-gateway-redis Redis 7.4                   Sa-Token 会话缓存

campus-appsmith   Appsmith CE v2.5.0            低代码界面（历史方案，**已于 2026-10-22 R2 下线**）
```

- 所有端口只绑定 `127.0.0.1`，不对局域网/公网暴露。
- **PR-D 起浏览器不再有 `/api` 直连入口**：`import-api` 无宿主端口，只能由网关在容器网络内按服务名调用。
- 业务表位于 `campus` schema，审计由数据库触发器保证「业务变更与审计同事务」。

### 2.2 独立 POC：RuoYi-Vue-Plus 验证环境（独立私有仓库）

```
Z:\ai\本地部署\ruoyi-plus-poc\        ← 不在本仓库
  ├─ backend/          RuoYi-Vue-Plus v6.0.0 (Java 21) + POC 代理控制器
  ├─ ui-react/         plus-ui-react 6.0.0 (React 19 + Umi Max 4.7)
  ├─ import-api-poc/   现有 import-api 的 POC 副本（加了验签与数据范围）
  └─ docker-compose.poc.yml
        poc-db      PostgreSQL 16.15   127.0.0.1:55433   ← 与主库完全独立
        poc-redis   Redis 7.4          127.0.0.1:6381
        poc-importapi / poc-api        仅内网，无宿主端口
        poc-java    Java 网关          127.0.0.1:9180
```

**POC 与主系统的关系**：POC 验证的是「未来若由若依承担认证与授权，业务接口如何安全接入」这一模式。它与主系统**不共享数据库、不共享代码、不共享密钥**。

---

## 3. 当前进度

| 模块 | 状态 | 说明 | 报告 |
|---|---|---|---|
| Excel 解析与表头识别 | ✅ 已完成 | 多工作表、前 15 行表头定位、别名/模糊匹配、冲突与未知列处理 | [IMPORT-MAPPING-TEST.md](docs/archive/IMPORT-MAPPING-TEST.md) |
| 导入闭环（预览→校验→提交） | ✅ 已完成 | 幂等保护、事务回滚、异常带 Excel 行号 | [IMPORT-API.md](docs/IMPORT-API.md) |
| 审计链路 | ✅ 已完成 | 触发器写 `operation_logs`，actor 来自事务级 GUC | [§10](#10-操作审计) |
| React 查询与导入页 | ✅ 已完成 | 20 项浏览器验收通过，生产构建与容器化部署 | [REACT-TEST-REPORT.md](docs/archive/REACT-TEST-REPORT.md) |
| 部署与回退 | ✅ 已完成 | 前端独立栈，停止/恢复主栈不受影响 | [DEPLOY-ACCEPTANCE-1.3.md](docs/archive/DEPLOY-ACCEPTANCE-1.3.md) |
| RuoYi 真实登录与身份贯通 | 🧪 POC 通过 | 登录 → Java 签名 → FastAPI 验签 → 审计 actor 正确 | [RUOYI-POC-AUTH-RESULTS.md](docs/archive/RUOYI-POC-AUTH-RESULTS.md) |
| 数据权限专项 | 🧪 POC 通过 | 框架 Mapper 与实际业务路径**分别**取证 | [RUOYI-POC-DATA-PERMISSION.md](docs/archive/RUOYI-POC-DATA-PERMISSION.md) |
| 学生管理切片 S1–S3 | 🧪 POC 通过 | 列表/详情/修改 + 12 项测试 | [RUOYI-POC-STUDENT-SLICE.md](docs/archive/RUOYI-POC-STUDENT-SLICE.md) |
| 配套 React 前端 | 🧪 POC 通过 | 生产构建成功、真实登录、动态菜单 | [RUOYI-POC-AUTH-RESULTS.md](docs/archive/RUOYI-POC-AUTH-RESULTS.md) §13.2 |
| **正式迁移** | 🟡 **PR-B/C/D 已实现，待评审** | 网关、学生域、导入域与统一入口均已进入主项目并通过端到端验证；PR 未合并 | [PROJECT-ROADMAP.md](PROJECT-ROADMAP.md) |
| 认证与权限（主系统） | 🟡 默认关闭 | 验签 + 权限点 + 学院范围已实现；`INTERNAL_AUTH_ENABLED=false` 保持关闭，正式切换需人工批准 | [INTERNAL-AUTH-SPEC.md](docs/INTERNAL-AUTH-SPEC.md) |
| 学生域网关（PR-B） | 🟡 PR 待评审 | 真实 RuoYi 登录 → 网关签名 → FastAPI 验签 → 学院范围 → 审计 actor | PR #21 |
| 导入域隔离（PR-C） | 🟡 PR 待评审 | 批次归属部门 + 逐行学院校验 + 批次/异常表审计；管理员硬限制已解除 | PR #22 |
| 统一入口（PR-D） | 🟡 PR 待评审 | 学生/聚合/导入全部经 `/gw`；移除 `/api` 与宿主 8010；multipart 经网关签名 | PR 描述 |
| AI 能力（Dify 等） | ❌ 未开始 | 按计划排在认证与权限之后 | [ADR-001-import-mapping.md](docs/ADR-001-import-mapping.md) |

🧪 = 结论仅在隔离 POC 成立，**不代表生产环境已具备同等保护**。

### 3.1 已知未完成 / 未验证

- 关闭态（默认）接口保持旧行为、无认证；开启态已有 HMAC 验签 + 权限点 + 学院范围；
- 正式库尚未执行 `004`、`005`、`006`；隔离库升级与回退演练已完成（详见 [PR-E 验收报告](docs/PR-E-ACCEPTANCE-REPORT.md)）；
- 现行认证契约见 [INTERNAL-AUTH-SPEC.md](docs/INTERNAL-AUTH-SPEC.md)，阶段与顺序见 [PROJECT-ROADMAP.md](PROJECT-ROADMAP.md)；旧认证方案已归档，禁止作为实施依据；
- PR-E 已实测：并发学生更新、并发导入提交、9MB 文件、nonce 增长与周期清理、1000 行批量审计；**仍未验证**：数据库异常注入回滚、长时间多用户压测。

---

## 4. 环境要求

### 4.1 主系统

| 项目 | 要求 | 本机实测 |
|---|---|---|
| 操作系统 | Windows 11 + Docker Desktop | Windows 11 |
| Docker | Docker Desktop，固定版本标签 | Engine 29.2.0 / Compose v5.0.2 |
| 内存 | 建议 8 GB 以上（当前主栈 db/api/web 实测约 1–2 GB） | 31.8 GB |
| 磁盘 | 项目盘剩余 ≥ 15 GB | Z: 141 GB 可用（代码）/ F: 27 GB 可用（镜像与数据卷） |
| 端口 | 8082、55432、55434、6382、9190 未被占用（8010 已随 PR-D 取消宿主发布；8081/8443 随 Appsmith 下线已释放） | 已确认（5432/8000/8080 被其他服务占用，故整体避开） |
| PostgreSQL | 16.15（镜像 `postgres:16.15-alpine`） | 容器内 |
| JDK / Maven | 21 / 3.9+（仅构建 gateway） | 已安装（`C:\Program Files\Java\jdk-21`） |
| Python | 3.12（镜像 `python:3.12-slim`） | 仅构建期；运行时在容器内 |
| Node.js | 不需要 | 前端在容器内构建（2026-10-21 起）；仅修改前端代码时本地装 Node 更方便 |

**磁盘告警阈值**：低于 10 GB 时停止拉取新镜像并提示清理；低于 5 GB 时禁止大批量导入。用 `./scripts/check-disk.sh` 快速检查。

### 4.2 独立 POC（可选）

| 组件 | 版本 |
|---|---|
| JDK | 21（本机 `C:\Program Files\Java\jdk-21`） |
| Node / pnpm | ≥ 20.19 / ≥ 10（前端固定 `pnpm@10.34.5`） |
| Redis | 7.4（镜像 `redis:7.4-alpine`） |
| Maven | 3.9+（工程自带 `mvnw`） |

---

## 5. 目录结构

```text
campus-data-ai/
├─ gateway/                   # RuoYi 网关（登录、权限点、学生/聚合/导入签名代理）
├─ docker-compose.yml          # 主栈：campus-db / import-api / gateway(-db/-redis)（Appsmith 已下线）
├─ docker-compose.web.yml      # 前端独立栈（campus-web）
├─ import-api/                 # FastAPI 服务（含 wheels 离线依赖）
├─ web/                        # React + TypeScript + Ant Design 前端
├─ sql/                        # 001 表结构 / 002 视图 / 003 最小权限角色
├─ scripts/                    # backup / restore / fetch-wheels / check-disk
├─ samples/                    # 虚构样例数据（可提交）
├─ docs/                       # 全部设计与验收文档（索引见 docs/README.md）
└─ .env                        # 本地凭据（禁止提交；模板见 .env.example）
```

---

## 6. 快速开始（主系统）

### 6.1 准备配置

```bash
git clone https://github.com/123asdtte/campus-data-ai.git
cd campus-data-ai
cp .env.example .env      # 然后逐项替换 __CHANGE_ME_* 占位符
```

密码生成：`openssl rand -base64 24`。`.env` 已被 `.gitignore` 排除，**不要提交**。

### 6.2 启动

```bash
docker compose up -d --build             # db / import-api（镜像自动构建）
docker compose exec -T campus-db psql -U campus_dba -d campus \
  -v app_password="$APP_DB_PASSWORD" -v ro_password="$RO_DB_PASSWORD" \
  -q -f - < sql/003_roles.sql          # 最小权限账号（只做一次）
docker compose exec -T campus-db psql -U campus_dba -d campus \
  -q -f - < sql/004_internal_auth.sql  # 内部认证 nonce 表（可重复执行）
docker compose exec -T campus-db psql -U campus_dba -d campus \
  -q -f - < sql/006_import_scope.sql   # 导入批次归属 + 批次审计（可重复执行）
```

> 初始化顺序是 **001 → 003 → 004 → 006**；`005_gateway_bootstrap.sql` 只用于独立认证库
> `campus_gateway`（由 gateway-db 容器首次启动时自动执行），**不要**在业务库执行。
> `002_seed_demo.sql` 是本地演示数据，
> 且会宽范围删除审计记录，**不要用于测试库或生产库**。
> 测试库一键初始化：`python scripts/init-test-db.py --admin-dsn <DSN> --verify`。

前端（独立栈，同样容器内构建，**无需宿主机 Node**）：

```bash
docker compose -p campus-web -f docker-compose.web.yml up -d --build
```

网关（需要 JDK 21 + Maven；首次构建约 2–3 分钟）：

```bash
cd gateway
mvn -B -DskipTests -pl ruoyi-admin -am package
cd ..
docker compose up -d gateway-db gateway-redis     # 独立认证库 + 会话缓存
docker compose up -d --build gateway              # 登录 + 学生/聚合/导入签名代理
```

> 2026-10-21 起前端改为多阶段构建（node:22-alpine 容器内 npm ci + vite build），
> 构建阶段显式绕开 Docker Desktop 注入的失效代理，直连官方源。
> 若你的网络无法直连 PyPI/npm，再退回离线路径：`./scripts/fetch-wheels.sh` + 宿主机构建（见 §14）。

### 6.3 访问入口

| 服务 | 地址 |
|---|---|
| React 前端 | http://127.0.0.1:8082 （统一入口；业务请求经 `/gw/`） |
| Gateway | http://127.0.0.1:9190 （登录 + 学生/聚合/导入代理） |
| Import API | **仅容器内网** `import-api:8000`（PR-D 起无宿主端口） |
| Gateway DB / Redis | 127.0.0.1:55434 / 6382（独立于业务库） |
| Appsmith（历史方案，已下线） | 不再提供（2026-10-22 R2：容器停止、compose 移除、卷保留） |
| PostgreSQL | 127.0.0.1:55432（库 `campus`） |

### 6.4 内部认证开关（默认关闭）

| 开关 | 行为 |
|---|---|
| `INTERNAL_AUTH_ENABLED=false`（默认） | 11 个业务接口保持旧行为；`PUT /students/{no}` **不注册**（405） |
| `INTERNAL_AUTH_ENABLED=true` | 所有业务接口要求 `X-Internal-*` 签名；`PUT` 注册 |

```bash
# 生成密钥（≥32 字符），同时写入网关与服务端
openssl rand -hex 32
# .env: INTERNAL_AUTH_ENABLED=true / INTERNAL_HMAC_SECRET=<同一个值>
docker compose up -d --force-recreate import-api
```

- 开关在进程导入期定型，修改后必须重建容器；
- 开启前先执行 `sql/004_internal_auth.sql`，否则启动即失败；
- 健康检查：`/health` 为 liveness（只返回 `{"status":"ok"}`），`/health/ready` 为数据库就绪探针；
- 规范见 `docs/INTERNAL-AUTH-SPEC.md`，迁移路线见 `docs/SECURITY-MIGRATION-EXECUTION-PLAN.md`。

### 6.5 日志、停止与恢复

```bash
docker compose logs -f import-api
docker compose ps                       # 健康状态
docker compose stop                     # 停止
docker compose up -d                    # 恢复
docker compose -p campus-web -f docker-compose.web.yml logs -f
```

---

## 7. 独立 POC 的启动（可选，仓库之外）

见 `Z:\ai\本地部署\ruoyi-plus-poc\` 下的 `docker-compose.poc.yml` 与 `test_slice.sh`。
**POC 使用自己的数据库、Redis 与凭据文件 `.env.poc`，与主系统完全隔离。**

---

## 8. 测试现状

`import-api/tests/` 已建立，`pytest` 接入 CI（`.github/workflows/ci.yml` 的 `backend-tests` job）。
用例分三层，按「是否需要数据库」切开：

| 层次 | 文件 | 覆盖内容 | 依赖 |
|---|---|---|---|
| 表头与映射 | `test_mapping.py`、`test_parsing.py` | 规范化、别名、包含匹配、冲突、未知列、多工作表、表头定位、重名列 | 无 |
| 校验规则 | `test_validation.py`、`test_business_rules.py` | 类型预转换、必填/长度/枚举/范围、行号偏移、学号重复与库内已存在 | 无 |
| 接口契约 | `test_api_contract.py` | 400/413/422 拒绝路径、base64 入口、健康检查降级 | 无（不触发 lifespan） |
| 真库集成 | `test_db_integration.py` | 状态机、幂等 409、事务、**审计触发器与业务同事务** | PostgreSQL |
| 安全·关闭态 | `test_auth_disabled.py` | OpenAPI 无 PUT、405 无副作用、旧行为回归 | 无 |
| 安全·开启态 | `test_internal_auth.py`、`test_route_matrix.py` | 缺头/篡改/过期/重放/权限/范围、11×5 矩阵 | PostgreSQL |
| Java 网关 | `gateway/` | `mvn -B -DskipTests -pl ruoyi-admin -am package` | JDK 21 + Maven |

**CI 实查（2026-10-22）**：关闭态 collected 213（**130 passed / 82 skipped / 1 xfailed**）；开启态 collected 88（**88 passed**）。

```bash
cd import-api
pip install -r requirements-dev.txt

python -m pytest                      # 前三层；真库用例自动 skip
CAMPUS_TEST_DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/campus_test \
  python -m pytest                    # 额外跑真库集成用例
```

真库用例会 **TRUNCATE 业务表**，只能指向独立测试库；CI 用 `postgres:16.15-alpine` service
并先执行 `python scripts/init-test-db.py` 建结构。**禁止把该变量指向主库 `campus`。**

本轮尚未覆盖（仍是空白，不是「已验证」）：

- 提交阶段的数据库异常注入与回滚；
- 并发对同一批次的提交（当前靠 `UPDATE ... WHERE batch_status='validated'` 兜底，未压测）；
- 超大文件（接近 10 MB / 10,000 行）；
- 前端交互仍靠人眼，Playwright 脚本在仓库之外的 POC 目录。

验收全部使用 **`samples/` 下的虚构数据**（学号形如 `SMPL2026xxxx`、`DEMO2021xxxx`）。**禁止把真实学生数据带入任何开发或验证环境。**

---

## 9. 导入接口速览

```bash
# 先登录网关获得 token（账号需具备 import:batch:* 权限点）
TOKEN=$(curl -s -X POST http://127.0.0.1:8082/gw/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"clientId":"e5cd7e4891bf95d1d19206ce24a7b32e","grantType":"password","username":"admin","password":"admin123","tenantId":"000000"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["data"]["access_token"])')

BASE=http://127.0.0.1:8082/gw/internal/proxy
AUTH=(-H "Authorization: Bearer $TOKEN" -H "clientid: e5cd7e4891bf95d1d19206ce24a7b32e")
# 1) 预览：识别工作表/表头/字段映射，返回 batch_id
curl "${AUTH[@]}" -X POST "$BASE/imports/preview" -F "file=@samples/students_clean.xlsx" -F "target_type=students"
# 2) 校验：写入异常明细，返回有效/异常行数
curl "${AUTH[@]}" -X POST "$BASE/imports/$BATCH/validate"
# 3) 提交：事务写入；重复提交返回 409
curl "${AUTH[@]}" -X POST "$BASE/imports/$BATCH/commit"
```

> PR-D 起 FastAPI 无宿主端口，以上命令必须经 `/gw`；直接访问 `127.0.0.1:8010` 会被拒绝。

完整说明见 [IMPORT-API.md](docs/IMPORT-API.md)。

---

## 10. 操作审计

- 业务表 `students` / `student_changes` 与导入批次表 `import_batches` / `import_issues` 均挂审计触发器；
- 操作人来自事务级 `set_config('campus.actor_user_id', ...)`，与业务写入**同一事务**——回滚时审计一并回滚；
- 审计表同时记录**数据库连接账号**（`actor_db_role`）与业务操作人（`actor_user_id`）；
- 敏感字段在写入审计前被剔除（`audit_payload()`）。

> ⚠️ 默认关闭态：操作人来自客户端可伪造的 `X-Actor`，**只具备演示价值**；
> 开启态：操作人来自验签通过的 `X-Internal-User`，PR-B/C/D 已完成端到端验证，正式切换待人工批准。

---

## 11. 备份与恢复

```bash
./scripts/backup.sh          # 生成 backups/campus_<时间戳>.sql.gz（不覆盖旧备份）
./scripts/restore.sh         # 交互式恢复，需二次确认
./scripts/check-disk.sh      # 磁盘余量检查
```

部署或迁移前务必先备份，并核对备份内行数与当前库一致。

---

## 12. 常用运维命令

```bash
docker compose ps
docker compose logs -f import-api
docker compose exec -T campus-db psql -U campus_dba -d campus
docker compose -p campus-web -f docker-compose.web.yml ps
```

---

## 13. 安全与注意事项（必读）

1. **不要提交**：`.env`、数据库备份（`backups/*.sql.gz`）、上传目录、任何真实学生数据、访问令牌。`.gitignore` 已覆盖，提交前请再确认一次 `git status`。
2. **不要分发凭据**：数据库密码、HMAC 密钥一律不通过微信/邮件/仓库文件传递；Appsmith 已下线，其历史加密密钥仅作留档，不得复用。新同事从 `.env.example` 开始，用自己的本地配置与独立数据库。
3. **POC 的加密关闭配置仅限 POC**：`--api-decrypt.enabled=false` 与 `VITE_APP_ENCRYPT=false` 不得用于生产；生产必须明确传输保护方案。
4. **POC 数据库与主库必须分离**：禁止把 POC 指向主库 `campus`。
5. **既有测试记录不要动**：批次 27（2007 行待提交）与批次 37 的暂存文件属于验收证据，不得删除、覆盖或重新提交。
6. **POC 通过 ≠ 生产就绪**：POC 结论只在隔离环境成立，主项目尚未合并任何认证/授权实现。
7. **不要把 RuoYi POC 代码与文档整理混在一次提交里**：文档整理独立成 commit，便于回退。

---

## 14. 已知限制

- 运行时容器无外网出口（Docker Desktop 注入失效代理）：构建阶段已绕开，但容器内不能再跑 pip/npm；
- 仅支持 `.xlsx` / `.xlsm` / `.csv`，不支持 `.xls`、多层合并表头、加密工作簿；
- 提交成功后暂存目录的 `.mapping.json` 不会被删除（已知小缺陷）；
- Appsmith 已按 R2 下线（容器停止、compose 移除、数据卷与配置保留，可受控恢复）；`campus_app` 账号仍存在，留待 PR-B 最小权限治理。

---

## 15. 文档与协作

- 文档总索引：[docs/README.md](docs/README.md)
- 贡献与分支规范：[CONTRIBUTING.md](CONTRIBUTING.md)
- Git 工作流细则：[docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md)
- 技术选型决策：[docs/ADR-001-import-mapping.md](docs/ADR-001-import-mapping.md)
