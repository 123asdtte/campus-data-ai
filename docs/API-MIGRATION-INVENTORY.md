# 正式迁移准备：现有 FastAPI 接口盘点与安全边界

- **日期**：2026-10-21
- **状态**：只读盘点 + 文档，未修改代码、数据库、容器或配置
- **依据代码**：`main` 分支 `5b5d0dc`，`import-api/app/{main.py,service.py,queries.py,parsing.py}`
- **对照基线**：POC 结果见 `RUOYI-POC-AUTH-RESULTS.md`、`RUOYI-POC-DATA-PERMISSION.md`

---

## 1. 盘点方法

沿路由装饰器 → 处理函数 → service/queries 层 → SQL 与事务 → 身份传递与审计触发器逐层追踪；对每个路由核对读写表、事务边界、身份来源和数据范围。以下每一条结论都对应到代码行。

**Git 回退点**：`main @ 5b5d0dc`，工作区干净（无未提交文件）。

---

## 2. 完整 API 清单（12 个路由，实际枚举自代码）

### 2.1 写库接口（5 个）

| # | 方法/路径 | 函数 | 写入表 | 身份 | 审计 | 文件 | 迁移建议 |
|---|---|---|---|---|---|---|---|
| 1 | `POST /imports/preview` | `create_batch` (service:361) | `import_batches` INSERT；缺列时 `import_issues` INSERT | `X-Actor` → `set_config`（420 行，可伪造） | 否（batches/issues 无触发器） | **接收上传文件**，落盘暂存 + `.mapping.json` | **Java 网关代理** |
| 2 | `POST /imports/preview-base64` | 同上（main.py:141） | 同上 | 同上 | 否 | 同上（base64 解码） | Java 网关代理 |
| 3 | `POST /imports/{id}/remap` | `remap_batch` (service:539) | `import_batches` UPDATE（重置为 uploaded）、`import_issues` DELETE+INSERT | 同上（549 行） | 否 | 重写 `.mapping.json` | Java 网关代理 |
| 4 | `POST /imports/{id}/validate` | `validate_batch` (service:642) | `import_issues` DELETE+INSERT、`import_batches` UPDATE 计数 | 同上（645 行） | 否 | 读暂存文件重解析 | Java 网关代理 |
| 5 | `POST /imports/{id}/commit` | `commit_batch` (service:701) | `students` INSERT（736 行）、`student_changes` INSERT（767 行）、`import_issues` INSERT（758 行，失败行）、`import_batches` UPDATE ×2（790/804 行） | 同上（703 行） | **是**（students/changes 走触发器，与业务同事务） | 成功后删除数据文件（sidecar 不删，已知缺陷） | Java 网关代理 + **最高优先保护** |

**重复提交保护**：commit 前按 `file_sha256 + batch_status='imported'` 查重（422 行），命中直接复用结果（幂等）。

### 2.2 只读接口（7 个）

| # | 方法/路径 | 数据表 | 学院/数据范围 | 迁移建议 |
|---|---|---|---|---|
| 6 | `GET /health` | 无 | — | 留在 Python（健康检查） |
| 7 | `GET /imports/{id}` | batches + issues（含异常明细、文件名） | 无 | Java 代理 |
| 8 | `GET /imports` | batches 列表（**含 `created_by` 等字段**） | 无 | Java 代理 |
| 9 | `GET /students` | students（keyword/college/class/status 分页） | **无强制范围**：`college` 是调用方可传的**过滤参数**（main.py:222-232），传什么看什么，不传看全部 | Java 代理 + **服务端强制学院范围** |
| 10 | `GET /students/{no}` | students + changes 详情 | 无 | Java 代理 + 强制范围 |
| 11 | `GET /meta/filters` | 学院/班级/状态聚合 | 无 | Java 代理 |
| 12 | `GET /stats/overview` | 全量统计 | 无 | Java 代理 |

### 2.3 认证与角色现状

| 项 | 现状 | 证据 |
|---|---|---|
| 认证 | **12 个路由全部无认证**（无 `Depends`/中间件/API Key） | main.py 全文检索 |
| 角色权限 | 无 | 同上 |
| 数据范围 | 无服务端强制；`college` 参数是过滤器不是边界 | main.py:222-232 |
| 身份 | `X-Actor` 头 → 截断 → `set_config`，可伪造 | main.py:48、service.py:53 |
| 事务 | 4 个写函数均用 `with pool.connection()`：正常退出提交、异常回滚（psycopg3 语义） | service.py:418/547/643/701 |
| 可直达性 | `8010` 绑 `127.0.0.1`，本机任意进程可直连；8082 的 `/dev-api` 代理后同样直达 | compose + nginx.conf |

---

## 3. POC 接口与现有接口对照

| POC 已验证能力 | 对应现有真实接口 | 一致性 | 差距 |
|---|---|---|---|
| 登录 → 会话 → 角色 | **不存在**（现有 API 无会话） | 不一致 | 需在 Java 网关补齐 |
| HMAC 签名 + 防重放 + 防伪造 | **不存在** | 不一致 | 需在 Java 出口 + FastAPI 入口实现 |
| 学院范围：列表只见本学院 | `/students` 无强制范围 | 不一致 | **FastAPI 需改为从签名声明取范围** |
| 学院范围：详情/修改 403 | `/students/{no}` 无修改接口（GET 详情可见任意学院） | 不一致 | 修改接口本身待建；详情需加范围 |
| 审计 actor=真实用户 | 机制相同（触发器 + GUC），但 actor 来自 `X-Actor` | 部分一致 | 身份来源必须换成签名声明 |
| 重放防护 | 无（内网直连场景） | 不一致 | 网关出口防重放 |
| 低权限 403 | 无角色体系 | 不一致 | Java 侧角色 + 权限点 |

**重要**：POC 的 `poc-api` 是独立小服务，**不是** `import-api`。POC 的通过只证明「链路模式可行」，不等于现有 12 个接口已接入。

---

## 4. 审计覆盖矩阵与缺口

| 表 | 写操作来源 | 触发器 | 审计覆盖 | 缺口 |
|---|---|---|---|---|
| `students` | commit（Python）+ POC 代理 | `trg_students_audit` | **有**，同事务 | actor 来自可伪造头；POC 已验证换签名声明即可修复 |
| `student_changes` | commit（Python） | `trg_changes_audit` | 有 | 同上 |
| `import_batches` | preview/remap/validate/commit | **无触发器** | **无** | 谁创建/校验/提交了批次不可追溯；建议后续加触发器或应用层记录 |
| `import_issues` | remap（DELETE+INSERT）/validate/commit | 无 | **无**（且 `campus_app` 有 **DELETE** 权限，是全库唯一能物理删数据的角色授权） | 校验结果被每次 validate 整表替换，历史校验结论不可追溯 |
| 失败导入 | commit 跳过失败行并写 issues | — | 部分（issues 有行号与原因，但 actor 可伪造） | 重试/回滚场景依赖批次状态机，本身可追溯 |

**同一事务性**：审计触发器与业务写入在同一连接同一事务内（行级触发器），POC 复测已验证（跨学院 403 时**零落库**）。这一点现有实现是正确的，迁移时必须保持。

---

## 5. 必须先修复的安全问题（按优先级）

| # | 问题 | 位置 | 修复层 | 说明 |
|---|---|---|---|---|
| 1 | 全部接口无认证 | main.py 全部 12 路由 | Java 网关 | 网关统一要求 Sa-Token 会话 |
| 2 | `X-Actor` 可伪造 | main.py:48、service.py:53 | FastAPI | 改为从内部签名声明取，POC 已验证方案 |
| 3 | `/students` 无强制学院范围 | main.py:222、queries.list_students | FastAPI | 从签名声明取 college 并强制 AND 条件；`college` 参数降级为「在范围内再筛」 |
| 4 | FastAPI 可被宿主机直连 | compose 8010 端口发布 | 部署 | 迁移完成后取消宿主端口发布，仅内网 |
| 5 | 批次/校验无审计 | 触发器缺失 | DB（后续） | 本轮不改；列入数据治理阶段 |
| 6 | `campus_app` 拥有 import_issues 的 DELETE | 003_roles.sql | DB（后续） | 数据治理阶段评估 |
| 7 | `.mapping.json` 孤儿文件 | service.py 提交成功只删数据文件 | Python（小改） | 迁移学生切片时顺带修复 |

---

## 6. 最小业务切片建议（第 2 阶段：学生管理）

**一个纵向切片 = 新前端登录 → Java 权限校验 → Java 代理 → FastAPI 数据范围校验 → PostgreSQL → 审计核验**，覆盖读、改两类操作：

| 切片接口 | 现有实现 | 需要的改造 |
|---|---|---|
| 学生列表 | `GET /students` | Java 加 `@SaCheckPermission("poc:student:list")` 风格权限点 + 代理签名；FastAPI 从声明强制学院 |
| 学生详情 | `GET /students/{no}` | 同上；跨学院 403（POC 已验证模式） |
| 学生修改 | **当前不存在**（现有系统没有任何学生修改接口） | 需在 FastAPI 新增 `PUT /students/{no}`（限定 college + 必填校验 + 触发器自动审计），Java 侧加写权限点 |
| 审计核验 | 触发器已有 | 断言 `actor_user_id = ry:<登录名>` |

**切片不包含**：导入（preview/validate/commit 涉及文件上传与批量写入，放在切片 2）、导出、总览。

**导入流程过渡**：先做到预览与校验（只写批次表），commit 在安全验收后接入——与你的规划一致。

---

## 7. 实施顺序与回退

| 步骤 | 内容 | 回退 |
|---|---|---|
| S1 | Java 网关为 POC 代理补齐学生列表/详情/修改的签名转发（POC 已有模式，纯扩展） | 保留旧入口 8082/8010，随时切回 |
| S2 | FastAPI（**POC 副本先做**）新增 `PUT /students/{no}` 并把三处查询改为声明驱动范围 | POC 目录内回滚，主项目不动 |
| S3 | 用虚构数据跑通切片 + 负向测试（伪造头、跨学院、无权限、重放） | 不通过则停在 S2 |
| S4 | 通过后把 S2 的改动合入主项目 `import-api`（保持 8010 端口不变，前端无感） | git revert 单个 commit |
| S5 | 新前端迁移学生查询页 | 旧 8082 保留 |
| S6 | 导入页迁移（预览/校验先行，commit 最后） | 同上 |

**S2 放 POC 副本先做的原因**：主项目 `import-api` 是生产服务，未验证的改造不应直接进入；POC 已有同结构 schema，验证成本最低。

---

## 8. 本轮确认的环境状态

| 项 | 状态 |
|---|---|
| Git | `main @ 5b5d0dc`，工作区干净 |
| 主栈 | 4 容器 healthy（web/db/api/appsmith） |
| 数据 | students 235 / changes 305 / batches 37 / issues 51 / logs 544 |
| 批次 27 | `validated` 2007 行，未动 |
| 批次 37 暂存 | 未清理 |
| POC | `ruoyi-poc` 栈运行中（db/redis/api），Java 容器已停止可随时重启 |
