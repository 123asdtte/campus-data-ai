# 开发环境标准化（Windows / Docker Desktop）

对应 issue #3。目标：新同事从一台干净的 Windows 电脑出发，按统一命令启动、测试、停止、恢复，
全程不依赖原作者的本机路径、预构建产物或个人凭据。

第一阶段的问题清单见 [DOCKER-ENV-AUDIT.md](DOCKER-ENV-AUDIT.md)。本文档是**第二阶段的执行面**：
把清单里的手工步骤脚本化，并把实测结论固化下来。

---

## 1. 安装前提

| 项 | 版本/说明 | 检查方式 |
|---|---|---|
| Windows | 10 22H2 / 11，需支持 WSL2 | 见下 |
| Docker Desktop | 4.x，**安装时勾选 WSL 2 后端** | `docker version` |
| Python（仅首次构建需要） | 3.9+，用于预取离线 wheel | `python --version` |
| Node.js（仅前端栈需要） | 18+ | `node -v` |

> **Windows 家庭版没有 Hyper-V**，Docker Desktop 只能走 WSL2 后端，这是唯一可选方案。
> 若安装器提示 WSL 不完整，用**管理员** PowerShell 执行 `wsl --install --no-distribution`，
> 然后**重启**再继续。

### 国内网络必做：配置镜像加速

`registry-1.docker.io` 在本网络不可达，`docker pull` 会超时。编辑
`C:\Users\<你>\.docker\daemon.json`（Docker Desktop 的 Settings → Docker Engine 也是改这个文件），
加上：

```json
"registry-mirrors": [
  "https://docker.1panel.live",
  "https://docker.m.daocloud.io",
  "https://hub.rat.dev"
]
```

改完重启 Docker Desktop，用 `docker info` 里的 `Registry Mirrors` 确认生效。
注意：**不要去改全局 Docker 代理**去解决拉镜像的问题（审计文档第 5 节第 1 条）。

---

## 2. 主系统：日常命令

所有脚本都在 `scripts/dev/`，用普通 PowerShell 执行（不需要管理员）：

```powershell
.\scripts\dev\check-prereqs.ps1    # 只看不改：Docker / 端口 / .env / wheels / 磁盘
.\scripts\dev\up-main.ps1          # 启动：补 .env → 补 wheel → compose up → 等健康检查
.\scripts\dev\smoke-test.ps1       # 冒烟：健康检查 + 只读接口 + 一次完整导入
.\scripts\dev\down-main.ps1        # 停止：**保留数据卷**，下次启动数据还在
```

首次执行 `up-main.ps1` 会自动做三件事，不需要手工干预：

1. 对齐 `.env`：不存在就从 `.env.example` 复制；已存在的按 `.env.example`
   **补齐缺的键、填实空值与 `__CHANGE_ME_*` 占位符**（已有值一律不动）；
2. `import-api/wheels` 为空时用本机 Python 预取（`--platform manylinux… --python-version 312`）；
3. 数据库健康后按顺序执行 `003_roles.sql` → `004_internal_auth.sql` → `006_import_scope.sql`。

第 1、3 条都是实测补上的，见第 5 节。

**为什么要第 1 条**：compose 里加了新服务（网关就是这么进来的）之后，旧的 `.env`
里没有那几个变量，`docker compose` 的**任何**子命令都会直接报
`required variable GATEWAY_DB_PASSWORD is missing a value`——连 `exec`、`logs`
都跑不了，而报错位置指向 compose 文件，很容易被误判成 compose 写错了。
另外 compose 把「空值」也算缺失，所以 `INTERNAL_HMAC_SECRET=` 这样写着也不够。

**为什么要第 3 条**：initdb 只挂了 001/002，而 006 建的
`campus.clear_import_issues()` 是当前主干代码的**硬依赖**——缺了它，预览能过，
一进「校验 / 提交」就 `function does not exist`（或退化成权限报错）。

### 启动后的地址

主栈（`docker-compose.yml`）只有 PostgreSQL 对外发布；Import API 的 8010 宿主
发布已由 PR-D 移除，业务请求统一经 Java 网关：

| 服务 | 地址 | 说明 |
|---|---|---|
| PostgreSQL | 127.0.0.1:55432 | 主栈 |
| Java 网关 | 127.0.0.1:9190 | 需要 `ruoyi-admin` jar（issue #1），本机通常构建不出来 |
| Import API | **无宿主端口** | 只在容器内 `127.0.0.1:8000`，冒烟测试进容器访问 |
| campus-web | 127.0.0.1:8082 | 前端栈，`docker compose -p campus-web -f docker-compose.web.yml up -d` |

> Appsmith 已按 R2 路线图下线（前端主入口改为 campus-web）。服务定义从
> `docker-compose.yml` 删除，数据卷 `campus_appsmith_stacks` 保留，需要时可将
> 服务定义原样加回。旧的 Appsmith 容器如果还在跑，它只是 compose 项目里的孤儿，
> 不影响主栈，但会占着 8081/8443。

### 停止与清理（红线）

- **日常停止只用 `down-main.ps1`**，等价于 `compose down`，**不带 `-v`**，数据卷保留。
- 删卷是破坏性操作，必须显式 `-Purge`，并且要手工输入 `DELETE` 二次确认：

```powershell
.\scripts\dev\down-main.ps1 -Purge
```

- 删卷前建议先 `.\scripts\backup.sh`。

### 孤儿 sidecar 清理

`.mapping.json` 是预览阶段写在暂存文件旁的映射表。PR #29 之前，提交只删暂存文件、
不删它，于是在 `UPLOAD_DIR` 里留下一堆查不回去的碎文件（详见
`docs/TEST-BEHAVIOR-DECISIONS.md` D-1）。新代码不再产生新的孤儿，存量用这个脚本清：

```bash
./scripts/cleanup-orphan-sidecars.sh             # 默认 dry-run，只打印不删
./scripts/cleanup-orphan-sidecars.sh --apply     # 确认清单无误后再删
./scripts/cleanup-orphan-sidecars.sh --path DIR  # 扫宿主机目录（非 Docker 部署）
```

不带 `--path` 时进容器扫 `/data/uploads`。**判定标准是「同名的暂存文件还在不在」**——
在就不动。所以千万别图省事用 `find ... -name '*.mapping.json' -delete`，那样会把正在
使用的 sidecar 一起删掉。

在 Git Bash 里跑就行；脚本内部已经处理了 MSYS 把 `/data/uploads` 改写成
`E:/…/data/uploads` 的坑。

---

## 3. RuoYi POC

POC 源码**尚未入库**（见 [POC-SHARING-PLAN.md](POC-SHARING-PLAN.md) 与 issue #1），
因此脚本不会去猜路径，找不到就明确报错退出：

```powershell
$env:POC_ROOT = 'D:\ai\ruoyi-plus-poc'
.\scripts\dev\up-poc.ps1
.\scripts\dev\down-poc.ps1
```

- 也可以 `-PocRoot <路径>` 传参；或者把 POC 放在仓库同级目录 `ruoyi-plus-poc`。
- POC 用**独立 Compose 项目名与网络**（`ruoyi-poc`），不连主库。
- POC 的 `poc-importapi` 复用主项目镜像 `campus-import-api:0.1.0`，
  所以**必须先跑过 `up-main.ps1`**，脚本会检查镜像是否存在。

---

## 4. 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `docker pull` 超时 | Docker Hub 不可达 | 配镜像加速（第 1 节） |
| `compose build` 卡在 pip | 容器内无外网，`wheels/` 为空 | 让 `up-main.ps1` 自动预取，或手工跑 `scripts/fetch-wheels.sh` |
| `password authentication failed for user "campus_app"` | 角色没建 | 跑 `up-main.ps1`（会自动执行 003→004→006）；手工补：`docker compose exec -T campus-db psql -U <user> -d <db> -v app_password=... -v ro_password=... -f sql/003_roles.sql` |
| `required variable GATEWAY_DB_PASSWORD is missing a value`（**任何 compose 子命令都报**） | `.env` 缺键，或值是空的 | 跑 `up-main.ps1` 或 `check-prereqs.ps1`：按 `.env.example` 补齐。空值也算缺失 |
| `no such service: appsmith` | Appsmith 已按 R2 下线 | 主栈只点名 `campus-db` + `import-api` |
| `COPY ruoyi-admin/target/ruoyi-admin.jar: not found` | 网关要 RuoYi jar，源码未入库（issue #1） | `up-main.ps1` 不构建网关；需要网关时先解决 issue #1 |
| **预览成功，一进校验/提交就 500** | 006 没执行，`clear_import_issues()` 不存在 | 跑 `up-main.ps1` 补齐 003→004→006 |
| `permission denied for table import_issues` | 003 的 `GRANT DELETE` 被 GBK 吞行吃掉，从未执行 | 用 `-Encoding UTF8` 重跑 003（006 会收回该 DELETE，改用受控函数） |
| 校验全行无效、`DUPLICATE_STUDENT_NO` | 样例学号上次已导入 | 冒烟测试现在会自动加随机前缀，可直接重跑 |
| 端口冲突 | 55432/8082/9190 被占 | `check-prereqs.ps1` 会打印占用进程名 |
| 健康检查失败（wget 报连接被拒） | Docker 向容器注入了指向容器自身的 `HTTP_PROXY` | 健康检查统一用 `curl --noproxy '*'`（已落实在 compose 里） |
| 服务互访不通 | 容器内 `127.0.0.1` 是容器自己 | 用 Compose 服务名（`campus-db`），不要写 localhost |
| 脚本输出中文乱码 | 只设了 `[Console]::OutputEncoding` | stdin 那一路要设 `$OutputEncoding`（`_common.ps1` 已设） |
| Java 构建报「不支持发行版本 21」 | `JAVA_HOME` 指向 17 | 构建时显式指定 JDK 21 的 `JAVA_HOME` |

---

## 5. 本次实测记录（2026-10-22，Windows 11 家庭版 26200 + Docker Desktop 4.96.2 / Engine 29.9.2）

按「干净环境」的口径跑完整流程，结论如下：

| 步骤 | 结果 |
|---|---|
| `check-prereqs.ps1` | 如实报出两个缺口：`.env` 不存在、`wheels` 为空（正是新同事会遇到的） |
| `up-main.ps1` 首次 | 自动生成 `.env`（5 个密钥）、拉取 38 个 wheel、构建镜像、三个容器全部 healthy |
| `smoke-test.ps1` | 全绿：健康检查 / 只读接口 / 预览→校验→提交 10 行 |
| `down-main.ps1` | 容器移除，**三个数据卷保留** |
| `up-main.ps1` 二次 | 全绿；学生总数仍为 210，导入的 `SMPL20260021` 仍在 |

### 实测中发现并修掉的问题

1. **`003_roles.sql` 不在容器初始化里**（最严重）。
   `docker-compose.yml` 只把 001/002 挂进 `initdb`，而 003 需要 psql 变量
   （`app_password` / `ro_password`）。不跑它，`campus_app` 根本不存在，
   import-api 会一直 `password authentication failed` 并崩溃重启——
   **新同事按原文档操作必然卡在这里**。现在由 `up-main.ps1` 在数据库健康后自动执行，
   003 本身幂等，重复执行安全。
2. **004 / 006 同样不在 initdb 里，而 006 是主干代码的硬依赖**。
   006 建的 `campus.clear_import_issues()` 是受控删除导入明细的 SECURITY DEFINER
   函数，`service.py` 在校验与提交时直接调用。缺 006 的表现很迷惑：
   **预览能过，一进校验/提交就 500**。本地库里此前三个函数一个都没有。
   现在 003 → 004 → 006 一起按 CI 的顺序补齐，三个文件都可重复执行。
3. **Docker Hub 不可达**：配置镜像加速后解决（第 1 节）。
4. **PowerShell 5.1 的 `Get-Content` 默认按 GBK 解码 UTF-8 文件**（最阴的一个）。
   一个汉字是三字节，末尾字节若落在 `0x81-0xFE`，GBK 解码器会把它当成双字节
   字符的前导字节，**顺手把紧跟其后的换行符 `\n` 吃掉**，于是两行并成一行。
   后果是静默的：`sql/003_roles.sql` 里一条以「。」结尾的中文注释，把下一行的
   `GRANT DELETE ON campus.import_issues TO campus_app;` 并进了 `--` 注释，
   这条授权从此不执行——而报错要到很久以后才以
   `permission denied for table import_issues` 的形式出现。
   实测 `003_roles.sql` 64 行，默认解码只剩 57 行。
   **所有读数一律显式 `-Encoding UTF8`。**
5. **`.env` 跟不上 `.env.example`**：写死一份「已知键」清单补 `.env` 的做法，
   在 compose 加了网关服务之后立刻失效——四个新变量没补上，`docker compose`
   的**任何**子命令都报 `required variable GATEWAY_DB_PASSWORD is missing a value`。
   现在改为以 `.env.example` 为准，缺键补、空值与占位符填实。
   顺带修掉 `Set-Content -Encoding UTF8` 会给 `.env` 加 BOM 的问题。
6. **`compose up` 不带服务名会连带构建网关**：网关镜像要
   `ruoyi-admin/target/ruoyi-admin.jar`，源码还没入库（issue #1），
   整个 up 直接失败。现在显式点名 `campus-db` + `import-api`。
   Appsmith 已按 R2 下线，点名它会报 `no such service`。
7. **脚本自身的两个 Windows 坑**（写脚本时踩到，已修）：
   - `Invoke-RestMethod` 会走系统代理访问 127.0.0.1 被掐断（已改用容器内访问）；
   - native 命令的 UTF-8 输出被按 GBK 解码成乱码，设 `[Console]::OutputEncoding`；
   - 管道喂给 native 命令的 stdin 用的是 `$OutputEncoding`（默认 ASCII），
     中文脚本内容会变成问号——把 Python 客户端管道给 `docker compose exec`
     时踩到，两行都要设 UTF8。
8. **冒烟测试原先不可重复运行**：样例学号是固定的，第一次跑完就落库，
   第二次会因为 `DUPLICATE_STUDENT_NO` 全部判成无效行。#3 验收只跑过一次，
   没暴露这个问题。现在客户端在容器内给学号加随机前缀，连跑两次均全绿
   （学生数 210 → 220 → 230）。

---

## 6. 仍未覆盖

- **前端栈**（`docker-compose.web.yml`，项目名 `campus-web`）已存在但未脚本化：
  它需要 `web/` 下先 `npm ci && npm run build` 出 `web/dist`，再
  `docker compose -p campus-web -f docker-compose.web.yml up -d`。主栈不依赖它。
- **POC 的 Java 构建**（JDK 21 + Maven）未脚本化：等 POC 源码入库（issue #1）后
  一起做。它同时挡着网关——网关镜像要从 `ruoyi-admin/target/ruoyi-admin.jar`
  构建，jar 不在仓库里，所以本机跑不起网关，`up-main.ps1` 也就不去构建它。
- **旧的 Appsmith 孤儿容器**：如果它还在跑，只是 compose 项目里的孤儿，
  不影响主栈，但占着 8081/8443。要清掉就 `docker rm -f campus-appsmith`
  （数据卷 `campus_appsmith_stacks` 会保留）。
- **Umi `max dev` 在本机不监听**：前端开发调试流程待单独排查。
- 未验证 WSL2 后端下 bind mount 的性能（本项目写频次不高，暂不处理）。
