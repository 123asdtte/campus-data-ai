# RuoYi POC 可复现性：取证结果与共享方案（第一阶段产出）

- **日期**：2026-10-21
- **状态**：取证完成，方案已给出推荐；**发布需经批准，本轮未推送、未建远程仓库**
- **关联 Issue**：[P0] 将 RuoYi POC 整理为可共享、可复现的开发环境

---

## 1. 取证结果

### 1.1 Git 状态

| 目录 | 是否 Git 仓库 | 上游 | 基线 | 未提交内容 |
|---|---|---|---|---|
| `ruoyi-plus-poc/`（根） | **否**，普通目录 | — | — | Compose、SQL 夹具、两个测试脚本、poc-api、poc-config、import-api-poc |
| `backend/` | 是（shallow clone） | `dromara/RuoYi-Vue-Plus` | tag **v6.0.0** @ `7180b52` | **5 项**：修改 `ruoyi-admin/pom.xml`、`application.yml`、`application-dev.yml`；新增 `Dockerfile.poc`、`PocProxyController.java` |
| `ui-react/` | 是（shallow clone） | `CrazyLionCat/plus-ui`，分支 `6.X-React` | **`25e69f1`** | **4 项**：修改 `.env.production`（POC 变量）、`vite.config.ts`（代理目标参数化）；新增 `.env.development.local`、`.env.production.bak` |
| `import-api-poc/` | 否（普通目录） | 基线 = 主项目 `import-api/app`（`d635d8e` 时期） | — | **3 处**：新增 `poc_auth.py`；`main.py` 三接口挂依赖+新增 PUT；`queries.py` 加 `forced_college` + `update_student` |

### 1.2 敏感文件（发布时必须排除）

| 文件 | 内容 | 处置 |
|---|---|---|
| `.env.poc`（195 B） | POC 数据库/Redis/HMAC 密码与密钥 | **绝不入库**；提供 `.env.poc.example`（占位值） |
| `backend/.m2/`（数百 MB） | Maven 本地仓库 | 不入库；新环境构建时重新下载 |
| `ui-react/node_modules/`、`dist/` | 依赖与产物 | 不入库 |
| `backend/.git`、`ui-react/.git` | 上游历史 | vendored 提交前需移除，否则会被 Git 记为 gitlink（空引用），同事拿不到代码 |

### 1.3 定制修改清单（必须可复现的全部内容）

**backend（5 个文件，均在 `ruoyi-admin/` 内）**

| 文件 | 改动 |
|---|---|
| `pom.xml` | 启用 `org.postgresql:postgresql` 驱动 |
| `src/main/resources/application.yml` | 端口 8080→9180；`captcha.enable=false` |
| `src/main/resources/application-dev.yml` | 数据源 MySQL→PostgreSQL（POC 库）、Redis 指向 POC |
| `Dockerfile.poc`（新增） | temurin:21-jre + jar |
| `controller/poc/PocProxyController.java`（新增） | HMAC 签名网关（list/detail/update/create + 权限点 + admin 声明） |

**ui-react（4 个文件）**

| 文件 | 改动 |
|---|---|
| `.env.production` | 追加 `VITE_APP_BASE_API` / `VITE_APP_CLIENT_ID` / `VITE_APP_ENCRYPT=false` / `VITE_APP_MESSAGE_ENABLED=false` |
| `vite.config.ts` | 代理目标参数化（`VITE_APP_PROXY_TARGET`） |
| `.env.development.local`（新增） | 端口 8090 / 代理目标 |
| `.env.production.bak`（新增） | 改动前备份，发布时排除 |

**import-api-poc（3 处差异，基线 = 主项目 `import-api/app`）**

| 文件 | 改动 |
|---|---|
| `poc_auth.py`（新增） | HMAC 验签依赖（含 admin 声明、nonce 防重放） |
| `main.py` | 三个学生接口挂验签依赖；新增 `PUT /students/{no}` |
| `queries.py` | `list_students` 加 `forced_college`；新增 `update_student`（白名单 + 范围 WHERE + 同事务审计） |

**根目录（8 个文件）**：`docker-compose.poc.yml`、`poc-config/application-{local,dev}.yml`、`sql/01_ruoyi.sql`（上游拷贝）、`sql/02_campus.sql`（主项目拷贝）、`sql/03_datascope_fixture.sql`、`sql/04_proxy_perms.sql`、`poc-api/main.py`（旧对照）、`test_slice.sh` / `test_datascope.sh`。

---

## 2. 方案对比

### 方案 A：`ruoyi-plus-poc` 整体初始化为独立私有 Git 仓库（推荐）

做法：在根目录 `git init` → 写 `.gitignore`（排除 `.env.poc`、`.m2/`、`node_modules/`、`dist/`、两个上游 `.git/`）→ 提交全部定制与脚本 → 推送到 GitHub 私有仓库（如 `123asdtte/campus-ruoyi-poc`）。

| 维度 | 评价 |
|---|---|
| 复现性 | **最高**：同事克隆一个仓库即获得全部定制、Compose、夹具与测试脚本；上游以「固定 commit + 变更清单」记录在 `VERSIONS.md` |
| 体积 | 排除 `.m2`/`node_modules`/`dist` 后约 25–40 MB（backend 源码 21 MB），可接受 |
| 许可证 | RuoYi-Vue-Plus 与 plus-ui 均 MIT，允许再分发（保留版权声明即可） |
| 跟随上游 | 定制以补丁形式天然可见；升级上游 = 换基线 + 重放变更，可控 |
| 维护成本 | 低：一个仓库、一条分支 |

### 方案 B：主仓库只存「配置 + 补丁」，脚本按固定 commit 拉上游

做法：主仓库新增 `poc/` 目录，内含 `patches/*.patch`、`versions.lock`、`setup.ps1`（clone 上游 → 应用补丁 → 拷贝副本）。

| 维度 | 评价 |
|---|---|
| 复现性 | 理论可行，但补丁对行号敏感；上游浅克隆 + 补丁链一旦冲突，排障成本高 |
| 同事 AI 友好度 | **差**：AI 需要先理解「拉上游→打补丁→再覆盖副本」的多步流程，任何一步环境差异都会失败 |
| 主仓库洁净度 | 好 |
| 结论 | **不推荐**作为当前形态；若未来定制收敛为 1–2 个文件再考虑 |

**推荐：方案 A。** 决定性理由：定制横跨三个来源（上游 Java、上游 React、自有 Python）共 12 个文件，散布式补丁的脆弱性远大于一个 40 MB 私有仓库的成本。

---

## 3. 发布前必须完成（第三阶段，待批准后执行）

1. `ruoyi-plus-poc` 根目录 `git init`，编写 `.gitignore`：
   ```
   .env.poc
   .m2/
   backend/.git/          ← 或发布前删除两个上游 .git
   ui-react/.git/
   ui-react/node_modules/
   ui-react/dist/
   *.local
   *.bak
   ```
2. 移除两个上游 `.git/`（保留源码与定制），在 `VERSIONS.md` 记录上游地址与 commit；
3. 生成 `.env.poc.example`（占位值），`.env.poc` 保留本地；
4. 首个 commit 信息注明基线：`chore: 导入 RuoYi POC（上游 v6.0.0@7180b52 / 6.X-React@25e69f1 + 定制）`；
5. 在 GitHub 创建**私有**仓库并推送（创建仓库与邀请协作者由管理员操作）；
6. 附 `README.md`（POC 用）：获取方式、构建步骤、`test_slice.sh` 复跑方法、`.env.poc` 生成方式。

---

## 4. 敏感信息核查（本轮）

| 项 | 结果 |
|---|---|
| `.env.poc` 是否进入任何 Git | **否**（根目录不是仓库；backend/ui-react 的 status 中也不含它） |
| 源码/配置中硬编码密码 | 未发现（Redis 密码经 `--requirepass ${POC_REDIS_PASSWORD}` 注入） |
| 真实学生数据 | POC 库仅虚构数据（POCA/POCB/SMPL 系列） |
| 待发布仓库的排除清单 | 见 §3 第 1–2 条 |

---

## 5. 待批准事项

1. 是否按方案 A 创建私有仓库（仓库名建议 `campus-ruoyi-poc`）；
2. 由谁执行推送（本机 AI 可代执行，需确认目标仓库与可见性）；
3. 是否同步邀请同事为该仓库协作者（Write）。

批准前，本目录保持现状：**可运行、可测试，但不可分享**。
