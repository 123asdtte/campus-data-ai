# Docker 环境审计（第一阶段只读取证）

- **日期**：2026-10-21
- **方法**：只读检查 Compose / Dockerfile / 脚本 / 运行中容器 / Git 跟踪状态；**未修改任何文件或容器**
- **目的**：为「新同事可从干净电脑复现环境」找出差距

---

## 1. Compose 与服务清单（以实际文件为准）

### 1.1 主系统 `docker-compose.yml`（项目名 = 目录名 `campus-data-ai`）

| 服务 | 镜像 | 端口（仅 127.0.0.1） | 数据卷 | 健康检查 |
|---|---|---|---|---|
| `campus-db` | postgres:16.15-alpine | 55432→5432 | `campus_pgdata` + `./sql` 初始化挂载 | pg_isready |
| `appsmith` | appsmith-ce:v2.5.0 | 8081→80, 8443→443 | `campus_appsmith_stacks` | 自带 |
| `campus-import-api` | `campus-import-api:0.1.0`（本地构建） | 8010→8000 | `campus_uploads` + `./samples` 只读 | HTTP /health |

网络：`campus-net`（bridge，显式命名）。日志轮转 json-file 10m×3。

### 1.2 前端独立栈 `docker-compose.web.yml`（项目名 `campus-web`）

| 服务 | 镜像 | 端口 | 依赖 |
|---|---|---|---|
| `campus-web` | `campus-data-web:0.1.0`（本地构建，nginx 1.29-alpine） | 8082→80 | 无（独立于主栈网络） |

构建上下文 `web/`，`Dockerfile.web` 只 `COPY dist`——**前提是宿主机已执行 `npm run build`**。

### 1.3 POC `Z:\ai\本地部署\ruoyi-plus-poc\docker-compose.poc.yml`（项目名 `ruoyi-poc`，仓库之外）

| 服务 | 镜像 | 端口 | 说明 |
|---|---|---|---|
| `poc-db` | postgres:16.15-alpine | 55433→5432 | 卷 `ruoyi_poc_pgdata`，初始化脚本挂载 |
| `poc-redis` | redis:7.4-alpine | 6381→6379 | 带密码 |
| `poc-api` | **复用 `campus-import-api:0.1.0`** | 无发布端口 | 挂载简化验签服务 |
| `poc-importapi` | **复用 `campus-import-api:0.1.0`** | 无发布端口 | 挂载业务代码副本 |
| `poc-java` | `ruoyi-poc-java:6.0.0`（本地构建） | 9180→9180 | eclipse-temurin:21-jre |

网络：`ruoyi-poc-net`（独立）。凭据来自 `.env.poc`（**含真实生成密码，195 字节，绝不入库**）。

---

## 2. Dockerfile 清单

| 文件 | 基础镜像 | 用途 | 关键点 |
|---|---|---|---|
| `import-api/Dockerfile` | python:3.12-slim | Import API | **优先离线装 `wheels/*.whl`**，否则回退 PyPI；非 root 用户 |
| `web/Dockerfile.web` | nginx:1.29-alpine | 前端 | 只 `COPY dist`，**须先宿主机构建** |
| POC `backend/Dockerfile.poc` | eclipse-temurin:21-jre | Java 网关 | 只 `COPY ruoyi-admin/target/ruoyi-admin.jar`，**须先宿主机构建** |

---

## 3. CI 与脚本现状

| 项 | 现状 |
|---|---|
| `.github/workflows/ci.yml` | 前端 `npm ci + tsc + build`；后端语法/导入检查；**pytest 双模式（关闭态 130 passed / 开启态 88 passed）与 AI 评审**；仍无 Docker 构建验证 |
| `scripts/fetch-wheels.sh` | 在宿主机按 `manylinux/cp312` 预下载 wheel 到 `import-api/wheels/`（该目录已 gitignore，新克隆为空） |
| `scripts/backup.sh / restore.sh / check-disk.sh` | 备份/恢复/磁盘检查，restore 需 `.env` 中 `APP_DB_PASSWORD`、`RO_DB_PASSWORD` |

---

## 4. 「远程仓库 vs 仅本机」清单

### 4.1 在远程仓库中（新同事克隆即可获得）

- 主系统全部源码：`web/`、`import-api/app`、`sql/`、`scripts/`、两个主 Compose、`Dockerfile*`、`.env.example`、`samples/`（虚构数据）、`docs/`。
- **不包含**：`wheels/*.whl`（已 ignore，需跑 `fetch-wheels.sh`）、`web/dist`（须宿主机构建）、`import-api/tests`（尚不存在）。

### 4.2 仅存在于本机（当前同事拿不到）

> **状态更新（2026-10-22）**：POC 已整理为独立仓库 `campus-ruoyi-poc`（PR #3 合并，origin/main `f1c2856`），下表"仅存在于本机"描述的是整理前状态。

| 内容 | 位置 | 状态 |
|---|---|---|
| RuoYi 后端定制（5 个文件） | `ruoyi-plus-poc/backend`（上游 shallow clone + 未提交修改） | **未提交、未推送** |
| React 前端定制（4 个文件） | `ruoyi-plus-poc/ui-react`（分支 6.X-React @ `25e69f1`） | **未提交、未推送** |
| FastAPI 业务副本 + 定制（3 处差异） | `ruoyi-plus-poc/import-api-poc/app`（普通目录，非 Git） | 未版本化 |
| 简化验签服务、POC Compose、SQL 夹具、测试脚本 | `ruoyi-plus-poc/*` 根目录散文件 | 未版本化 |
| `.env.poc`（含 POC 密码） | 同上 | **敏感，禁止入库** |
| Maven 本地仓库 `.m2`（~数百 MB） | 同上 | 不入库，构建时重新下载 |

### 4.3 跨栈依赖

- POC 的 `poc-api` 与 `poc-importapi` 复用**主项目构建的镜像** `campus-import-api:0.1.0`——POC 环境隐式依赖主项目先执行过 `docker compose build import-api`。

---

## 5. 已知环境问题（本次与历史实测）

| # | 问题 | 影响 | 规避 |
|---|---|---|---|
| 1 | 容器运行时无外网（Docker 注入 `HTTP_PROXY=127.0.0.1:8080` 指向容器内不存在的地址） | 运行时 pip/npm 全挂；健康检查不能用 busybox wget | 构建在宿主机完成；健康检查用 `curl --noproxy '*'`；**不要改全局 Docker 代理** |
| 2 | 端口 8000 被 diet-gateway（0.0.0.0）占用 | 任何想用 8000 的服务（含 Umi dev）冲突 | 主/POC 端口规划避开 8000 |
| 3 | 容器内 `127.0.0.1` 指向容器自身 | 服务互访必须用 Compose 服务名 | 已在所有配置落实 |
| 4 | 前端构建产物 `web/dist` 被 gitignore | 新同事直接 `compose build` 会因缺 dist 失败 | 文档已写「先宿主机构建」；标准化 Issue 需把该步骤脚本化 |
| 5 | `import-api/wheels` 为空目录（gitignore） | 新同事离线构建失败 | 文档已写「先跑 fetch-wheels.sh」 |
| 6 | Umi `max dev` 在本机不监听 | 前端开发调试受阻 | POC 用「构建产物 + 静态代理」验证；标准化的 dev 流程待解决 |
| 7 | Java 构建需 JDK 21，而本机 `JAVA_HOME` 指向 17 | Maven 报「不支持发行版本 21」 | 构建命令显式指定 JAVA_HOME；标准 Issue 需固化 |

---

## 6. 问题分级与第二阶段修复建议

| 级别 | 事项 |
|---|---|
| **P0** | ✅ 已完成：POC 定制代码已整理为独立仓库 `campus-ruoyi-poc`（PR #3），方案见 `../../ruoyi-plus-poc/README.md` |
| P1 | 前端「宿主机构建 → 静态托管 → 代理」流程脚本化（`scripts/dev/up-web.ps1` 等），消除对手工命令的依赖 |
| P1 | `fetch-wheels.sh` 纳入主栈首次启动前置检查（检测 wheels 为空时提示） |
| P2 | CI 增加「Compose 配置语法校验」与「Dockerfile 构建」任务 |
| P2 | Umi dev server 不监听问题单独排查（疑似与 `max dev` 的端口检测有关） |
| P2 | 文档化 Windows 下 `JAVA_HOME` 切换（或提供 `scripts/dev/build-java.ps1`） |

**第二阶段红线**：不修改主栈 Compose 的服务结构；`down -v` 类清理必须独立命令并带二次确认；健康检查与内部调用不得依赖外网地址。

---

## 7. 未验证项

- 未在一台「干净电脑」上实测完整克隆→构建→启动流程（本机已有缓存与镜像，结论存在幸存者偏差）；
- 未验证 Maven 在干净环境下拉取 SpringBoot 4.1 全量依赖的耗时与成功率（本机 `.m2` 已有缓存）；
- 未验证 WSL2 后端下 bind mount 的性能（当前用 Windows 路径挂载，SQLite 类高频写场景可能受影响，本项目场景不明显）。
