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
.\scripts\dev\smoke-test.ps1       # 冒烟：网关登录 + 只读接口 + 一次完整导入
.\scripts\dev\down-main.ps1        # 停止：**保留数据卷**，下次启动数据还在
```

首次执行 `up-main.ps1` 会自动做四件事，不需要手工干预：

1. `.env` 不存在时从 `.env.example` 复制，并把 `__CHANGE_ME_*` / 空值占位符替换成随机 32 位密钥
   （业务库 3 个 + 网关认证库 / Redis / HMAC / JWT 共 7 个）；
2. `import-api/wheels` 为空时用本机 Python 预取（`--platform manylinux… --python-version 312`）；
3. 数据库健康后执行 `sql/003_roles.sql`，建出 `campus_app` / `campus_ro`；
4. 紧接着重放 `sql/004_internal_auth.sql` 与 `sql/006_import_scope.sql`——
   这两个脚本不在 initdb 里，缺 004 网关 nonce 落库失败，缺 006 导入审计函数与
   `import_issues` 权限控制缺失。

第 3、4 条是统一入口合并后实测补上的关键步骤，见第 5 节。

启动后的地址（全部只绑 127.0.0.1）：

| 服务 | 地址 |
|---|---|
| **统一入口（Java 网关）** | http://127.0.0.1:9190 |
| Import API | 仅容器内 `http://import-api:8000`（**宿主 8010 已关闭**） |
| PostgreSQL 业务库 | 127.0.0.1:55432 |
| PostgreSQL 网关认证库 | 127.0.0.1:55434 |
| 网关 Redis | 127.0.0.1:6382 |
| 前端静态站（独立 compose） | http://127.0.0.1:8082 |

> PR-D 之后浏览器只访问网关：前端 nginx 把 `/gw/*` 反代到 `gateway:9180`，
> 由网关验登录态后签名转发内网 `import-api:8000`。宿主不存在绕过网关的业务端口。
> Appsmith 已按 R2 下线，不再启动，也不再需要 `APPSMITH_*` 密钥。

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
| `password authentication failed for user "campus_app"` | 角色没建 | 跑 `up-main.ps1`（会自动执行 003 并重放 004/006）；手工补：`docker compose exec -T campus-db psql -U <user> -d <db> -v app_password=... -v ro_password=... -f sql/003_roles.sql` |
| 导入报「审计函数不存在」或权限错误 | 006 未执行 | 重跑 `up-main.ps1`，或手工 `psql -f sql/006_import_scope.sql`（幂等） |
| 登录返回 500 / `请配置jwt秘钥` | `.env` 的 `JWT_SECRET_KEY` 为空 | 填入 ≥32 字符随机值后 `docker compose up -d --force-recreate gateway` |
| `compose` 报 `INTERNAL_HMAC_SECRET 未设置` | `.env` 缺网关密钥 | 跑 `up-main.ps1` 自动补随机值 |
| 端口冲突 | 55432/55434/6382/9190/8082 被占 | `check-prereqs.ps1` 会打印占用进程名 |
| 健康检查失败（wget 报连接被拒） | Docker 向容器注入了指向容器自身的 `HTTP_PROXY` | 健康检查统一用 `curl --noproxy '*'`（已落实在 compose 里） |
| 服务互访不通 | 容器内 `127.0.0.1` 是容器自己 | 用 Compose 服务名（`campus-db`），不要写 localhost |
| Java 构建报「不支持发行版本 21」 | `JAVA_HOME` 指向 17 | 构建时显式指定 JDK 21 的 `JAVA_HOME` |

---

## 5. 实测记录

### 5.1 统一入口复测（2026-10-22，PR-D 合并后）

> 上一小节 5.2 是 Appsmith + 8010 时代的记录，仅作历史参考；当前拓扑以下表为准。

| 步骤 | 结果 |
|---|---|
| `check-prereqs.ps1` | 栈运行时 `FAIL=0 / WARN=5`（5 个端口被本栈占用属预期）；端口检查已改为 55432/55434/6382/9190/8082 |
| `up-main.ps1 -NoBuild` | 5 个容器全部 healthy；自动重放 003 + **004 + 006** 成功 |
| `smoke-test.ps1` | 连续运行 3 次全部 `FAIL=0`：登录 → 只读接口 → 预览→校验→提交 3 行 → 按学号检索 |
| 安全边界 | 无 token 访问被拒；宿主 `8010` 不可达 |
| `down-main.ps1` → `up-main.ps1` | 数据卷保留；重启后上次导入的 `SMK1022214253%` 仍为 3 行 |

本轮修掉的问题：

1. **004/006 未随 003 重放**：全新库会缺 `internal_nonce`、导入范围列与审计函数。
   现在 `up-main.ps1` 在 003 之后固定重放 004、006（均幂等）。
2. **PowerShell 5.1 编码坑（两层）**：
   - 脚本文件无 BOM 时，PS 5.1 按 GBK 读源码，中文直接乱码甚至语法错误 → 所有 `scripts/dev/*.ps1` 改为 **UTF-8 with BOM**；
   - `Get-Content -Raw` 默认按 ANSI 读 SQL，经管道喂给 psql 时中文注释会吞掉换行，
     导致 004 报 `syntax error at or near "campus_nonce_cleaner"` → 统一用
     `Get-Content -Encoding UTF8`，并设置 `$OutputEncoding` 为 UTF-8。
3. **冒烟测试不可重复**：固定样例第二次运行全部命中 `DUPLICATE_STUDENT_NO`。
   现在每次生成唯一学号的临时 CSV，跑完删除。

### 5.2 历史记录（Appsmith + 8010 时代，2026-10-22 早于 PR-D 合并）

按「干净环境」的口径跑完整流程，结论如下：

| 步骤 | 结果 |
|---|---|
| `check-prereqs.ps1` | 如实报出两个缺口：`.env` 不存在、`wheels` 为空（正是新同事会遇到的） |
| `up-main.ps1` 首次 | 自动生成 `.env`（5 个密钥）、拉取 38 个 wheel、构建镜像、三个容器全部 healthy |
| `smoke-test.ps1` | 全绿：健康检查 / 只读接口 / 预览→校验→提交 10 行 |
| `down-main.ps1` | 容器移除，**三个数据卷保留** |
| `up-main.ps1` 二次 | 全绿；学生总数仍为 210，导入的 `SMPL20260021` 仍在 |

### 实测中发现并修掉的三个问题

1. **`003_roles.sql` 不在容器初始化里**（最严重）。
   `docker-compose.yml` 只把 001/002 挂进 `initdb`，而 003 需要 psql 变量
   （`app_password` / `ro_password`）。不跑它，`campus_app` 根本不存在，
   import-api 会一直 `password authentication failed` 并崩溃重启——
   **新同事按原文档操作必然卡在这里**。现在由 `up-main.ps1` 在数据库健康后自动执行，
   003 本身幂等，重复执行安全。
2. **Docker Hub 不可达**：配置镜像加速后解决（第 1 节）。
3. **脚本自身的两个 Windows 坑**（写脚本时踩到，已修）：
   - `Invoke-RestMethod` 会走系统代理访问 127.0.0.1 被掐断，改用 `curl.exe --noproxy '*'`；
   - native 命令的 UTF-8 输出被按 GBK 解码成乱码，接口里的中文会让 `ConvertFrom-Json` 失败，
     脚本里统一设置了 `[Console]::OutputEncoding`。

---

## 6. 仍未覆盖

- **前端栈**（`docker-compose.web.yml`）未脚本化：`web/dist` 需要 `npm ci && npm run build` 产出。
  审计文档把它列为 P1，本次未做（主栈不依赖它）。
- **POC 的 Java 构建**（JDK 21 + Maven）未脚本化：等 POC 源码入库（issue #1）后一起做。
- **Umi `max dev` 在本机不监听**：前端开发调试流程待单独排查。
- 未验证 WSL2 后端下 bind mount 的性能（本项目写频次不高，暂不处理）。
