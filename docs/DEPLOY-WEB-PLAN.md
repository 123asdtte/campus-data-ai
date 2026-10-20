# 前端容器化方案（待确认，尚未实施）

**日期**：2026-10-20　**状态**：方案待批准　**本轮**：仅只读检查与方案设计，未改动任何代码、容器或配置

---

## 0. 前置核查：批次 27（未提交、未删除）

### 0.1 元数据（只读查询）

| 项 | 值 |
|---|---|
| 批次 id / code | 27 / `IMP-20261020-205302-57096E` |
| 来源文件 | `13_招生录取数据（强智系统导出）.csv`（219,600 字节，仍在暂存卷） |
| 目标类型 | students |
| 状态 | `validated`（已校验，未提交） |
| 行数 | 2007 行，有效 2007，异常 0 |
| 异常明细 | 0 条 |
| 创建人 / 时间 | `local.operator` / 2026-10-20 20:53:02 |
| 映射 | `考生号→学号`（手动指定）、`姓名→姓名`、`录取专业→专业` |

### 0.2 核查结论

| 判断项 | 结论 | 依据 |
|---|---|---|
| 是否为重复导入 | **否** | 该文件 `file_sha256` 在全表中唯一，未出现在重复分组里 |
| 是否为测试夹具 | **否** | 文件名、2007 行规模、`考生号` 列均不属于本轮任何测试样例 |
| 为什么仍未提交 | **用户未点击确认**，不是系统阻塞 | 状态机为 `uploaded → validated → imported`；`validated` 表示校验通过但 `commit` 未调用；`finished_at` 为空 |
| 是否存在过期暂存文件 | **无过期机制** | 当前没有 TTL 或清理任务；文件自 20:53 起一直保留 |
| 数据性质 | **待确认** | 文件形态符合真实教务系统导出，但无法从系统内部证明来源；按要求标记为待确认 |

### 0.3 建议处理方式（三选一，均未执行）

| 方案 | 适用前提 | 操作 | 风险 |
|---|---|---|---|
| A. 提交入库 | 确认是合法业务数据，且已完成学号重复性人工抽查 | `POST /imports/27/commit` | **高**：2007 条一次性入库，当前无认证，且导入后无法通过界面回退 |
| B. 归档放弃 | 想留档但暂不入库 | 保持 `validated`，不操作 | 低；但暂存文件会长期占用（219 KB，可忽略） |
| C. 清理废弃 | 确认不再需要 | 需先实现按批次清理接口（目前只能手工删卷内文件） | 中；删除后不可恢复 |

**我的建议**：先按 B 保持不动，等你确认文件来源。若确认为真实数据，**不要在补齐认证前提交**——提交后系统没有任何权限边界来保护这 2007 条记录。

---

## 1. 现状

| 项 | 现状 |
|---|---|
| 编排 | `docker-compose.yml` 三个服务：`campus-db`、`appsmith`、`import-api` |
| 网络 | `campus-net`（bridge），三服务同网段 |
| 卷 | `campus_pgdata`、`campus_appsmith_stacks`、`campus_uploads` |
| 端口 | 55432（DB）、8081/8443（Appsmith）、8010（API），均绑 `127.0.0.1` |
| 前端 | **未容器化**，靠 `npm run dev`（5173）；进程已两次被回收，需手动重启 |
| 构建产物 | `web/dist` 已存在（1.25 MB JS / 18 KB CSS） |

## 2. 三个必须先说清的约束

1. **容器没有外网出口**（PyPI、npm registry 均不可达）。因此镜像内**不能** `npm install`，必须在宿主机 `npm run build` 后只拷贝 `dist`。
2. **容器内 `localhost` 指向容器自身**。nginx 反代必须写 `http://import-api:8000`（服务名），不能用 `127.0.0.1:8010`。
3. **前端请求前缀 `/api`** 需要在 nginx 里剥离后再转发，否则后端收到 `/api/students` 会 404。

## 3. 方案

**新增独立 Compose 配置，不改动现有 `docker-compose.yml`**，两个栈互不影响。

### 3.1 新增文件（3 个）

| 文件 | 作用 |
|---|---|
| `web/Dockerfile.web` | `FROM nginx:1.29-alpine` + `COPY dist` + `COPY nginx.conf`，不含构建步骤 |
| `web/nginx.conf` | 静态托管 + `/api/` 反代到 `import-api:8000` + `/healthz` + SPA 回退 |
| `docker-compose.web.yml` | 单服务 `web`，镜像 `campus-data-web:0.1.0`，端口 `127.0.0.1:8082:80`，接入外部网络 `campus-net` |

**不修改**：`docker-compose.yml`、`.env`、任何 SQL、任何后端代码。

### 3.2 关键配置

```yaml
# docker-compose.web.yml（示意）
services:
  web:
    image: campus-data-web:0.1.0
    build:
      context: ./web
      dockerfile: Dockerfile.web
    ports:
      - "127.0.0.1:8082:80"
    networks: [campus-net]
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1/healthz"]
      interval: 15s
      timeout: 3s
      retries: 3
networks:
  campus-net:
    external: true
    name: campus-net
```

```nginx
location /api/ {
  proxy_pass http://import-api:8000/;   # 末尾斜杠用于剥离 /api 前缀
  proxy_set_header Host $host;
  proxy_read_timeout 120s;              # 与前端导入超时对齐
}
```

### 3.3 为什么用独立项目名

前端栈用 `-p campus-web` 启动，避免与主栈共用项目名导致 `docker compose up` 时被当作孤儿服务处理：

```bash
docker compose -p campus-web -f docker-compose.web.yml up -d
```

## 4. 启动 / 停止 / 健康检查 / 回退

```bash
# 1) 宿主机构建（容器无外网，必须先构建）
cd web && npm ci && npm run build && cd ..

# 2) 构建镜像
docker compose -p campus-web -f docker-compose.web.yml build

# 3) 启动
docker compose -p campus-web -f docker-compose.web.yml up -d

# 4) 健康检查
curl -s http://127.0.0.1:8082/healthz          # 期望 ok
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/students   # 期望 200
docker compose -p campus-web -f docker-compose.web.yml ps

# 5) 停止（保留镜像）
docker compose -p campus-web -f docker-compose.web.yml stop

# 6) 完全回退
docker compose -p campus-web -f docker-compose.web.yml down
# 主栈的 DB / API / Appsmith 全程不受影响
```

**后端不可用时**：页面能打开，接口请求返回 502（nginx 层）。前端会显示「无法连接后端服务」。
**后端重启后**：无需重启 web 容器，nginx 会重新解析服务名。
**版本回退**：镜像标签固定为 `0.1.0`；回退到上一版用 `docker compose ... up -d --force-recreate` 配合保留的旧镜像，或直接 `down` 回退到 dev server。

## 5. 影响评估

| 项 | 评估 |
|---|---|
| 磁盘 | 新增 nginx 镜像约 50–60 MB；F: 现有 **29 GB** 可用，Z: 141 GB |
| 内存 | nginx 常驻约 5–15 MB |
| 端口 | 8082 当前空闲（已确认 5173/8010/8080/8081/55432 在用） |
| 现有服务 | 不改动、不重建；Appsmith 仍可作对照界面 |
| 数据 | 不涉及任何数据库操作 |
| 启动时长 | 镜像构建 < 30 s（只拷 dist），启动 < 5 s |

## 6. 需要你确认的高风险操作

1. **拉取 `nginx:1.29-alpine` 镜像**（约 60 MB，写入 F:）。
2. **新建并启动 `campus-web` 容器**（8082 端口）。
3. **批次 27 的处置**（提交 / 保持 / 删除），我倾向保持不动。
4. 是否允许我在部署前**执行一次 `scripts/backup.sh`**（会新增一个带时间戳的备份文件，不覆盖旧的）。

## 7. 备份现状（重要）

| 项 | 状态 |
|---|---|
| 现有备份 | `backups/campus_20261020_155950.sql.gz`，**23,977 字节，15:59 生成** |
| 是否覆盖最新数据 | **否**。之后新增了 4 条学生、23 个批次、若干异常与审计记录 |
| 恢复流程 | `scripts/restore.sh` 已存在，需手动输入库名二次确认；曾做过独立库恢复演练 |
| 结论 | 部署前应重新备份一次；新文件按时间戳命名，不会覆盖旧备份 |

## 8. 本轮不做

- 不拉取镜像、不创建容器、不改 `docker-compose.yml`
- 不提交、不删除批次 27 或任何暂存文件
- 不接入 Dify / Ollama / 任何模型
- 不调整数据库结构
- 不安装前端新依赖（容器化只复用现有 `dist`）
