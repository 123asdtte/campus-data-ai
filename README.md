# 校园数据管理与 AI 助手平台

本地验证用的校园数据管理工具：**PostgreSQL（业务主库） + Appsmith（管理页面） + FastAPI 导入校验服务**。
第一阶段只使用**虚构数据**，不接触真实学生信息；Dify AI 助手在第二阶段接入。

> 当前状态：**阶段 1 已完成并实测通过**（数据库、导入闭环、审计、备份恢复）。
> 阶段 2（Dify 制度问答）尚未部署，`docker-compose.yml` 中不包含 Dify。

---

## 1. 环境要求

| 项目 | 要求 | 本机实测 |
|---|---|---|
| 操作系统 | Windows 11 + WSL2 后端 | Windows 11 家庭中文版 |
| Docker | Docker Desktop，固定版本标签 | Engine 29.2.0 / Compose v5.0.2 |
| 内存 | 建议 16 GB 以上（Appsmith 约占 2–4 GB） | 31.8 GB |
| 磁盘 | 项目盘剩余 ≥ 15 GB | Z: 141 GB 可用（代码）/ F: 27 GB 可用（镜像与数据卷） |
| 端口 | 8081、8443、55432、8010 未被占用 | 已确认空闲（5432/8000/8080 被其他服务占用，故整体避开） |

**磁盘告警阈值**：低于 10 GB 时停止拉取新镜像并提示清理；低于 5 GB 时禁止大批量导入。
使用 `./scripts/check-disk.sh` 快速检查。

---

## 2. 目录结构

```text
campus-data-ai/
├─ docker-compose.yml          # 三项服务：campus-db / appsmith / import-api
├─ .env.example                # 变量名与占位符；真实 .env 不入库
├─ sql/
│  ├─ 001_schema.sql           # 5 张表 + 唯一/外键约束 + 更新时间与审计触发器
│  ├─ 002_seed_demo.sql        # 虚构数据：学生 200、异动 300、历史批次 1
│  └─ 003_roles.sql            # 最小权限账号 campus_app / campus_ro
├─ import-api/                 # FastAPI + Pandera + openpyxl
│  ├─ app/                     # config / db / mapping / schemas / service / main
│  ├─ scripts/make_samples.py  # 生成虚构样例 Excel
│  └─ wheels/                  # 离线依赖（容器无外网时使用）
├─ samples/                    # 生成的样例文件（虚构数据）
├─ scripts/                    # backup / restore / check-disk
└─ docs/                       # 施工记录、环境检查、接口契约、安全清单、测试计划、页面搭建
```

---

## 3. 快速开始

### 3.1 准备配置

```bash
cd campus-data-ai
cp .env.example .env
```

将 `.env` 中 4 个 `__CHANGE_ME__` 替换为随机值（**初始化后不可再改**，否则已保存的数据库密码无法解密）：

```bash
python -c "import secrets;[print(secrets.token_urlsafe(24)) for _ in range(4)]"
```

### 3.2 启动

```bash
docker compose up -d
docker compose ps
```

首次启动会自动执行 `001_schema.sql` 与 `002_seed_demo.sql`（仅在数据卷为空时执行一次）。

### 3.3 初始化最小权限账号（只做一次）

```bash
APP_PW=$(grep '^APP_DB_PASSWORD=' .env | cut -d= -f2)
RO_PW=$(grep '^RO_DB_PASSWORD=' .env | cut -d= -f2)
docker compose exec -T campus-db psql -U campus_dba -d campus \
  -v app_password="$APP_PW" -v ro_password="$RO_PW" -f - < sql/003_roles.sql
```

> 注意：`003_roles.sql` 依赖 psql 变量，**不能**放入 `docker-entrypoint-initdb.d` 自动执行。

### 3.4 访问入口

| 服务 | 地址 | 说明 |
|---|---|---|
| Appsmith | http://127.0.0.1:8081 | 首次打开需创建管理员账号 |
| Import API 文档 | http://127.0.0.1:8010/docs | Swagger UI |
| Import API 健康检查 | http://127.0.0.1:8010/health | `{"status":"ok"}` 表示数据库连通 |
| PostgreSQL | 127.0.0.1:55432 | 仅供本机调试，Appsmith 走容器网络 |

所有端口均绑定 `127.0.0.1`，**不会**暴露到局域网或公网。

---

## 4. 两个数据库不是一回事

这是部署中最容易混淆的点，必须分清：

| 存储 | 容器/卷 | 用途 | 是否需要备份 |
|---|---|---|---|
| **校园业务库** `campus` | `campus-db` + 卷 `campus_pgdata` | students、student_changes、import_batches、import_issues、operation_logs | **必须**，见第 6 节 |
| **Appsmith 自身元数据** | `appsmith` + 卷 `campus_appsmith_stacks` | 页面定义、账号、数据源配置、内嵌 MongoDB/Redis | 可选（建议随版本升级前备份） |

Appsmith 容器内自带 MongoDB 与 Redis，用于保存应用定义与缓存；**它们不存放任何校园业务数据**，也不能当作业务库使用。

---

## 5. 账号与权限

| 账号 | 用途 | 权限 |
|---|---|---|
| `campus_dba` | 初始化、备份、结构变更 | 库所有者（仅运维使用） |
| `campus_app` | Appsmith 数据源、Import API | 5 张表的 SELECT/INSERT/UPDATE；`import_issues` 额外允许 DELETE（重新校验时重生成）；**无 DELETE 业务表、无 UPDATE 审计表** |
| `campus_ro` | 只读查看者 | 全部表与视图 SELECT |

Appsmith 连接串（数据源配置中填写）：

```text
postgresql://campus_app:<APP_DB_PASSWORD>@campus-db:5432/campus
```

Appsmith 的 PostgreSQL 表单**没有 schema 字段**，因此所有查询必须写全限定表名（`campus.students`、`campus.student_changes` 等），不要依赖默认 `public`。**不要把 `campus_dba` 填进 Appsmith 数据源。**

---

## 6. 备份与恢复

```bash
./scripts/backup.sh                 # 输出 backups/campus_YYYYmmdd_HHMMSS.sql.gz
./scripts/restore.sh backups/xxx.sql.gz   # 需二次确认
```

- 备份使用 `pg_dump --no-owner`，恢复到新建库后由 `campus_dba` 重新授权。
- **每次结构变更前必须备份**；校内试点阶段目标为每日自动备份 + 每月恢复演练。
- 备份文件含虚构数据时应保存在 `backups/`（已 gitignore）；接入真实数据后必须加密存放。

恢复演练记录见 `docs/TEST-PLAN.md` 的 AT-016。

---

## 7. 导入接口

完整契约见 `docs/IMPORT-API.md`。最小流程：

```bash
# 1) 预览（返回 batch_id、列映射、前 20 行）
curl --noproxy '*' -X POST http://127.0.0.1:8010/imports/preview \
  -F "file=@samples/students_demo.xlsx" -F "target_type=students" -H "X-Actor: demo.teacher"

# 2) 校验（写入异常明细，返回有效/异常行数）
curl --noproxy '*' -X POST http://127.0.0.1:8010/imports/2/validate

# 3) 提交（事务写入；重复提交返回 409）
curl --noproxy '*' -X POST http://127.0.0.1:8010/imports/2/commit -H "X-Actor: demo.teacher"

# 4) 查询结果
curl --noproxy '*' http://127.0.0.1:8010/imports/2
```

生成样例：

```bash
docker compose exec -T import-api python scripts/make_samples.py
```

---

## 8. 操作审计

`operation_logs` 由数据库触发器在同一事务内写入，应用侧没有 UPDATE/DELETE 权限。

操作人身份通过会话变量注入：

```sql
SELECT set_config('campus.actor_user_id', 'demo.teacher', true);  -- 事务内
```

- Import API 每次写操作自动注入（来源 `X-Actor` 头）。
- Appsmith 直连数据库时无法注入，此时 `actor_user_id` 为 NULL、仅记录 `actor_db_role`。
  **这是阶段 1 的已知限制**，接入真实数据前必须改为受控 API 写入。详见 `docs/SECURITY-CHECKLIST.md`。

---

## 9. 版本锁定

| 组件 | 版本 | 说明 |
|---|---|---|
| `postgres` | `16.15-alpine` | 2026-09 发布，不用 `latest` |
| `appsmith/appsmith-ce` | `v2.5.0` | 2026-10-09 发布 |
| `python` | `3.12-slim` | Import API 基础镜像 |
| pandas / pandera / fastapi | 2.3.3 / 0.34.1 / 0.150.0 | 见 `import-api/wheels` 与构建日志 |

升级流程：备份 → 修改镜像标签 → `docker compose up -d` → 跑 `docs/TEST-PLAN.md` 冒烟用例 → 异常则回滚标签并恢复备份。

---

## 10. 已知限制（阶段 1）

1. **Appsmith 社区版只有 3 个固定角色**，无字段级/行级权限、无审计日志。三角色隔离靠数据库账号 + 页面可见性实现，不构成安全边界。
2. **`X-Actor` 头未经认证**，仅用于演示审计链路，不能作为真实身份依据。
3. **Dify 未部署**；AI 助手页面在阶段 2 接入（iframe 嵌入 WebApp，与 API 调用是两条独立路径）。
4. 导入限制：单文件 10 MB / 10,000 行，可通过 `.env` 调整。
5. 不支持移动端适配，按 1366×768 及以上桌面分辨率设计。

---

## 11. 常用运维命令

```bash
docker compose ps                        # 状态
docker compose logs -f campus-db         # 数据库日志
docker compose logs -f import-api        # 导入服务日志
docker compose restart import-api        # 重启导入服务
docker compose down                      # 停止（保留数据）
docker compose down -v                   # 停止并删除数据卷（危险，仅限重建测试环境）
./scripts/check-disk.sh                  # 磁盘余量检查
```

---

## 12. React 前端（界面迁移）

`web/` 是用 React + TypeScript + Vite + Ant Design 重做的业务界面，逐步替代 Appsmith。
**两套界面可以并存**：Appsmith 仍在 8081，React 在 5173，共用同一套后端与数据库。

### 12.1 启动

```bash
cd web
npm install                    # 首次
npm run dev                    # http://127.0.0.1:5173/students
```

开发服务器把 `/api` 代理到 `http://127.0.0.1:8010`（见 `vite.config.ts`），
所以浏览器不需要直连数据库，也不会有跨域问题。

### 12.2 构建

```bash
npm run build                  # 先 tsc --noEmit 再 vite build，产物在 web/dist
npm run preview                # 本地预览构建产物
```

### 12.3 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `VITE_API_BASE` | `/api` | 请求基址；改成完整地址可绕过代理直连 |
| `VITE_ACTOR` | `local.operator` | 展示用操作人标识，随 `X-Actor` 发送。**不是认证** |

### 12.4 本轮已实现的页面

| 页面 | 路由 | 能力 |
|---|---|---|
| 总览 | `/` | 关键指标、异动类型分布、最近导入批次、近六个月趋势、模块入口 |
| 学生信息查询 | `/students` | 关键词搜索、学院/班级/状态筛选、服务端分页、详情抽屉（含异动列表） |
| 学生数据导入 | `/import` | 选文件 → 预览 → 校验 → 确认导入，异常明细带 Excel 行号，支持按批次号恢复 |

首页视觉取自 [hairline](https://hairline.lucasmarkes.com/)：0.9px 描边、四级灰（`#232327 / #a4a4ac / #c3c3c9 / #e0e0e4`）、纯白底、无阴影。交互图形使用其官方组件 `@lucasmarkes/hairline`（MIT），hero 区的柱状图会跟随指针。

**学校标识**：侧边栏与页面标题使用「郴州思科职业学院 · 数据管理平台」；品牌标记 `BrandMark.tsx` 取材校徽的校门与三台进阶弧线，纯线条无填充；首页页脚标注校训「自立自强　兼济天下」。校名为正式全称，未使用未经核实的英文译名。

侧边栏只保留这三个真实入口，未做空壳页面。

界面视觉基于 TypeUI 的 Refined 设计规范（`web/DESIGN.md`）实现：单一强调色、发丝线边框、4px 间距栅格、8px 圆角、等宽数字。令牌与 AntD 覆写集中在 `web/src/styles.css`，改主题只需动这一个文件。

### 12.5 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `npm run dev` 报端口占用 | 5173 被占用 | 改 `vite.config.ts` 的 `server.port`，或关掉占用进程 |
| 页面显示「无法连接后端服务」 | Import API 未启动 | `docker compose ps` 确认 `campus-import-api` 健康 |
| 接口 404 | 代理目标错误 | 检查 `VITE_PROXY_TARGET` 或 `vite.config.ts` 的 target |
| 提交时提示超时 | 文件过大或后端慢 | 前端超时 120 s；仍超时用「按批次号恢复」查状态，不要重复点击 |
| 导入提示缺列 | 表头不匹配 | 用 `samples/` 下的模板，或对照 `docs/DATA-DICTIONARY.md` 的列名 |

### 12.6 容器化（未启用）

`web/dist` 构建产物可以交给 nginx 直接托管，但**本轮没有修改 `docker-compose.yml`**。
如需上线，建议以独立文件追加服务（不改动现有三服务）：

```bash
docker compose -f docker-compose.yml -f docker-compose.web.yml up -d
```

注意：容器内无法访问 npm registry，前端镜像必须先在宿主机 `npm run build`，镜像只负责拷贝 `dist`。

