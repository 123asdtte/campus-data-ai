# 施工记录：从零到可运行

**日期：** 2026-10-20　**耗时：** 约 55 分钟　**执行者：** AI 助手
**结论：** 完成阶段 1（数据库 + 管理页面平台 + 导入校验服务），三个容器全部 healthy，导入闭环实测通过。**未安装 Dify**。

---

## 0. 一页速览

| 做了 | 没做 |
|---|---|
| 环境勘察（Docker / 端口 / 磁盘 / 内存） | 未安装 Dify（阶段 2） |
| 回收 11.16 GB Docker 构建缓存 | 未搭建 Appsmith 的 10 个页面（需人工在界面操作） |
| 建 5 张表 + 约束 + 触发器 | 未接入任何真实学生数据 |
| 灌入虚构数据（学生 200 / 异动 300） | 未做 HTTPS、未开公网端口 |
| 建 3 个数据库角色（最小权限） | 未初始化 Git 仓库 |
| 部署 Appsmith + PostgreSQL + FastAPI | |
| 实现并测试导入四步闭环 | |
| 修复 6 个实际故障 | |
| 完成一次备份恢复演练 | |

**运行入口**：Appsmith http://127.0.0.1:8081 ｜ 导入服务 http://127.0.0.1:8010/docs ｜ 数据库 127.0.0.1:55432

---

## 1. 阶段 A：环境勘察

目的：确认能不能跑、会不会和现有服务冲突。全部为只读操作，未改任何配置。

| 命令 | 目的 | 结论 |
|---|---|---|
| `docker version --format '{{.Server.Version}}'` | 引擎版本 | 29.2.0 |
| `docker compose version` | Compose 版本 | v5.0.2 |
| `docker info --format '{{.OperatingSystem}} \| CPUs={{.NCPU}} \| Mem={{.MemTotal}}'` | 容器资源上限 | 24 vCPU / 15.5 GiB |
| `docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'` | 已有容器 | 11 个 `diet-*` 常驻，占内存与端口 |
| `netstat -ano \| grep LISTENING` | 端口占用 | 5432、8000、8080 已被占 |
| `Get-NetTCPConnection -LocalPort 5432 -State Listen` | 定位占用进程 | 5432=宿主 postgres，8000=diet-gateway，8080=verge-mihomo |
| `Get-CimInstance Win32_ComputerSystem` | 物理内存 | 31.8 GB，空闲 15.7 GB |
| `Get-CimInstance Win32_LogicalDisk` | 各盘余量 | Z: 141.6 GB、F: 27 GB、C: 12.2 GB |
| `df -Pk . \| awk ...` | 项目盘余量 | 同上（Git Bash 方式） |
| `docker system df` | 镜像/缓存占用 | 镜像 16.8 GB，构建缓存 12.49 GB |
| `curl https://hub.docker.com/v2/repositories/appsmith/appsmith-ce/tags` | 查可用镜像标签 | 确认 `v2.5.0` 存在 |
| `curl https://hub.docker.com/v2/repositories/library/postgres/tags?name=16` | 查 PG 标签 | 确认 `16.15-alpine` 存在 |
| `curl https://hub.docker.com/v2/repositories/langgenius/dify-api/tags` | 查 Dify 标签 | 确认 `1.17.1` 存在（**仅查询，未拉取**） |
| `WebFetch https://www.appsmith.com/pricing` | 核对社区版能力 | 免费版仅 3 个固定角色，自定义角色/审计日志需付费 |

> `wsl.exe -l -v` 被执行环境的安全策略拦截（程序黑名单），无法核验 WSL 发行版；Docker 正常运行即说明后端可用。

**勘察结论**：Docker 数据目录已在 `F:\DockerData\docker`（不在 C 盘），但 F 盘只剩 27 GB，是唯一需要处理的资源问题。

---

## 2. 阶段 B：存储处置

```bash
# 1) 确认数据目录位置（读 Docker Desktop 配置）
Get-Content "$env:APPDATA\Docker\settings-store.json" -Raw | ConvertFrom-Json
# → dataRoot = F:\DockerData\docker

# 2) 确认 vhdx 实际大小
Get-ChildItem "F:\DockerData\docker" -Recurse -Filter *.vhdx
# → docker_data.vhdx 19.7 GB

# 3) 回收构建缓存（只删可重建的缓存，不动镜像与容器）
docker builder prune -f
# → Total: 11.16GB

# 4) 复查
docker system df
```

**关键认知**：vhdx 是稀疏文件，回收后宿主 `df` 仍显示 27 GB，但容器内部空间已释放。后续拉取 Appsmith（4.31 GB）时 vhdx 只增长 0.1 GB，验证了这一点。

**最终落盘规则**：代码在 Z:，镜像与卷在 F:，C: 不承载任何数据。

---

## 3. 阶段 C：代码与配置落地

### 3.1 文件清单

| 文件 | 作用 |
|---|---|
| `docker-compose.yml` | 三个服务的编排（端口、卷、健康检查、日志上限） |
| `.env.example` / `.env` | 变量模板 / 实际密码（`.env` 已 gitignore） |
| `.gitignore` | 排除 `.env`、`backups/`、`data/`、`__pycache__` |
| `sql/001_schema.sql` | 5 张表 + 唯一/外键约束 + `updated_at` 触发器 + 审计触发器 + 2 个视图 |
| `sql/002_seed_demo.sql` | 虚构数据：学生 200、异动 300、历史批次 1、异常 2 |
| `sql/003_roles.sql` | `campus_app`（读写）/ `campus_ro`（只读），幂等创建 |
| `import-api/app/config.py` | 环境变量配置 |
| `import-api/app/db.py` | psycopg 连接池 |
| `import-api/app/mapping.py` | 中文表头 → 字段名映射、枚举字典 |
| `import-api/app/schemas.py` | Pandera 结构校验规则 |
| `import-api/app/service.py` | 解析 → 映射 → 校验 → 事务提交 |
| `import-api/app/main.py` | FastAPI 路由 |
| `import-api/scripts/make_samples.py` | 生成虚构样例 Excel（学号自动取未占用的号段） |
| `import-api/Dockerfile` | 优先离线 wheel 安装，无则回退索引源 |
| `import-api/wheels/` | 38 个 manylinux wheel（容器无外网时使用） |
| `scripts/backup.sh` / `restore.sh` / `check-disk.sh` | 备份 / 恢复 / 磁盘阈值检查 |

### 3.2 生成密码

```bash
python -c "import secrets;[print(secrets.token_urlsafe(24)) for _ in range(4)]"
```

`.env` 中四个必填项：`POSTGRES_PASSWORD`、`APP_DB_PASSWORD`、`APPSMITH_ENCRYPTION_PASSWORD`、`APPSMITH_ENCRYPTION_SALT`。**Appsmith 两个密钥初始化后不可更改**，否则已保存的数据源密码无法解密。

---

## 4. 阶段 D：部署与初始化

```bash
cd "Z:/ai/本地部署/campus-data-ai"

# 1) 校验编排文件（只校验，不启动）
docker compose config --quiet

# 2) 启动数据库（首次启动自动执行 001 + 002）
docker compose up -d campus-db
docker compose logs campus-db | grep -E "ERROR|FATAL"

# 3) 建最小权限角色（依赖 psql 变量，不能放进 initdb 自动执行）
APP_PW=$(grep '^APP_DB_PASSWORD=' .env | cut -d= -f2)
RO_PW=$(grep '^RO_DB_PASSWORD=' .env | cut -d= -f2)
docker compose exec -T campus-db psql -U campus_dba -d campus \
  -v app_password="$APP_PW" -v ro_password="$RO_PW" -f - < sql/003_roles.sql

# 4) 构建导入服务镜像
docker compose build import-api

# 5) 启动导入服务与 Appsmith
docker compose up -d import-api appsmith

# 6) 检查
docker compose ps
curl -s http://127.0.0.1:8010/health
curl -s http://127.0.0.1:8081/api/v1/health
```

### 4.1 初始化后核验数据量

```bash
docker compose exec -T campus-db psql -U campus_dba -d campus -t -c "
SELECT 'students='||count(*) FROM campus.students
UNION ALL SELECT 'changes='||count(*) FROM campus.student_changes
UNION ALL SELECT 'batches='||count(*) FROM campus.import_batches
UNION ALL SELECT 'logs='||count(*) FROM campus.operation_logs;"
```

### 4.2 容器互通验证（Appsmith 用 dash，没有 `/dev/tcp`）

```bash
docker compose exec -T appsmith node -e "
const net=require('net');
function probe(h,p){return new Promise(r=>{const s=net.connect(p,h,()=>{console.log(h+':'+p+' OPEN');s.end();r()});s.on('error',e=>{console.log(h+':'+p+' '+e.code);r()})})}
(async()=>{await probe('campus-db',5432);await probe('import-api',8000)})()"
# → campus-db:5432 OPEN / import-api:8000 OPEN
```

---

## 5. 阶段 E：接口验证（实际执行的 curl）

```bash
# 生成样例（写入 /app/samples，已绑定到宿主 samples/）
docker compose exec -T import-api python scripts/make_samples.py

# 1) 预览：multipart 方式
curl --noproxy '*' -X POST http://127.0.0.1:8010/imports/preview \
  -F "file=@samples/students_demo.xlsx" -F "target_type=students" -H "X-Actor: demo.teacher"

# 2) 校验
curl --noproxy '*' -X POST http://127.0.0.1:8010/imports/2/validate

# 3) 提交
curl --noproxy '*' -X POST http://127.0.0.1:8010/imports/2/commit -H "X-Actor: demo.teacher"

# 4) 查询批次
curl --noproxy '*' http://127.0.0.1:8010/imports/2

# 5) 批次列表
curl --noproxy '*' "http://127.0.0.1:8010/imports?limit=5"

# 6) 健康检查
curl --noproxy '*' http://127.0.0.1:8010/health
```

> `--noproxy '*'` 是必须的：本机设置了 `HTTP_PROXY=127.0.0.1:8080`，不加会把本地请求也送去代理。

### 5.1 实测结果

| 场景 | 输入 | 结果 |
|---|---|---|
| 正常导入 | `students_clean.xlsx` 10 行 | 10 有效 / 0 异常，提交写入 10 条 |
| 学生异常 | `students_demo.xlsx` 15 行 | 5 类异常全部识别，行号 12–16 |
| 异动异常 | `student_changes_demo.xlsx` 9 行 | 4 类异常，行号 7–10 |
| 缺列 | 只有「编号/名字」两列 | 批次 `failed`，`COLUMN_MAPPING_REQUIRED` |
| 重复文件 | 同一文件再传 | `DUPLICATE_BATCH`（warning） |
| 重复提交 | 同一批次再 commit | HTTP 409 |
| 提交失败 | 撤销 INSERT 权限后 commit | HTTP 500「已整体回滚」，数据不变，状态仍 `validated` |

### 5.2 最小权限与审计验证

```bash
# 用业务账号做 CRUD，验证约束与授权
docker compose exec -T -e PGPASSWORD="$APP_PW" campus-db \
  psql -U campus_app -d campus -h 127.0.0.1 -f - < /tmp/crud_test.sql
# 结果：insert OK / 重复学号被唯一约束拒绝 / delete 被拒绝(permission denied)
#       为不存在的学生建异动 → INSERT 0 0

# 验证审计能记录到人
docker compose exec -T campus-db psql -U campus_dba -d campus -c "
BEGIN;
SELECT set_config('campus.actor_user_id','demo.teacher', true);
UPDATE campus.students SET class_name='软件技术2022级9班' WHERE student_no='DEMO2022040001';
COMMIT;
SELECT actor_user_id, actor_db_role, action, changed_fields FROM campus.operation_logs ORDER BY id DESC LIMIT 1;"
```

---

## 6. 阶段 F：六个实际故障与修复

这是本次施工最有价值的部分，均为实测发现，不是预设。

### 6.1 种子脚本产生重复学号

- **现象**：`ERROR: duplicate key value violates unique constraint "students_student_no_key"`，容器初始化失败后反复重启。
- **根因**：`JOIN college_major ON college_code = ...`，一个学院对应两个专业，导致每条记录被放大成两行。
- **修复**：给专业表加 `row_number()` 唯一序号，改用 `JOIN ... ON cm.idx = s.cm_idx`。
- **重建**：`docker compose down -v && docker compose up -d campus-db`（数据为空时才重跑 initdb）。

### 6.2 审计日志记录不到真实操作角色

- **现象**：以 `campus_app` 身份改数据，日志里 `actor_db_role` 却是 `campus_dba`。
- **根因**：触发器是 `SECURITY DEFINER`，函数内的 `current_user` 会变成函数属主，不是登录用户。
- **修复**：改用 `session_user`，并同步修正 `001_schema.sql`。
- **复测**：日志显示 `campus_app`，`changed_fields={class_name,updated_at}`。

### 6.3 校验接口 500：permission denied for table import_issues

- **根因**：重新校验要「先清空本批次旧异常」，但 `campus_app` 没有 DELETE 权限。
- **修复**：仅对 `import_issues` 单独授予 DELETE；`students` / `student_changes` 仍然禁止物理删除。

### 6.4 容器无外网，pip 装不上依赖

- **现象**：`Could not find a version that satisfies the requirement fastapi`；容器内访问 pypi.org、清华、阿里镜像全部 `Connection refused`，但 `docker pull` 正常。
- **根因**：镜像拉取走 Docker Desktop 的代理，容器自身没有出口。
- **修复**：在宿主机下载 Linux 平台 wheel，镜像内离线安装。

```bash
python -m pip download -r requirements.txt -d wheels \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 \
  --python-version 312 --implementation cp --abi cp312 \
  --index-url https://pypi.org/simple      # 必须显式指定，本机 pip 默认指向的镜像不可达

# uvloop 带 sys_platform != "win32" 标记，在 Windows 宿主会被跳过，必须单独补下
python -m pip download uvloop -d wheels --only-binary=:all: \
  --platform manylinux2014_x86_64 --python-version 312 --implementation cp --abi cp312 \
  --index-url https://pypi.org/simple --no-deps
```

Dockerfile 内对应逻辑：存在 `wheels/*.whl` 就 `pip install --no-index --find-links`，否则回退 `PIP_INDEX_URL`。

### 6.5 异动导入误报学号重复

- **现象**：同一学生在同一文件里有多条异动，被判 `DUPLICATE_STUDENT_NO`。
- **根因**：文件内学号唯一性检查对所有目标类型都生效。
- **修复**：该检查仅对 `students` 生效；`student_changes` 允许一人多条。

### 6.6 提交失败的报错不可读

- **现象**：事务失败只返回 `Internal Server Error`。
- **修复**：捕获 `psycopg.Error`，转换为「提交失败，已整体回滚：<主错误信息>」，返回 500。事务本身已保证回滚，改动只影响提示语。

---

## 7. 阶段 G：备份与恢复演练

```bash
# 1) 备份
chmod +x scripts/*.sh
./scripts/backup.sh
# → backups/campus_20261020_155950.sql.gz (24 KB)

# 2) 在独立库中恢复（不覆盖生产库）
docker compose exec -T campus-db psql -U campus_dba -d postgres \
  -c "DROP DATABASE IF EXISTS campus_drill;" -c "CREATE DATABASE campus_drill;"
gunzip -c backups/campus_20261020_155950.sql.gz | \
  docker compose exec -T campus-db psql -U campus_dba -d campus_drill -q -v ON_ERROR_STOP=1

# 3) 核对
docker compose exec -T campus-db psql -U campus_dba -d campus_drill -t -c "
SELECT 'students='||count(*) FROM campus.students
UNION ALL SELECT 'changes='||count(*) FROM campus.student_changes;"
# → students=221  changes=305  batches=9  issues=33  logs=530（与生产库一致）

# 4) 清理演练库
docker compose exec -T campus-db psql -U campus_dba -d postgres -c "DROP DATABASE campus_drill;"
```

覆盖式恢复脚本 `scripts/restore.sh` 也已提供，需手动输入库名二次确认。

---

## 8. 关于 Dify：没有装，也没跑过任何安装命令

**本次没有执行过任何 Dify 相关命令。** 唯一涉及 Dify 的动作是查了一次 Docker Hub 的标签列表（确认 `1.17.1` 存在），没拉镜像、没建容器、没配 Key。

原因：阶段 1 的目标是「虚构 Excel → 校验 → 入库 → 页面查询 → 审计 → 备份恢复」这条闭环，Dify 不属于闭环的一环；同时 F 盘只剩 26 GB，Dify 全栈约 9–12 GB，提前装会挤压后续空间。

### 8.1 阶段 2 的官方命令（供参考，本次未执行）

```bash
# 官方仓库
git clone https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env          # 按需修改，至少检查端口与密钥
docker compose up -d          # 官方 compose 含 api/worker/web/db/redis/weaviate/sandbox/sslm/nginx 等约 9 个容器
```

本机落地时必须改两处：

1. **端口冲突**：Dify 默认占用 80/443，本机 8080 已被代理占用，建议在 `.env` 设 `EXPOSE_NGINX_PORT=8090`。
2. **磁盘**：先跑 `./scripts/check-disk.sh`，低于 10 GB 不要拉取。

另外注意：Dify 自带的 PostgreSQL/Weaviate 是它自己的元数据与向量库，**不能**当作校园业务库；校园业务数据仍然只在 `campus-db` 里。

### 8.2 接入方式（阶段 2 才做）

| 场景 | 实现 |
|---|---|
| 制度问答 | Appsmith 用 Iframe 组件嵌入 Dify WebApp 地址 |
| 导入报告生成说明 | FastAPI 调 Dify API，Key 存服务端环境变量 |
| AI 改学生数据 | 不允许，只出建议，由受控接口 + 人工确认执行 |

---

## 9. 完整命令速查

```bash
cd "Z:/ai/本地部署/campus-data-ai"

# --- 日常启停 ---
docker compose up -d                 # 启动全部
docker compose ps                    # 状态
docker compose logs -f import-api    # 看日志
docker compose restart import-api    # 重启单个服务
docker compose down                  # 停止（保留数据）
docker compose down -v               # 停止并删数据卷（危险）

# --- 数据库 ---
docker compose exec -T campus-db psql -U campus_dba -d campus          # 进 psql
docker compose exec -T campus-db pg_dump -U campus_dba -d campus ...   # 手工备份

# --- 导入服务 ---
docker compose exec -T import-api python scripts/make_samples.py       # 生成样例
curl --noproxy '*' http://127.0.0.1:8010/health                        # 健康检查
curl --noproxy '*' http://127.0.0.1:8010/docs                          # Swagger

# --- 运维 ---
./scripts/backup.sh                  # 备份
./scripts/restore.sh <file.sql.gz>   # 恢复（需二次确认）
./scripts/check-disk.sh              # 磁盘阈值检查
```

---

## 10. 未完成事项

| 项 | 原因 | 后续 |
|---|---|---|
| Appsmith 10 个页面 | 必须在 Web 界面手工搭建，无法脚本化 | 按 `docs/APPSMITH-SETUP.md` 操作 |
| 页面级验收（AT-011/012/015 完整版） | 依赖页面 | 页面完成后补测 |
| Dify 部署与 AI 验收 | 阶段 2 | 见第 8 节 |
| Git 仓库初始化 | 未要求 | `git init && git add . && git commit`，`.env` 已被忽略 |
| 接入真实数据 | 需学校授权 | 见 `docs/SECURITY-CHECKLIST.md` 第 9 节阻断项 |
