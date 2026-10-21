# 学生管理业务切片（S1–S3）验收报告

- **日期**：2026-10-21 10:00–13:45
- **环境**：`ruoyi-plus-poc` 隔离栈；后端 v6.0.0（commit `7180b52`）；业务副本 = 现有 `import-api` 代码
- **结论**：**学生管理切片 S1–S3 全部通过**（12 项测试全部执行，无跳过项；仅 1 项实现缺陷在过程中发现并修复）
- **主项目状态**：未修改（`main @ d635d8e`，工作区干净）；主栈 4 容器 healthy；计数 235/305/37/51/544 未变；批次 27/37 未动

---

## 1. 执行前检查

| 项 | 结果 |
|---|---|
| 主项目 Git | `main @ d635d8e`，工作区干净 |
| Java 源码 | POC 副本 `backend/`（v6.0.0 + 7180b52 基线 + POC 控制器） |
| 前端 | `6.X-React` @ `25e69f1`（上一轮已验收，本轮未动） |
| **poc-api 性质确认** | **是简化验签服务**（`poc-api/main.py` 头注释自证），不是 import-api 副本 → 按指令重建了业务副本 |
| 业务副本 | `ruoyi-plus-poc/import-api-poc/app/`（10 个 py 文件，完整拷贝主项目 import-api/app） |
| 连接隔离 | 副本只连 `poc-db:5432/ruoyi` 的 `campus` schema；未发布宿主机端口（`PortBindings={}`） |

---

## 2. S1：Java 代理（已完成）

`PocProxyController` 扩展为四个签名端点，**学生业务全部指向业务副本**（`poc-importapi:8000`）：

| Java 端点 | 方法 | 权限点 | 上游 |
|---|---|---|---|
| `/poc/proxy/students` | GET | `poc:student:list` | `importapi /students`（keyword 透传） |
| `/poc/proxy/students/{no}` | GET | `poc:student:list` | `importapi /students/{no}` |
| `/poc/proxy/students/{no}` | PUT | `poc:student:write` | `importapi /students/{no}` |
| `/poc/proxy/students` | POST | `poc:student:write` | `poc-api /poc/students`（旧对照，保留） |

签名升级：canonical 追加 **X-Poc-Admin**（`roleKey == "superadmin"` 由服务端判定）；网关不读取、不透传任何客户端身份头；上游 4xx 原样透传。

权限点与角色的绑定：`poc_college` 角色拥有 `poc:student:list` + `poc:student:write` 两个菜单权限（`sql/04_proxy_perms.sql`）；`admin` 为 superadmin 自然通过；`poc_readonly` 无任何角色。

---

## 3. S2：FastAPI 业务副本改造

| 文件 | 改动 |
|---|---|
| `app/poc_auth.py`（新增） | HMAC 依赖 `require_internal()`：验签（含 X-Poc-Admin）、时间窗、nonce 一次性（复用 `campus.poc_nonce`）、请求体摘要比对；`require_college()` 强制非管理员必须有学院声明（缺失 403，**不回退为全库**）；admin（服务端判定）才有全范围 |
| `app/main.py` | 三个学生接口挂 `Depends(require_internal)`；列表传入 `forced_college`，`college` 参数降级为范围内过滤；详情先取记录再比学院，越权 403 且**不返回任何记录**（含异动明细）；**新增 `PUT /students/{no}`** |
| `app/queries.py` | `list_students` 增加 `forced_college` 参数（SQL 层 AND）；新增 `update_student`：白名单字段（`student_name/class_name/major_name/enrollment_year/student_status`）、未知字段 422、类型与长度校验、`student_status` 枚举校验、**UPDATE WHERE 同时限定学号与学院**、`set_config` 与 UPDATE 同事务 |
| `docker-compose.poc.yml` | 新增 `poc-importapi` 服务（复用 `campus-import-api:0.1.0` 镜像，挂载副本代码，无宿主端口） |

**明确禁止**：`PUT` 不接受 `student_no`、`college_name` 字段（传了直接 422）——学号与学院归属不通过此接口修改。

---

## 4. S3：测试矩阵与证据（12/12 执行，全部通过）

| # | 测试 | 结果 | 证据 |
|---|---|---|---|
| 1 | 学院A 只查到本学院 | 通过 | 列表 college_name 全部为「计算机学院」（`total=5`） |
| 2 | 学院A 传 `college=电子信息学院` | 通过 | 结果仍只含计算机学院记录（参数被 AND 进范围，无法扩大） |
| 3 | 学院A 查学院B 详情 | 通过 | 403 `越权：不能查看其他学院的学生` |
| 4 | 学院A 改学院B 学生 | 通过 | 403；DB 复查 `POCB0001 | 乙同学 | 电子信息学院` 未变 |
| 5 | 学院A 改本学院学生 | 通过 | 200：`student_status=enrolled→suspended`（部分更新，仅传状态即可） |
| 6 | 审计正确性 | 通过 | `log_id=15`：`ry:poc_college_a` / `campus_app` / `update` / `changed_fields={student_status, updated_at}`；与业务更新同一事务 |
| 7 | 低权限不能修改 | 通过 | `poc_readonly` → 业务码 403（Java 权限点拦截，请求未达 FastAPI） |
| 8 | 签名缺失/篡改/过期/重放 | 通过 | 401×3、重放 409（同一 nonce 表，与简化服务共享防护） |
| 9 | 伪造 `X-Actor`/`X-Poc-User`/`X-Poc-College` | 通过 | 带有效 token + 三个伪造头写入，审计仍为 `ry:poc_college_a`、学院仍为本人学院 |
| 10 | 绕过 Java 直连 FastAPI | 通过 | `PortBindings={}` 无宿主端口；跨网络容器访问返回 `Connection refused` |
| 11 | 分页/参数变化不扩大范围 | 通过 | `page=2&pageSize=200&include_inactive=true` 结果仍只有本学院 |
| 12 | 拒绝路径无残留 | 通过 | 422（未知字段）与 403 后：审计条数不变、无脏数据。**DB 级异常注入未执行**（见 §6 风险） |

**过程中发现并修复的缺陷**：初版把 `student_name` 设为修改必填，导致「只改状态」被 422 拒绝——与部分更新语义（COALESCE 实现）矛盾。已改为「提供才校验」，复测通过。

---

## 5. 事务 / 审计 / 学院隔离核验

| 核验点 | 结果 |
|---|---|
| 业务更新与审计同事务 | 同一 `pool.connection()` 内：`set_config` → `UPDATE` → 提交；触发器 `changed_fields={student_status, updated_at}` 与实际变更一致 |
| 拒绝路径零残留 | 403/422 后审计条数与业务数据均无变化 |
| 学院隔离位置 | SQL WHERE 层（`college_name = %s`），不是展示层过滤 |
| 身份来源 | 全部来自 Java 网关签名；`X-Actor` 在新接口中**完全不读取** |
| 全范围管理员 | `superadmin` 由 Java 服务端判定并签名（`X-Poc-Admin=true`），FastAPI 信任该签名声明而非客户端 |

---

## 6. 尚未验证 / 已知限制

| # | 项 | 说明 |
|---|---|---|
| 1 | DB 级异常注入的回滚 | 未构造数据库层异常（约束冲突已被应用层前置校验拦截）；应用层 422/403 路径已验证无残留 |
| 2 | 框架 `@DataPermission` 在学生表上的适用性 | 学生查询仍在 Python，不经过 Java Mapper；`sys_dept` 数据范围与 `college_name` 的映射结论见 `RUOYI-POC-DATA-PERMISSION.md` §6 |
| 3 | 并发场景 | 未测并发修改同一学生 |
| 4 | nonce 表清理 | `campus.poc_nonce` 只增不删，长期需 TTL |
| 5 | 旧简化服务 | `poc-api`（ruoyi-poc-api）仍在运行，仅作历史对照，不属于业务切片 |

---

## 7. 回退方法

- **业务副本回退**：`docker compose -p ruoyi-poc -f docker-compose.poc.yml stop poc-importapi` → 移除该服务即可，主项目与主栈零关联；
- **Java 回退**：POC 控制器只在 POC 镜像内，主项目无任何改动；
- **数据回退**：POC 库整体 `down -v` 重建（含全部测试数据）。

---

## 8. 建议

切片已具备合入主项目 `import-api` 的条件（三处改动：`poc_auth.py` 新增、`queries.py` 两处、`main.py` 三处，均为**增量**且可独立回退）。建议下一轮：

1. 把 S2 改动以特性开关（如 `POC_AUTH_ENABLED`，默认关闭）合入主项目；
2. 开启开关后复跑同一测试矩阵（指向主库 + 虚构数据）；
3. 再评估 React 学生查询页的接入。

在此之前不动 `main` 分支的任何业务代码。
