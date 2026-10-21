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
  │  /api/* 反向代理（剥前缀）
  ▼
campus-import-api FastAPI + pandas/openpyxl     解析 / 校验 / 入库 / 审计上下文
  │  psycopg + 事务级 set_config('campus.actor_user_id')
  ▼
campus-db         PostgreSQL 16.15               业务表 + 审计触发器
                    │
                    └─ operation_logs（触发器写入，与业务同事务）

campus-appsmith   Appsmith CE v2.5.0            低代码界面（历史方案，非主入口）
```

- 所有端口只绑定 `127.0.0.1`，不对局域网/公网暴露。
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
| Excel 解析与表头识别 | ✅ 已完成 | 多工作表、前 15 行表头定位、别名/模糊匹配、冲突与未知列处理 | [IMPORT-MAPPING-TEST.md](docs/IMPORT-MAPPING-TEST.md) |
| 导入闭环（预览→校验→提交） | ✅ 已完成 | 幂等保护、事务回滚、异常带 Excel 行号 | [IMPORT-API.md](docs/IMPORT-API.md) |
| 审计链路 | ✅ 已完成 | 触发器写 `operation_logs`，actor 来自事务级 GUC | [§10](#10-操作审计) |
| React 查询与导入页 | ✅ 已完成 | 20 项浏览器验收通过，生产构建与容器化部署 | [REACT-TEST-REPORT.md](docs/REACT-TEST-REPORT.md) |
| 部署与回退 | ✅ 已完成 | 前端独立栈，停止/恢复主栈不受影响 | [DEPLOY-ACCEPTANCE-1.3.md](docs/DEPLOY-ACCEPTANCE-1.3.md) |
| RuoYi 真实登录与身份贯通 | 🧪 POC 通过 | 登录 → Java 签名 → FastAPI 验签 → 审计 actor 正确 | [RUOYI-POC-AUTH-RESULTS.md](docs/RUOYI-POC-AUTH-RESULTS.md) |
| 数据权限专项 | 🧪 POC 通过 | 框架 Mapper 与实际业务路径**分别**取证 | [RUOYI-POC-DATA-PERMISSION.md](docs/RUOYI-POC-DATA-PERMISSION.md) |
| 学生管理切片 S1–S3 | 🧪 POC 通过 | 列表/详情/修改 + 12 项测试 | [RUOYI-POC-STUDENT-SLICE.md](docs/RUOYI-POC-STUDENT-SLICE.md) |
| 配套 React 前端 | 🧪 POC 通过 | 生产构建成功、真实登录、动态菜单 | [RUOYI-POC-AUTH-RESULTS.md](docs/RUOYI-POC-AUTH-RESULTS.md) §13.2 |
| **正式迁移** | ❌ **未开始** | S1–S3 的**实现代码尚未进入主项目**，仓库内只有验收文档 | [API-MIGRATION-INVENTORY.md](docs/API-MIGRATION-INVENTORY.md) |
| 认证与权限（主系统） | ❌ 未实现 | 主系统 12 个接口目前**均无认证**，`X-Actor` 可伪造 | [SECURITY-AUTH-DESIGN.md](docs/SECURITY-AUTH-DESIGN.md) |
| AI 能力（Dify 等） | ❌ 未开始 | 按计划排在认证与权限之后 | [ADR-001-import-mapping.md](docs/ADR-001-import-mapping.md) |

🧪 = 结论仅在隔离 POC 成立，**不代表生产环境已具备同等保护**。

### 3.1 已知未完成 / 未验证

- 主系统接口无认证、无角色、无数据范围强制（`/students` 的 `college` 参数只是过滤器）；
- `import_batches`、`import_issues` **无审计触发器**；
- 认证方案的技术选型见 [SECURITY-AUTH-DECISION.md](docs/SECURITY-AUTH-DECISION.md)，实施路线见 [SECURITY-AUTH-ROADMAP.md](docs/SECURITY-AUTH-ROADMAP.md)；
- 边界项：数据库异常注入回滚、并发修改、nonce 表 TTL 清理均未验证。

---

## 4. 环境要求

### 4.1 主系统

| 项目 | 要求 | 本机实测 |
|---|---|---|
| 操作系统 | Windows 11 + Docker Desktop | Windows 11 |
| Docker | Docker Desktop，固定版本标签 | Engine 29.2.0 / Compose v5.0.2 |
| 内存 | 建议 16 GB 以上（Appsmith 约占 2–4 GB） | 31.8 GB；当前容器实测占用约 3.2 GB |
| 磁盘 | 项目盘剩余 ≥ 15 GB | Z: 141 GB 可用（代码）/ F: 27 GB 可用（镜像与数据卷） |
| 端口 | 8081、8443、55432、8010、8082 未被占用 | 已确认（5432/8000/8080 被其他服务占用，故整体避开） |
| PostgreSQL | 16.15（镜像 `postgres:16.15-alpine`） | 容器内 |
| Python | 3.12（镜像 `python:3.12-slim`） | 仅构建期；运行时在容器内 |
| Node.js | 20+ / npm | **仅构建前端时需要**（容器无外网，须在宿主机构建） |

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
├─ docker-compose.yml          # 主栈：campus-db / appsmith / import-api
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
docker compose up -d                     # db / appsmith / import-api
docker compose exec -T campus-db psql -U campus_dba -d campus \
  -v app_password="$APP_DB_PASSWORD" -v ro_password="$RO_DB_PASSWORD" \
  -q -f - < sql/003_roles.sql          # 最小权限账号（只做一次）
```

前端（独立栈，**须先在宿主机构建**）：

```bash
cd web && npm ci && npm run build && cd ..
docker compose -p campus-web -f docker-compose.web.yml build
docker compose -p campus-web -f docker-compose.web.yml up -d
```

> 容器内**没有外网出口**，不能 `npm install`，必须在宿主机构建后只拷产物。

### 6.3 访问入口

| 服务 | 地址 |
|---|---|
| React 前端 | http://127.0.0.1:8082 |
| Import API | http://127.0.0.1:8010 （`/health` 探活） |
| Appsmith（历史方案） | http://127.0.0.1:8081 |
| PostgreSQL | 127.0.0.1:55432（库 `campus`） |

### 6.4 日志、停止与恢复

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

| 层次 | 现状 |
|---|---|
| 后端自动化单元测试 | **目前没有** `import-api/tests` 目录，`pytest` 尚未接入 CI |
| 前端类型检查与构建 | `npm run build`（含 `tsc --noEmit`），CI 中已启用 |
| 浏览器验收 | 由 Playwright 驱动 Chromium 完成，脚本在 POC 目录（仓库外） |
| 验收报告 | 全部在 `docs/`，见 [docs/README.md](docs/README.md) |

验收全部使用 **`samples/` 下的虚构数据**（学号形如 `SMPL2026xxxx`、`DEMO2021xxxx`）。**禁止把真实学生数据带入任何开发或验证环境。**

---

## 9. 导入接口速览

```bash
BASE=http://127.0.0.1:8010
# 1) 预览：识别工作表/表头/字段映射，返回 batch_id
curl -X POST "$BASE/imports/preview" -F "file=@samples/students_clean.xlsx" -F "target_type=students"
# 2) 校验：写入异常明细，返回有效/异常行数
curl -X POST "$BASE/imports/$BATCH/validate"
# 3) 提交：事务写入；重复提交返回 409
curl -X POST "$BASE/imports/$BATCH/commit"
```

完整说明见 [IMPORT-API.md](docs/IMPORT-API.md)。

---

## 10. 操作审计

- 业务表 `students` / `student_changes` 上挂了 `trg_*_audit` 触发器；
- 操作人来自事务级 `set_config('campus.actor_user_id', ...)`，与业务写入**同一事务**——回滚时审计一并回滚；
- 审计表同时记录**数据库连接账号**（`actor_db_role`）与业务操作人（`actor_user_id`）；
- 敏感字段在写入审计前被剔除（`audit_payload()`）。

> ⚠️ 当前操作人来自客户端可伪造的 `X-Actor` 请求头，**只具备演示价值**，正式身份链路尚未落地。

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
2. **不要分发凭据**：数据库密码、Appsmith 加密密钥、HMAC 密钥一律不通过微信/邮件/仓库文件传递；新同事从 `.env.example` 开始，用自己的本地配置与独立数据库。
3. **POC 的加密关闭配置仅限 POC**：`--api-decrypt.enabled=false` 与 `VITE_APP_ENCRYPT=false` 不得用于生产；生产必须明确传输保护方案。
4. **POC 数据库与主库必须分离**：禁止把 POC 指向主库 `campus`。
5. **既有测试记录不要动**：批次 27（2007 行待提交）与批次 37 的暂存文件属于验收证据，不得删除、覆盖或重新提交。
6. **POC 通过 ≠ 生产就绪**：POC 结论只在隔离环境成立，主项目尚未合并任何认证/授权实现。
7. **不要把 RuoYi POC 代码与文档整理混在一次提交里**：文档整理独立成 commit，便于回退。

---

## 14. 已知限制

- 容器无外网出口：依赖需用 `scripts/fetch-wheels.sh` 预下载，前端需在宿主机构建；
- 仅支持 `.xlsx` / `.xlsm` / `.csv`，不支持 `.xls`、多层合并表头、加密工作簿；
- 提交成功后暂存目录的 `.mapping.json` 不会被删除（已知小缺陷）；
- Appsmith 目前仍持有可写数据库账号 `campus_app`，**属待处理的高风险项**。

---

## 15. 文档与协作

- 文档总索引：[docs/README.md](docs/README.md)
- 贡献与分支规范：[CONTRIBUTING.md](CONTRIBUTING.md)
- Git 工作流细则：[docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md)
- 技术选型决策：[docs/ADR-001-import-mapping.md](docs/ADR-001-import-mapping.md)
