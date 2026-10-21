# RuoYi 身份贯通 POC：执行结果

- **日期**：2026-10-20 23:20 → 2026-10-21 09:05
- **版本锁定**：`dromara/RuoYi-Vue-Plus` tag **v6.0.0**，commit **`7180b529776834fee912113b23f0bd7a387a8222`**
- **隔离目录**：`Z:\ai\本地部署\ruoyi-plus-poc\`（独立 compose 项目 `ruoyi-poc`）
- **主栈影响**：**零**（见 §6）
- **总结论**：**部分通过，Java→FastAPI 一段被登录 403 阻塞，未完成；不得视为通过**

---

## 1. 第一步：审计契约核对（只读，已完成）

| # | 问题 | 结论与证据 |
|---|---|---|
| 1 | `actor_user_id` 类型与语义 | `varchar(150)`、**可为空**、无外键、无 CHECK。历史值形如 `demo.teacher` / `web.ui` / `import.test` / `local.operator`，是**自由文本标识**，不是主键 |
| 2 | 触发器如何取操作人 | `campus.audit_row()` 读 `current_setting('campus.actor_user_id', true)`，为空则写 NULL |
| 3 | 是否依赖事务变量 | **是**。API 侧 `_set_actor()` 执行 `set_config('campus.actor_user_id', %s, true)`，第三参数 `true` 表示**事务级**，事务结束即失效 |
| 4 | 哪些接口写审计 | **只有** `students`、`student_changes` 两张表挂了 `audit_row` 触发器；`import_batches` / `import_issues` **不写审计**。导入提交时业务写入与审计在**同一事务**（行级触发器），回滚一致 |
| 5 | `X-Actor` 如何处理 | `main.py` 取请求头 → `_actor()` 仅截断到 150 字符 → 直接作为 actor。**可任意伪造** |
| 6 | `sys_user` 如何映射 | `sys_user.user_name`（唯一登录名）→ 映射为 `ry:<user_name>`，长度可控（`ry:` + ≤64）且与历史值可区分 |

**额外发现（必须先知道，但不属于本轮改动）**

- `operation_logs.action` 有 CHECK 约束，**只允许 `insert/update/delete`**，没有 `login/logout`。要记录登录事件必须改约束，本轮未做。
- `audit_payload()` 会剔除 `id_card_no / phone_no / home_address / family_info` 四列（当前表中并无这些列，属预留）。

**结论：`actor_user_id` 适合存「登录名」，但需要约定前缀与长度上限；这是本轮 POC 的映射依据。**

---

## 2. 第二步：隔离环境（已完成）

| 组件 | 实际 | 端口 |
|---|---|---|
| PostgreSQL | `postgres:16.15-alpine`，库 `ruoyi`，`postgres_ry_vue.sql` 建表 | `127.0.0.1:55433` |
| Redis | `redis:7.4-alpine`，带密码 | `127.0.0.1:6381`（6379/6380 已被占用） |
| FastAPI（POC） | 复用 `campus-import-api:0.1.0` 镜像 + 挂载代码 | **未发布宿主机端口**，仅 `ruoyi-poc-net` 内可达 |
| Java 后端 | `eclipse-temurin:21-jre` + 自建 jar | `127.0.0.1:9180` |

**PostgreSQL 兼容性：通过。** 官方 `postgres_ry_vue.sql` 在 PG 16.15 上**零修改**建出 **24 张表**；另有 `campus` schema 7 个对象（本项目的表结构副本）。**未出现需要改脚本的情况**（对应评估报告 no-go 条件「改动 >10 处」——实际 0 处）。

**环境踩坑（已在 POC 内解决，未改主栈）**

1. `JAVA_HOME` 指向 JDK 17，首次构建报「不支持发行版本 21」→ 改用 `C:/Program Files/Java/jdk-21`。
2. 容器内 `127.0.0.1` 指向容器自身 → 数据源必须写 `poc-db:5432`、Redis 写 `poc-redis:6379`。
3. Docker 注入 `HTTP_PROXY=127.0.0.1:8080` 导致 pytest 客户端请求打向死代理 → 客户端显式安装空 `ProxyHandler`。
4. compose 里 `command` 传参未能让容器正常启动（原因未定位），改为 `docker run` 手工传参后成功启动（21.2 秒）。

---

## 3. 第三步：签名桥接（已实现并通过负向测试）

签名规范：

```
canonical = METHOD \n PATH \n TIMESTAMP \n NONCE \n BODY_SHA256 \n USER \n ROLE \n COLLEGE
signature = HMAC-SHA256(secret, canonical)
```

| 防护 | 实现 |
|---|---|
| 身份来源 | 仅从内部签名头读取；不采信 `X-Actor` |
| 请求体完整性 | 签名覆盖 `BODY_SHA256`，服务端重算比对 |
| 过期 | 时间戳偏移 > 60 s 拒绝 |
| 重放 | `campus.poc_nonce` 表 `INSERT ... ON CONFLICT DO NOTHING`，命中即 409 |
| 签名比较 | `hmac.compare_digest`（常量时间） |
| 端口暴露 | `poc-api` 不发布宿主机端口，只能内网调用 |
| 密钥 | 只在 `.env.poc` 与运行参数中，不入 Git |

### 3.1 实测结果（真实执行，非推演）

| 用例 | 结果 | 证据 |
|---|---|---|
| 合法签名写入 | **200** | `student_id=3`，审计 `actor_user_id=ry:zhangsan`、`actor_db_role=campus_app`、`action=insert` |
| 缺失签名头 | **401** | `{"detail":"缺少内部签名头"}` |
| 请求体被篡改 | **401** | `{"detail":"请求体被篡改"}` |
| 时间戳过期 1 小时 | **401** | `{"detail":"请求已过期"}` |
| 同一 nonce 重放（第一次） | **200** | `log_id=4` |
| 同一 nonce 重放（第二次） | **409** | `{"detail":"重放请求：nonce 已被使用"}` |
| 伪造 `X-Poc-User: ry:admin`（不重签） | **401** | `{"detail":"签名校验失败"}` |
| 跨学院写入（计算机学院身份写电子信息学院） | **403** | `{"detail":"越权：不能写入其他学院数据"}` |

**审计表实际内容**（POC 库）：

```
id=3 | ry:zhangsan | campus_app | insert | students
id=4 | ry:zhangsan | campus_app | insert | students
id=1 | (空)        | ruoyi      | insert | students   ← 种子直连 SQL，无 actor
id=2 | (空)        | ruoyi      | insert | students   ← 同上
```

第 1、2 行恰好证明：**不设置事务变量的写入，审计操作人为空**——这正是现有系统的风险点。

---

## 4. 第四步：Java 侧（部分完成，卡在登录）

| 项 | 状态 |
|---|---|
| 源码构建 | **成功**（Maven，JDK 21，`ruoyi-admin.jar` 257 MB） |
| 启动 | **成功**，日志 `Started DromaraApplication in 21.2 seconds` |
| 连接 PG | **成功**（24 表所在库） |
| 连接 Redis | **成功** |
| 代理控制器 | 已编写 `PocProxyController`，编译通过 |
| **真实登录** | **失败：HTTP 403 `没有访问权限，请联系管理员授权`** |

登录请求：

```
POST http://127.0.0.1:9180/auth/login
{"clientId":"e5cd7e4891bf95d1d19206ce24a7b32e","grantType":"password",
 "username":"admin","password":"admin123","tenantId":"000000"}
→ {"code":403,"msg":"没有访问权限，请联系管理员授权"}
```

后台日志：`GlobalExceptionHandler - 没有访问权限`（`NotPermissionException`），发生在 `/auth/login` 路径上，说明该路径**被权限拦截器覆盖**，而非密码错误（密码错误会返回「用户不存在/密码错误」）。

已确认 `sys_client` 中存在该 clientId（`grant_type=password,social`，`status=0`），`sys_user` 中 `admin` 存在且 `status=0`。**根因未定位**，需要读拦截器排除规则或 client 校验逻辑。

**因此：Java → FastAPI 的真实调用、`ry:zhangsan` 由会话产生、端到端审计，全部未验证。**

---

## 5. 测试清单对照（用户定义的 A–I）

| 编号 | 项目 | 状态 |
|---|---|---|
| A | 真实用户登录后可访问受保护 Java 接口 | **未执行**（登录 403） |
| B | Java 调 FastAPI 成功且审计正确 | **未执行**（同上）；FastAPI 侧等价能力已由 §3 证明 |
| C | 缺失/错误/过期/篡改签名被拒 | **通过**（4 项全 401） |
| D | 一次性随机值不可重放 | **通过**（200 → 409） |
| E | 伪造身份头不改变服务端识别 | **部分通过**：FastAPI 侧 401；**Java 侧未验证** |
| F | 绕过 Java 直连 FastAPI 不可行 | **通过**：`poc-api` 无宿主机端口，外部 curl 不可达 |
| G | 低权限用户不能执行未授权操作 | **未执行**（无角色体系用例） |
| H | 跨学院不能越权 | **部分通过**：FastAPI 侧 403；数据范围未在 Java/Casbin 层验证 |
| I | POC 停止后主栈不变 | **通过**（见 §6） |

---

## 6. 主栈零影响（实测）

| 项 | 状态 |
|---|---|
| `campus-web` | Up（healthy） |
| `campus-db` | Up 17h（healthy） |
| `campus-import-api` | Up 12h（healthy） |
| `campus-appsmith` | Up 17h（healthy） |
| 五张表计数 | students **235** / changes **305** / batches **37** / issues **51** / logs **544**（与 POC 前完全一致） |
| 批次 27 | 未触碰，仍 `validated` 2007 行 |
| 主项目文件 | 未修改（POC 全部在独立目录） |

---

## 7. 已知缺陷

1. **登录 403 未解决** —— 阻塞端到端验证的唯一硬点。
2. `poc-api` 的 `college` 头需 percent-encoding（HTTP 头只支持 latin-1），已在客户端/服务端处理，但这是实现细节，未来换成 JSON body 更干净。
3. `campus.poc_nonce` 表只增不删，长期需要 TTL 清理（POC 未做）。
4. `operation_logs.action` 无 `login/logout`，登录事件目前无法入审计。
5. compose `command` 传参启动 Java 失败原因未定位，目前靠 `docker run` 手工启动。

---

## 8. 耗时与产出

| 项 | 值 |
|---|---|
| 总耗时 | 约 2.5 小时（含首次 Maven 依赖下载约 7 分钟、两次失败重建） |
| 新增文件 | `docker-compose.poc.yml`、`sql/01_ruoyi.sql`、`sql/02_campus.sql`、`poc-api/main.py`、`poc-api/client.py`、`poc-config/*.yml`、`backend/Dockerfile.poc`、`PocProxyController.java` |
| 主项目改动 | **仅新增两份文档** |
