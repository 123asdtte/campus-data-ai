# POC 全新克隆复现报告

- **日期**：2026-10-21
- **仓库**：`campus-ruoyi-poc`（PRIVATE）
- **基线**：`7b39fa6`（验证起点）→ `7d3df69`（修复后）
- **结论**：**修复后可从全新克隆完整复现**（构建 → 启动 → 12/12 测试通过）；修复前**无法启动**

---

## 1. 验证方法

| 项 | 做法 |
|---|---|
| 隔离 | 在 `Z:/ai/本地部署/.tmp/poc-fresh/` 全新 `gh repo clone`，不复用开发目录 |
| 数据 | 全新数据卷（`fresh_poc_pgdata`），由 `sql/01–06` 从零初始化 |
| 镜像 | 用新克隆产物重新 `mvn package` + `docker build`，不复用旧镜像 |
| 端口/容器名 | 保持默认（55433/6381/9180），验证期间临时停掉原 POC 栈 |
| 主项目 | 未修改、未连接 |

---

## 2. 修复前发现的阻塞问题（6 项）

| # | 问题 | 现象 | 严重度 |
|---|---|---|---|
| 1 | 仓库残留 `poc-config/`，内含**未经过滤的** `application-dev.yml`（`@monitor.username@` 占位符），且 compose 把它挂到 `/app/config` | Spring 默认加载该目录 → YAML 解析失败，**启动即崩** | 阻断 |
| 2 | `docker-compose.poc.yml` 缺 `--api-decrypt.enabled=false`（`--captcha.enable=false` 已有） | 登录被加密过滤器拦截，返回 **403「没有访问权限」** | 阻断 |
| 3 | 全新库缺 `campus_app` 角色、授权与 `campus.poc_nonce` 表——这些在原环境是**手工创建**，从未入库 | `poc-importapi` 连接池 30s 超时后退出 → 代理请求 500 | 阻断 |
| 4 | 测试夹具缺 `poc_readonly`（无角色账号），T7 低权限用例无法执行 | T7 取不到 token，退化为 401 | 高 |
| 5 | `test_slice.sh` 的 T9 走 `127.0.0.1:8090`（**主系统**的静态代理），不是 POC 自身端口 | 在纯 POC 环境不构成有效验证（空响应/502） | 中 |
| 6 | `sql/05` 若用 `.sh` 实现，Windows 挂载丢失执行位 | 容器启动报 exit 126 | 中（实现方式已规避） |

> 另有一项**非仓库问题**：compose 固定 `container_name`，同一台机器无法并行跑两套 POC 栈（验证时用临时 override 规避）。记录为已知限制，不阻塞新开发者。

---

## 3. 修复内容（PR #1，commit `ad0a969` / `f2a7604`）

| 修复 | 文件 |
|---|---|
| 删除残留配置目录与挂载 | `poc-config/`（删除）、`docker-compose.poc.yml` |
| 补 POC 专用参数并注明生产不可照搬 | `docker-compose.poc.yml` |
| 新增最小权限账号与 nonce 表（密码用 `\getenv` 从容器环境读取，不落盘） | `sql/05_poc_app_role.sql`、`sql/06_poc_app_grants.sql` |
| 夹具补无角色账号 | `sql/03_datascope_fixture.sql` |
| T9 改为带 token 经 9180 的伪造头测试并核对审计 | `test_slice.sh` |
| 说明首次启动自动执行 01–06 | `README.md` |

---

## 4. 修复后实测证据（全新克隆 + 全新卷）

**构建**

| 步骤 | 结果 |
|---|---|
| `mvn -DskipTests -pl ruoyi-admin -am package`（JDK 21，全新 `~/.m2`） | **BUILD SUCCESS，9 分 46 秒**（含全量依赖下载） |
| `docker build -f backend/Dockerfile.poc` | 成功，jar 245 MB |
| `docker compose up -d` | 5 个容器全部启动；首次 init 自动建表、建角色、灌虚构数据 |

**初始化校验**

```
campus_app 角色   = 1
campus.poc_nonce  = 1
sys_user 5 条（admin / poc_college_a / poc_college_b / poc_readonly / test...）
campus.students   = 4（两个学院各 2 条虚构数据）
```

**12 项测试（`bash test_slice.sh`）**

| # | 结果 |
|---|---|
| token 获取 | A=519 / B=523 / readonly=513 / admin=504（均成功） |
| T1 学院 A 列表 | 只含「计算机学院」 |
| T2 传 `college=电子信息学院` | 仍只见本学院（参数不能扩范围） |
| T3 跨学院详情 | **403** `越权：不能查看其他学院的学生` |
| T4 跨学院修改 | **403**；DB 复查 `POCB0001=乙同学` **未变** |
| T5 本学院修改 | **200**，`student_status: enrolled→suspended` |
| T6 审计 | `ry:poc_college_a / campus_app / update / {student_status,updated_at}` |
| T7 低权限修改 | 业务码 **403**（Java 权限点拦截） |
| T8 无效 token | **401** |
| T9 伪造 `X-Actor`/`X-Poc-*` | 写入成功但审计仍为 `ry:poc_college_a`（伪造无效） |
| T10 直连内部 FastAPI | 无宿主端口；跨网络不可达 |
| T11 分页/参数变化 | 仍只含本学院 |
| T12 非法字段 422 | 审计条数 5→5（无残留）、无脏数据 |

---

## 5. 许可证与第三方代码核查

| 项 | 结果 |
|---|---|
| RuoYi-Vue-Plus 后端 | 仓库内保留 `backend/LICENSE`（MIT，Copyright 2019 RuoYi-Vue-Plus） ✓ |
| plus-ui 前端 | 上游 GitHub 标记 **MIT**，但**该 commit 根目录没有 LICENSE 文件**，`package.json` 也无 `license` 字段 ⚠️ |
| FastAPI 副本 | 本项目自有代码，随主仓库分发 |
| 建议 | 在 POC 仓库补 `THIRD-PARTY-NOTICES.md`，写明两个上游仓库、commit、MIT 许可与版权归属；不因此认定「无附加义务」 |

---

## 6. 未验证 / 剩余风险

| # | 项 | 说明 |
|---|---|---|
| 1 | **前端（ui-react）全新构建未在本次复跑** | 上次在原环境验证过（`pnpm install` 6m35s + `build` 33s）；全新克隆下依赖下载与构建**属待验证** |
| 2 | 未在**物理干净机**（无 Docker 缓存、无镜像）上跑过 | 本机已有基础镜像缓存，首次 `docker pull` 耗时未知 |
| 3 | 依赖下载依赖网络 | Maven/NPM/PyPI 均走直连；离线环境需另备 wheels 与 npm 缓存 |
| 4 | 固定容器名 | 同机不能并行两套栈；如需并行，需加 `COMPOSE_PROJECT_NAME` 与端口参数化 |
| 5 | 许可证缺口 | 见 §5 |

---

## 7. 结论与下一步

**「已推到 GitHub」与「别人能拿下来跑起来」之间的差距，这次是 4 个真实阻塞。** 修复后，新开发者按 README 三步即可：

```bash
gh repo clone 123asdtte/campus-ruoyi-poc
cp .env.poc.example .env.poc      # 填自己的密码
docker compose -p ruoyi-poc -f docker-compose.poc.yml --env-file .env.poc up -d --build
bash test_slice.sh                # 12/12
```

下一步建议：把 ui-react 的全新构建补进验收（或写进 Issue #3 的 Docker 标准化范围），并补 `THIRD-PARTY-NOTICES.md`。
